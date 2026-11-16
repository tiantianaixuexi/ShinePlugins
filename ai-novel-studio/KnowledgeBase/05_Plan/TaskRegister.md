# 任务账本（`T-xx`）

> **唯一真源**。只允许 `.agents/scripts/task_queue.py` 写本文件——手改会与 `.agents/task-state.json`
> 里的租约/尝试次数不一致。要加任务用 `task_queue.py add`，不要手写行。
>
> 表格列固定 8 列，单元格内**不要出现竖线**。状态列由脚本维护。


## 1. 待办

| 编号 | 优先级 | 模块 | 现象 | 证据 | 修法 | 验证 | 状态 |
|---|---|---|---|---|---|---|---|
| T-07 | P1 | ai | agent_configs 零读写方，无法按 Agent 选模型 | models/studio.py:90-93；全仓引用仅模型层 4 处 | 按 operation 查 agent_configs 决定 model_config_id，缺省回落默认模型 | pytest：配置了绑定的 operation 走指定模型 | 待办 |
| T-08 | P1 | frontend | AI 面板无拒绝/丢弃，结果不持久化 | components/editor/ai-panel.tsx:293-311 | 加丢弃按钮并清空草稿；未完成流式结果落 drafts 并标注未完成 | 手动：点丢弃后正文与版本均不变 | 待办 |
| T-09 | P1 | frontend | outline 与 write 两个后端操作无 UI 入口 | ai-panel.tsx:52-53 留空壳 | 补两个操作入口与占位提示 | 面板里可见 7 个操作 | 待办 |
| T-10 | P1 | frontend | /operations /prompts /tasks 三个端点无消费方 | lib/ai.ts:48 只调 stream；types/api.ts:288 仅类型声明 | 操作列表与 prompt 列表改为从端点拉取；任务面板展示 token 与成本 | 手动：改内置模板后 UI 生效 | 待办 |
| T-11 | P1 | rag | knowledge_chunks 无检索，长文只能靠章节截断 | models/novel.py:173-176；db/project_db.py:113 仅 count | 阶段 3：切分 + FTS5 + 向量 + 混合检索（设计见 docs/rag.md） | 阶段 3 验收判据全绿 | 待办 |
| T-12 | P1 | ai | 上下文只截断最近章节，无摘要回填 | ai/services/ai_service.py:200-205 | 依赖 T-01，用摘要拼上下文并按模型 context_window 缩放预算 | 长项目生成时上下文含摘要段且不超窗 | 待办 |
| T-13 | P2 | ai | get_task 已实现但无路由暴露 | ai/services/ai_service.py:472-477 | 加 GET /api/ai/tasks/{id} | pytest 命中 200 与未知 id 404 | 待办 |
| T-14 | P2 | ai | 生成记录只存 prompt_key，模板改动后历史不可复现 | ai/services/ai_service.py:410-415 | 存模板正文快照或 content_hash | 改模板后旧任务仍能复原当时 prompt | 待办 |
| T-15 | P2 | ai | generation_tasks 只增不删，无 pruner | ai/services/ai_service.py:353-371 | 按项目保留最近 N 条或按时间清理 | 跑 pruner 后行数下降 | 待办 |
| T-17 | P1 | import | TXT/DOCX/Markdown 导入导出全未实现 | api/routes 下无导入导出路由；novel_service.append_chapters 无调用方 | 加导入与导出端点，用 python-docx 读写 | pytest 导入3章；导出 docx 能被 python-docx 读回 | 待办 |
| T-18 | P1 | characters | 人物与世界观 8 张表零 API 零服务层 | models/novel.py:279-409；api/routes 无 characters.py；services 仅 4 个 py | 先做 characters CRUD + character_states 只读视图 | pytest 增删改查 + 状态历史查询 | 待办 |
| T-19 | P1 | workflow | 工作流 5 张表不存在，React Flow 零引用 | models 下无 workflow_ 表；package.json 有 @xyflow/react 但 src 零引用 | 阶段4建表 + 独立执行引擎，UI 与执行分离 | 一条工作流跑通并断点续跑 | 待办 |
| T-20 | P2 | editor | 编辑器无查找替换，撤销依赖 textarea 原生 | components/editor/chapter-editor.tsx 无 find/replace 实现 | 加查找替换浮层，支持全章匹配与替换 | 手动：查找命中高亮，替换后可撤销 | 待办 |
| T-21 | P2 | data | paragraphs 表无写入方，只有切分函数 | models/novel.py:68 定义；仅 utils/text.py 有 split_paragraphs | 段落随章节保存写入，或明确删表并说明理由 | 保存章节后 paragraphs 有行，或表被删除并有记录 | 待办 |
| T-25 | P1 | test | 无 E2E 黄金路径与 500 章合成语料 | tests 无 Playwright；无造语料脚本；正文只有单元与冒烟 | Playwright 跑一条主流程 + 脚本生成带标注的 500 章语料 | E2E 一条绿；语料脚本输出可复现 | 待办 |

