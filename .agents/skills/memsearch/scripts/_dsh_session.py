#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""DSH（DeepSeek Harness）会话日志读取：定位 → 解压 → 版本检查 → 轮次抽取。

为什么需要它（DEF-252）：
  · CodeBuddy 的 Stop payload 里 `transcript_path` 指向**明文 JSONL**；
  · DSH 侧 `@deepseek-ai/dsh-hooks-claude-code` 桥构造的 payload 只有
    `{session_id, transcript_path, cwd, hook_event_name}`（rc.5
    `lib/index.js:350-357` `base()`，`:387-392` `stopPayload()` 追加
    `stop_hook_active`），其中 `transcript_path` 取
    `ctx.get("sessionPersistence")?.locate(header)?.path ?? ""`——
    拿不到就是**空串**；即便拿到了，也指向下面这种 zstd 日志，不是明文 JSONL。
    旧 capture.py 只认明文 JSONL，于是 DSH 会话**一条都不落盘**。

日志布局（实测 DSH 0.0.1-rc / 会话格式 v4，2026-11-16）：
    ~/.dsh/sessions/<工作区目录>/<sessionId>/session.v4.jsonl.zstd
  · 工作区目录名是把 cwd 里的 `:` `\` 变成 `-`、其余特殊字符 `~XXXX` 转义后的形式
    （`E:\\c++\\ShineEngine` → `--E-c~002B~002B-ShineEngine--`）；本模块**不去猜
    编码规则**，直接按 sessionId 扫 `~/.dsh/sessions/*/`，命中即可。
  · 一个 zstd 文件由**很多个带校验的 frame 首尾相接**（一次 append 一个 frame，
    实测 479 KB 里有 455 个 frame），读取必须**跨 frame**；
    会话正在写时尾部可能是只写了一半的 frame —— 解压要能容忍并保留已解出的部分。

解压后的 JSONL（每行一个事件）：
    {"type":"session","version":4,"id":"<uuid>","createdAt":...,"cwd":"..."}   ← 首行，格式版本在这里
    {"type":"user/message","seq":9,"data":{"content":[{"type":"text","text":"..."}]}}
    {"type":"assistant/message","seq":17,"data":{"message":{"role":"assistant",
          "content":[{"type":"text","text":"..."},{"type":"tool-call",...}]}}}
    {"type":"tool/call"|"tool/result"|"step/start"|"step/end"|"turn/start"|...} ← 落盘时全部丢弃

约束（与 `_common.py` 一致）：
  · 只用标准库；`zstandard` 不在就退回 `zstd` CLI；两者都没有**不抛异常**，
    返回 None 让调用方打印可读警告并跳过（hook 必须永远 exit 0）。
  · 版本不认识（≠ v4）时**不崩**，打印可读警告后跳过。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from _common import BOM, decode_bytes, log

# 本脚本认识的会话日志格式版本；遇到别的版本只警告、不猜。
KNOWN_SESSION_FORMAT_VERSION = 4

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"  # zstd frame magic
_READ_CHUNK = 1 << 16
# 扫 ~/.dsh/sessions/*/ 的上限：正常只有个位数量级的工作区目录。
_MAX_WORKSPACE_DIRS = 2000
_CLI_TIMEOUT_S = 60


# --------------------------------------------------------------------- zstd

def is_zstd_file(path) -> bool:
    """按 magic 判断是不是 zstd 容器（不看扩展名）。"""
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == ZSTD_MAGIC
    except OSError:
        return False


def _decompress_zstd(blob: bytes) -> bytes | None:
    """解压（支持多 frame 与尾部截断）。没有可用解压器时返回 None。"""
    try:
        import zstandard  # type: ignore
    except Exception:
        zstandard = None

    if zstandard is not None:
        import io

        out = bytearray()
        reader = None
        try:
            # read_across_frames：一个文件里 N 个 frame 要当一条流读
            reader = zstandard.ZstdDecompressor().stream_reader(
                io.BytesIO(blob), read_across_frames=True
            )
            while True:
                chunk = reader.read(_READ_CHUNK)
                if not chunk:
                    break
                out += chunk
        except Exception as exc:
            if not out:
                log(f"zstandard 解压失败: {exc}")
                return None
            # 会话还在写、尾部 frame 不完整 —— 已解出的部分仍然可用
            log(f"zstandard 解压中断（会话可能还在写）：{exc}")
        finally:
            try:
                if reader is not None:
                    reader.close()
            except Exception:
                pass
        return bytes(out)

    try:  # Python 3.14+ 自带 compression.zstd
        from compression import zstd as _zstd  # type: ignore

        return _zstd.decompress(blob)
    except Exception:
        pass
    return None


def _decompress_with_cli(path: Path) -> bytes | None:
    """退路：调 PATH 上的 `zstd` CLI。仍然失败就返回 None（不抛）。"""
    exe = shutil.which("zstd")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-q", "-d", "-c", str(path)],
            capture_output=True,
            timeout=_CLI_TIMEOUT_S,
        )
    except Exception as exc:
        log(f"zstd CLI 调用失败: {exc}")
        return None
    if proc.returncode != 0:
        log(f"zstd CLI 解压失败(exit {proc.returncode}): {decode_bytes(proc.stderr)[:200]}")
    return proc.stdout or None


def _read_log_bytes(path: Path) -> bytes | None:
    try:
        blob = path.read_bytes()
    except OSError as exc:
        log(f"读不到会话日志 {path}: {exc}")
        return None
    if not blob:
        log(f"会话日志是空的: {path}")
        return None
    if blob[:4] != ZSTD_MAGIC:
        log(f"会话日志不是 zstd 容器（magic {blob[:4].hex()}）: {path}")
        return None
    data = _decompress_zstd(blob)
    if data is None:
        data = _decompress_with_cli(path)
    if data is None:
        log("缺少 zstd 解压能力（`zstandard` 不可用且 PATH 上没有 `zstd`），已跳过自动落盘")
    return data


