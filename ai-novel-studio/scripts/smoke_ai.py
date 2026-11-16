"""Real end-to-end AI check against a configured provider.

Creates a throwaway project in a temporary data directory, then runs one
non-streaming operation and one streaming operation against the real provider.
The API key comes from the environment (see ``configure_model.py``).

    $env:MINIMAX_API_KEY = "<key>"
    backend/.venv/Scripts/python.exe scripts/smoke_ai.py `
        --base-url https://api.minimax.io/v1 `
        --model MiniMax-M2 `
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ai.llm.errors import LLMAdapterError  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.errors import StudioError  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.runtime import Runtime  # noqa: E402
from app.schemas.ai import AIRequest  # noqa: E402
from app.schemas.model_config import ModelConfigCreate  # noqa: E402
from app.schemas.novel import ChapterCreate  # noqa: E402
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
        deltas = 0
        first_token_at: float | None = None
        text_parts: list[str] = []
        done_payload: dict | None = None
        error_payload: dict | None = None

        async def consume() -> None:
            nonlocal deltas, first_token_at, done_payload, error_payload
            async for event in runtime.ai.stream(
                "continue",
                AIRequest(
                    project_id=project.id,
                    chapter_id=chapter.id,
                    instruction="续写 150 字左右，保持悬疑气氛，不要重复已有情节。",
                    temperature=0.7,
                    model_config_id=model.id,
                ),
            ):
                if event.type == "delta":
                    deltas += 1
                    if first_token_at is None:
                        first_token_at = time.perf_counter() - started
                    text_parts.append(event.text)
                elif event.type == "done":
                    done_payload = event.data
                else:
                    error_payload = event.data

        await consume()
        elapsed = time.perf_counter() - started

        check("流式没有报错", error_payload is None, str(error_payload))
        check("收到增量文本", deltas > 1, f"{deltas} 个增量")
        check("完成事件带用量", bool(done_payload and done_payload.get("output_tokens")), str(done_payload))
        if first_token_at is not None:
            print(f"  首字延迟 {first_token_at:.2f}s · 总耗时 {elapsed:.1f}s · {deltas} 个增量")
        print("  结果预览：")
        for line in "".join(text_parts).strip().splitlines()[:5]:
            print(f"    {line}")
        print()

        # 3. Task ledger ---------------------------------------------------
        tasks = runtime.ai.list_tasks(project_id=project.id)
        check("任务已记账", len(tasks) >= 2, f"{len(tasks)} 条")
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
    parser.add_argument("--base-url", default="https://api.minimax.io/v1")
    parser.add_argument("--model", default="MiniMax-M2")
    parser.add_argument("--provider", default="minimax")
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