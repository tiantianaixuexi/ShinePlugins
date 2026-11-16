---
name: current-status
description: 各子系统的实现状态总表（AI 层、编辑器、数据层、侧车、前端集成），每行带证据指针与缺口描述。回答"这个功能到底做完没有"从这里查。
status: 现行（每轮更新）
---

# 当前状态

- 最后更新：2026-11-16（依据后端 AI 层实测核查，非文档转述）
- 状态取值见 [`README.md`](README.md)。**状态与代码不符时以代码为准**，改本页。
- `../../docs/development-plan.md` 已于 2026-11-16 按本页结论重写（阶段 2 拆 2a/2b，补入 AI 层已实现清单）。
  历史：该文 §3.2 曾写「AI 部分完全未开工」，与代码不符（实际 `backend/app/ai/` 10 个 py、
  `api/routes/ai.py` 5 个端点、20 条 AI 相关测试），已修正，见 `T-16`。

## 1. AI 层（`backend/app/ai/`）

| 项 | 状态 | 证据 / 缺口 |
|---|---|---|
| LLM 适配器抽象（`complete` / `stream`） | 已实现 | `ai/llm/base.py:30-61`；token 估算 `:15-27` |
| OpenAI 兼容适配器真实 HTTP 调用 | 已实现 | `ai/llm/openai_compatible.py:46,163-187` |
| 重试（指数退避 + 可重试码分类） | 已实现 | `openai_compatible.py:37,147-161,216-232`；`errors.py:3-5` |
| 流式输出（SSE 到前端） | 已实现 | `openai_compatible.py:234-289`；`services/ai_service.py:128-195`；`routes/ai.py:43-69`（`EventSourceResponse`） |
| 主备降级 `fallback_ids` | 已实现（有测试） | `llm/registry.py:69-128`；`tests/test_llm_fallback.py` 9 条。**遗留缺陷**：链路只校验 primary 的 `is_active` → `T-26` |
| 结构化输出（JSON 模式 + 解析 + 修复重试） | 已实现 | `ai/structured.py`：`parse_json_object` 三级解析 + `complete_json`（置 `json_mode`、修复重试一次、失败回原文降级）；6 条测试 |
| 提示词模板（内置 + DB 双源） | 已实现 | `ai/prompts/builtin.py`（9 个，含 `memory.summary`/`outline.structured`）；`prompts/service.py` seed / DB 优先 / 渲染 |
| 提示词版本号 | 已实现 | `prompts/service.py` 新增 `upsert_override`（写即 `version=max+1`，旧行保留）；`PATCH /api/ai/prompts/{key}` |
| 生成任务记账（token/成本/失败） | 已实现 | `services/ai_service.py:349-372,389-434`；`routes/ai.py:72-96` |
| 按 Agent 绑定模型 `agent_configs` | **未实现**（仅建表） | `models/studio.py:90-93`；全仓无读写方 → `T-07` |

## 2. 记忆与上下文

| 项 | 状态 | 证据 / 缺口 |
|---|---|---|
| 上下文拼装（角色/事件摘要 + 章节截断） | 部分实现 | `services/ai_service.py:200-205`（截断）、`:200-280`（摘要注入） |
| `chapter_summaries` 写入 | 已实现 | `ai_service.summarize_chapter` + `POST /api/ai/summary/{chapter_id}`（`memory.summary` 模板，宽松解析，按 chapter_id upsert）；不进自动保存路径 |
| `knowledge_chunks` 检索（RAG） | **未实现** | `models/novel.py:173-176`；`db/project_db.py:113` 仅 `count(*)`。无 embedding、无向量 → `T-11`（阶段 3） |
| `outlines` 读写 | 已实现 | `ai_service.generate_outline` + `POST /api/ai/outline/{chapter_id}`（`outline.structured` 模板，`level=chapter`、`parent_id=chapter_id` upsert） |

## 3. 前端集成（`desktop/src/`）

| 项 | 状态 | 证据 / 缺口 |
|---|---|---|
| SSE 客户端（`fetch` + 帧解码 + `AbortSignal`） | 已实现 | `lib/ai.ts:33-149`；5 条单测 `lib/ai.test.ts` |
| AI 助手面板 | 已实现 | `components/editor/ai-panel.tsx`；`pages/.../novel-editor-page.tsx:108-114` 已挂载 |
| 操作入口 | 部分实现 | 续写/扩写/改写/润色/审稿 5 个可用（`ai-panel.tsx:38-44`）；`outline`/`write` 无入口（`:52-53` 空壳）→ `T-09` |
| 预览 / 停止 / 应用 | 部分实现 | 预览、停止、复制/替换选中/插入末尾/替换全文可用；应用已走 `accept-ai` 端点。**仍无"拒绝/丢弃"** → `T-08` |
| 消费 `/operations` `/prompts` `/tasks` | 部分实现 | 已接 `accept-ai`；`/operations`、`/prompts`、`/tasks` 仍无消费方 → `T-10` |
| AI 产出写入 `chapter_versions.source="ai"` | 已实现 | `POST /chapters/{id}/accept-ai`：先存原文为 `user` 快照，再写 `source="ai"` + `task_id`（新列 + 迁移 v2）；`api.chapters.acceptAi` |

## 4. 编辑器与数据层（阶段 2 已完成部分）

| 项 | 状态 | 证据 |
|---|---|---|
| 卷/章 CRUD 与排序 | 已实现 | `api/routes/novels.py`；`services/novel_service.py` |
| 自动保存（1200 ms 防抖 + flush） | 已实现 | `components/editor/chapter-editor.tsx` |
| 乐观并发（`row_version` → 409） | 已实现 | 同上 + `novel_service.update_chapter` |
| 章节版本管理（列表/快照/恢复） | 已实现 | `routes/novels.py`；`version-history-dialog.tsx` |
| 迁移执行器（拒绝降级 + 迁移前备份） | 已实现 | `db/migrations.py`；`tests/test_migrations.py` |
| 模型配置 + DPAPI 加密密钥 | 已实现 | `routes/model_configs.py`；`core/keystore.py` |
| sidecar 拉起（动态端口 + 令牌 + 日志泵） | 已实现 | `desktop/src-tauri/src/sidecar.rs` |

## 5. 验收基线

| 命令 | 期望 | 最近结果（2026-11-16 实跑） |
|---|---|---|
| `pytest -q`（backend） | 全绿 | ✅ `96 passed`（2026-11-16 晚，T-01…T-06 落地后；原 60 基线 + 36 条新用例） |
| `pnpm test`（desktop） | 全绿 | ✅ `Tests 32 passed (32)` / 5 个文件 |
| `pnpm typecheck` | 无输出 | 待跑 |
| `scripts/smoke_api.py` | `SMOKE PASSED` | 待跑 |
| `scripts/smoke_ai.py --from-store` | `AI SMOKE PASSED` | 待跑（需已配置模型） |

> 数字只在这一处与 `../INDEX.md` 维护，别在别的文档里另写一份基线。
> `T-24` 的剩余部分不是数字，而是**没有 E2E 黄金路径与 500 章合成语料**。
