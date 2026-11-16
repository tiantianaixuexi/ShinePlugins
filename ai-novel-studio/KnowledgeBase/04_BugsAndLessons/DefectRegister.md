---
name: defect-register
description: 缺陷唯一真源。DEF-xx 编号，证据/影响/修法/验收四列 + 状态机。只收"代码写错"的缺陷，未实现功能归 T-xx。
status: 现行（2026-11-16 建档）
---

# 缺陷登记表（唯一真源）

> 收录口径见 [`README.md`](README.md)。事实型文档里最多写一行 `→ DEF-xx`。
> **未实现功能不是缺陷**：T-11/T-17/T-19 等在 `../05_Plan/TaskRegister.md`，不在本表。

## §0 计数与索引

| 状态 | 数量 | 编号 |
|---|---|---|
| 待修 | 2 | DEF-01、DEF-02 |
| 已关闭（历史归档） | 11 | DEF-03、DEF-04 ~ DEF-13 |

> 2026-11-16 18:16 同步：DEF-03 已随 `T-35` 关闭（`complete_json` 降级回退最长原文，pytest 111+），从待修移入归档。

- 可信度：✅ 有代码/测试证据；△ 有依据未验证。
- 分类：`静态`（代码可验证）/ `已发生`（有历史事件为证）。

## §1 待修缺陷

### DEF-01 · 前情摘要泄漏未来章（前情剧透） `静态` ✅

- **现象**：`_recent_summaries(project_id, chapter_id, ...)` 收了 `chapter_id` 但查询完全不用它，只按 `Chapter.sort_order.desc()` 取全局最近 5 条。写第 3 章时可能把第 20 章摘要喂给模型。
- **证据**：`backend/app/services/ai_service.py:977-997`（where 条件 `:986-989` 无 chapter 过滤，排序 `:990`）。
- **影响**：破坏悬念/连贯性；长项目尤甚。
- **修法**：先查目标章 `sort_order`，where 加 `Chapter.sort_order < target_order` 再 desc 取前序。
- **验收**：造多章+各自摘要，断言生成第 N 章的 context 不含第 N+1 章及之后的摘要文本。
- **关联**：`T-33`（`../05_Plan/TaskRegister.md`）；来源 `TaskPitfalls.md:47`。
- **状态**：待修

### DEF-02 · 摘要只回填 write/outline，其余操作无前情 `静态` ✅

- **现象**：`_build_variables` 仅当 `operation in ("write","outline")` 才拼 `【前情提要】`；continue/expand/polish/review 拿不到摘要。
- **证据**：`backend/app/services/ai_service.py:938-941`。
- **影响**：最需要前情的续写/润色/审稿全程无记忆。
- **修法**：把摘要回填扩到全章类操作（`WHOLE_CHAPTER_OPERATIONS`）或按白名单显式配置。
- **验收**：对 continue/polish/review 各跑一次，断言 prompt 变量 `context` 含 `【前情提要】` 且不超预算。
- **关联**：`T-12`；来源 `TaskPitfalls.md:46`。
- **状态**：待修

## §2 已关闭（历史归档）

> 来源：`../05_Plan/TaskRegister.md` 已关闭区（均 2026-11-16）。这些是"确实修了 bug"的任务映射为 DEF 编号，作为历史留档；修法与验证输出详见 TaskRegister 对应行（本表只留指针，不重复描述）。

| DEF | 原 T-xx | 现象（摘要） | 修法指针 | 验证 |
|---|---|---|---|---|
| DEF-03 | T-35 | 非流式大纲修复轮空回复丢原文，degraded 结果 content 为空 | complete_json 降级回退最长原文（新增 longest_text）；流式/非流式均据此写 content | pytest 111（新增 3 条）；smoke_ai PASSED（降级路径靠单测覆盖） |
| DEF-04 | T-01 | 前情提要恒为空（chapter_summaries 只读无写） | 新增 memory.summary + summarize_chapter upsert + POST /ai/summary/{id} | pytest 64→…；smoke_api PASSED |
| DEF-05 | T-02 | AI 采纳记成 source=user，task_id 血缘丢失 | POST /chapters/{id}/accept-ai；迁移 v2 | pytest 69；typecheck 干净；test 32 |
| DEF-06 | T-03 | 结构化输出缺失，json_mode 硬编码 false | 新增 ai/structured.py 宽松解析+一次修复 | pytest 75；ruff clean |
| DEF-07 | T-04 | outlines 死表，大纲不落库 | outline.structured + generate_outline upsert | pytest 81；smoke_api PASSED |
| DEF-08 | T-05 | PromptService 零测试、版本恒 1、无覆盖端点 | upsert_override + PATCH /ai/prompts/{key} | pytest 87 collected 0 failed |
| DEF-09 | T-06 | 主备降级链零覆盖 | test_llm_fallback.py 9 用例（未改实现） | pytest 96；fallback 9 passed |
| DEF-10 | T-07 | agent_configs 零读写，无法按 Agent 选模型 | AgentConfigService + _resolve_model 优先级 | pytest 101；smoke_api PASSED |
| DEF-11 | T-08 | AI 面板无丢弃，结果不持久化 | 加「丢弃」abort+清空 | typecheck 干净；test 32；build ✓ |
| DEF-12 | T-26 | 降级链不校验备模型 is_active | _chain 对 fallback 也校验 is_active | pytest 96；fallback 9 passed |
| DEF-13 | T-30（部分） | 非流式大纲 103.7s 无反馈 | 新增两个 /stream 端点 | pytest 105；流式大纲 41 增量/50.1s PASS |

> DEF-13 说明：T-30 的"加进度反馈"已通过流式端点实现并关闭；其暴露的降级空内容另立 DEF-03，也已随 T-35 关闭。两者是同一任务的正反两面，分列编号。
>
> 另：T-36（推理型模型首字长时间无输出，解析 `reasoning_content` 为 thinking 事件）已关闭，属体验改进非"代码写错"，不单列 DEF，见 TaskRegister T-36。

## §3 明确不收（避免误录）

- **T-22 WS→SSE、T-23 Tiptap→textarea**：设计取舍，归 ADR/development-plan。
- **T-11 RAG、T-17 导入导出、T-19 工作流、T-32 摘要自动保存**：未实现功能，归 T-xx。
- **Plan_Gaps 的 P0**：3.1 SQLite 并发、3.2 schema 迁移已被代码与记忆推翻（`.memsearch/memory/2026-11-16.md:49`、`backend/app/db/session.py:3-11,31-37`），其余是"计划文档该写没写"，归计划层，非代码缺陷。
