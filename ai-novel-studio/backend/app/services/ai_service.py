"""AI writing service.

Turns a high-level request ("继续这一章") into:

1. an explicit **context bundle** (system prompt + chapter outline + relevant
   history + the current text, all inside a token budget),
2. a chat completion against the configured model,
3. a persisted :class:`GenerationTask` with token and cost accounting.

Nothing here writes to the manuscript. Results are returned to the caller, which
shows them for review — the author decides whether to accept them.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select

from app.ai.llm.errors import AllProvidersFailed, LLMAdapterError
from app.ai.llm.registry import ChatClient
from app.ai.llm.types import ChatMessage, LLMRequest, LLMUsage
from app.ai.prompts.builtin import OPERATIONS, OUTLINE_PROMPT_KEY, SUMMARY_PROMPT_KEY
from app.ai.prompts.service import PromptService, render
from app.ai.structured import (
    REPAIR_INSTRUCTION,
    as_str_list,
    complete_json,
    longest_text,
    parse_json_object,
)
from app.core.errors import NotFound, ProviderError, ValidationFailed
from app.core.ids import new_id
from app.core.logging import get_logger
from app.db.session import Database
from app.models.novel import Chapter, ChapterSummary, Outline
from app.models.studio import GenerationTask, ModelConfig
from app.schemas.ai import AIRequest, AIResult
from app.services.agent_config_service import AgentConfigService
from app.services.model_config_service import ModelConfigService
from app.services.novel_service import NovelService
from app.services.project_service import ProjectService

logger = get_logger(__name__)

#: Operations that reason over the whole chapter rather than a selection.
WHOLE_CHAPTER_OPERATIONS = frozenset({"write", "continue", "review", "outline"})
SELECTION_OPERATIONS = frozenset({"expand", "rewrite", "polish"})
#: Operations whose prompt asks for the forward-looking 「伏笔与后续规划」 block.
FORESHADOW_OPERATIONS = frozenset({"write", "outline", "continue"})

DEFAULT_TARGET_WORDS = 2000
MAX_CONTEXT_CHARS = 24_000


@dataclass(slots=True)
class AIStreamEvent:
    """One server-sent event for a streaming generation."""

    #: ``reset`` tells the client to throw away every ``delta`` received so far:
    #: the reply is being regenerated from scratch (the JSON repair retry).
    #: ``thinking`` carries a reasoning-model chain-of-thought delta; it is shown
    #: separately by the UI and is **never** part of the answer text.
    type: Literal["delta", "thinking", "reset", "done", "error"]
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _Streamed:
    """Accumulator for one streamed structured reply.

    The ``delta`` frames are yielded straight to the client, so the assembled
    text lives here instead of being returned from the generator.
    """

    text: str = ""
    usage: LLMUsage = field(default_factory=LLMUsage)


def _usage_dict(usage: LLMUsage) -> dict[str, int]:
    return {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}


def _truncate(text: str, limit: int, *, from_end: bool = False) -> str:
    """Clip *text* to *limit* characters, marking the elision."""
    if limit <= 0 or len(text) <= limit:
        return text
    if from_end:
        return f"…（前文已省略）\n{text[-limit:]}"
    return f"{text[:limit]}\n…（后文已省略）"


def _one_line(text: str) -> str:
    """Collapse whitespace so a field can live on a single bullet line."""
    return " ".join(text.split())


def _dedupe(items: list[Any], limit: int = 8) -> list[str]:
    """Order-preserving de-duplication of short labels (empty ones dropped)."""
    seen: dict[str, None] = {}
    for item in items:
        label = _one_line(str(item))
        if label and label not in seen:
            seen[label] = None
        if len(seen) >= limit:
            break
    return list(seen)


#: Short-word columns of a :class:`ChapterSummary` row.
SUMMARY_LIST_FIELDS = ("characters", "events", "locations", "keywords", "foreshadows")


def content_fingerprint(content: str) -> str:
    """Fingerprint of a chapter body, stored as ``chapter_summaries.source_hash``.

    Trimmed first so a stray trailing newline from an editor does not buy a paid
    regeneration. 32 hex chars (128 bits) is far beyond collision risk for one
    project and keeps the column short.
    """
    return hashlib.sha256((content or "").strip().encode("utf-8")).hexdigest()[:32]


def _summary_payload(text: str, data: dict[str, Any] | None) -> dict[str, Any]:
    """Shape a parsed reply into the columns of a ``chapter_summaries`` row.

    When the model never produced JSON we degrade to treating the whole reply as
    the summary — a slightly noisy memory line beats losing the summary (and the
    tokens already spent on it).
    """
    raw = (text or "").strip()
    parsed: dict[str, Any] = {
        "summary": raw,
        "plot_progress": "",
        **{name: [] for name in SUMMARY_LIST_FIELDS},
    }
    if data is None:
        return parsed
    parsed["summary"] = str(data.get("summary") or "").strip() or raw
    parsed["plot_progress"] = str(data.get("plot_progress") or "").strip()
    for name in SUMMARY_LIST_FIELDS:
        parsed[name] = as_str_list(data.get(name))
    return parsed


#: Short-word columns of an :class:`Outline` row.
OUTLINE_LIST_FIELDS = ("characters", "key_events", "foreshadows")
#: Single-line text columns of an :class:`Outline` row.
OUTLINE_TEXT_FIELDS = ("goal", "conflict", "twists", "ending")


def _outline_payload(
    chapter_title: str, text: str, data: dict[str, Any] | None
) -> dict[str, Any]:
    """Shape a parsed reply into the columns of an ``outlines`` row.

    A model that ignores the JSON instruction must not cost the author the
    outline: the reply is then kept verbatim in ``content`` and the row is
    flagged as ``degraded`` instead of raising. ``text`` is the reply
    :func:`~app.ai.structured.complete_json` picked as the longest of all
    attempts, so a truncated first answer survives an empty repair turn.
    """
    raw = (text or "").strip()
    parsed: dict[str, Any] = {
        "title": (chapter_title or "").strip()[:300] or "（未命名）",
        "content": raw,
        **{name: "" for name in OUTLINE_TEXT_FIELDS},
        **{name: [] for name in OUTLINE_LIST_FIELDS},
        "target_word_count": 0,
        "degraded": True,
    }
    if data is None:
        return parsed
    parsed["degraded"] = False
    parsed["title"] = str(data.get("title") or "").strip()[:300] or parsed["title"]
    for name in OUTLINE_TEXT_FIELDS:
        parsed[name] = str(data.get(name) or "").strip()
    for name in OUTLINE_LIST_FIELDS:
        parsed[name] = as_str_list(data.get(name))
    try:
        parsed["target_word_count"] = max(0, int(data.get("target_word_count") or 0))
    except (TypeError, ValueError):
        parsed["target_word_count"] = 0
    return parsed


def _outline_result(
    row: Outline, *, chapter_id: str, cached: bool, degraded: bool
) -> dict[str, Any]:
    """Serialise an :class:`Outline` row for the API while still in session."""
    return {
        "chapter_id": chapter_id,
        "outline_id": row.id,
        "level": row.level,
        "parent_id": row.parent_id,
        "title": row.title,
        "goal": row.goal,
        "conflict": row.conflict,
        "characters": list(row.characters or []),
        "key_events": list(row.key_events or []),
        "twists": row.twists,
        "foreshadows": list(row.foreshadows or []),
        "ending": row.ending,
        "target_word_count": row.target_word_count,
        "content": row.content,
        "degraded": degraded,
        "cached": cached,
        "row_version": row.row_version,
    }


class AIService:
    def __init__(
        self,
        studio_db: Database,
        projects: ProjectService,
        model_service: ModelConfigService,
        prompts: PromptService,
        agent_configs: AgentConfigService,
    ) -> None:
        self.studio_db = studio_db
        self.projects = projects
        self.model_service = model_service
        self.prompts = prompts
        self.agent_configs = agent_configs
        self.novels = NovelService(projects)
        self.chat = ChatClient(model_service)

    # ------------------------------------------------------------------
    # Model resolution
    # ------------------------------------------------------------------
    def _resolve_model(self, operation: str, model_config_id: str | None) -> ModelConfig:
        """Pick the model for one call. **The only** resolution path.

        Precedence: the request's explicit id beats the per-agent binding, which
        beats the writer's default model. A binding to a deleted / disabled model
        degrades to the default (with a log line) rather than failing the call —
        the author's chapter still gets written.
        """
        if model_config_id:
            return self.chat.resolve(model_config_id)

        agent = self.agent_configs.resolve_for_operation(operation)
        if agent is not None and agent.model_config_id:
            try:
                return self.chat.resolve(agent.model_config_id)
            except (NotFound, ValidationFailed) as exc:
                logger.warning(
                    "agent_model_unavailable",
                    operation=operation,
                    agent_type=agent.agent_type,
                    model_config_id=agent.model_config_id,
                    error=str(exc),
                )
        return self.chat.resolve(None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def validate_operation(self, operation: str) -> str:
        if operation not in OPERATIONS:
            raise ValidationFailed(
                f"未知的写作操作：{operation}",
                details={"allowed": sorted(OPERATIONS)},
            )
        return operation

    async def run(self, operation: str, payload: AIRequest) -> AIResult:
        self.validate_operation(operation)
        model = self._resolve_model(operation, payload.model_config_id)
        variables = self._build_variables(operation, payload, model)
        messages, prompt_key, missing = self.prompts.render_for(operation, variables)
        if missing:
            logger.warning("prompt_variables_missing", operation=operation, missing=missing)

        task_id = self._start_task(operation, payload, model, prompt_key)
        request = self._llm_request(payload, messages, model)

        try:
            response = await self.chat.complete(request, model_config_id=model.id)
        except AllProvidersFailed as exc:
            self._fail_task(task_id, f"所有模型均调用失败：{exc}")
            raise ProviderError(
                "所有模型都调用失败，请检查模型配置或稍后重试。",
                details={"attempts": getattr(exc, "attempts", [])},
            ) from exc
        except LLMAdapterError as exc:
            self._fail_task(task_id, str(exc))
            raise ProviderError(str(exc), details={"code": exc.code}) from exc

        usage = response.usage
        self._finish_task(
            task_id,
            text=response.text,
            model=model,
            prompt_key=prompt_key,
            usage=usage,
        )
        return self._result(
            task_id, operation, response.text, response.model, prompt_key, usage, model
        )

    async def stream(self, operation: str, payload: AIRequest) -> AsyncIterator[AIStreamEvent]:
        self.validate_operation(operation)
        model = self._resolve_model(operation, payload.model_config_id)
        variables = self._build_variables(operation, payload, model)
        messages, prompt_key, missing = self.prompts.render_for(operation, variables)
        if missing:
            logger.warning("prompt_variables_missing", operation=operation, missing=missing)

        task_id = self._start_task(operation, payload, model, prompt_key)
        request = self._llm_request(payload, messages, model)

        produced: list[str] = []
        usage = LLMUsage()
        used_model = model.model_name
        settled = False

        try:
            async for chunk in self.chat.stream(request, model_config_id=model.id):
                if chunk.thinking:
                    # Chain-of-thought: forwarded for display only, never stored
                    # in ``produced`` and never billed as answer text.
                    yield AIStreamEvent(type="thinking", text=chunk.thinking)
                if chunk.text:
                    produced.append(chunk.text)
                    yield AIStreamEvent(type="delta", text=chunk.text)
                if chunk.usage is not None:
                    usage = chunk.usage
            text = "".join(produced)
            self._finish_task(task_id, text=text, model=model, prompt_key=prompt_key, usage=usage)
            settled = True
            yield AIStreamEvent(
                type="done",
                data=self._result(
                    task_id, operation, text, used_model, prompt_key, usage, model
                ).model_dump(),
            )
        except AllProvidersFailed as exc:
            self._fail_task(task_id, f"所有模型均调用失败：{exc}")
            settled = True
            yield AIStreamEvent(
                type="error",
                data={
                    "code": "all_providers_failed",
                    "message": "所有模型都调用失败，请检查模型配置或稍后重试。",
                    "attempts": getattr(exc, "attempts", []),
                },
            )
        except LLMAdapterError as exc:
            self._fail_task(task_id, str(exc))
            settled = True
            yield AIStreamEvent(
                type="error",
                data={"code": exc.code, "message": str(exc)},
            )
        except Exception as exc:
            logger.exception("ai_stream_failed", operation=operation)
            self._fail_task(task_id, f"{type(exc).__name__}: {exc}")
            settled = True
            yield AIStreamEvent(
                type="error",
                data={"code": "internal_error", "message": "生成过程中出现异常。"},
            )
        finally:
            if not settled and produced:
                # The client hung up mid-stream: keep what we generated.
                self._finish_task(
                    task_id,
                    text="".join(produced),
                    model=model,
                    prompt_key=prompt_key,
                    usage=usage,
                )

    # ------------------------------------------------------------------
    # Streamed structured replies (summary / outline)
    # ------------------------------------------------------------------
    async def _stream_json(
        self, model: ModelConfig, request: LLMRequest, out: _Streamed
    ) -> AsyncIterator[AIStreamEvent]:
        """Stream one JSON-shaped reply, repairing a non-JSON answer **once**.

        Yields ``delta`` frames for the first attempt *and* for the repair, so
        the UI keeps moving during the long calls real models make. ``out.text``
        always ends up holding exactly one reply: the repair **replaces** the
        first attempt instead of being appended to it, which is why the caller
        re-parses ``out.text`` afterwards and never concatenates the two.

        A ``reset`` frame is emitted right before the repair, so a client that
        concatenates deltas (the only thing a dumb client can do) still ends up
        with the repaired reply alone instead of two replies glued together.
        """
        produced: list[str] = []
        request.json_mode = True

        async for chunk in self.chat.stream(request, model_config_id=model.id):
            if chunk.thinking:
                # Kept out of ``produced``: the JSON parse must only ever see the
                # answer body, never the chain of thought.
                yield AIStreamEvent(type="thinking", text=chunk.thinking)
            if chunk.text:
                produced.append(chunk.text)
                yield AIStreamEvent(type="delta", text=chunk.text)
            if chunk.usage is not None:
                out.usage = chunk.usage

        out.text = "".join(produced)
        if parse_json_object(out.text) is not None:
            return

        # The repair re-sends the whole answer; without this frame the client
        # would splice the two replies into one unparseable string.
        yield AIStreamEvent(type="reset")
        data, text, usage = await self._repair_json(model, request, out.text, out.usage)
        out.usage = usage
        if data is None:
            # Degraded: the row will store this text verbatim, so keep whichever
            # reply says more instead of a blank (or shorter) repair turn.
            text = longest_text(out.text, text)
        if text:
            out.text = text
            yield AIStreamEvent(type="delta", text=text)
        elif data is None:  # pragma: no cover - defensive, text is never blank here
            return

    async def _repair_json(
        self, model: ModelConfig, request: LLMRequest, text: str, usage: LLMUsage
    ) -> tuple[dict[str, Any] | None, str, LLMUsage]:
        """Ask once more, non-streamed, when the streamed reply was not JSON.

        Token usage of both attempts is merged so the task row bills the whole
        conversation the author paid for.
        """
        repair = LLMRequest(
            model=request.model,
            messages=[
                *request.messages,
                ChatMessage(role="assistant", content=text),
                ChatMessage(role="user", content=REPAIR_INSTRUCTION),
            ],
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=request.max_tokens,
            json_mode=True,
        )
        reply = await complete_json(self.chat, repair, retries=0, model_config_id=model.id)
        merged = LLMUsage(
            input_tokens=usage.input_tokens + reply.usage.input_tokens,
            output_tokens=usage.output_tokens + reply.usage.output_tokens,
        )
        return reply.data, reply.text, merged

    def preflight_summary(self, project_id: str, chapter_id: str) -> None:
        """Raise ``NotFound`` / ``ValidationFailed`` **before** an SSE stream starts."""
        self.novels.get_chapter(project_id, chapter_id)
        self._resolve_model("summary", None)

    def preflight_outline(self, project_id: str, chapter_id: str) -> None:
        """Raise ``NotFound`` / ``ValidationFailed`` **before** an SSE stream starts."""
        self.projects.get(project_id)
        self.novels.get_chapter(project_id, chapter_id)
        self._resolve_model("outline_persist", None)

    # ------------------------------------------------------------------
    # L1 memory: chapter summaries
    # ------------------------------------------------------------------
    async def summarize_chapter(
        self,
        project_id: str,
        chapter_id: str,
        *,
        force: bool = False,
        model_config_id: str | None = None,
    ) -> dict[str, Any]:
        """Distil one chapter into a ``chapter_summaries`` row (L1 memory).

        This is the **only** writer of that table. Every miss is a paid model
        request, so the cache is deliberately content-aware: a row is reused only
        when it was made from the *same* chapter text (``source_hash``). That is
        what makes it safe for the UI to fire this off when the author leaves a
        chapter — an untouched chapter costs nothing, an edited one costs one call.
        """
        chapter = self.novels.get_chapter(project_id, chapter_id)
        content = (chapter.content or "").strip()
        if not content:
            return {
                "chapter_id": chapter_id,
                "summary": "",
                "cached": False,
                "skipped": "empty",
            }

        fingerprint = content_fingerprint(content)
        existing = self._summary_row(project_id, chapter_id)
        if (
            existing is not None
            and existing.summary
            and existing.source_hash == fingerprint
            and not force
        ):
            return {"chapter_id": chapter_id, "summary": existing.summary, "cached": True}

        model = self._resolve_model("summary", model_config_id)
        messages, missing = self._summary_messages(chapter.title, content, model)
        if missing:
            logger.warning(
                "prompt_variables_missing",
                prompt_key=SUMMARY_PROMPT_KEY,
                missing=missing,
            )

        payload = AIRequest(project_id=project_id, chapter_id=chapter_id)
        task_id = self._start_task("summary", payload, model, SUMMARY_PROMPT_KEY)
        request = self._llm_request(payload, messages, model)

        try:
            reply = await complete_json(self.chat, request, model_config_id=model.id)
        except AllProvidersFailed as exc:
            self._fail_task(task_id, f"所有模型均调用失败：{exc}")
            raise ProviderError(
                "所有模型都调用失败，请检查模型配置或稍后重试。",
                details={"attempts": getattr(exc, "attempts", [])},
            ) from exc
        except LLMAdapterError as exc:
            self._fail_task(task_id, str(exc))
            raise ProviderError(str(exc), details={"code": exc.code}) from exc

        self._finish_task(
            task_id,
            text=reply.text,
            model=model,
            prompt_key=SUMMARY_PROMPT_KEY,
            usage=reply.usage,
        )
        parsed = _summary_payload(reply.text, reply.data)
        self._write_summary(project_id, chapter_id, parsed, model.id, fingerprint)
        logger.info(
            "chapter_summary_saved",
            project_id=project_id,
            chapter_id=chapter_id,
            chars=len(parsed["summary"]),
        )
        return {"chapter_id": chapter_id, "summary": parsed["summary"], "cached": False}

    async def stream_summary(
        self,
        project_id: str,
        chapter_id: str,
        *,
        force: bool = False,
        model_config_id: str | None = None,
    ) -> AsyncIterator[AIStreamEvent]:
        """Streaming twin of :meth:`summarize_chapter`.

        Same prompt, same table write, same ``done`` payload (plus ``usage``);
        the only difference is that the reply arrives as ``delta`` frames, so the
        author sees progress instead of a 100-second blank screen.
        """
        chapter = self.novels.get_chapter(project_id, chapter_id)
        content = (chapter.content or "").strip()
        if not content:
            yield AIStreamEvent(
                type="done",
                data={
                    "chapter_id": chapter_id,
                    "summary": "",
                    "cached": False,
                    "skipped": "empty",
                    "usage": _usage_dict(LLMUsage()),
                },
            )
            return

        fingerprint = content_fingerprint(content)
        existing = self._summary_row(project_id, chapter_id)
        if (
            existing is not None
            and existing.summary
            and existing.source_hash == fingerprint
            and not force
        ):
            yield AIStreamEvent(
                type="done",
                data={
                    "chapter_id": chapter_id,
                    "summary": existing.summary,
                    "cached": True,
                    "skipped": None,
                    "usage": _usage_dict(LLMUsage()),
                },
            )
            return

        model = self._resolve_model("summary", model_config_id)
        messages, missing = self._summary_messages(chapter.title, content, model)
        if missing:
            logger.warning(
                "prompt_variables_missing",
                prompt_key=SUMMARY_PROMPT_KEY,
                missing=missing,
            )

        payload = AIRequest(project_id=project_id, chapter_id=chapter_id)
        task_id = self._start_task("summary", payload, model, SUMMARY_PROMPT_KEY)
        request = self._llm_request(payload, messages, model)
        reply = _Streamed()
        settled = False

        try:
            async for event in self._stream_json(model, request, reply):
                yield event
            parsed = _summary_payload(reply.text, parse_json_object(reply.text))
            self._finish_task(
                task_id,
                text=reply.text,
                model=model,
                prompt_key=SUMMARY_PROMPT_KEY,
                usage=reply.usage,
            )
            settled = True
            self._write_summary(project_id, chapter_id, parsed, model.id, fingerprint)
            logger.info(
                "chapter_summary_saved",
                project_id=project_id,
                chapter_id=chapter_id,
                chars=len(parsed["summary"]),
                streamed=True,
            )
            yield AIStreamEvent(
                type="done",
                data={
                    "chapter_id": chapter_id,
                    "summary": parsed["summary"],
                    "cached": False,
                    "skipped": None,
                    "usage": _usage_dict(reply.usage),
                },
            )
        except AllProvidersFailed as exc:
            self._fail_task(task_id, f"所有模型均调用失败：{exc}")
            settled = True
            yield AIStreamEvent(
                type="error",
                data={
                    "code": "all_providers_failed",
                    "message": "所有模型都调用失败，请检查模型配置或稍后重试。",
                    "attempts": getattr(exc, "attempts", []),
                },
            )
        except LLMAdapterError as exc:
            self._fail_task(task_id, str(exc))
            settled = True
            yield AIStreamEvent(
                type="error",
                data={"code": exc.code, "message": str(exc)},
            )
        except Exception as exc:
            logger.exception("ai_summary_stream_failed", chapter_id=chapter_id)
            self._fail_task(task_id, f"{type(exc).__name__}: {exc}")
            settled = True
            yield AIStreamEvent(
                type="error",
                data={"code": "internal_error", "message": "生成摘要时出现异常。"},
            )
        finally:
            if not settled:
                # The client hung up: a half-written JSON blob is worthless, so
                # the task is recorded as failed rather than left "running".
                self._fail_task(task_id, "客户端中断了流式连接")

    def _summary_messages(
        self, title: str, content: str, model: ModelConfig
    ) -> tuple[list[dict[str, str]], list[str]]:
        spec = self.prompts.resolve(SUMMARY_PROMPT_KEY)
        variables = {
            "chapter_title": title or "（未命名）",
            "context": _truncate(content, self._context_budget(model)),
        }
        system_text, system_missing = render(spec.system, variables)
        user_text, user_missing = render(spec.user, variables)
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]
        return messages, sorted(set(system_missing + user_missing))

    def _summary_row(self, project_id: str, chapter_id: str) -> ChapterSummary | None:
        database = self.novels.database_for(project_id)
        with database.session() as session:
            return session.scalar(
                select(ChapterSummary).where(ChapterSummary.chapter_id == chapter_id)
            )

    def _write_summary(
        self,
        project_id: str,
        chapter_id: str,
        parsed: dict[str, Any],
        model_config_id: str | None,
        source_hash: str,
    ) -> None:
        """Upsert by ``chapter_id`` (the column is unique).

        *source_hash* is the fingerprint of the text that was just summarised, so
        a later call can tell "same body, reuse it" from "the author edited it".
        """
        prompt_version = self._prompt_version(SUMMARY_PROMPT_KEY)
        database = self.novels.database_for(project_id)
        with database.session() as session:
            row = session.scalar(
                select(ChapterSummary).where(ChapterSummary.chapter_id == chapter_id)
            )
            if row is None:
                row = ChapterSummary(
                    id=new_id("sum"),
                    project_id=project_id,
                    chapter_id=chapter_id,
                )
                session.add(row)
            row.summary = parsed["summary"]
            for name in SUMMARY_LIST_FIELDS:
                setattr(row, name, parsed[name])
            row.plot_progress = parsed["plot_progress"]
            row.model_config_id = model_config_id
            row.prompt_version = prompt_version
            row.source_hash = source_hash

    # ------------------------------------------------------------------
    # L1 outlines: structured, persisted chapter outlines
    # ------------------------------------------------------------------
    async def generate_outline(
        self,
        project_id: str,
        chapter_id: str,
        *,
        force: bool = False,
        instruction: str = "",
        model_config_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate one chapter outline and **write it to ``outlines``**.

        The toolbar's ``outline`` operation returns free text for the editor (the
        front-end still relies on that). This method is the structured variant:
        it asks for JSON and upserts a row keyed by
        ``(project_id, level="chapter", parent_id=chapter_id)``, so a chapter
        always has at most one outline row no matter how often it is regenerated.

        A reply that never parses as JSON is **not** an error: the raw text is
        stored in ``content`` and the result is flagged ``degraded``.
        """
        project = self.projects.get(project_id)
        chapter = self.novels.get_chapter(project_id, chapter_id)

        existing = self._outline_row(project_id, chapter_id)
        if existing is not None and not force and (existing["content"] or existing["goal"]):
            return existing

        model = self._resolve_model("outline_persist", model_config_id)
        messages, missing = self._outline_messages(project, chapter, instruction)
        if missing:
            logger.warning(
                "prompt_variables_missing", prompt_key=OUTLINE_PROMPT_KEY, missing=missing
            )

        payload = AIRequest(
            project_id=project_id, chapter_id=chapter_id, instruction=instruction
        )
        task_id = self._start_task("outline.structured", payload, model, OUTLINE_PROMPT_KEY)
        request = self._llm_request(payload, messages, model)

        try:
            reply = await complete_json(self.chat, request, model_config_id=model.id)
        except AllProvidersFailed as exc:
            self._fail_task(task_id, f"所有模型均调用失败：{exc}")
            raise ProviderError(
                "所有模型都调用失败，请检查模型配置或稍后重试。",
                details={"attempts": getattr(exc, "attempts", [])},
            ) from exc
        except LLMAdapterError as exc:
            self._fail_task(task_id, str(exc))
            raise ProviderError(str(exc), details={"code": exc.code}) from exc

        self._finish_task(
            task_id,
            text=reply.text,
            model=model,
            prompt_key=OUTLINE_PROMPT_KEY,
            usage=reply.usage,
        )
        parsed = _outline_payload(chapter.title, reply.text, reply.data)
        result = self._write_outline(
            project_id, chapter_id, chapter.sort_order, parsed
        )
        logger.info(
            "outline_saved",
            project_id=project_id,
            chapter_id=chapter_id,
            outline_id=result["outline_id"],
            degraded=parsed["degraded"],
        )
        return result

    async def stream_outline(
        self,
        project_id: str,
        chapter_id: str,
        *,
        force: bool = False,
        instruction: str = "",
        model_config_id: str | None = None,
    ) -> AsyncIterator[AIStreamEvent]:
        """Streaming twin of :meth:`generate_outline`.

        Outline generation is the slowest call in the product (103 s measured
        against a real provider), so it is the one that most needs frames on the
        wire. Prompt, table write and ``done`` payload are identical to the
        non-streaming version — plus ``usage``.
        """
        project = self.projects.get(project_id)
        chapter = self.novels.get_chapter(project_id, chapter_id)

        existing = self._outline_row(project_id, chapter_id)
        if existing is not None and not force and (existing["content"] or existing["goal"]):
            yield AIStreamEvent(
                type="done",
                data={**existing, "usage": _usage_dict(LLMUsage())},
            )
            return

        model = self._resolve_model("outline_persist", model_config_id)
        messages, missing = self._outline_messages(project, chapter, instruction)
        if missing:
            logger.warning(
                "prompt_variables_missing", prompt_key=OUTLINE_PROMPT_KEY, missing=missing
            )

        payload = AIRequest(
            project_id=project_id, chapter_id=chapter_id, instruction=instruction
        )
        task_id = self._start_task("outline.structured", payload, model, OUTLINE_PROMPT_KEY)
        request = self._llm_request(payload, messages, model)
        reply = _Streamed()
        settled = False

        try:
            async for event in self._stream_json(model, request, reply):
                yield event
            parsed = _outline_payload(chapter.title, reply.text, parse_json_object(reply.text))
            self._finish_task(
                task_id,
                text=reply.text,
                model=model,
                prompt_key=OUTLINE_PROMPT_KEY,
                usage=reply.usage,
            )
            settled = True
            result = self._write_outline(project_id, chapter_id, chapter.sort_order, parsed)
            logger.info(
                "outline_saved",
                project_id=project_id,
                chapter_id=chapter_id,
                outline_id=result["outline_id"],
                degraded=parsed["degraded"],
                streamed=True,
            )
            yield AIStreamEvent(
                type="done",
                data={**result, "usage": _usage_dict(reply.usage)},
            )
        except AllProvidersFailed as exc:
            self._fail_task(task_id, f"所有模型均调用失败：{exc}")
            settled = True
            yield AIStreamEvent(
                type="error",
                data={
                    "code": "all_providers_failed",
                    "message": "所有模型都调用失败，请检查模型配置或稍后重试。",
                    "attempts": getattr(exc, "attempts", []),
                },
            )
        except LLMAdapterError as exc:
            self._fail_task(task_id, str(exc))
            settled = True
            yield AIStreamEvent(
                type="error",
                data={"code": exc.code, "message": str(exc)},
            )
        except Exception as exc:
            logger.exception("ai_outline_stream_failed", chapter_id=chapter_id)
            self._fail_task(task_id, f"{type(exc).__name__}: {exc}")
            settled = True
            yield AIStreamEvent(
                type="error",
                data={"code": "internal_error", "message": "生成大纲时出现异常。"},
            )
        finally:
            if not settled:
                self._fail_task(task_id, "客户端中断了流式连接")

    def _outline_messages(
        self, project: Any, chapter: Any, instruction: str
    ) -> tuple[list[dict[str, str]], list[str]]:
        summaries = self._recent_summaries(project.id, chapter.id)
        variables = {
            "novel_type": project.novel_type or "",
            "synopsis": project.synopsis or "",
            "context": "\n".join(summaries) if summaries else "（暂无前情提要）",
            "outline": (chapter.summary or "").strip() or "（暂无既有大纲，请自行设计）",
            "instruction": instruction.strip() or "（无特殊要求）",
        }
        spec = self.prompts.resolve(OUTLINE_PROMPT_KEY)
        system_text, system_missing = render(spec.system, variables)
        user_text, user_missing = render(spec.user, variables)
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]
        return messages, sorted(set(system_missing + user_missing))

    def _outline_row(self, project_id: str, chapter_id: str) -> dict[str, Any] | None:
        """Existing chapter-level outline for *chapter_id*, already serialised."""
        database = self.novels.database_for(project_id)
        with database.session() as session:
            row = session.scalar(
                select(Outline).where(
                    Outline.project_id == project_id,
                    Outline.level == "chapter",
                    Outline.parent_id == chapter_id,
                )
            )
            if row is None:
                return None
            return _outline_result(
                row,
                chapter_id=chapter_id,
                cached=True,
                degraded=not (row.goal or row.key_events),
            )

    def _write_outline(
        self,
        project_id: str,
        chapter_id: str,
        sort_order: int,
        parsed: dict[str, Any],
    ) -> dict[str, Any]:
        """Upsert by ``(project_id, level, parent_id)``; bump ``row_version``."""
        database = self.novels.database_for(project_id)
        with database.session() as session:
            row = session.scalar(
                select(Outline).where(
                    Outline.project_id == project_id,
                    Outline.level == "chapter",
                    Outline.parent_id == chapter_id,
                )
            )
            if row is None:
                row = Outline(
                    id=new_id("out"),
                    project_id=project_id,
                    level="chapter",
                    parent_id=chapter_id,
                )
                session.add(row)
            else:
                row.row_version += 1
            row.sort_order = sort_order
            row.title = parsed["title"]
            row.content = parsed["content"]
            for name in OUTLINE_TEXT_FIELDS:
                setattr(row, name, parsed[name])
            for name in OUTLINE_LIST_FIELDS:
                setattr(row, name, parsed[name])
            row.target_word_count = parsed["target_word_count"]
            session.flush()
            return _outline_result(
                row, chapter_id=chapter_id, cached=False, degraded=parsed["degraded"]
            )

    # ------------------------------------------------------------------
    # Context assembly
    # ------------------------------------------------------------------
    def _context_budget(self, model: ModelConfig) -> int:
        """Characters of manuscript the prompt may contain."""
        window = max(model.context_window, 4096)
        # Leave room for the system prompt, the answer and provider overhead.
        budget = int(window * 0.45)
        return max(1_000, min(budget, MAX_CONTEXT_CHARS))

    def _build_variables(
        self, operation: str, payload: AIRequest, model: ModelConfig
    ) -> dict[str, str]:
        project = self.projects.get(payload.project_id)
        budget = self._context_budget(model)

        chapter = None
        content = payload.content or ""
        if payload.chapter_id:
            chapter = self.novels.get_chapter(payload.project_id, payload.chapter_id)
            content = chapter.content or content

        sections: list[str] = []

        if operation in ("write", "outline"):
            # Only chapters *before* the target one: the target's own summary and
            # anything after it would leak plot the author has not written yet.
            summaries = self._recent_summaries(payload.project_id, payload.chapter_id)
            if summaries:
                sections.append("【前情提要】\n" + "\n".join(summaries))

        if operation in WHOLE_CHAPTER_OPERATIONS:
            if content:
                if operation == "continue":
                    sections.append(
                        "【已有正文（结尾）】\n" + _truncate(content, budget, from_end=True)
                    )
                else:
                    sections.append("【当前正文】\n" + _truncate(content, budget))
        elif operation in SELECTION_OPERATIONS and content:
            sections.append("【所在章节（供参考）】\n" + _truncate(content, budget // 3))

        context = "\n\n".join(sections)

        outline = payload.outline or (chapter.summary if chapter is not None else "")
        selection = payload.selection or payload.content

        characters = ""
        events = ""
        if operation == "review":
            characters = self._characters_digest(payload.project_id)
            events = self._events_digest(payload.project_id)

        # Forward-looking channel. Kept strictly separate from ``context``: what
        # has not happened yet must never be phrased as if it had.
        foreshadows = "（无）"
        if operation in FORESHADOW_OPERATIONS:
            foreshadows = self._foreshadow_digest(payload.project_id, payload.chapter_id) or "（无）"

        return {
            "novel_type": project.novel_type or "",
            "synopsis": project.synopsis or "",
            "context": context,
            "foreshadows": foreshadows,
            "outline": outline,
            "selection": selection,
            "instruction": payload.instruction or "（无特殊要求）",
            "target_words": str(payload.target_words or DEFAULT_TARGET_WORDS),
            "characters": characters,
            "events": events,
        }

    def _recent_summaries(
        self, project_id: str, chapter_id: str | None, limit: int = 5
    ) -> list[str]:
        """Summaries of the *prior* chapters, newest last.

        "Prior" is ``Chapter.sort_order`` strictly below the target chapter's, so
        neither the target's own summary nor a later chapter's leaks into
        「前情提要」. Without a resolvable target the last *limit* chapters are
        used, which is what an unscoped request wants.
        """
        database = self.novels.database_for(project_id)
        with database.session() as session:
            statement = (
                select(ChapterSummary)
                .join(Chapter, Chapter.id == ChapterSummary.chapter_id)
                .where(
                    ChapterSummary.project_id == project_id,
                    Chapter.is_deleted.is_(False),
                )
            )
            target = self._target_chapter(session, project_id, chapter_id)
            if target is not None:
                statement = statement.where(Chapter.sort_order < target.sort_order)
            rows = list(
                session.scalars(
                    statement.order_by(Chapter.sort_order.desc()).limit(limit)
                )
            )
        summaries = [row.summary for row in reversed(rows) if row.summary]
        if not summaries:
            return []
        return [f"- {summary}" for summary in summaries]

    @staticmethod
    def _target_chapter(session: Any, project_id: str, chapter_id: str | None) -> Chapter | None:
        """The chapter being written, or ``None`` when it cannot be resolved."""
        if not chapter_id:
            return None
        chapter = session.get(Chapter, chapter_id)
        if chapter is None or chapter.project_id != project_id or chapter.is_deleted:
            return None
        return chapter

    def _foreshadow_digest(self, project_id: str, chapter_id: str | None) -> str:
        """The 「伏笔与后续规划」 block: planned-forward plus already planted."""
        plan = self._story_plan(project_id, chapter_id)
        planted = self._unresolved_foreshadows(project_id)
        parts = [part for part in (plan, planted) if part]
        return "\n\n".join(parts)

    def _story_plan(
        self, project_id: str, chapter_id: str | None, lookahead: int = 3
    ) -> str:
        """What the target chapter and up to *lookahead* chapters plan to do.

        Read from the chapter-level ``outlines`` rows first and from
        ``chapter_summaries`` when a chapter has no outline yet. This is material
        for the *direction* of the writing only — the prompt labels it as "not
        yet happened", so it can never be narrated as fact.
        """
        if not chapter_id:
            return ""
        database = self.novels.database_for(project_id)
        with database.session() as session:
            chapters = list(
                session.scalars(
                    select(Chapter)
                    .where(
                        Chapter.project_id == project_id,
                        Chapter.is_deleted.is_(False),
                    )
                    .order_by(Chapter.sort_order, Chapter.created_at)
                )
            )
            index = next((i for i, row in enumerate(chapters) if row.id == chapter_id), None)
            if index is None:
                return ""
            window = chapters[index : index + max(lookahead, 0) + 1]
            ids = [row.id for row in window]
            outlines = {
                row.parent_id: row
                for row in session.scalars(
                    select(Outline).where(
                        Outline.project_id == project_id,
                        Outline.level == "chapter",
                        Outline.parent_id.in_(ids),
                    )
                )
            }
            summaries = {
                row.chapter_id: row
                for row in session.scalars(
                    select(ChapterSummary).where(
                        ChapterSummary.project_id == project_id,
                        ChapterSummary.chapter_id.in_(ids),
                    )
                )
            }

        lines: list[str] = []
        for offset, chapter in enumerate(window):
            outline = outlines.get(chapter.id)
            summary = summaries.get(chapter.id)
            goal = ((outline.goal if outline else "") or (summary.plot_progress if summary else ""))
            clues = _dedupe(
                [
                    *((outline.foreshadows if outline else None) or []),
                    *((summary.foreshadows if summary else None) or []),
                ]
            )
            if not goal.strip() and not clues:
                continue
            number = index + offset + 1
            title = ((outline.title if outline else "") or chapter.title or "").strip()
            details = [f"目标={_one_line(goal)}"] if goal.strip() else []
            if clues:
                details.append("伏笔=" + "、".join(clues))
            lines.append(f"- 第 {number} 章「{title[:40]}」：" + "；".join(details) + "；")
        return "\n".join(lines)

    def _unresolved_foreshadows(self, project_id: str, limit: int = 12) -> str:
        """Foreshadows planted in existing chapter outlines, flagged as open.

        Reminder-only: there is no "resolved" flag in the schema yet, so every
        planted item is listed as 「已埋」 for the author to close out.
        """
        database = self.novels.database_for(project_id)
        with database.session() as session:
            rows = list(
                session.scalars(
                    select(Outline)
                    .where(Outline.project_id == project_id, Outline.level == "chapter")
                    .order_by(Outline.sort_order)
                )
            )
        lines: list[str] = []
        for row in rows:
            for clue in _dedupe(list(row.foreshadows or [])):
                lines.append(f"- {clue}（已埋，见大纲「{(row.title or '')[:40]}」，待回收）")
                if len(lines) >= limit:
                    break
            if len(lines) >= limit:
                break
        if not lines:
            return ""
        return "【此前已埋伏笔】\n" + "\n".join(lines)

    def _characters_digest(self, project_id: str, limit: int = 12) -> str:
        from app.models.novel import Character

        database = self.novels.database_for(project_id)
        with database.session() as session:
            rows = list(
                session.scalars(
                    select(Character)
                    .where(
                        Character.project_id == project_id,
                        Character.is_deleted.is_(False),
                    )
                    .limit(limit)
                )
            )
        if not rows:
            return "（未录入人物）"
        lines = []
        for row in rows:
            state = row.current_state or {}
            location = state.get("location") if isinstance(state, dict) else None
            parts = [row.name]
            if row.identity:
                parts.append(f"身份：{row.identity}")
            if location:
                parts.append(f"所在地：{location}")
            if row.personality:
                parts.append(f"性格：{row.personality[:60]}")
            lines.append("- " + "；".join(str(part) for part in parts if part))
        return "\n".join(lines)

    def _events_digest(self, project_id: str, limit: int = 10) -> str:
        from app.models.novel import Event

        database = self.novels.database_for(project_id)
        with database.session() as session:
            rows = list(
                session.scalars(
                    select(Event)
                    .where(Event.project_id == project_id)
                    .order_by(Event.sort_order.desc())
                    .limit(limit)
                )
            )
        if not rows:
            return "（未录入事件）"
        return "\n".join(f"- {row.name}：{row.description[:80]}" for row in reversed(rows))

    # ------------------------------------------------------------------
    # Request helpers
    # ------------------------------------------------------------------
    def _llm_request(
        self, payload: AIRequest, messages: list[dict[str, str]], model: ModelConfig
    ) -> LLMRequest:
        temperature = payload.temperature if payload.temperature is not None else model.temperature
        return LLMRequest(
            model=model.model_name,
            messages=[ChatMessage(role=msg["role"], content=msg["content"]) for msg in messages],  # type: ignore[arg-type]
            temperature=temperature,
            top_p=model.top_p,
            max_tokens=min(model.max_tokens, max(model.max_output_tokens, 256)),
            json_mode=False,
        )

    # ------------------------------------------------------------------
    # Task bookkeeping
    # ------------------------------------------------------------------
    def _start_task(
        self, operation: str, payload: AIRequest, model: ModelConfig, prompt_key: str
    ) -> str:
        task_id = new_id("tsk")
        with self.studio_db.session() as session:
            session.add(
                GenerationTask(
                    id=task_id,
                    project_id=payload.project_id,
                    kind=f"ai.{operation}",
                    status="running",
                    model_config_id=model.id,
                    payload={
                        "chapter_id": payload.chapter_id,
                        "operation": operation,
                        "instruction": payload.instruction[:500],
                        "target_words": payload.target_words,
                    },
                    result={},
                    prompt_version=self._prompt_version(prompt_key),
                    started_at=datetime.now(UTC),
                )
            )
        return task_id

    def _prompt_version(self, prompt_key: str) -> int | None:
        try:
            spec = self.prompts.resolve(prompt_key)
        except KeyError:  # pragma: no cover - defensive
            return None
        with self.studio_db.session() as session:
            from app.models.studio import PromptTemplate

            row = session.scalar(
                select(PromptTemplate)
                .where(PromptTemplate.key == spec.key)
                .order_by(PromptTemplate.version.desc())
            )
        return row.version if row else None

    def _finish_task(
        self,
        task_id: str,
        *,
        text: str,
        model: ModelConfig,
        prompt_key: str,
        usage: LLMUsage,
    ) -> None:
        cost = (
            usage.input_tokens * model.input_price_per_1m
            + usage.output_tokens * model.output_price_per_1m
        ) / 1_000_000
        with self.studio_db.session() as session:
            task = session.get(GenerationTask, task_id)
            if task is None:  # pragma: no cover - task rows are never deleted here
                return
            task.status = "success"
            task.input_tokens = usage.input_tokens
            task.output_tokens = usage.output_tokens
            task.cost = round(cost, 6)
            task.result = {
                "prompt_key": prompt_key,
                "model": model.model_name,
                "chars": len(text),
                "preview": text[:200],
            }
            task.finished_at = datetime.now(UTC)
        logger.info(
            "ai_task_finished",
            task_id=task_id,
            model=model.model_name,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost=round(cost, 6),
        )

    def _fail_task(self, task_id: str, message: str) -> None:
        with self.studio_db.session() as session:
            task = session.get(GenerationTask, task_id)
            if task is None:  # pragma: no cover
                return
            task.status = "failed"
            task.error = message[:2000]
            task.finished_at = datetime.now(UTC)
        logger.warning("ai_task_failed", task_id=task_id, error=message)

    def _result(
        self,
        task_id: str,
        operation: str,
        text: str,
        model: str,
        prompt_key: str,
        usage: LLMUsage,
        config: ModelConfig,
    ) -> AIResult:
        cost = (
            usage.input_tokens * config.input_price_per_1m
            + usage.output_tokens * config.output_price_per_1m
        ) / 1_000_000
        return AIResult(
            task_id=task_id,
            operation=operation,
            text=text,
            model=model,
            prompt_key=prompt_key,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost=round(cost, 6),
        )

    # ------------------------------------------------------------------
    # Task history
    # ------------------------------------------------------------------
    def list_tasks(self, *, project_id: str | None = None, limit: int = 50) -> list[GenerationTask]:
        with self.studio_db.session() as session:
            statement = select(GenerationTask).order_by(GenerationTask.created_at.desc())
            if project_id:
                statement = statement.where(GenerationTask.project_id == project_id)
            statement = statement.where(GenerationTask.kind.like("ai.%"))
            return list(session.scalars(statement.limit(limit)))

    def get_task(self, task_id: str) -> GenerationTask:
        with self.studio_db.session() as session:
            task = session.get(GenerationTask, task_id)
            if task is None:
                raise NotFound(f"Task {task_id} not found")
            return task
