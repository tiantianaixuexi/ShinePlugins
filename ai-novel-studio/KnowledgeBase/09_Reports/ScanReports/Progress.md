---
name: scan-progress
description: 知识库唯一进度真源：当前阶段、已建/待建文档、AI 接手必读、未解决问题。每次工作结束更新本页。
status: 现行（每轮更新）
---

# 进度（唯一真源）

- 最后更新：2026-11-16 18:16（同步另一会话推进后的账本与基线：T-30/31/34/35/36/37 已关闭，T-33 在办；基线 pytest 117 / pnpm 37）
- 基线 commit：`21d5595`（2026-11-16 17:47，main...origin/main）。**本仓库是 git 仓库**，根在 `e:\ShinePlugins`，开工/收尾用 `git status`/`git log` 核对他人改动。

## §0 AI 接手须知（每次开工先读）

**必读顺序（只读这几页，不要全库 grep）**

| 顺序 | 文件 | 为什么 |
|---|---|---|
| 1 | `../../INDEX.md` | 唯一入口、硬规则、验证表 |
| 2 | `../../05_Plan/CurrentStatus.md` | 一句话现状（注意：数字旧，见 §3） |
| 3 | `../../05_Plan/CurrentMilestone.md` | 当前里程碑与验收判据 |
| 4 | 本页 §0–§4 | 覆盖口径 + 当前状态 + 未解决问题 |
| 5 | `../../05_Plan/TaskRegister.md`（用 `task_queue.py row/pick`，不读全文） | 待办真源 |
| 6 | 只在要改某模块时读对应 `01_CodeMap/` 清单 + `02_Modules` | — |

**当前状态一行**（截至 2026-11-16 18:16，队列数字是流动快照，实时值跑 `task_queue.py stats`）：总计 37 / 待办 16（P1 10 / P2 6）/ 已关闭 21；在办 T-33。阶段 3 RAG、阶段 4 工作流未开工。知识库分区已补全（除 03_ADR/08_AI_Memory 待建）。

**下一件事**：T-33 租约在办，task-next 会硬停；等其释放后跑 `/task-next` 清剩余待办。`DefectRegister.md` 待修只剩 DEF-01（摘要泄漏未来章 = T-33，正在进行）、DEF-02（摘要回填不全 = T-12）；DEF-03 已随 T-35 关闭。

**口径与纪律**：
1. 文档与代码不符 → 改文档（代码为准），冲突登记到本页 §4。
2. 新增结论带 `文件:行` 或「命令+输出」；推断标 △，不确定标 ❓。
3. 缺陷只写 `DefectRegister.md`（DEF-xx）；事实型文档最多留 `→ DEF-xx`。
4. 未实现功能写 T-xx，不写 DEF。
5. 改文件前先 `read_file` + 开工前 `git status`（并行会话改同一文件，见 `Lessons.md` L-06）。

## §1 阶段状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| 阶段 1 基础 | 完成 | 编辑器链路、模型配置、迁移执行器 |
| 阶段 2 收口 | P0 完成，P1 进行中 | AI 层已落地；记忆/血缘已补；剩余 P1 见 TaskRegister |
| 阶段 3 RAG | 未开工 | T-11，`docs/rag.md` 设计完成 |
| 阶段 4 工作流 | 未开工 | T-19，`docs/workflow.md` 设计完成 |

## §2 知识库文档覆盖

| 分区 | 状态 | 文件数 |
|---|---|---|
| `INDEX.md` | ✅ 现行 | 1 |
| `00_Project/` | ✅ 本次新建 | 4（ProjectOverview / RepositoryMap / BuildAndEnvironment / ThirdPartyDependencies） |
| `01_CodeMap/` | ✅ 本次新建 | 6（README / 01-map / 02-lifecycle / 10/11/12-files） |
| `02_Modules/` | ⬜ 待建（小项目不照搬引擎的逐行模块文档） | 0 |
| `03_ADR/` | ⬜ 待建 | 0 |
| `04_BugsAndLessons/` | ✅ 本次新建 | 3（README / DefectRegister / Lessons） |
| `05_Plan/` | ✅ 现行 | 8（含本次新建 TaskPitfalls） |
| `09_Reports/ScanReports/` | ✅ 本次新建 | 2（本页 / InitialScan） |

## §3 验证基线（2026-11-16 18:16 实测，唯一权威）

| 命令 | 实测 | 命令细节 |
|---|---|---|
| pytest（backend） | **117 passed in 55.45s** | `python -m pytest -o addopts='' -q --tb=no`（叠加 -q 会静默到无汇总行） |
| pnpm test（desktop） | **37 passed (5 文件)**：utils 14 · ai 10 · text-edit 6 · api 4 · sidecar 3 | `pnpm test` |
| pnpm typecheck | 干净（`tsc --noEmit` 无输出） | `pnpm typecheck` |
| smoke_api / smoke_ai / cargo check | 本轮未跑 | 另一会话 T-36 验证栏记 smoke_api PASSED、smoke_ai PASSED（真实模型） |

> **数字持续变化**：另一会话仍在推进（T-33 在办），测例随任务增加。本页是快照；改约定类文档（`AGENTS.md`/`CODEBUDDY.md`）需两边一起改，当前其期望值（pytest 全绿 / pnpm 29）仍是旧描述，但"全绿/无输出"的判据未变。

## §4 未解决问题 / 冲突登记

| # | 问题 | 证据 | 处理 |
|---|---|---|---|
| 1 | 验证数字多方不一致（本页 117/37；CurrentStatus 96/32；INDEX 60→已同步为实测；README 多处旧值） | §3 | 已记本页为权威；改数字类文档按需同步，约定类（AGENTS/CODEBUDDY）判据是"全绿"不需改数 |
| 2 | T-33 租约在办（18:10:03），task-next 会硬停 | `.agents/task-state.json` | 等释放后跑 `/task-next` |
| 3 | 原"待办却已实现"项已消解：T-30/34/35 均已关闭 | `TaskRegister.md` 已关闭区 | 无需 park；TaskPitfalls 订正横幅已标注 |
| 4 | TaskPitfalls 部分 `文件:行` 路径写错（写成 `app/ai/services/`，真实 `app/services/`） | 本次取证 | 已加订正横幅；DefectRegister/Lessons 用正确路径 |
| 5 | T-22/T-23 设计取舍缺独立 ADR | 03_ADR 待建 | 补 ADR 时从 TaskRegister 迁入 |
