#!/usr/bin/env python
"""任务账本状态机：唯一允许写 TaskRegister.md 的程序。

用法（在工作区根执行）：
    python .agents/scripts/task_queue.py <命令> [参数]

命令：
    stats                        队列统计
    pick [--size N]              取一批（P0/P1 单条，P2 凑同模块）
    claim T-01 [--owner X]       领租约（已被别人领 → 退出码 3）
    release T-01 [--note ...]    放掉租约，attempts 保留
    done T-01 [--note ...] [--evidence ...]   关闭：移到 §2
    park T-01 [--reason ...]     挂起：移到 §3（同时放租约）
    row T-01                     打印单条
    context T-01,T-02            打印多条 + 证据段（给 worker 的载荷）
    add --symptom ... --evidence ... --priority P1 --module ai [--fix ...] [--verify ...]
    delete T-01 --yes            从账本删除（仅用于误建条目）
    stale [--hours N]            列出超时租约
    check                        校验账本与状态文件的一致性

退出码：0 正常，2 用法错误，3 租约冲突/条目不存在，4 一致性校验失败。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WS = Path(__file__).resolve().parents[2]
LEDGER = WS / "ai-novel-studio" / "KnowledgeBase" / "05_Plan" / "TaskRegister.md"
STATE = WS / ".agents" / "task-state.json"

SECTIONS = [
    ("## 1. 待办", "待办"),
    ("## 2. 已关闭", "已关闭"),
    ("## 3. 挂起", "挂起"),
]
HEADER = "| 编号 | 优先级 | 模块 | 现象 | 证据 | 修法 | 验证 | 状态 |"
SEP = "|---|---|---|---|---|---|---|---|"
COLS = 8
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def die(msg: str, code: int = 3):
    print(msg)
    raise SystemExit(code)


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- 账本读写


def parse_ledger() -> tuple[str, dict[str, list[str]], list[str]]:
    """返回 (前言, {编号: 单元格}, 章节顺序)。单元格 8 列。"""
    text = LEDGER.read_text(encoding="utf-8")
    lines = text.splitlines()
    prefix_lines: list[str] = []
    rows: dict[str, list[str]] = {}
    in_table_area = False

    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(title) for title, _ in SECTIONS):
            in_table_area = True
            continue
        if not in_table_area:
            prefix_lines.append(line)
            continue
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) != COLS or not re.fullmatch(r"T-\d+", cells[0]):
            continue  # 表头 / 分隔行 / 空表
        if cells[0] in rows:
            die(f"账本里有重复编号：{cells[0]}", 4)
        rows[cells[0]] = cells

    return "\n".join(prefix_lines).rstrip() + "\n", rows, [s for s, _ in SECTIONS]


def write_ledger(prefix: str, rows: dict[str, list[str]]) -> None:
    by_section: dict[str, list[list[str]]] = {name: [] for _, name in SECTIONS}
    for cells in rows.values():
        status = cells[7]
        if status.startswith("已关闭"):
            by_section["已关闭"].append(cells)
        elif status.startswith("挂起"):
            by_section["挂起"].append(cells)
        else:
            by_section["待办"].append(cells)

    out = [prefix, ""]
    for title, name in SECTIONS:
        out.append(title)
        out.append("")
        out.append(HEADER)
        out.append(SEP)
        for cells in sorted(by_section[name], key=lambda c: c[0]):
            out.append("| " + " | ".join(cells) + " |")
        out.append("")
    LEDGER.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def load_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        die(f"状态文件损坏：{STATE}", 4)


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def norm_ids(raw: str) -> list[str]:
    return [p.strip().upper() for p in raw.split(",") if p.strip()]


def show_row(cells: list[str]) -> str:
    labels = ["编号", "优先级", "模块", "现象", "证据", "修法", "验证", "状态"]
    return "\n".join(f"  {k}: {v}" for k, v in zip(labels, cells))


# ---------------------------------------------------------------- 命令


def cmd_stats(_args) -> int:
    _, rows, _ = parse_ledger()
    state = load_state()
    todo = [c for c in rows.values() if c[7].startswith("待办")]
    closed = [c for c in rows.values() if c[7].startswith("已关闭")]
    parked = [c for c in rows.values() if c[7].startswith("挂起")]
    busy = [tid for tid in state if state[tid].get("owner")]
    print(f"总计 {len(rows)}：待办 {len(todo)} / 已关闭 {len(closed)} / 挂起 {len(parked)}")
    for p in ("P0", "P1", "P2"):
        n = len([c for c in todo if c[1] == p])
        print(f"  待办 {p}: {n}")
    print(f"在办（有租约）: {len(busy)} {sorted(busy) if busy else ''}")
    return 0


def cmd_pick(args) -> int:
    _, rows, _ = parse_ledger()
    state = load_state()
    size = max(1, args.size)
    cands = [
        c
        for c in rows.values()
        if c[7].startswith("待办")
        and not state.get(c[0], {}).get("owner")
        and state.get(c[0], {}).get("attempts", 0) < 3
    ]
    if not cands:
        print("QUEUE_EMPTY")
        parked = [c[0] for c in rows.values() if c[7].startswith("挂起")]
        if parked:
            print("需人看（挂起）：" + " ".join(parked))
        return 0

    cands.sort(key=lambda c: (PRIORITY_ORDER.get(c[1], 9), c[0]))
    head = cands[0]
    batch = [head]
    if head[1] == "P2":
        same = [c for c in cands[1:] if c[1] == "P2" and c[2] == head[2]]
        batch += same[: max(0, size - 1)]

    for cells in batch:
        print(show_row(cells))
        print("")
    print("PICK " + ",".join(c[0] for c in batch))
    return 0


def cmd_claim(args) -> int:
    _, rows, _ = parse_ledger()
    tid = args.id.upper()
    if tid not in rows:
        die(f"{tid} 不在账本里", 3)
    if rows[tid][7].startswith("已关闭") or rows[tid][7].startswith("挂起"):
        die(f"{tid} 状态是「{rows[tid][7]}」，不能领", 3)
    state = load_state()
    rec = state.setdefault(tid, {"attempts": 0})
    if rec.get("owner") and rec["owner"] != args.owner:
        die(f"{tid} 已被 {rec['owner']} 占用（自 {rec.get('started', '?')}）", 3)
    rec["owner"] = args.owner
    rec["started"] = now_iso()
    rec["attempts"] = rec.get("attempts", 0) + 1
    save_state(state)
    print(f"{tid} 已领取（{args.owner}，第 {rec['attempts']} 次）")
    print(show_row(rows[tid]))
    return 0


def cmd_release(args) -> int:
    state = load_state()
    tid = args.id.upper()
    rec = state.get(tid)
    if not rec or not rec.get("owner"):
        print(f"{tid} 没有租约，无需释放")
        return 0
    rec.pop("owner", None)
    rec.pop("started", None)
    if args.note:
        rec["note"] = args.note
    save_state(state)
    print(f"{tid} 租约已释放" + (f"：{args.note}" if args.note else ""))
    return 0


def cmd_done(args) -> int:
    prefix, rows, _ = parse_ledger()
    tid = args.id.upper()
    if tid not in rows:
        die(f"{tid} 不在账本里", 3)
    cells = rows[tid]
    note = args.note or "已修复"
    cells[7] = f"已关闭 {today()} — {note}"
    if args.evidence:
        cells[6] = f"{cells[6]}；实测：{args.evidence}"
    state = load_state()
    rec = state.get(tid, {})
    rec.pop("owner", None)
    rec.pop("started", None)
    rec["closed"] = now_iso()
    state[tid] = rec
    save_state(state)
    write_ledger(prefix, rows)
    print(f"{tid} 已关闭：" + note)
    return 0


def cmd_park(args) -> int:
    prefix, rows, _ = parse_ledger()
    tid = args.id.upper()
    if tid not in rows:
        die(f"{tid} 不在账本里", 3)
    rows[tid][7] = f"挂起 — {args.reason or '未写原因'}"
    state = load_state()
    rec = state.get(tid, {})
    rec.pop("owner", None)
    rec.pop("started", None)
    rec["parked"] = now_iso()
    rec["park_reason"] = args.reason or ""
    state[tid] = rec
    save_state(state)
    write_ledger(prefix, rows)
    print(f"{tid} 已挂起：{args.reason or '未写原因'}")
    return 0


def cmd_row(args) -> int:
    _, rows, _ = parse_ledger()
    tid = args.id.upper()
    if tid not in rows:
        die(f"{tid} 不在账本里", 3)
    cells = rows[tid]
    where = "§2 已关闭" if cells[7].startswith("已关闭") else "§3 挂起" if cells[7].startswith("挂起") else "§1 待办"
    print(f"{tid} 在 {where}")
    print(show_row(cells))
    rec = load_state().get(tid)
    if rec:
        print(f"  租约: {rec.get('owner') or '无'} 尝试: {rec.get('attempts', 0)}")
    return 0


def cmd_context(args) -> int:
    _, rows, _ = parse_ledger()
    ids = norm_ids(args.ids)
    missing = [t for t in ids if t not in rows]
    if missing:
        die("不在账本里：" + ",".join(missing), 3)
    print(f"# 载荷：{len(ids)} 条\n")
    for tid in ids:
        cells = rows[tid]
        print(f"## {tid}  {cells[1]}  {cells[2]}")
        print(f"- 现象：{cells[3]}")
        print(f"- 证据点：{cells[4]}")
        print(f"- 修法：{cells[5]}")
        print(f"- 验证：{cells[6]}")
        print(f"- 状态：{cells[7]}\n")
    print("上面每个「证据点」都写明了 文件:行；只读那一段（前后 80 行内），不要整份读大文件。")
    return 0


def cmd_add(args) -> int:
    prefix, rows, _ = parse_ledger()
    nums = [int(t.split("-")[1]) for t in rows] or [0]
    tid = f"T-{max(nums) + 1:02d}"
    cells = [
        tid,
        args.priority.upper(),
        args.module,
        args.symptom,
        args.evidence,
        args.fix or "待定",
        args.verify or "待定",
        "待办",
    ]
    if any("|" in c for c in cells):
        die("单元格里不能出现竖线", 2)
    rows[tid] = cells
    write_ledger(prefix, rows)
    print(f"已新增 {tid}（{cells[1]} {cells[2]}）")
    return 0


def cmd_delete(args) -> int:
    prefix, rows, _ = parse_ledger()
    tid = args.id.upper()
    if tid not in rows:
        die(f"{tid} 不在账本里", 3)
    if not args.yes:
        die(f"删除 {tid} 需要加 --yes（关闭的任务一般不要删，挂起的更不要删）", 2)
    rows.pop(tid)
    state = load_state()
    state.pop(tid, None)
    save_state(state)
    write_ledger(prefix, rows)
    print(f"{tid} 已从账本删除")
    return 0


def cmd_stale(args) -> int:
    state = load_state()
    limit = datetime.now() - timedelta(hours=args.hours)
    found = False
    for tid, rec in sorted(state.items()):
        started = rec.get("started")
        if not rec.get("owner") or not started:
            continue
        try:
            ts = datetime.fromisoformat(started)
        except ValueError:
            continue
        if ts < limit:
            found = True
            print(f"{tid}  {rec['owner']}  自 {started}（{args.hours}h 未动）")
    if not found:
        print(f"无超过 {args.hours} 小时的租约")
    return 0


def cmd_check(_args) -> int:
    prefix, rows, _ = parse_ledger()
    problems = []
    for tid, cells in rows.items():
        if len(cells) != COLS:
            problems.append(f"{tid} 列数 {len(cells)} != {COLS}")
        if cells[1] not in PRIORITY_ORDER:
            problems.append(f"{tid} 优先级非法：{cells[1]}")
    state = load_state()
    for tid in state:
        if tid not in rows:
            problems.append(f"状态文件里的 {tid} 已不在账本里")
    if problems:
        print("一致性校验失败：")
        for p in problems:
            print("  - " + p)
        return 4
    print(f"一致性 OK：{len(rows)} 条，状态文件 {len(state)} 条")
    return 0


# ---------------------------------------------------------------- 入口


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="任务账本状态机")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats").set_defaults(func=cmd_stats)
    sub.add_parser("check").set_defaults(func=cmd_check)

    sp = sub.add_parser("pick")
    sp.add_argument("--size", type=int, default=4)
    sp.set_defaults(func=cmd_pick)

    sp = sub.add_parser("claim")
    sp.add_argument("id")
    sp.add_argument("--owner", default="worker")
    sp.set_defaults(func=cmd_claim)

    sp = sub.add_parser("release")
    sp.add_argument("id")
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_release)

    sp = sub.add_parser("done")
    sp.add_argument("id")
    sp.add_argument("--note", default="")
    sp.add_argument("--evidence", default="")
    sp.set_defaults(func=cmd_done)

    sp = sub.add_parser("park")
    sp.add_argument("id")
    sp.add_argument("--reason", default="")
    sp.set_defaults(func=cmd_park)

    sp = sub.add_parser("row")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_row)

    sp = sub.add_parser("context")
    sp.add_argument("ids")
    sp.set_defaults(func=cmd_context)

    sp = sub.add_parser("add")
    sp.add_argument("--symptom", required=True)
    sp.add_argument("--evidence", required=True)
    sp.add_argument("--priority", default="P2")
    sp.add_argument("--module", default="misc")
    sp.add_argument("--fix", default="")
    sp.add_argument("--verify", default="")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("delete")
    sp.add_argument("id")
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_delete)

    sp = sub.add_parser("stale")
    sp.add_argument("--hours", type=float, default=1.0)
    sp.set_defaults(func=cmd_stale)

    return p


def main() -> int:
    if not LEDGER.exists():
        die(f"账本不存在：{LEDGER}", 2)
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
