---
name: plan-layer
description: 计划层入口与约定。进度总表、当前里程碑、技术债、路线图、交接文档都放这里；任务账本 TaskRegister.md 也从这里进。
status: 现行
---

# 计划层（`05_Plan/`）

回答四类问题：**现在到哪一步了 / 下一步做什么 / 欠了什么账 / 谁依赖谁**。

## 目录

| 文件 | 内容 | 谁维护 |
|---|---|---|
| [`CurrentStatus.md`](CurrentStatus.md) | 实现状态总表（按子系统），每行带证据 | 人 + agent，改代码后同步 |
| [`CurrentMilestone.md`](CurrentMilestone.md) | 当前里程碑与验收判据 | 人 |
| [`TaskRegister.md`](TaskRegister.md) | **任务唯一真源**（`T-xx`）。只允许 `task_queue.py` 写 | 脚本 |
| [`TechnicalDebt.md`](TechnicalDebt.md) | 技术债视图，条目引用 `T-xx`，不重复描述 | 人 |
| [`Roadmap.md`](Roadmap.md) | 7 阶段路线，只写已确定方向 | 人 |
| [`handoffs/`](handoffs/) | 交接文档：换人/换会话时的现状快照 + 待办 | 写一次不改 |

## 什么**不**放这里

- **工程事实**（代码在哪、接口怎么定、表结构）→ `../INDEX.md` 与 `../../docs/`。
- **决策与踩坑的过程**（"为什么当时这么选"）→ `.memsearch/memory/`。
- **已完成且不再变化的一次性产物** → `docs/archive/<年-月>/`，标注"历史快照，非现状"。

判据：**"这份东西还会被改动吗？"** 会 → 计划层；不会 → archive。

## 状态取值（全层统一，禁用别的说法）

| 状态 | 含义 | 必填 |
|---|---|---|
| 已实现 | 代码存在且被测试或实际运行验证过 | 证据指针（`文件:行` 或测试名） |
| 部分实现 | 主路径可用，但有明确缺口 | 缺口的**具体**描述 |
| 未实现 | 只有设计/只有表/没有代码 | 计划落点（哪个文件） |
| 存在缺陷 | 可用但有已知 bug | 复现条件 + 影响面 |
| 已废弃 | 曾计划或曾实现，现已放弃 | 放弃原因 |
| 待确认 | 无法判断（缺证据/缺决策人） | 缺什么才能确定 |

禁止把"推断"写成"已实现"。状态与证据不符时**以代码为准**，改本层。

## 三条维护规则

1. **完成即迁出**：任务关闭后，把工程事实写进 `INDEX.md` 或 `docs/`，本层只留一行"已完成 + 指针"。
2. **一项一条**：`TaskRegister.md` 一条一行，带证据与验证方式；`TechnicalDebt.md` 一条债一行，只引用 `T-xx`。
3. **交接不改历史**：`handoffs/` 下的文档是快照，只在顶部加"后续进展"横幅，不改正文。

## 与任务账本的关系

`TaskRegister.md` 由 `.agents/scripts/task_queue.py` 读写（`pick`/`claim`/`done`/`park`/`release`）。
**手改会与脚本状态不一致**（`.agents/task-state.json` 存租约），要加任务用 `task_queue.py add`。
