"""Real end-to-end AI check against a configured provider.

Creates a throwaway project in a temporary data directory, then runs one
non-streaming operation and one streaming operation against the real provider.
The API key comes from the environment (see ``configure_model.py``).

推荐直接用应用里已保存的默认模型（含 DPAPI 加密的密钥），不写死任何模型名：

    backend/.venv/Scripts/python.exe scripts/smoke_ai.py --from-store

也可以显式指定（两者都给）：

    $env:MODEL_API_KEY = "<key>"
    backend/.venv/Scripts/python.exe scripts/smoke_ai.py `
        --base-url https://<your-gateway>/v1 `
        --model <model-name> `
        --context-window 200000

Exits non-zero if any step fails. Nothing is written to the real library.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ai.llm.errors import LLMAdapterError  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.errors import StudioError  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.runtime import Runtime  # noqa: E402
from app.schemas.ai import AIRequest  # noqa: E402
from app.schemas.model_config import ModelConfigCreate  # noqa: E402
from app.schemas.novel import ChapterAcceptAi, ChapterCreate  # noqa: E402
from app.schemas.project import ProjectCreate  # noqa: E402
from app.services.novel_service import NovelService  # noqa: E402

SAMPLE = (
    "雨下了整夜。林清推开客栈的木窗，楼下的青石板泛着冷光。\n\n"
    "她把那封没有署名的信摊在桌上，信纸边缘已经被雨水洇开，只剩下一行字还看得清："
    "「子时，城南旧仓。」\n\n"
    "门外传来三更的梆子声。她数着，一声，两声，第三声迟迟没有落下。"
)

failures = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures
    if not condition:
        failures += 1
    print(f"[{'PASS' if condition else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not condition else ""))


@dataclass
class Drained:
    """What one streamed generation produced, with both frame timings."""

    deltas: int = 0
    thoughts: int = 0
    resets: int = 0
    done: dict | None = None
    error: dict | None = None
    text: str = ""
    thinking: str = ""
    first_delta_at: float | None = None
    first_thinking_at: float | None = None


async def drain(events, started: float) -> Drained:
    """Consume one streamed generation, timing the thinking and text frames."""
    out = Drained()
    parts: list[str] = []
    thoughts: list[str] = []
    async for event in events:
        if event.type == "thinking":
            out.thoughts += 1
            if out.first_thinking_at is None:
                out.first_thinking_at = time.perf_counter() - started
            thoughts.append(event.text)
        elif event.type == "delta":
            out.deltas += 1
            if out.first_delta_at is None:
                out.first_delta_at = time.perf_counter() - started
            parts.append(event.text)
        elif event.type == "reset":
            # Control frame, not an error: the JSON repair re-sends the whole
            # answer, so whatever the first attempt streamed is thrown away.
            out.resets += 1
            parts.clear()
        elif event.type == "done":
            out.done = event.data
        else:
            out.error = event.data
    out.text = "".join(parts)
    out.thinking = "".join(thoughts)
    return out


def _seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}s"


def frame_lines(drained: Drained) -> None:
    """Print the two frame timings this check exists for (thinking ≪ delta)."""
    if not drained.thoughts:
        print("  首个 thinking 帧 — ·（该模型本次未返回思考内容）")
    print(f"  首个 thinking 帧 {_seconds(drained.first_thinking_at)} · 首个 delta 帧 {_seconds(drained.first_delta_at)}")
    if drained.thoughts:
        print(f"  思考帧 {drained.thoughts} 个 / {len(drained.thinking)} 字（不计入正文）")
    if drained.resets:
        print(f"  收到 {drained.resets} 个 reset 帧（JSON 修复重试，已丢弃前一轮增量）")


def spend_line(runtime: Runtime, project_id: str, kind: str, elapsed: float) -> None:
    """Print wall time plus the token usage of the newest task of *kind*."""
    task = next(
        (item for item in runtime.ai.list_tasks(project_id=project_id) if item.kind == kind),
        None,
    )
    if task is None:
        print(f"  耗时 {elapsed:.1f}s · 未找到任务记录（{kind}）")
        return
    print(
        f"  耗时 {elapsed:.1f}s · 输入 {task.input_tokens} token · "
        f"输出 {task.output_tokens} token · cost={task.cost}"
    )


async def main_async(args: argparse.Namespace) -> int:
    key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("STUDIO_MODEL_API_KEY")
    source = "环境变量"

    if args.from_store:
        # Read the saved model (Base URL, model name, encrypted key) from the
        # app's real data directory, then test against a throwaway library.
        from app.core.config import get_settings
        from app.core.keystore import secret_label_for_model

        store = Runtime(get_settings())
        store.start()
        try:
            saved = store.model_configs.default_model()
            if saved is None:
                print("应用里还没有默认模型，请先在「系统设置 → 模型配置」添加并设为默认。")
                return 2
            key = store.model_configs.secrets.get(secret_label_for_model(saved.id))
            if not key:
                print(f"模型「{saved.name}」没有保存密钥，请在设置里补填 API Key。")
                return 2
            args.base_url = saved.base_url
            args.model = saved.model_name
            args.provider = saved.provider
            args.context_window = saved.context_window
            args.max_output = saved.max_output_tokens
            source = f"已保存的模型「{saved.name}」"
        finally:
            store.stop()

    if not key:
        print("缺少密钥：请设置环境变量 MINIMAX_API_KEY，或加 --from-store 使用应用里保存的模型。")
        return 2

    if not args.from_store and (not args.base_url or not args.model):
        print("缺少 --base-url / --model：推荐直接加 --from-store，用应用里已保存的模型。")
        return 2

    data_dir = Path(tempfile.mkdtemp(prefix="novel-studio-ai-smoke-"))
    settings = Settings(data_dir=data_dir, auth_token=None, log_level="WARNING")
    runtime = Runtime(settings)
    runtime.start()

    try:
        model = runtime.model_configs.create(
            ModelConfigCreate(
                name="AI 冒烟模型",
                provider=args.provider,
                base_url=args.base_url,
                model_name=args.model,
                api_key=key,
                context_window=args.context_window,
                max_output_tokens=args.max_output,
                temperature=args.temperature,
                input_price_per_1m=args.input_price,
                output_price_per_1m=args.output_price,
            )
        )
        print(f"模型：{model.name} / {model.model_name} @ {model.base_url}")
        print(f"密钥来源：{source}")
        print(f"数据目录（临时）：{data_dir}\n")

        project = runtime.project_service.create(
            ProjectCreate(
                name="AI 冒烟测试",
                novel_type="悬疑",
                synopsis="雨夜客栈，一封没有署名的信。",
                target_word_count=1000,
            )
        )
        chapter = NovelService(runtime.project_service).create_chapter(
            project.id, ChapterCreate(title="第一章 雨夜", content=SAMPLE)
        )
        check("测试项目与章节已创建", bool(project.id and chapter.id))

        # 1. Non-streaming polish -----------------------------------------
        print("→ 润色（非流式）…")
        started = time.perf_counter()
        try:
            result = await runtime.ai.run(
                "polish",
                AIRequest(
                    project_id=project.id,
                    chapter_id=chapter.id,
                    selection=SAMPLE,
                    instruction="保留原意与悬疑气氛，让语言更凝练。",
                    temperature=0.6,
                    model_config_id=model.id,
                ),
            )
            elapsed = time.perf_counter() - started
            check("润色返回文本", bool(result.text.strip()), result.text[:80])
            check(
                "记录了 token 与成本",
                result.input_tokens > 0 and result.output_tokens > 0,
                f"in={result.input_tokens} out={result.output_tokens} cost={result.cost}",
            )
            print(f"  耗时 {elapsed:.1f}s · 输入 {result.input_tokens} token · 输出 {result.output_tokens} token")
            print("  结果预览：")
            for line in result.text.strip().splitlines()[:5]:
                print(f"    {line}")
            print()
        except (LLMAdapterError, StudioError) as exc:
            check("润色调用成功", False, str(exc))
            return 1

        # 2. Streaming continue -------------------------------------------
        print("→ 续写（流式）…")
        started = time.perf_counter()
        drained = await drain(
            runtime.ai.stream(
                "continue",
                AIRequest(
                    project_id=project.id,
                    chapter_id=chapter.id,
                    instruction="续写 150 字左右，保持悬疑气氛，不要重复已有情节。",
                    temperature=0.7,
                    model_config_id=model.id,
                ),
            ),
            started,
        )
        elapsed = time.perf_counter() - started

        check("流式没有报错", drained.error is None, str(drained.error))
        check("收到增量文本", drained.deltas > 1, f"{drained.deltas} 个增量")
        check(
            "完成事件带用量",
            bool(drained.done and drained.done.get("output_tokens")),
            str(drained.done),
        )
        # The whole point of T-36: reasoning tokens arrive long before the first
        # character of the answer, and must not be spliced into it.
        check(
            "思考内容未混入正文",
            not drained.thinking or drained.thinking[:20] not in drained.text,
        )
        if drained.first_delta_at is not None:
            print(f"  首字延迟 {drained.first_delta_at:.2f}s · 总耗时 {elapsed:.1f}s · {drained.deltas} 个增量")
        frame_lines(drained)
        print("  结果预览：")
        for line in drained.text.strip().splitlines()[:5]:
            print(f"    {line}")
        print()

        # 3. Chapter summary (L1 memory) ------------------------------------
        print("→ 章节摘要（L1）…")
        started = time.perf_counter()
        try:
            summary = await runtime.ai.summarize_chapter(
                project.id, chapter.id, force=True, model_config_id=model.id
            )
        except (LLMAdapterError, StudioError) as exc:
            check("摘要调用成功", False, str(exc))
            return 1
        elapsed = time.perf_counter() - started
        summary_text = (summary.get("summary") or "").strip()
        check("摘要非空", bool(summary_text), str(summary)[:160])
        check("首次摘要未走缓存", summary.get("cached") is False, str(summary)[:160])
        spend_line(runtime, project.id, "ai.summary", elapsed)
        print("  摘要预览：")
        for line in summary_text.splitlines()[:3]:
            print(f"    {line}")
        print()

        started = time.perf_counter()
        cached_summary = await runtime.ai.summarize_chapter(
            project.id, chapter.id, model_config_id=model.id
        )
        cached_elapsed = time.perf_counter() - started
        check("二次摘要命中缓存", cached_summary.get("cached") is True, str(cached_summary)[:160])
        check("缓存摘要与首次一致", cached_summary.get("summary") == summary.get("summary"))
        print(f"  缓存命中耗时 {cached_elapsed:.2f}s（未调用模型）\n")

        # 4. Structured outline, persisted -----------------------------------
        print("→ 章节大纲（落库）…")
        started = time.perf_counter()
        try:
            outline = await runtime.ai.generate_outline(
                project.id, chapter.id, force=True, model_config_id=model.id
            )
        except (LLMAdapterError, StudioError) as exc:
            check("大纲调用成功", False, str(exc))
            return 1
        elapsed = time.perf_counter() - started
        check("大纲已落库", bool(outline.get("outline_id")), str(outline)[:160])
        check("大纲挂在当前章节下", outline.get("parent_id") == chapter.id, str(outline.get("parent_id")))
        check("大纲层级为 chapter", outline.get("level") == "chapter", str(outline.get("level")))
        if outline.get("degraded"):
            # A real model sometimes answers in prose instead of JSON. That is
            # acceptable, but the raw reply must still be stored.
            check(
                "降级大纲保留了原文",
                bool((outline.get("content") or "").strip()),
                str(outline)[:160],
            )
        else:
            check("大纲标题非空", bool((outline.get("title") or "").strip()), str(outline)[:160])
        spend_line(runtime, project.id, "ai.outline.structured", elapsed)
        print(f"  degraded={outline.get('degraded')} · 标题：{outline.get('title') or '（空）'}")
        print()

        # 4b. Streamed outline + summary (T-30) -------------------------------
        print("→ 章节大纲（流式，强制重算）…")
        started = time.perf_counter()
        streamed = await drain(
            runtime.ai.stream_outline(
                project.id, chapter.id, force=True, model_config_id=model.id
            ),
            started,
        )
        elapsed = time.perf_counter() - started
        done = streamed.done
        check("流式大纲没有报错", streamed.error is None, str(streamed.error))
        # ``> 0``, not ``> 1``: after a ``reset`` the repaired answer often arrives
        # as a single chunk, which is still a streamed reply.
        check("流式大纲收到增量", streamed.deltas > 0, f"{streamed.deltas} 个增量")
        check("流式大纲已落库", bool(done and done.get("outline_id")), str(done)[:160])
        if streamed.first_delta_at is not None:
            print(f"  首字延迟 {streamed.first_delta_at:.2f}s · 总耗时 {elapsed:.1f}s · {streamed.deltas} 个增量")
        frame_lines(streamed)
        print()

        print("→ 章节摘要（流式，强制重算）…")
        started = time.perf_counter()
        streamed = await drain(
            runtime.ai.stream_summary(
                project.id, chapter.id, force=True, model_config_id=model.id
            ),
            started,
        )
        elapsed = time.perf_counter() - started
        done = streamed.done
        check("流式摘要没有报错", streamed.error is None, str(streamed.error))
        check("流式摘要收到增量", streamed.deltas > 0, f"{streamed.deltas} 个增量")
        check(
            "流式摘要非空",
            bool(done and (done.get("summary") or "").strip()),
            str(done)[:160],
        )
        if streamed.first_delta_at is not None:
            print(f"  首字延迟 {streamed.first_delta_at:.2f}s · 总耗时 {elapsed:.1f}s · {streamed.deltas} 个增量")
        frame_lines(streamed)
        spend_line(runtime, project.id, "ai.summary", elapsed)
        print()

        # 5. Accept AI text, keeping the blood-line --------------------------
        print("→ 采纳 AI 正文（血缘）…")
        started = time.perf_counter()
        accepted_text = result.text.strip()
        accepted = NovelService(runtime.project_service).accept_ai(
            project.id,
            chapter.id,
            ChapterAcceptAi(
                content=accepted_text,
                task_id=result.task_id,
                note="AI 冒烟测试",
            ),
        )
        elapsed = time.perf_counter() - started
        check("采纳版本来源为 ai", accepted.version.source == "ai", accepted.version.source)
        check(
            "采纳版本携带 task_id",
            accepted.version.task_id == result.task_id,
            f"{accepted.version.task_id} != {result.task_id}",
        )
        check(
            "章节正文已换成 AI 文本",
            accepted.chapter.content == accepted_text,
            f"{len(accepted.chapter.content or '')} != {len(accepted_text)} 字",
        )
        print(f"  耗时 {elapsed:.2f}s · 版本 v{accepted.version.version_no} · {accepted.chapter.word_count} 字\n")

        # 6. Task ledger ---------------------------------------------------
        tasks = runtime.ai.list_tasks(project_id=project.id)
        check("任务已记账", len(tasks) >= 4, f"{len(tasks)} 条")
        for task in tasks:
            print(
                f"  {task.kind:<16} {task.status:<8} in={task.input_tokens:<5} "
                f"out={task.output_tokens:<5} cost={task.cost}"
            )

    finally:
        runtime.stop()

    print()
    if failures:
        print(f"AI SMOKE FAILED: {failures} 项未通过")
        return 1
    print("AI SMOKE PASSED: 真实模型调用成功")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a real AI smoke test.")
    # No hard-coded defaults: a stale model name here reads like "this is what
    # you are testing" and has already caused a wrong report once. Use
    # ``--from-store`` (recommended) or pass both ``--base-url`` and ``--model``.
    parser.add_argument("--base-url", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--provider", default="openai_compatible")
    parser.add_argument(
        "--from-store",
        action="store_true",
        help="Use the default model already saved in the app (reads the encrypted key)",
    )
    parser.add_argument("--context-window", type=int, default=200_000)
    parser.add_argument("--max-output", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--input-price", type=float, default=0.0)
    parser.add_argument("--output-price", type=float, default=0.0)
    args = parser.parse_args()

    configure_logging(level="WARNING", json_output=False)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())