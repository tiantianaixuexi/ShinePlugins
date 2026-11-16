#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UserPromptSubmit hook：按用户提问从记忆里召回 top-N，作为 systemMessage 注入。

**默认关闭**：设 MEMSEARCH_RECALL_ON_PROMPT=1 才生效。
理由：每次提问都注入会稳定消耗上下文，且召回不准时会误导；建议在"确实需要跨会话回忆"
的场景临时开启，或直接让 agent 用 /memory-recall 手动查。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import emit, find_repo_root, log, read_payload, run_memsearch  # noqa: E402

# 实测（两个语料都测过）：
#   · 3 chunk 的记忆库：强命中 0.98~1.0000，无关 0.48~0.50
#   · 332 chunk 的知识库：命中 0.5000 / 0.4919 / 0.4841 三档反复出现，
#     而**无关提问**（"今天晚饭吃什么"）同样能拿到 0.5000 —— 几乎相同的分数。
# 结论：score 是分桶的，只能区分"强命中（≈1.0）"与"其它"，**无法区分相关与无关**。
# 所以自动注入只在强命中时发生（宁缺勿错）；其它情况交给 /memory-recall 人工核对。
MIN_SCORE = 0.85
NEAR_TOP = 0.02
MAX_HITS = 3
MAX_TOKENS_CHARS = 700


def main() -> None:
    if os.environ.get("MEMSEARCH_RECALL_ON_PROMPT", "0").strip() != "1":
        emit({})

    payload = read_payload()
    prompt = str(payload.get("user_prompt") or payload.get("prompt") or "").strip()
    if len(prompt) < 6 or prompt.startswith("/"):
        emit({})

    root = find_repo_root(payload)
    code, out = run_memsearch(
        ["search", prompt, "-k", "5", "--json-output"], root, timeout=25
    )
    if code != 0 or not out:
        log(f"search failed: {out[:200] if out else 'empty'}")
        emit({})

    try:
        hits = json.loads(out[out.index("[") :])
    except Exception as exc:
        log(f"cannot parse search output: {exc}")
        emit({})

    if not isinstance(hits, list) or not hits:
        emit({})

    top_score = max(float(h.get("score") or 0.0) for h in hits if isinstance(h, dict))
    if top_score < MIN_SCORE:
        emit({})

    picked = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        score = float(h.get("score") or 0.0)
        if score >= MIN_SCORE and score >= top_score - NEAR_TOP:
            picked.append(h)
        if len(picked) >= MAX_HITS:
            break

    if not picked:
        emit({})

    lines = ["项目记忆命中（memsearch 语义检索，仅作线索，不要当事实断言）："]
    for idx, h in enumerate(picked, 1):
        source = str(h.get("source") or "").replace("\\", "/")
        heading = str(h.get("heading") or "").strip()
        body = " ".join(str(h.get("content") or "").split())
        local = source.split("/.memsearch/memory/")[-1] if "/.memsearch/memory/" in source else source
        lines.append(f"{idx}. {local} > {heading}：{body[:180]}")
        lines.append(f"   （可 `memsearch expand {h.get('chunk_hash', '')}` 看全文）")

    message = "\n".join(lines)[:MAX_TOKENS_CHARS]
    emit({"systemMessage": message})


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # 兜底：任何异常都不能阻塞用户提问
        log(f"unexpected error: {exc}")
        sys.stdout.write("{}")
        sys.exit(0)
