---
name: scan-progress
description: 知识库唯一进度真源：当前阶段、已建/待建文档、AI 接手必读、未解决问题。每次工作结束更新本页。
status: 现行（每轮更新）
---

# 进度（唯一真源）

- 最后更新：2026-11-16（知识库分区补全：新建 00_Project / 01_CodeMap / 04_BugsAndLessons / 09_Reports）
- 基线 commit：本仓库**非 git 仓库**，无法用 commit 定位；文件时间戳为准。

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

**当前状态一行**：阶段 2 P0 收口完成；待办 19（P1 13/P2 6），在办 T-30；知识库分区已补全为 8 个（除 03_ADR/08_AI_Memory 待建）。

**下一件事**：等 T-30 租约释放后跑 `/task-next` 清队列；优先修 `DefectRegister.md` 的 DEF-01/02/03（摘要泄漏/回填不全/降级空内容）。

**口径与纪律**：
1. 文档与代码不符 → 改文档（代码为准），冲突登记到本页 §4。
2. 新增结论带 `文件:行` 或「命令+输出」；推断标 △，不确定标 ❓。
3. 缺陷只写 `DefectRegister.md`（DEF-xx）；事实型文档最多留 `→ DEF-xx`。
4. 未实现功能写 T-xx，不写 DEF。
5. 改文件前先 `read_file`（非 git + 并行改动，见 `Lessons.md` L-06）。

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

## §3 验证基线（2026-11-16 实测，唯一权威）

| 命令 | 实测 | 旧文档冲突 |
|---|---|---|
| pytest -q（backend） | **104 passed** | CurrentStatus 96 / INDEX 60 / README 60 |
| pnpm test（desktop） | **36 passed (5 文件)** | AGENTS 29 / INDEX 29 / CurrentStatus 32 / README 349 写 29、384 写 25 |
| pnpm typecheck | 干净 | — |
| smoke_api / smoke_ai / cargo check | 本次未跑 | — |

> 待办：统一 `AGENTS.md`、`CODEBUDDY.md`、`INDEX.md`、`CurrentStatus.md`、`README.md` 的数字（改约定须 AGENTS+CODEBUDDY 两边一起改）。

## §4 未解决问题 / 冲突登记

| # | 问题 | 证据 | 处理 |
|---|---|---|---|
| 1 | 验证数字三处以上不一致 | §3 | 已记本页；待统一各方文档 |
| 2 | T-30 租约在办（17:10:27），task-next 硬停 | `.agents/task-state.json` | 等释放或确认后 release |
| 3 | 账本部分条目标"待办"但代码已实现（T-30 流式、T-34 reset、T-35） | `TaskPitfalls.md` + 取证 | t-next 分诊时按 false-positive 复核/park |
| 4 | TaskPitfalls 部分 `文件:行` 路径写错（写成 `app/ai/services/`，真实 `app/services/`） | 本次取证 | 已在 DefectRegister/Lessons 用正确路径；TaskPitfalls 待订正 |
| 5 | T-22/T-23 设计取舍缺独立 ADR | 03_ADR 待建 | 补 ADR 时从 TaskRegister 迁入 |
