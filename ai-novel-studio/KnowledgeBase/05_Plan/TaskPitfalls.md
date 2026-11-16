---
name: task-pitfalls
description: 待修复坑位清单——每条坑映射到 T-xx 修复任务，带代码证据。动手前读，修完按闭环关闭。
status: 现行（随任务账本更新）
---

# 待修复坑位清单

- 来源：2026-11-16 `task-next` 启动摸底（因 `T-30` 活跃租约硬停，未派 worker），只读代码取证。
- 性质：**行动项，不是留档**。每条坑都有修复去向（对应 `T-xx`，或本次已拆出的新任务），修复并验证后按 §5 标"已消解"。这里不是"看看就好"的坑位陈列。
- 时效：行号会随代码改动漂移。已发现 `T-12` 在账本里的证据 `ai_service.py:200-205` 指向的是模型解析，真正的上下文拼装在 `:915-966`。**动手前按症状重新定位，不要照抄行号。**

> **⚠️ 2026-11-16 二次取证订正**（详见 `../04_BugsAndLessons/DefectRegister.md` 与 `../09_Reports/ScanReports/Progress.md` §4）：
> 1. **路径错误**：本文多处写成 `ai/services/ai_service.py` / `backend/app/ai/services/...`，真实路径是 `backend/app/services/ai_service.py`（无 ai 层）。
> 2. **T-34 已失效**：reset 帧链路已全链路实现（后端 `ai_service.py:371` 发帧 → 前端 `lib/ai.ts:105-108` 清空 → `ai-panel.tsx` 接 onReset），不再是待修坑；应复核后关闭 T-34。
> 3. **T-31 部分失效**：前端已消费三类流式端点（`lib/ai.ts:216/246/281`），已非"只会打通用流"；但 done 帧字段不匹配（`ai.ts` 强转 AIResult）等边界仍在，见 `01_CodeMap/02-lifecycle.md`。
> 4. **T-30 流式已落地**：账本写"无流式"，实际路由 `routes/ai.py:161-184`、服务 `ai_service.py:728-822` 已实现；仅降级空内容（DEF-03）待修。
> 下述原始分析保留作发现记录，**结论以订正为准**。

## 0. 修复闭环（每条坑的去处）

| 坑位 | 修复去向 | 当前状态 |
|---|---|---|
| T-11 RAG 检索（表齐代码零 / 无外键 / 索引缺失） | `T-11` | 待办 |
| T-12 上下文（行号漂移 / 只回填部分路径） | `T-12` | 待办 |
| T-12 摘要不进自动保存 | `T-32`（本次新增） | 待办 |
| T-12 上下文泄漏未来章摘要 | `T-33`（本次新增） | 待办 |
| T-17 导入导出（路由空白 / 半成品写入） | `T-17` | 待办 |
| T-18 人物世界观（软删 vs CASCADE / 悬空引用） | `T-18` | 待办 |
| T-19 工作流（表缺 / 与任务表重叠） | `T-19` | 待办 |
| T-31 前端消费流（协议对不上 / 无入口） | `T-31` | 待办 |
| T-31 修复帧累加成坏 JSON | `T-34`（本次新增） | 待办 |
| T-30 / T-31 SSE 协议撞车 | `T-30`（在办，**前提已过期需先复核**）+ `T-31` | T-30 在办 / T-31 待办 |

> 修复完成以对应 `T-xx` 在 `TaskRegister.md` 关闭（移入 §2、带验证输出）为准，不是本页说了算。

## 1. 逐任务坑位（修复时的具体落点）

### T-11 RAG 检索（P1，阶段 3）

| 坑 | 证据 |
|---|---|
| 表齐、代码零：`KnowledgeChunk` 已建表，全仓唯一读写是统计 `COUNT(*)` | `backend/app/models/novel.py:182-211`；`backend/app/db/project_db.py:113` |
| 溯源列是裸 `String` 无外键，删章不清理索引（对比 `Embedding.chunk_id` 有 CASCADE） | `backend/app/models/novel.py:193-195`、`:221-226`；`docs/rag.md:264-277`（文档自认这是"当前最明确的正确性缺口"） |
| 脏标记有写无读：正文变更/版本恢复只置 `indexed_hash=None`，切分函数无调用方，索引任务完全缺失 | `backend/app/services/novel_service.py:227,323,359`；`docs/rag.md:78-80,254-262` |
| 预算字段没人读：`context_window/max_output_tokens` 无代码使用，仅 `_context_budget` 硬乘 0.45；`retrieval_logs` 无写入方 | `docs/rag.md:196-198`；`backend/app/ai/services/ai_service.py:908-913` |