## 2. 已关闭

| 编号 | 优先级 | 模块 | 现象 | 证据 | 修法 | 验证 | 状态 |
|---|---|---|---|---|---|---|---|
| T-01 | P0 | ai | 前情提要恒为空：chapter_summaries 只有读没有写 | ai/services/ai_service.py:260-280 读；全仓无 insert | 章节保存后生成 L1 摘要写库，复用现有适配器 | 保存章节后 chapter_summaries 有行且 _recent_summaries 非空；pytest 新用例；实测：pytest -q → 64 passed in 22.14s；scripts/smoke_api.py → SMOKE PASSED: all checks green（未提交：无 git） | 已关闭 2026-11-16 — 新增 memory.summary 内置 prompt + AIService.summarize_chapter（非流式调模型、宽松解析 JSON、按 chapter_id upsert 写 chapter_summaries）+ POST /api/ai/summary/{chapter_id} 显式端点；不进自动保存路径，_recent_summaries 未改 |
| T-02 | P0 | ai | AI 产出被采纳后记成 source=user，task_id 血缘丢失 | services/novel_service.py:188,231,314,328,434 | 新增采纳路径：写 chapter_versions 时带 source=ai 与 task_id | 接受 AI 结果后版本列表出现 source=ai 行；实测：pytest → 69 passed（0 failed）；pnpm typecheck 无输出；pnpm test → 32 passed；smoke_api → SMOKE PASSED；ruff All checks passed | 已关闭 2026-11-16 — 新增 POST /chapters/{id}/accept-ai：先存原文 source=user 快照，再改写正文，再落 source=ai + task_id 版本；chapter_versions 新增 nullable task_id 走 migrations v2；前端 handleApply 改调该端点 |
| T-03 | P0 | ai | 结构化输出缺失，模型只回自由文本 | ai/services/ai_service.py:343 硬编码 json_mode=False | 加 JSON 模式 + 解析 + 一次修复重试 + 失败降级为非结构化抽取 | tests/test_ai_adapters.py 新增 JSON 解析与降级用例；实测：pytest -o addopts='' (backend) → 75 passed；ruff check app tests → All checks passed；pnpm typecheck → exit 0 无 TS 错误 | 已关闭 2026-11-16 — 新增 ai/structured.py（parse_json_object + complete_json 含一次修复重试与降级），summarize_chapter 改走它，删掉局部 _parse_summary_json/_as_str_list |
| T-04 | P0 | ai | outlines 表纯死表，大纲不落库 | models/novel.py:123-126；db/project_db.py:110 仅 count | 依赖 T-03，把 outline 操作的结构化结果写入 outlines | 生成大纲后 outlines 有行；pytest 覆盖；实测：backend pytest -q → 81 passed in 28.95s；ruff check app tests → All checks passed；smoke_api.py → SMOKE PASSED | 已关闭 2026-11-16 — 新增 outline.structured prompt + AIService.generate_outline（JSON→upsert outlines，解析失败降级写原文）+ POST /api/ai/outline/{chapter_id}；outline.chapter 与 /ai/outline 行为未动 |
| T-05 | P0 | ai | PromptService 零测试，版本恒为 1，无覆盖端点 | ai/prompts/service.py:49-144；routes/ai.py:23-35 无写端点 | 加 PATCH /api/ai/prompts/{key}（写即 version+1）+ seed/resolve/render 测试 | pytest 新增 ≥3 用例；GET /prompts 能看到 version=2；实测：pytest -q → 87 collected, exit 0, 0 failed（基线 81 + 新增 6）; ruff check app tests → All checks passed!; smoke_api.py → SMOKE PASSED: all checks green | 已关闭 2026-11-16 — PromptService 新增 upsert_override（写即 version+1、保留旧版本、未知 key 抛 KeyError），新增 PATCH /api/ai/prompts/{key} 与 tests/test_prompt_service.py 6 条用例 |
| T-06 | P0 | ai | 主备降级链零覆盖 | ai/llm/registry.py:69-128；tests/test_ai_adapters.py:58 | 补 fallback 测试：主模型 5xx → 备模型成功；流式已 emitted 不降级 | pytest 新增 ≥2 用例；实测：pytest -q (backend) → 96 passed, 0 failed；tests/test_llm_fallback.py -v → 9 passed；ruff check app tests → All checks passed | 已关闭 2026-11-16 — 新增 tests/test_llm_fallback.py 9 条用例覆盖 ChatClient 主备降级链（complete 降级/全链失败/401 不降级/adapter 重试优先/链路跳过不可用备模型/流式首 token 前降级/已 emitted 不降级），未改实现 |
| T-16 | P2 | docs | development-plan.md 与代码严重不符 | docs/development-plan.md:107 写无 ai 包；实际 backend/app/ai 有 10 个 py | 按 CurrentStatus.md 重写 §3.2 与 §3.4 判据 | 文档中不再出现 AI 部分完全未开工；实测：docs/development-plan.md 全文替换，含 §9.1 已偿还 4 条 / §9.3 新增 4 条风险 | 已关闭 2026-11-16 — development-plan.md 已按代码重写（阶段2拆2a/2b、补AI层清单、风险表重写、验收可执行化） |
| T-22 | P2 | realtime | 无 WebSocket，原计划要求 4 个 | api/routes 无 ws 路由；core/security.py 仅提及；实际用 SSE | 定策略：生成流用 SSE 写死进计划，任务状态用 WS 或轮询 | 计划文档里不再有悬空的 4 个 WS 接口；实测：docs/development-plan.md §10.5 明确不做 WebSocket；实测：docs/development-plan.md 10.5 明确不做 WebSocket | 已关闭 2026-11-16 — WS 策略定稿：生成流用 SSE，任务状态用轮询，4 个 WS 接口作废 |
| T-23 | P2 | editor | Tiptap 已装未用，计划未记录 textarea 决策 | package.json 有 @tiptap 依赖；desktop/src 零引用；editor 用 textarea | 在开发计划 §5.2 与选型表标注 V1.x 用 textarea | 计划与代码不再互相矛盾；实测：docs/development-plan.md §3.4 决策定稿 + §10.5 明确不做；实测：docs/development-plan.md 3.4 决策定稿 + 10.5 明确不做 | 已关闭 2026-11-16 — Tiptap 决策定稿：V1.x 用 textarea，理由与演进路径已写入计划 |
| T-24 | P1 | test | 验收不可执行：无 E2E、无 500 章语料、pytest 数字自相矛盾 | tests 8 个文件无 E2E；README 写 44 passed 而 development-plan 写 37 passed | 补 E2E 黄金路径 + 合成语料脚本 + 统一数字 | 五条验收命令都能跑出确定结果；实测：实跑 pytest 60 passed + pnpm test 29 passed；INDEX 与 development-plan 已同步；实测：实跑 pytest 60 passed + pnpm test 29 passed；INDEX 与 development-plan 已同步 | 已关闭 2026-11-16 — 基线数字统一为 pytest 60 / vitest 29，验收改为命令表 |
| T-26 | P1 | ai | 降级链不校验备模型 is_active，停用的备模型仍会被调用 | ai/llm/registry.py:72-74 只对 primary 查 is_active；test_llm_fallback.py 已固化现状 | 构建链路时对 fallback 也过滤 is_active=False | 停用备模型后不再出现在链路里，pytest 覆盖；实测：pytest -q → 96 passed 0 failed；test_llm_fallback.py -v → 9 passed；ruff check app tests → All checks passed | 已关闭 2026-11-16 — _chain 对 fallback 取到 model 后校验 is_active，停用则 fallback_model_inactive warning + continue，不动 resolve/顺序/异常类型；测试扩展链构建用例覆盖停用备模型不在链 |
| T-27 | P2 | docs | api.md 未同步本轮新增的 4 个端点 | 新增 POST /ai/summary/{id}、POST /ai/outline/{id}、POST /chapters/{id}/accept-ai、PATCH /ai/prompts/{key} | 在 docs/api.md 补这 4 个端点的契约与错误码 | api.md 端点清单与 routes 目录一致；实测：§2 总览+9 行、§3.16 九端点详情、§5 AI 从「未实现」移除；README/INDEX 计数同步 | 已关闭 2026-11-16 — api.md 已补 4 个新端点契约并修正总数 30→39 |

## 3. 挂起

| 编号 | 优先级 | 模块 | 现象 | 证据 | 修法 | 验证 | 状态 |
|---|---|---|---|---|---|---|---|
