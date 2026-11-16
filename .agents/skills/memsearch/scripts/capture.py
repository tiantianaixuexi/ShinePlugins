#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stop hook：把本次会话的原始片段落盘到 .memsearch/memory/ 并增量建索引。

边界（刻意不做的事）：
  · 不生成摘要 —— hook 是 shell 进程，这里没有 LLM。摘要由 agent 用
    /memory-save 或技能里的 §3.3 补写，本脚本只留"证据"。
  · 不改动已存在的记忆段落，只追加。
  · 任何失败都静默降级为 `{}` + exit 0，不能影响会话结束。

环境变量：
  MEMSEARCH_CAPTURE=0   关闭自动落盘（临时排查用）
  MEMSEARCH_MAX_FILES   （保留，当前未使用）
  DSH_HOME              DSH 家目录覆盖（定位 session.v4.jsonl.zstd 用，见 _dsh_session.py）

DSH（DeepSeek Harness）分支（DEF-252）：
  CodeBuddy 的 Stop payload 带 `transcript_path` 指向明文 JSONL；DSH 的
  `@deepseek-ai/dsh-hooks-claude-code` 桥给的 `transcript_path` 可能是空串，
  即便有值也是 `session.v4.jsonl.zstd`（zstd 压缩的版本化日志）。
  所以：`transcript_path` 缺失/不存在但有 `session_id` 时，自己去
  `~/.dsh/sessions/*/<session_id>/` 找日志；`transcript_path` 是 zstd 时也走同一条路。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _dsh_session  # noqa: E402
from _common import (  # noqa: E402
    MARKER_PREFIX,
    already_recorded,
    emit,
    find_repo_root,
    iter_turns,
    log,
    memory_dir,
    memsearch_exe,
    read_payload,
    run_memsearch,
    today_file,
)

MAX_PROMPTS = 6
MAX_ASSISTANT = 3
MAX_CHARS = 320


def _clip(text: str, limit: int = MAX_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def selftest() -> None:
    """给 /memory-doctor 用：只检查环境，不写任何文件。"""
    problems = []
    print(f"python: {sys.version.split()[0]}")
    exe = memsearch_exe()
    print(f"memsearch: {exe or 'NOT FOUND'}")
    if not exe:
        problems.append("memsearch 不在 PATH")

    payload = {"cwd": os.getcwd()}
    root = find_repo_root(payload)
    print(f"repo root: {root}")
    print(f"memory dir: {memory_dir(root)}")
    print(f"project config: {(root / '.memsearch.toml').exists()}")

    code, out = run_memsearch(["config", "get", "milvus.collection"], root, timeout=30)
    print(f"collection: {out if code == 0 else f'ERROR {out}'}")
    if code != 0:
        problems.append("读不到 collection 配置")
    elif out.strip() != "novelstudio_memory":
        problems.append(f"collection 不是 novelstudio_memory（实际 {out.strip()}）")

    home = _dsh_session.dsh_home()
    print(f"dsh home: {home or 'NOT FOUND'}")
    if home is not None:
        print(f"dsh sessions: {home / 'sessions'}")
        print(f"dsh format: v{_dsh_session.KNOWN_SESSION_FORMAT_VERSION}")

    code, out = run_memsearch(["stats"], root, timeout=30)
    print(f"stats: {out.splitlines()[-1] if out else ''}")
    if code != 0:
        problems.append("stats 失败（可能还没 index 过）")

    if problems:
        print("selftest FAILED: " + "; ".join(problems))
    else:
        print("selftest OK")
    sys.exit(0)


def _turns_from_transcript(path: Path) -> tuple[list[str], list[str]]:
    """明文 JSONL（CodeBuddy / Claude Code 口径）。"""
    prompts: list[str] = []
    replies: list[str] = []
    for role, text in iter_turns(str(path)):
        role_l = role.lower()
        if "user" in role_l or role_l in ("human", "prompt"):
            prompts.append(_clip(text))
        elif "assistant" in role_l or role_l in ("ai", "model", "response"):
            replies.append(_clip(text))
    return prompts, replies


def _turns_from_dsh(path: Path) -> tuple[list[str], list[str]]:
    """DSH 会话日志（zstd + 版本化格式）。读不了/版本不认识 → 空列表（已在内部 log）。"""
    session = _dsh_session.load_session(path)
    if session is None:
        return [], []
    prompts: list[str] = []
    replies: list[str] = []
    for role, text in _dsh_session.iter_turns(session["events"]):
        (prompts if role == "user" else replies).append(_clip(text))
    return prompts, replies


def build_section(root: Path, payload: dict) -> str | None:
    transcript = str(payload.get("transcript_path") or "")
    session_id = str(payload.get("session_id") or "")
    path = Path(transcript) if transcript else None

    if path is not None and path.exists():
        if _dsh_session.is_zstd_file(path):
            log(f"transcript is a zstd session log (DSH): {path}")
            prompts, replies = _turns_from_dsh(path)
        else:
            prompts, replies = _turns_from_transcript(path)
    else:
        if transcript:
            log(f"transcript_path not on disk: {transcript}")
        prompts, replies = [], []
        # DSH 的桥常常给不出 transcript_path → 用 session_id 自己定位会话日志
        if session_id:
            found = _dsh_session.find_session_file(
                session_id, str(payload.get("cwd") or "")
            )
            if found is not None:
                log(f"using DSH session log: {found}")
                prompts, replies = _turns_from_dsh(found)
        if not prompts and not replies:
            log("no transcript_path in payload; skip capture")
            return None

    if not prompts and not replies:
        log("transcript parsed but no usable text; skip capture")
        return None

    stamp = datetime.now().strftime("%H:%M")
    lines = [
        "",
        f"## 会话片段 {stamp}（自动落盘，待补充结论）",
        "",
        f"{MARKER_PREFIX}{session_id or 'unknown'} -->",
        "",
    ]
    if prompts:
        lines.append("- 用户提问：")
        lines += [f"  - {p}" for p in prompts[-MAX_PROMPTS:]]
    if replies:
        lines.append("- 助手输出（节选）：")
        lines += [f"  - {r}" for r in replies[-MAX_ASSISTANT:]]
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if "--selftest" in sys.argv:
        selftest()

    if os.environ.get("MEMSEARCH_CAPTURE", "1").strip() == "0":
        log("MEMSEARCH_CAPTURE=0, skip")
        emit({})

    payload = read_payload()
    if str(payload.get("hook_event_name") or "Stop") not in ("Stop", "SessionEnd", "SubagentStop"):
        # 被误接到其它事件上时安静退出
        emit({})

    root = find_repo_root(payload)
    session_id = str(payload.get("session_id") or "unknown")
    target = today_file(root)

    if already_recorded(target, session_id):
        log(f"session {session_id} already recorded; skip")
        emit({})

    section = build_section(root, payload)
    if section is None:
        emit({})

    try:
        memory_dir(root).mkdir(parents=True, exist_ok=True)
        header = "" if target.exists() else f"# {datetime.now().strftime('%Y-%m-%d')}\n"
        with open(target, "a", encoding="utf-8", newline="\n") as fh:
            if header:
                fh.write(header)
            fh.write(section)
        log(f"appended session fragment to {target}")
    except Exception as exc:
        log(f"append failed: {exc}")
        emit({})

    code, out = run_memsearch(["index", str(memory_dir(root))], root, timeout=75)
    log(f"index -> {code}: {out.splitlines()[-1] if out else ''}")
    emit({})


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # 兜底：绝不把异常抛回 hook 层
        log(f"unexpected error: {exc}")
        sys.stdout.write("{}")
        sys.exit(0)
