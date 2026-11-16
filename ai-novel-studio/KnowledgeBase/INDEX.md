---
name: novel-studio-kb-index
description: AI Novel Studio 工程知识库唯一入口。找代码/文件、查 API/表字段、查项目基线与依赖、判断进度、查缺陷与验证命令，全从本页进。回答「某功能在哪个文件」应直接查本库，不要先派子代理扫仓库。
status: 现行（本页随代码更新）
---

# AI Novel Studio 工程知识库 · 总入口

Tauri 2 + React 19 桌面端，FastAPI + SQLite sidecar。仓库根 `ai-novel-studio/`。

> 本页是**唯一入口**。`docs/` 是详版层（长文、字段全表），本库是导航层。

## 分区

| 分区 | 内容 | 状态 |
|---|---|---|
| 本页 | 我该读哪几页 | ✅ |
| [`00_Project/`](00_Project/ProjectOverview.md) | 客观基线：项目概览 / 仓库地图 / 构建环境 / 第三方依赖 | ✅ 4 篇 |
| [`01_CodeMap/`](01_CodeMap/README.md) | 代码导航：目录→职责→文件级清单（backend 56 / desktop 62 / tauri 7）+ 调用链 | ✅ 6 篇 |
| `02_Modules/` | 逐模块边界与坑 | ⬜ 待建（小项目不照搬引擎级逐行文档） |
| `03_ADR/` | 设计决策记录（当前取舍暂记 `05_Plan/` 与 `docs/`） | ⬜ 待建 |
| [`04_BugsAndLessons/`](04_BugsAndLessons/README.md) | 缺陷唯一真源 `DefectRegister.md`（DEF-xx）+ `Lessons.md` | ✅ 3 篇 |
| [`05_Plan/`](05_Plan/README.md) | **进度层**：CurrentStatus / CurrentMilestone / TechnicalDebt / Roadmap / TaskRegister / TaskPitfalls / handoffs | ✅ |
| [`../docs/`](../docs/) | 详版层：架构 / API / 数据库 / RAG / 工作流 / 开发计划 | ✅ 7 篇 |
| [`09_Reports/ScanReports/`](09_Reports/ScanReports/Progress.md) | **进度唯一真源** `Progress.md` + 初始扫描报告 | ✅ 2 篇 |

## 详版层：现在有什么

| 你想知道 | 打开 |
|---|---|
| 39 个已实现端点的契约、错误信封、未实现端点 | [api.md](../docs/api.md) |
| 35 张表字段、迁移策略、软删除、级联 | [database.md](../docs/database.md) |
| 分层、sidecar 生命周期、数据目录 | [architecture.md](../docs/architecture.md) |
| 7 阶段计划、验收判据、风险表、版本范围 | [development-plan.md](../docs/development-plan.md)（2026-11-16 已按代码重写：阶段 2 拆 2a/2b，含 AI 层已实现清单） |
| **原计划 23 节 × 代码现状逐节对账 + 补全建议 + 修正后的阶段计划** | [plan-reconciliation.md](../docs/plan-reconciliation.md) |
| L0–L4 分层记忆、混合检索、token 预算（**设计完成，未实现**） | [rag.md](../docs/rag.md) |
| React Flow 编辑 vs Python 执行、状态机、断点续跑（**设计完成，未实现**） | [workflow.md](../docs/workflow.md) |
| 怎么跑起来、脚本清单、目录结构 | [README.md](../README.md) |

## 代码落点（先看这里，别扫仓库）

| 要找 | 去哪 |
|---|---|
| HTTP 路由 | `backend/app/api/routes/`（health / projects / novels / model_configs / ai / system） |
| 业务逻辑 | `backend/app/services/`（project_service / novel_service / model_config_service / ai_service） |
| AI 适配器 | `backend/app/ai/llm/`（`openai_compatible.py` 是唯一适配器，不按厂商分派） |
| Prompt 模板 | `backend/app/ai/prompts/`（内置 7 套，播种进 `prompt_templates`，数据库优先） |
| 表结构 | `backend/app/models/`（`studio.py` 全局 8 表 · `novel.py` 项目 27 表） |
| 迁移执行器 | `backend/app/db/migrations.py`（拒绝降级 + 迁移前在线备份 + 单事务） |
| 密钥存储 | `backend/app/core/keystore.py`（Windows DPAPI，密钥只写不回显） |
| sidecar 拉起 | `desktop/src-tauri/src/sidecar.rs`（动态端口 + 令牌 + 日志泵） |
| 编辑器组件 | `desktop/src/components/editor/`（`chapter-editor` + `ai-panel`；正文有意用 `<textarea>`，理由见 development-plan.md §3.3） |
| 前端 HTTP 客户端 | `desktop/src/lib/api.ts`（502/504/网络失败 → `backend_unreachable`） |
| AI 流式解析 | `desktop/src/lib/ai.ts`（`EventSource` 不能 POST，自行解析 SSE） |
| 字数算法（两侧镜像） | `backend/app/utils/text.py::count_words` ↔ `desktop/src/lib/utils.ts::countWords` |

