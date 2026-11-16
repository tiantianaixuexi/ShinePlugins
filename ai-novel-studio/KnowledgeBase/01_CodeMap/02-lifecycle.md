---
name: lifecycle
description: 跨层调用链：sidecar 拉起、AI 请求/SSE、章节自动保存与采纳、版本恢复。回答"一次操作从 UI 到库经过哪些环节"。
status: 部分级（2026-11-16 取证，带 文件:行）
---

# 跨层调用链

> 部分级：结论有 `文件:行` 证据，但未逐行读完所有相关文件。行为细节以代码为准。
> 坑与边界见 `../05_Plan/TaskPitfalls.md`。

## 1. sidecar 拉起（桌面 → Python）

1. `Tauri setup` 后台拉起（`src-tauri/src/lib.rs:60-69`）：`pick_port()` 选空闲端口 → 生成一次性 token → 注入环境变量 → `python -m app`（cwd=backend）。
2. 写 `sidecar.json` 握手文件（`sidecar.rs:867-882`）：含 baseUrl/token/port/pid/startedAt。
3. 健康检查 `/api/health`：250ms 轮询、45s 预算、带 Bearer（`sidecar.rs:730-863`）。
4. 前端 `lib/sidecar.ts:57-65` **只轮询** `get_sidecar_info`，拿到 ready 才缓存地址（历史坑："空地址缓存→落回 Vite 代理 8765"，见 `Lessons.md`）。
5. 退出：`run_with_exit_guard` → `terminate()` 宽限 5s 再强杀 + Windows Job Object 防孤儿（`lib.rs:84`、`sidecar.rs:928-938`、`process_job.rs`）。

## 2. AI 写作请求（UI → 适配器 → 记账）

**非流式**：`ai-panel.run()` → `streamAI`/`streamOutline`/`streamSummary`（`desktop/src/components/editor/ai-panel.tsx:224-245`）→ 后端 `api/routes/ai.py` → `AIService.run/generate_outline/summarize_chapter` → `_resolve_model`（显式 id > Agent 绑定 > 默认，`ai_service.py:197-220`）→ `ChatClient.complete`（`ai/llm/registry.py:93`）→ `OpenAICompatibleAdapter` → `_start_task`/`_finish_task` 记账（`ai_service.py:1066,1106`）。

**流式**：前端 `lib/ai.ts` 自解析 SSE（EventSource 不能 POST，`lib/ai.ts:210-215`）：
- `parseFrame` 解 `event:`/可多行 `data:`（`:44-53`）；
- 帧语义 `delta|reset|done|error`（`:62-99`），`applyStreamOutcome` 对 delta 追加、reset 清空（`:101-109`）——`reset` 配合后端"JSON 修复重发"，防两段回答拼成非法 JSON；
- 三个端点：`/{operation}/stream`、`/summary/{id}/stream`、`/outline/{id}/stream`（`:216,246,281`）；
- 不可达状态归一为 `backend_unreachable`（`:145-151`）。

**后端流式**：`AIService.stream`（`ai_service.py:268`）/ `stream_summary`(`:491`) / `stream_outline`(`:737`)；结构化流 `_stream_json`(`:340`)+`_repair_json`(`:380`)，修复发 `reset` 帧(`:371`)。

> **边界**：流正常结束但从未收到 `done`（代理截断无错误帧）时，前端 `onDone/onError` 都不触发，面板停在 streaming（`lib/ai.ts:179-208`、`ai-panel.tsx:118-125`）。帧切分依赖字面 `\n\n`，`\r\n\r\n` 不成帧（`lib/ai.ts:185`）。

## 3. 章节自动保存（编辑器 → 乐观并发）

1. `chapter-editor.tsx` 是 presentational，文本与保存在 `useChapterDraft`（`:66-73`），与 AI 面板共享缓冲。
2. `onChange` 先 `setTitle/setContent`，非 IME 组字时 `markDirty()`，组字中延到 `compositionend`（`chapter-editor.tsx:96-106,144-148`）。
3. 防抖 1.2s 保存（`use-chapter-draft.ts:85-90`）；`beforeunload`/卸载/`Ctrl+S` 补刷（`:92-114`）。
4. PUT 带 `rowVersion`（`:55-59`）：409 或 code=`conflict` 触发冲突提示（`api.ts:61-63`、`use-chapter-draft.ts:67-75`）。
5. 成功用响应版本覆盖 ref、写回 Query 缓存并使列表失效（`:60-63`）。

> **边界（→ 待修复，见 `TaskPitfalls.md`）**：`flush` 先清 dirty 再发请求、无 in-flight 互斥（`:50-51`）；409 分支只 `invalidateQueries`，未用服务端最新内容重置本地 buffer（`:64-75`）；恢复版本前未先 flush 草稿（`version-history-dialog.tsx:56-68`）。

## 4. AI 采纳闭环（面板 → 血缘版本）

`applyText`（`lib/text-edit.ts:28-51`）生成新文本 → 先调后端 `accept-ai` 让采纳前内容存为 `source=ai` 版本（`novel-editor-page.tsx:65-69,87-100`；端点 `api.ts:234-236`）→ 成功后 `draft.adopt()` 同步刷新且不标脏（`use-chapter-draft.ts:124-135`）→ 失败退化为本地编辑并告警（`:101-109`）。

> **边界**：SSE `done` 帧携带 `task_id`（`types/api.ts:293-295`），但采纳时固定传 `task_id: null`（`novel-editor-page.tsx:88-95`）。

## 5. 版本恢复

对话框触发（`version-history-dialog.tsx:56-68`）→ 后端恢复 → hook 写回章节缓存（`use-novel.ts:99-109`）→ 上层 `refetch + epoch++` 强制重挂载载入恢复文本（`novel-editor-page.tsx:221-224,285-288`）。