### T-12 上下文摘要回填（P1）

| 坑 | 证据 |
|---|---|
| 账本证据行号已漂移，实施时不能照旧行号改 | 账本 `TaskRegister.md:16` 写 `:200-205`；真逻辑 `backend/app/ai/services/ai_service.py:915-966` |
| 摘要只回填 write/outline；续写/扩写/润色/审稿拿不到前情 | `backend/app/ai/services/ai_service.py:929-943` |
| "最近章节"取的是**全局**最近、不是目标章前序，`chapter_id` 收了却没用于查询 → 长项目把未来章摘要塞进上下文（已拆出 `T-33`） | `backend/app/ai/services/ai_service.py:968-988` |
| 预算单位是字符且封顶 24k、硬编码 0.45，不扣 `max_output_tokens`；摘要写入靠人工调显式端点（已拆出 `T-32`） | `backend/app/ai/services/ai_service.py:48,908-913`；`backend/app/ai/routes/ai.py:94-111`；`TaskRegister.md:34` |

### T-17 TXT/DOCX/Markdown 导入导出（P1）

| 坑 | 证据 |
|---|---|
| 坑不是缺依赖：`python-docx==1.2.0` 已在册，属"依赖在册未用" | `backend/pyproject.toml:28`、`backend/requirements.txt:29`；`docs/development-plan.md:137` |
| 路由层完全空白：router 只挂 7 个 router，无 import/export 文件，端点表也无 | `backend/app/api/router.py:7-16`；`docs/api.md:123-125` |
| `append_chapters` 是半成品：只吃 `list[dict{title,content}]`，无调用方，不解析文件格式、不处理卷归属/标题切章/幂等 | `backend/app/services/novel_service.py:511-532`；`docs/plan-reconciliation.md:200` |
| 写入语义：`sort_order` 从 `max+1` 盲目追加、不写 paragraph、逐章 flush，中途失败无回滚/去重 | `backend/app/services/novel_service.py:516-531` |

### T-18 人物/世界观 8 表零 API（P1）

| 坑 | 证据 |
|---|---|
| 表在、接口/service 全无 | `backend/app/models/novel.py:287-426`；`backend/app/api/router.py:7-16` |
| 软删 vs CASCADE 语义冲突：`Character` 继承 `SoftDeleteMixin`，但关联表 `character_id`/`source_character_id` 是 FK+CASCADE，且 `foreign_keys=ON` → 硬删真级联、软删留孤儿，CRUD 必须先定策略 | `backend/app/models/novel.py:287,328-330,345-350`；`backend/app/db/session.py:34` |
| 大量悬空引用无 FK：`first_chapter_id`、`leader_character_id`、`owner_character_id`、`CharacterState.chapter_id/event_id/location_id` 全是裸字符串 | `backend/app/models/novel.py:317,331-333,387,401` |
| 条件唯一索引的 upsert 坑：`uq_characters_project_name_active` 带 `sqlite_where=is_deleted=0`，改名/恢复/重建须自己处理软删行；`aliases/current_state/state/constraints` 是 JSON 列需序列化校验 | `backend/app/models/novel.py:289-298` |

### T-19 工作流 5 表（P1，阶段 4）

| 坑 | 证据 |
|---|---|
| 表确实全缺；实际 35 表不含这 5 张 | `docs/workflow.md:12-13,200-249`；`docs/plan-reconciliation.md:57` |
| 前端依赖在册零引用：`@xyflow/react 12.12.1`，`/workflows` 是占位页，导航标 `implemented:false` | `desktop/package.json:41`；`desktop/src/router.tsx:32`；`desktop/src/config/navigation.ts:105-111` |
| 与现有任务表语义重叠：`generation_tasks`/`task_logs` 已建带 CASCADE 但零读写，设计要求节点用 `workflow_node_runs.task_id` 关联 → 建表前定"复用还是另建" | `backend/app/models/studio.py:169-221`；`docs/workflow.md:373-391`；`docs/development-plan.md:215-217` |
| 引擎不是简单 DAG：须支持环/条件/迭代上限，断点续跑依赖 `graph_snapshot` 而非 `workflow_id`，表结构一次设计到位 | `docs/workflow.md:154-196,251-268` |

