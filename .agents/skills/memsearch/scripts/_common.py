#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memsearch hook 公共工具。

设计约束（重要）：
  · 任何异常都不能冒泡到 hook 层 —— 调用方必须永远 exit 0，否则可能卡住会话。
  · 只用标准库，不依赖项目里的 Python 环境。
"""

from __future__ import annotations

import json
import locale
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MEMORY_DIRNAME = Path(".memsearch") / "memory"
MARKER_PREFIX = "<!-- session:"
BOM = "\ufeff"


def log(msg: str) -> None:
    """错误只写 stderr，stdout 必须留给 hook 协议的 JSON。"""
    print(f"[memsearch-hook] {msg}", file=sys.stderr)


def decode_bytes(data: bytes) -> str:
    """容错解码：UTF-8 →（带 BOM）→ 系统区域编码 → 最后才 replace。

    为什么需要：Windows 上如果宿主用 ANSI(cp936) 写 stdin，只按 UTF-8 解码会把中文
    变成替换字符且**不报错**——表现为"查询词变成乱码、召回永远为空"，极难排查。
    """
    if not data:
        return ""
    for enc in ("utf-8", "utf-8-sig", locale.getpreferredencoding(False), "gbk"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def read_payload() -> dict:
    """读 stdin 的 hook payload；读不到就返回空 dict，绝不抛。"""
    try:
        raw = decode_bytes(sys.stdin.buffer.read())
    except Exception as exc:  # pragma: no cover - 极端环境
        log(f"read stdin failed: {exc}")
        return {}
    raw = raw.strip().lstrip(BOM)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log(f"payload is not JSON: {exc}")
        return {}


def find_repo_root(payload: dict) -> Path:
    """从 payload.cwd（或当前目录）向上找带 .memsearch.toml 或 .git 的目录。"""
    start = payload.get("cwd") or os.getcwd()
    try:
        here = Path(start).resolve()
    except Exception:
        here = Path.cwd()
    for cand in [here, *here.parents]:
        if (cand / ".memsearch.toml").exists() or (cand / ".git").exists():
            return cand
    return here


def memory_dir(root: Path) -> Path:
    return root / MEMORY_DIRNAME


def today_file(root: Path) -> Path:
    return memory_dir(root) / f"{datetime.now().strftime('%Y-%m-%d')}.md"


def memsearch_exe() -> str | None:
    return shutil.which("memsearch")


def run_memsearch(args: list[str], cwd: Path, timeout: int = 60) -> tuple[int | None, str]:
    """返回 (returncode|None, 组合输出)。找不到 CLI 或超时都返回 None，不抛。"""
    exe = memsearch_exe()
    if not exe:
        return None, "memsearch not found on PATH"
    try:
        proc = subprocess.run(
            [exe, *args],
            cwd=str(cwd),
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return None, f"memsearch {args[0]} timed out after {timeout}s"
    except Exception as exc:  # pragma: no cover
        return None, f"memsearch {args[0]} failed: {exc}"


def already_recorded(mem_file: Path, session_id: str) -> bool:
    """同一个 session 只落盘一次（幂等），避免重复 Stop 把记忆灌爆。"""
    if not session_id or not mem_file.exists():
        return False
    try:
        text = mem_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    return f"{MARKER_PREFIX}{session_id}" in text


def emit(payload: dict) -> None:
    """按 hook 协议输出单个 JSON 并正常退出。

    必须写 **UTF-8 字节**，不能用 sys.stdout.write(str)：
    Windows 控制台默认 cp936，遇到 `›`、emoji 等字符会抛 UnicodeEncodeError，
    而异常一旦被吞掉就变成"输出 {} 且无任何报错"——排查成本极高（已实际踩过）。
    """
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except Exception:
        data = b"{}"
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    except Exception:
        try:
            sys.stdout.write("{}")
            sys.stdout.flush()
        except Exception:
            pass
    sys.exit(0)


# ---------------------------------------------------------------- transcript

def _text_of(content) -> str:
    """把 message.content（str | list[block]）拍平成纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                for key in ("text", "content", "thinking"):
                    val = block.get(key)
                    if isinstance(val, str) and val.strip():
                        parts.append(val)
                        break
        return "\n".join(parts)
    return ""


def iter_turns(transcript_path: str):
    """容忍多种 JSONL 形态：尽量产出 (role, text)。

    未知格式不会报错，只会产出很少的条目 —— 上层按"没有可用内容"处理。
    """
    try:
        with open(transcript_path, "rb") as fh:
            for line in decode_bytes(fh.read()).splitlines():
                line = line.strip().lstrip(BOM)
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                role = obj.get("role") or obj.get("type") or ""
                message = obj.get("message")
                if isinstance(message, dict):
                    role = message.get("role") or role
                    text = _text_of(message.get("content"))
                else:
                    text = _text_of(obj.get("content")) or _text_of(obj.get("text"))
                if text.strip():
                    yield str(role), text
    except FileNotFoundError:
        log(f"transcript not found: {transcript_path}")
    except Exception as exc:
        log(f"transcript read failed: {exc}")
