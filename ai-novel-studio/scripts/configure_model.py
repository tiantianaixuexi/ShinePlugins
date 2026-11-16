"""Register or update one model configuration from the command line.

The API key is read from an **environment variable** — never from argv (which
lands in shell history) and never into a file in the repository. It is stored
through the same DPAPI-encrypted store the desktop app uses, so afterwards the
key only exists inside the user's application data directory.

Examples (PowerShell)::

    $env:MODEL_API_KEY = "<key>"
    backend/.venv/Scripts/python.exe scripts/configure_model.py `
        --name "<display name>" --provider openai_compatible `
        --base-url https://<your-gateway>/v1 `
        --model <model-name> `
        --context-window 200000 --max-output 8192 --set-default

    # update an existing row instead of creating a new one
    ... configure_model.py --model-id mdl_xxx --model <new-model-name>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.runtime import Runtime  # noqa: E402
from app.schemas.model_config import (  # noqa: E402
    PROVIDERS,
    ModelConfigCreate,
    ModelConfigUpdate,
)

KEY_ENV_VARS = ("MINIMAX_API_KEY", "STUDIO_MODEL_API_KEY", "OPENAI_API_KEY")


def resolve_key(explicit: str | None) -> str | None:
    if explicit:
        return explicit.strip()
    for name in KEY_ENV_VARS:
        value = os.environ.get(name)
        if value and value.strip():
            print(f"使用环境变量 {name} 中的密钥")
            return value.strip()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or update one model configuration."
    )
    parser.add_argument("--model-id", help="Update this row instead of creating a new one")
    parser.add_argument("--name", default="MiniMax", help="Display name")
    parser.add_argument("--provider", default="minimax", choices=list(PROVIDERS))
    parser.add_argument("--base-url", default="", help="OpenAI-compatible base URL")
    parser.add_argument("--model", dest="model_name", default="", help="Model id")
    parser.add_argument("--api-key", default=None, help="Key value (prefer an env var)")
    parser.add_argument("--clear-key", action="store_true", help="Remove the stored key")
    parser.add_argument("--context-window", type=int, default=32768)
    parser.add_argument("--max-output", type=int, default=8192)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--input-price", type=float, default=0.0)
    parser.add_argument("--output-price", type=float, default=0.0)
    parser.add_argument("--json-mode", action="store_true")
    parser.add_argument("--set-default", action="store_true")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Override the application data directory (default: the OS user data dir)",
    )
    args = parser.parse_args()

    configure_logging(level="WARNING", json_output=False)

    settings = get_settings()
    if args.data_dir:
        settings = settings.model_copy(update={"data_dir": Path(args.data_dir).expanduser().resolve()})

    runtime = Runtime(settings)
    runtime.start()
    try:
        service = runtime.model_configs

        if args.model_id:
            key = None if args.clear_key else resolve_key(args.api_key)
            payload = ModelConfigUpdate(
                name=args.name or None,
                provider=args.provider,
                base_url=args.base_url or None,
                model_name=args.model_name or None,
                context_window=args.context_window,
                max_output_tokens=args.max_output,
                temperature=args.temperature,
                input_price_per_1m=args.input_price,
                output_price_per_1m=args.output_price,
                supports_json_mode=args.json_mode or None,
                row_version=service.get(args.model_id).row_version,
                api_key=key,
            )
            model = service.update(args.model_id, payload)
            action = "updated"
        else:
            if not args.name or not args.model_name:
                parser.error("--name and --model are required when creating a new row")
            key = None if args.clear_key else resolve_key(args.api_key)
            payload = ModelConfigCreate(
                name=args.name,
                provider=args.provider,
                base_url=args.base_url,
                model_name=args.model_name,
                api_key=key,
                temperature=args.temperature,
                context_window=args.context_window,
                max_output_tokens=args.max_output,
                input_price_per_1m=args.input_price,
                output_price_per_1m=args.output_price,
                supports_json_mode=args.json_mode,
            )
            model = service.create(payload)
            action = "created"

        if args.set_default:
            model = service.set_default(model.id)

        print()
        print(f"模型配置已 {action}：")
        print(f"  id            : {model.id}")
        print(f"  name          : {model.name}")
        print(f"  provider      : {model.provider}")
        print(f"  base_url      : {model.base_url or '(未设置)'}")
        print(f"  model         : {model.model_name}")
        print(f"  context window: {model.context_window}")
        print(f"  max output    : {model.max_output_tokens}")
        print(f"  密钥          : {'已加密保存' if service.secrets.has(model.api_key_ref or '') else '未设置'}")
        print(f"  默认模型      : {'是' if model.is_default else '否'}")
        print(f"  data dir      : {settings.data_dir}")
        return 0
    finally:
        runtime.stop()


if __name__ == "__main__":
    raise SystemExit(main())