### T-31 前端消费结构化流（P1）

| 坑 | 证据 |
|---|---|
| 客户端只会打通用流 `/{operation}/stream`，body 无 `force`，命中不了 `/ai/outline/{id}/stream`、`/ai/summary/{id}/stream` | `desktop/src/lib/ai.ts:48`；`backend/app/schemas/ai.py:10-28`；`backend/app/ai/routes/ai.py:137-184` |
| 面板无入口：`outline/write` 的提示是空串 | `desktop/src/components/editor/ai-panel.tsx:39-45,53-54` |
| done 帧协议对不上：后端 outline 是 `OutlineResult+usage`、summary 是 `{chapter_id,summary,cached,skipped}`，前端无条件强转 `AIResult`，读 `model/input_tokens` 得到 `undefined` | `backend/app/ai/services/ai_service.py:791-794,560-566`；`backend/app/schemas/ai.py:77-99`；`desktop/src/lib/ai.ts:116-119`；`ai-panel.tsx:295-300` |
| delta 是 JSON 原文、修复会重发一遍，前端直接累加 → 坏 JSON（已拆出 `T-34`） | `backend/app/ai/services/ai_service.py:343-367`；`desktop/src/lib/ai.ts:116-119`；`ai-panel.tsx:116-118` |

## 2. T-30 / T-31 撞车分析（修复时必须先拆）

**结论：文件层基本不撞，接口/协议层高度撞车；且 T-30 的"未实现"前提已与代码不符。**

1. **T-30 前提已过期**：账本 `TaskRegister.md:27` 仍写"POST /ai/outline 无流式"，但流式大纲**已落地**——路由 `backend/app/ai/routes/ai.py:161-184`、服务 `backend/app/ai/services/ai_service.py:728-822`、预检 `:403-410`，并有测试固定帧形状 `backend/app/tests/test_stream_structured.py:199-265`。处理 T-30 的会话实际是在这段现成代码上动刀。
2. **改动文件不重叠**：T-30 落点 `routes/ai.py:161-184` + `ai_service.py:338-367,728-822`；T-31 落点 `lib/ai.ts:33-150` + `ai-panel.tsx:39-45,106-132,295-300`。
3. **真正的撞点是共享 SSE 契约**：done 帧现为 `OutlineResult+usage`（`ai_service.py:791-794`）而 T-31 强转 `AIResult`（`lib/ai.ts:116-119`）；delta 修复"替换而非追加"语义（`ai_service.py:350-367`）若被 T-30 调整，T-31 增量展示（`ai-panel.tsx:116-118`）同步失效；测试 `test_stream_structured.py:214-265` 也钉住了协议。
4. **建议隔离线（修法选择）**：以 `backend/app/schemas/ai.py:77-99` 的 `OutlineResult` 为唯一 done 契约。T-30 若只做"非流式端点加进度心跳/超时提示"，就不碰 `_stream_json` 与 `/outline/{id}/stream`，让 T-31 直接消费已存在的流端点，可完全规避撞车。

## 3. 本次分析已转化为任务

| 任务 | 缺口 | 证据 |
|---|---|---|
| `T-32` | 章节保存后不自动生成摘要，前情提要需手动调端点 | `backend/app/ai/routes/ai.py:94-111` |
| `T-33` | 上下文泄漏未来章摘要（按全局排序而非前序） | `backend/app/ai/services/ai_service.py:968-988` |
| `T-34` | 流式 JSON 修复重发被前端累加成坏 JSON | `backend/app/ai/services/ai_service.py:350-367`；`desktop/src/lib/ai.ts:116-119` |

## 4. 验证与关闭口径

坑的"修好"以对应 `T-xx` 在 `TaskRegister.md` 关闭（状态移入 §2、带 pytest/smoke 输出）为准，不是本页说了算。本页证据是取证时快照，动手前复核行号；本轮未跑基线（task-next 在派活前硬停，按协议 §6 基线只在 `QUEUE_EMPTY` 收尾时跑）。

## 5. 消解记录

> 任务关闭后在此追加一行：`T-xx 已关闭（日期）— 对应坑位已修复，证据：…`。未出现在此表的坑位均为**待修复**。