## 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| 保存模型 / 生成时报 `HTTP 502` | 浏览器开发时 Vite 代理返回**纯文本 502**，说明 **Python 后端没在跑**（不是模型的问题） | 先起后端：`scripts\dev.ps1`（同时起前后端）；桌面端用 `pnpm tauri dev`，Rust 会自动拉起 sidecar |
| 浏览器开发时 401 | `desktop/.env` 缺失或 token 与后端不一致 | `scripts\dev.ps1` 首次运行会按 `.env.example` 生成 `.env`（token `dev-token`） |
| 桌面端启动时 Vite 报 `ECONNREFUSED 127.0.0.1:8765` | 前端把 sidecar 未就绪时的 `stopped` 空地址缓存下来，请求落回 Vite 代理（固定 8765）；sidecar 实际用动态端口 | 已修复：`desktop/src/lib/sidecar.ts` 轮询 `get_sidecar_info` 到 `ready` 才缓存 |
| 桌面端跨端口 `/api/*` 预检返回 401 | `TokenMiddleware` 曾拦截无凭据的 `OPTIONS`，`CORSMiddleware` 没机会回应 | 已修复：`backend/app/main.py` 放行 `OPTIONS`；真实请求仍需 token |

## 进度与任务（别凭记忆答"做完没有"）

| 想知道 | 打开 |
|---|---|
| 某功能到底做完没有（带证据） | [05_Plan/CurrentStatus.md](05_Plan/CurrentStatus.md) |
| 下一步做什么、做到什么算完 | [05_Plan/CurrentMilestone.md](05_Plan/CurrentMilestone.md) |
| 有哪些任务待办 | [05_Plan/TaskRegister.md](05_Plan/TaskRegister.md)（**只允许 `.agents/scripts/task_queue.py` 写**） |
| 待修复的坑及修复去向（每条坑→`T-xx`，修完即关闭） | [05_Plan/TaskPitfalls.md](05_Plan/TaskPitfalls.md)（每条带 `文件:行` 证据，行号动手前复核） |
| 欠了什么账 | [05_Plan/TechnicalDebt.md](05_Plan/TechnicalDebt.md) |
| 各阶段状态与版本范围 | [05_Plan/Roadmap.md](05_Plan/Roadmap.md) |
| 缺陷（代码写错）与历史踩坑 | [04_BugsAndLessons/DefectRegister.md](04_BugsAndLessons/DefectRegister.md) · [Lessons.md](04_BugsAndLessons/Lessons.md) |
| 构建/环境/依赖/仓库地图 | [00_Project/](00_Project/ProjectOverview.md) |
| 某功能/某文件在哪、一次操作怎么走 | [01_CodeMap/](01_CodeMap/README.md) |
| 知识库进度真源、AI 接手必读顺序 | [09_Reports/ScanReports/Progress.md](09_Reports/ScanReports/Progress.md) |

任务驱动开发：`/task-next`（流程见 `.agents/skills/task-next/SKILL.md`）会循环「取批 → 分诊 → 派 worker → 核对」，
状态存在 `.agents/task-state.json`，换会话可续跑。

## 验证（改完必须跑）

| 命令（cwd） | 期望（2026-11-16 实测） |
|---|---|
| `backend\.venv\Scripts\python.exe -m pytest`（backend） | `117 passed`（用 `-o addopts='' -q --tb=no` 取汇总；叠加 -q 无汇总行） |
| `backend\.venv\Scripts\python.exe scripts\smoke_api.py`（仓库根） | `SMOKE PASSED: all checks green`（27 项） |
| `backend\.venv\Scripts\python.exe scripts\smoke_ai.py --from-store`（仓库根） | `AI SMOKE PASSED`（需已配置的模型） |
| `pnpm test`（desktop） | `37 passed (5 文件)`：utils 14 · ai 10 · text-edit 6 · api 4 · sidecar 3 |
| `pnpm typecheck`（desktop） | 无输出（`tsc --noEmit` 干净） |
| `pnpm build`（desktop） | `✓ built`，产出 `dist/` |
| `cargo check`（desktop/src-tauri） | `Finished`，无 error |

> **权威数字只在 [`09_Reports/ScanReports/Progress.md` §3](09_Reports/ScanReports/Progress.md) 维护**——数字随任务推进持续变化，本表是 2026-11-16 18:16 快照。改约定类文档（AGENTS/CODEBUDDY）判据写"全绿/无输出"，不含具体数字。

## 三条规则

1. 动手前先查本页与对应详版页。文档与代码不符 → **改文档**（以代码为准），并把冲突记进 `09_Reports/ScanReports/Progress.md`。
2. 新增结论必须带证据：`文件:行` 或「命令 + 期望输出」。推断标 △，无法确定的写「待确认」，不要写成事实。
3. 缺陷只有一个真源（[`04_BugsAndLessons/DefectRegister.md`](04_BugsAndLessons/DefectRegister.md)，DEF-xx）；事实型文档里最多留一行 `→ DEF-xx`，不写现象与修法。未实现功能归 `T-xx`，不进 DEF。

## 文档状态约定

- **现行**：描述当前实现，可直接据此改代码。
- **设计/计划**：开头有实施状态表；未落地项**不是**现状（`rag.md`、`workflow.md` 属此类）。
- **归档**：`docs/archive/<年-月>/`，历史快照，不作为现状依据。