# ------------------------------------------------------------------ 定位

def dsh_home() -> Path | None:
    """DSH 家目录：`DSH_HOME` 覆盖 > `~/.dsh`（与 dsh-home-paths 同口径）。"""
    env = os.environ.get("DSH_HOME", "").strip()
    home = Path(env).expanduser() if env else Path.home() / ".dsh"
    try:
        return home if home.is_dir() else None
    except OSError:
        return None


def find_session_file(session_id: str, cwd: str = "") -> Path | None:
    """按 sessionId 在 `~/.dsh/sessions/*/<sessionId>/` 下找会话日志。

    不做工作区目录名的编码/解码（那属于 DSH 内部实现，会随版本变）：直接扫一层
    工作区目录，命中 sessionId 就返回。多个命中时取最新的那个。
    """
    if not session_id:
        return None
    home = dsh_home()
    if home is None:
        env = os.environ.get("DSH_HOME", "").strip()
        log(f"找不到 DSH 家目录（DSH_HOME={env or '未设置'}，也没有 ~/.dsh）")
        return None
    root = home / "sessions"
    if not root.is_dir():
        log(f"找不到 DSH 会话目录: {root}")
        return None

    try:
        with os.scandir(root) as it:
            workspaces = [entry.path for entry in it if entry.is_dir()]
    except OSError as exc:
        log(f"扫 DSH 会话目录失败 {root}: {exc}")
        return None
    if len(workspaces) > _MAX_WORKSPACE_DIRS:
        log(f"DSH 工作区目录过多（{len(workspaces)}），只扫前 {_MAX_WORKSPACE_DIRS} 个")

    matches: list[Path] = []
    for ws in workspaces[:_MAX_WORKSPACE_DIRS]:
        cand = Path(ws) / session_id
        try:
            if not cand.is_dir():
                continue
            matches += sorted(cand.glob("session.v*.jsonl.zstd"))
        except OSError:
            continue
    if not matches:
        log(f"DSH 会话目录里没有 {session_id} 的日志（cwd={cwd or '未提供'}）")
        return None
    # 同 id 理论上只有一个；保险起见取最新的
    matches.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return matches[0]


# ------------------------------------------------------------------ 解析

def _text_blocks(content) -> str:
    """只取 `{"type":"text"}` 块（工具调用/thinking 一律丢弃）。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


# DSH 会把一批**不是人打的字**也记成 `user/message`（时钟、子代理完成通知、
# 运行时上下文、审批策略变更…）。这些进记忆只会淹掉真正的提问，落盘前剔掉。
_INJECTED_PREFIXES = (
    "Time sampled while preparing turn",
    "Background subagent ",
    "Current runtime context.",
    "[model changed:",
    "The user changed the approval policy",
    "Caveat: The messages below were generated",
)
_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)


def _clean_injected(text: str) -> str:
    """去掉 `<system-reminder>…</system-reminder>` 注入块；剩下的才是人说的话。"""
    return _REMINDER_RE.sub("", text).strip()


def _is_injected(text: str) -> bool:
    head = text.lstrip()
    return any(head.startswith(prefix) for prefix in _INJECTED_PREFIXES)


def load_session(path) -> dict | None:
    """读一个 DSH 会话日志 → `{'version', 'id', 'cwd', 'events'}`。

    任何失败（读不到 / 不是 zstd / 没解压器 / 版本不认识）都**返回 None**，
    并留下一条可读的 stderr 日志 —— 绝不抛异常。
    """
    data = _read_log_bytes(Path(path))
    if data is None:
        return None

    header: dict | None = None
    events: list[dict] = []
    bad = 0
    for line in data.decode("utf-8", errors="replace").splitlines():
        line = line.strip().lstrip(BOM)
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            bad += 1
            continue
        if not isinstance(obj, dict):
            bad += 1
            continue
        if header is None and obj.get("type") == "session":
            header = obj
            continue
        events.append(obj)

    if header is None:
        log(f"{path}: 没找到 `session` 头，不像 DSH 会话日志，已跳过")
        return None

    version = header.get("version")
    if version != KNOWN_SESSION_FORMAT_VERSION:
        log(
            f"不支持的 DSH 会话格式版本 v{version}（本脚本只认 "
            f"v{KNOWN_SESSION_FORMAT_VERSION}），已跳过自动落盘：{path}"
        )
        return None
    if bad:
        log(f"{path}: 有 {bad} 行无法解析（多为会话正在写时的半条记录），已跳过")

    return {
        "version": version,
        "id": str(header.get("id") or ""),
        "cwd": str(header.get("cwd") or ""),
        "events": events,
    }


def iter_turns(events):
    """按日志顺序产出 (role, text)，role ∈ {'user', 'assistant'}；工具调用已丢弃。

    DSH 注入的"伪用户消息"（时钟/子代理通知/运行时上下文/system-reminder）会被跳过。
    """
    for event in events:
        etype = str(event.get("type") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if etype == "user/message":
            text = _text_blocks(data.get("content"))
            role = "user"
        elif etype == "assistant/message":
            message = data.get("message") if isinstance(data.get("message"), dict) else {}
            text = _text_blocks(message.get("content"))
            role = "assistant"
        else:
            continue
        text = _clean_injected(text)
        if not text.strip() or _is_injected(text):
            continue
        yield role, text