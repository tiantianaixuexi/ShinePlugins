"""Structured (JSON) completions: ask for JSON, parse it loosely, retry once.

Providers are told about strict JSON through ``response_format`` — but only when
the model row advertises ``supports_json_mode`` (see
:class:`~app.ai.llm.openai_compatible.OpenAICompatibleAdapter`). Even then the
reply is not guaranteed to be bare JSON: models wrap it in ``` fences or in a
sentence of prose. So the flow here is:

1. parse the reply with :func:`parse_json_object` (direct → de-fenced → brace span),
2. if that fails and retries remain, append the offending reply plus a repair
   instruction and ask once more,
3. if it still fails, hand back ``None`` together with the **longest** raw text
   seen so far — a truncated JSON body is still worth more to the author than
   the empty string a repair turn sometimes answers with — so the caller can
   degrade to non-structured extraction instead of failing the task.

This module is deliberately free of service-layer imports so both the summary
writer and any future structured operation can share it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from app.ai.llm.registry import ChatClient
from app.ai.llm.types import ChatMessage, LLMRequest, LLMUsage

#: Appended after a non-JSON reply, before the single repair attempt.
REPAIR_INSTRUCTION = (
    "上一次的输出不是合法的 JSON 对象。请只输出一个 JSON 对象，"
    "不要任何解释、前后缀或代码围栏。"
)

_FENCE = "```"


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort parse of a model reply into a JSON object.

    Tries, in order: the reply as-is, the body of a ``` fence, and the span from
    the first ``{`` to the last ``}``. Returns ``None`` when nothing parses to a
    JSON **object** (arrays and scalars are rejected on purpose: every caller
    here reads named fields).
    """
    raw = (text or "").strip()
    if not raw:
        return None
    for candidate in (raw, _strip_fences(raw), _brace_span(raw)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


def as_str_list(value: Any, limit: int = 50) -> list[str]:
    """Coerce whatever the model returned into a list of short strings."""
    if isinstance(value, str):
        items = [part.strip() for part in re.split(r"[、,，;；\n]", value)]
    elif isinstance(value, list | tuple):
        items = [str(item).strip() for item in value]
    else:
        items = []
    return [item[:120] for item in items if item][:limit]


def _strip_fences(text: str) -> str:
    """Return the body of the first ``` block, or ``""`` when there is none."""
    parts = text.split(_FENCE)
    if len(parts) < 3:
        return ""
    body = parts[1].strip()
    head, _, tail = body.partition("\n")
    # A bare language tag on the opening line ("```json") is not part of the JSON.
    if head and "{" not in head and "}" not in head:
        body = tail.strip()
    return body


def _brace_span(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return ""
    return text[start : end + 1]


def longest_text(*candidates: str) -> str:
    """Return whichever candidate carries the most non-blank text.

    Used by every degradation path: when a repair turn answers with ``""`` (or
    with less prose than the first attempt) the reply the author already paid
    for must not be thrown away. Blank candidates never win, so the result is
    ``""`` only when *every* attempt was blank.
    """
    best = ""
    best_size = 0
    for candidate in candidates:
        text = candidate or ""
        size = len(text.strip())
        if size > best_size:
            best, best_size = text, size
    return best


@dataclass(slots=True)
class StructuredReply:
    """Outcome of :func:`complete_json`.

    ``data`` is ``None`` when every attempt failed to produce a JSON object, in
    which case ``text`` holds the **longest** raw reply from any attempt (never
    a blank repair turn when the first attempt did say something) for the caller
    to degrade on. When an attempt parses, ``text`` is that attempt's reply.
    Unpacks as ``(data, text)``; ``usage`` and ``attempts`` stay reachable as
    attributes so token accounting covers the repair call too.
    """

    data: dict[str, Any] | None
    text: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    attempts: int = 0

    @property
    def ok(self) -> bool:
        return self.data is not None

    def __iter__(self) -> Iterator[Any]:
        yield self.data
        yield self.text


async def complete_json(
    client: ChatClient,
    request: LLMRequest,
    *,
    retries: int = 1,
    model_config_id: str | None = None,
) -> StructuredReply:
    """Run *request* in JSON mode, retrying once when the reply is not JSON.

    ``request.json_mode`` is switched on here; the adapter decides whether the
    provider actually supports it, so this is safe for models without the
    capability (they just get the prompt-level instruction).

    The returned ``text`` is never blank when any attempt produced text: on
    total failure it is the longest reply seen, not merely the last one (see
    :func:`longest_text`).
    """
    request.json_mode = True
    messages = list(request.messages)
    usage = LLMUsage()
    attempts = 0
    raw = ""

    while True:
        request.messages = messages
        response = await client.complete(request, model_config_id=model_config_id)
        attempts += 1
        usage = LLMUsage(
            input_tokens=usage.input_tokens + response.usage.input_tokens,
            output_tokens=usage.output_tokens + response.usage.output_tokens,
        )

        data = parse_json_object(response.text)
        if data is not None:
            # The reply that parsed wins: callers re-derive fields from it.
            return StructuredReply(
                data=data, text=response.text, usage=usage, attempts=attempts
            )
        raw = longest_text(raw, response.text)
        if attempts > retries:
            return StructuredReply(
                data=None, text=raw, usage=usage, attempts=attempts
            )

        messages = [
            *messages,
            ChatMessage(role="assistant", content=response.text),
            ChatMessage(role="user", content=REPAIR_INSTRUCTION),
        ]
