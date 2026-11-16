# 开发计划（工作版）

本文是 AI Novel Studio 的**执行用**开发计划：说明现在到哪了、每个阶段必须产出什么、以及怎么判断做完了。
它不是原始计划（23 节，需求方持有）的副本。

- 总周期：**16 周**（2–3 人）；单人约 **24–32 周**
- 当前进度：**阶段 2 进行中**（阶段 2a 编辑器已完成，阶段 2b AI 可审计进行中）
- 最后核对：2026-11-16，**依据仓库实际代码**
- 原计划 × 现状的逐节对账见 [plan-reconciliation.md](plan-reconciliation.md)
- 实现状态真源见 [../KnowledgeBase/05_Plan/CurrentStatus.md](../KnowledgeBase/05_Plan/CurrentStatus.md)
- 任务账本见 [../KnowledgeBase/05_Plan/TaskRegister.md](../KnowledgeBase/05_Plan/TaskRegister.md)（`T-xx`）

> 依赖策略：**所有库用最新版**，实际锁定版本记录在 [README.md](../README.md) 的「技术栈与固定版本」。

## 1. 进度总览

| 阶段 | 周期 | 主题 | 交付物 | 状态 |
|---|---|---|---|---|
| 1 | 第 1–2 周 | 桌面框架和项目管理 | 可运行的桌面应用 | ✅ 完成 |
| 2a | 第 3–5 周 | 小说编辑器 | 卷/章/正文/版本全链路 | ✅ 完成 |
| 2b | 第 5 周起 | AI 写作可审计 | LLM 接入 + 记忆写入 | 🔄 进行中（AI 层已实现，记忆与血缘待补） |
| 3 | 第 6–8 周 | 小说记忆和 RAG | 长篇索引系统 | ⬜ 未开始（**前置：阶段 2b 的摘要管道**） |
| 4 | 第 9–10 周 | Agent 和工作流 | 自动创作引擎 | ⬜ 未开始 |
| 5 | 第 11–12 周 | 剧本和故事板 | 故事板系统 | ⬜ 未开始 |
| 6 | 第 13–14 周 | AI 媒体生成 | 媒体生产系统 | ⬜ 未开始 |
| 7 | 第 15–16 周 | 测试和打包 | MVP 安装包 | ⬜ 未开始 |

状态图例：✅ 完成 · 🔄 进行中 · ⬜ 未开始 · ⚠️ 受阻

设计文档：[rag.md](rag.md)（阶段 3）· [workflow.md](workflow.md)（阶段 4）·
[api.md](api.md)（接口契约）· [database.md](database.md)（表结构）。

## 2. 阶段 1：桌面框架和项目管理 ✅ 完成

**目标**：能正常启动桌面软件，创建多个小说项目并保存到本地。

### 2.1 已完成

| 任务 | 落点 | 证据 |
|---|---|---|
| Tauri 2 项目 | `desktop/src-tauri/` | `Cargo.toml`（tauri 2.12.5）、`tauri.conf.json` |
| React / TypeScript / Vite / Tailwind / shadcn | `desktop/` | `vite.config.ts`、`components.json`、22 个 shadcn 组件 |
| Rust 命令 | `src-tauri/src/commands/system.rs` | 5 个 `#[tauri::command]` |
| 桌面主窗口 | `tauri.conf.json` | 1440×900，最小 1024×640 |
| 左侧导航 / 顶部栏 / 状态栏 | `components/layout/` | `sidebar.tsx`、`topbar.tsx`、`status-bar.tsx`、`app-shell.tsx` |
| 深色主题 | `next-themes` + `hooks/use-theme.ts` | — |
| SQLite 数据库 | `backend/app/db/` | studio.db + 每项目 novel.db，35 张表 |
| **并发策略** | `backend/app/db/session.py` | WAL + `synchronous=NORMAL` + 单写进程（Rust 不直连库）+ 复制前 `wal_checkpoint` |
| 项目创建/删除/打开/复制 | `api/routes/projects.py` | 7 个项目端点（含 `duplicate`、软删/硬删） |
| 项目目录管理 | `core/paths.py`、`project_service.py` | 标准目录树 + 路径沙箱 |
| Python Sidecar 启动机制 | `src-tauri/src/sidecar.rs` | 动态端口、令牌、日志泵、进程组 |
| FastAPI 健康检查 | `api/routes/health.py` + `sidecar.rs` | `/api/health` + 45s 轮询 |
| **迁移执行器** | `app/db/migrations.py` | 拒绝降级、迁移前在线备份、单事务、逐步打戳 |
| 后端测试 | `backend/tests/` | 7 个测试文件 + `conftest.py` |
| 前端测试 | `desktop/src/lib/*.test.ts` | vitest |

实测通过（2026-11-16，全新数据目录）：

- 应用可启动，`GET /api/health` 返回 200
- `POST /api/projects` 返回 201，中文项目名正确往返
- `PUT` 递增 `row_version`，过期 `row_version` 返回 409；`"name": null` 返回 422
- `DELETE` 软删除后 404，`DELETE ?hard=true` 移除目录
- `POST /api/projects/{id}/duplicate` 返回 201，目录内容一致（复制前做了 WAL checkpoint）
- 无令牌 401、未知项目 404、空名 422、未知路由 404、错误方法 405、异常 500 均返回 JSON 信封
- 全新库启动自动写入 `app_meta.schema_version`；库版本高于本构建时拒绝打开

### 2.2 阶段 1 验收判据

| 判据 | 期望 | 结果 |
|---|---|---|
| 桌面应用能启动并显示主界面 | 窗口出现，无白屏 | ✅ |
| 能创建 ≥2 个项目 | 列表可见，`NovelProjects/` 下有对应目录 | ✅ |
| 重启应用后项目仍在 | 列表持久 | ✅ |
| 复制项目可用 | 201 且目录内容一致 | ✅ |
| 后端测试全绿 | 0 失败 | ✅ |
| 迁移不损坏老库 | 拒绝降级 + 迁移前备份 | ✅ |

一键复现：`backend/.venv/Scripts/python.exe scripts/smoke_api.py`
（输出 `SMOKE PASSED: all checks green`）。

## 3. 阶段 2：小说编辑器与 AI 写作 🔄 进行中

**交付**：小说创作系统。拆成两半，各自可独立验收。

- **2a 编辑器链路** ✅ 完成
- **2b AI 可审计** 🔄 进行中：AI 能力已落地，但**记忆与血缘断裂**（摘要不写、AI 产出的版本身份丢失）

### 3.1 阶段 2a 已完成（编辑链路）

| 任务 | 落点 | 证据 |
|---|---|---|
| 卷管理（增/删/改/排序） | `api/routes/novels.py` + `services/novel_service.py` | 删卷时章节 `volume_id` 置 NULL，不删章节 |
| 章节管理（增/删/改/排序） | 同上 | `PUT/DELETE /chapters/{id}`、`POST /chapters/reorder` |
| 章节树 UI | `components/editor/chapter-tree.tsx` | 卷分组、状态色点、字数、行内删除 |
| 正文编辑 | `components/editor/chapter-editor.tsx` | **有意使用 `<textarea>`**，见 §3.4 |
| 自动保存 | 同上 | 停止输入 1200 ms 落库；`Ctrl/Cmd+S`；切章/关窗 flush；`beforeunload` 兜底 |
| 乐观并发 | 同上 + `novel_service.update_chapter` | 保存带 `row_version`，409 时提示并重新拉取 |
| 字数统计 | `app/utils/text.py::count_words` + `desktop/src/lib/utils.ts::countWords` | 两侧算法逐字镜像：CJK 每字 1，拉丁/数字连续段 1 |
| 章节版本管理 | `routes/novels.py` + `version-history-dialog.tsx` | 列表、强制快照、恢复；恢复前先存档当前正文 |
| 模型配置（含加密密钥） | `routes/model_configs.py` + `core/keystore.py` | 密钥写-only，存 `<data_dir>/secrets.json`（Windows DPAPI） |
| 模型配置 UI | `components/settings/model-config-panel.tsx` | 列表、新建、删除、设为默认 |
| 首次启动模板 | `model_config_service.ensure_default_model()` | 自动插入「本地 / OpenAI 兼容」模板 |
| 前端路由 | `router.tsx` | `/editor`（`?project=`）、`/projects/:projectId/editor` |

### 3.2 阶段 2b 已实现（AI 层）

| 任务 | 落点 | 证据 | 缺口 |
|---|---|---|---|
| LLM 适配器抽象 | `ai/llm/base.py:30-61` | `complete`/`stream` 抽象 + token 估算（:15-27） | — |
| OpenAI 兼容实现 | `ai/llm/openai_compatible.py:46,163-187` | httpx POST + 状态码映射 | 只支持 `/chat/completions`；Anthropic/Gemini 原生被显式拒绝（`registry.py:25-40`） |
| 重试与错误分类 | 同上 `:37,147-161,216-232` | 指数退避 + 可重试码；401 不重试 | — |
| SSE 流式输出 | `openai_compatible.py:234-289` + `services/ai_service.py:128-195` + `routes/ai.py:43-69` | `data:` 逐帧 + `[DONE]`；前端 `lib/ai.ts:33-149` | 无分块续传 |
| 主备降级链 | `ai/llm/registry.py:69-128` | 按 `fallback_ids` 建链；流式已 emitted 不降级 | **零测试**（`T-06`） |
| Prompt 模板 | `ai/prompts/builtin.py:52-164`（7 个）+ `prompts/service.py:49-144` | 内置 seed + DB 优先 + 变量渲染 | 无升版端点，version 恒为 1（`T-05`） |
| 生成任务记账 | `services/ai_service.py:349-434` | token/成本/失败/耗时写 `generation_tasks` | 无 pruner（`T-15`） |
| 提示词版本关联 | `ai_service.py:368,410-415` | 记录 `prompt_version` 与 `prompt_key` | 不存模板正文快照（`T-14`） |
| 后端端点 | `api/routes/ai.py` | `/ai/operations`、`/ai/prompts`、`/ai/{op}`、`/ai/{op}/stream`、`/ai/tasks` | `/ai/tasks/{id}` 未暴露（`T-13`） |
| 前端 SSE 客户端 | `desktop/src/lib/ai.ts:33-149` | fetch + 帧解码 + `AbortSignal` + 断帧容错 | — |
| AI 助手面板 | `components/editor/ai-panel.tsx` | 续写/扩写/改写/润色/审稿 + 预览 + 停止 + 应用 | 无拒绝/丢弃（`T-08`）；`outline`/`write` 无入口（`T-09`） |
| 测试 | `tests/test_ai_adapters.py`(13) + `test_ai_stream_e2e.py`(2) + `desktop/src/lib/ai.test.ts`(5) | 适配器/重试/SSE/记账 | 降级链、PromptService、上下文组装零覆盖 |

### 3.3 阶段 2b 剩余工作

| 任务 | 编号 | 说明 |
|---|---|---|
| **章节摘要写入** | `T-01` | `chapter_summaries` 只有读没有写 → 「前情提要」恒为空。**阶段 3 的前置** |
| **AI 产出血缘** | `T-02` | 采纳后写 `chapter_versions.source="ai"` + `task_id`；当前全记成 `user` |
| 结构化输出 | `T-03` | `ai_service.py:343` 硬编码 `json_mode=False`，无 JSON 解析/修复/降级 |
| 大纲落库 | `T-04` | `outlines` 是死表 |
| Prompt 升版 + 测试 | `T-05` | 无 `PATCH /api/ai/prompts/{key}`，version 恒 1 |
| 降级链测试 | `T-06` | 主模型 5xx → 备模型成功；流式已 emitted 不降级 |
| 按 Agent 绑模型 | `T-07` | `agent_configs` 零读写方 |
| 拒绝/丢弃交互 | `T-08` | 面板只能靠关闭清空，结果不持久化 |
| `outline`/`write` 入口 | `T-09` | 后端有操作，UI 无入口 |
| 消费只读端点 | `T-10` | `/operations`、`/prompts`、`/tasks` 前端零调用 |
| 上下文 Token 预算 | `T-12` | 现在只有字符截断（`ai_service.py:200-205`） |
| TXT/DOCX 导入导出 | `T-17` | `append_chapters` 无调用方；`python-docx` 依赖在册未用 |
| 查找替换 | `T-20` | 编辑器无实现，撤销依赖原生 |
| Tiptap 富文本 | `T-23` | **决策见 §3.4：V1.x 不做** |

### 3.4 为什么编辑器用 `<textarea>` 而不是 Tiptap（决策定稿）

这是**有意的技术选择**，不是遗漏，也不再需要「补 Tiptap」。

1. **保真**：`chapters.content` 是纯文本。Tiptap 输出 HTML，往返一次就要面对「HTML → 纯文本 → HTML」的有损转换。
2. **输入法**：中文创作依赖 IME 组合输入。组件用 `onCompositionStart` / `onCompositionEnd` 显式处理 composing，
   避免「拼音未上屏就触发保存」；`contenteditable` 在部分 WebView 上不一致。
3. **性能**：几十万字章节在 `<textarea>` 里滚动是原生行为；富文本编辑器要维护整棵文档树。
4. **可演进**：`chapters.content` 存储格式不变，将来要加富文本只需换组件，不需要迁移数据。
   `@tiptap/*` 依赖已安装但 `desktop/src` 里零引用，留待需要时接入。

> 结论：**V1.x 保持纯文本编辑器**。若将来要接 Tiptap，必须先解决存储格式与纯文本的互转保真问题。

### 3.5 阶段 2 验收判据

| # | 判据 | 结果 |
|---|---|---|
| ① | 新建小说 → 3 卷 10 章 → 全部可编辑 | ✅ |
| ② | 重启后正文与版本历史完整 | ✅（`test_novels.py` 覆盖） |
| ③ | 配置 OpenAI 兼容端点，续写 1 章成功且流式可见 | ✅（`test_ai_stream_e2e.py` 全链路） |
| ④ | 写一章关闭重开，`chapter_summaries` 有该章一行 | ❌ 待 `T-01` |
| ⑤ | 采纳 AI 结果后版本列表出现 `source="ai"` 且带 `task_id` | ❌ 待 `T-02` |
| ⑥ | 改过 prompt 后 `GET /api/ai/prompts` 出现 `version=2` | ❌ 待 `T-05` |
| ⑦ | 导出 DOCX 用 Word 打开内容格式一致 | ❌ 待 `T-17` |

**结论**：①②③ 已达成，④⑤⑥⑦ 未达成。阶段 2 按「2a 完成 / 2b 进行中」记录。

## 4. 阶段 3：小说记忆和 RAG

**交付**：长篇索引系统。

**开工前置（P0，缺一不可）**：

1. **摘要管道可用**（`T-01`）：RAG 的输入是摘要 + 人物状态 + 原文块，摘要在空，检索建在空数据上。
2. **Token 预算绑定模型窗口**（`T-12`）：以所选模型的 `context_window` 为基准自动缩放，而不是按字符截断。
3. **标定值确定**：recall@k 的 X% 与 token 下降的 Y%，开工前写进本节。
4. **合成测试语料**：脚本生成带已知实体/伏笔/时间线的长文本（天然带标注答案），不依赖真实网文的版权与标注。

| 任务 | 验收信号 |
|---|---|
| 知识块结构 + 文本解析与切分 | `knowledge_chunks` 写入带 `chunk_type` 与原文偏移；章/场景/段落三级切分 |
| 元数据提取 | 人物/事件/地点/伏笔抽取入库 |
| FTS5 全文索引 | 关键词检索可用（需建虚拟表，当前只有普通表） |
| Embedding 模型 + sqlite-vec | 向量写入 `embeddings` 并可向量检索（当前为 BLOB 表，需改虚拟表） |
| 混合检索 + Reranker | 三路融合，有 rerank 打分 |
| 原文片段读取 | 返回可溯源到章节/偏移的片段 |
| 章节摘要（L1） | `chapter_summaries` 自动生成（依赖 `T-01`） |
| 人物/事件/伏笔/时间线提取 | 对应表写入（当前 8 张人物世界观表零读写方，见 `T-18`） |
| 人物状态记录（L3） | `character_states` 带 `event_id` 来源 |
| 上下文组装 + Token 预算 | 以模型 `context_window` 为基准动态缩放 |
| 检索记录 | `retrieval_logs` 记录漏斗与耗时 |
| 增量索引 | 改章后只重算变化块（`content_hash` 比对） |
| 索引状态监控 + 重建 | 状态可见，可一键重建 |

**本阶段必须同时补齐**（P0）：

- **实体消歧**：别名 → 主实体对齐，消歧决定可人工裁决（原计划未写，长篇小说核心难题）
- **Embedding 迁移预案**：换模型触发全量重建，期间降级为纯 FTS5；向量记录带 `embedding_model`+`version`，
  版本不符视为失效
- **删除级联**：软删除 + 检索默认排除已删 + 向量/关系级联清理

**验收判据**：① 导入 500 章合成语料，索引构建完成；② 按人物/事件/关键词/语义四类查询均有正确命中；
③ recall@k ≥ X%；④ 同等质量下 token 成本较滑动窗口基线下降 ≥ Y%；
⑤ 修改 1 章后仅该章相关块被重算（增量索引 ≤ 30s）；⑥ 删除 1 章后检索不再返回其内容。

设计文档：[rag.md](rag.md)。当前状态：**表结构就绪（35 张里记忆相关 5 张），检索代码零实现**。

## 5. 阶段 4：Agent 和工作流

**交付**：自动创作引擎。

**前置（P1）**：

- **表归属先理清**：`generation_tasks` / `task_logs` 已被 AI 层（阶段 2b）占用，
  工作流要复用还是另建 `workflow_runs` 必须先定；`workflow_definitions` / `workflow_nodes` /
  `workflow_edges` / `workflow_runs` / `workflow_node_runs` **5 张表当前不存在**（`T-19`）。
- `@xyflow/react` 已安装但 `desktop/src` 零引用。

**必须产出**：Agent 基础架构（9 类 Agent 可注册、可绑定模型，见 `agent_configs`）·
总编剧/大纲/写作/人物/剧情/连贯性/润色/记忆 Agent（各自独立 system prompt）·
章节自动生成 · 自动记忆更新 · 自动剧情审核（问题入「受影响内容审核」队列）·
React Flow 节点编辑 · 工作流保存执行 · 任务状态更新/重试/日志/暂停恢复。

**验收判据**：跑一条工作流完成大纲生成 → 章节生成 → 连贯性检查 → 记忆更新，中途暂停再恢复，
结果与不中断一致。

设计文档：[workflow.md](workflow.md)。当前状态：表不存在、UI 依赖零引用、无 Agent 编排层。

## 6. 阶段 5：剧本和故事板

**交付**：故事板系统。

**前置（P0）**：**建 6 张表**——`storyboard_scenes` / `storyboard_shots` / `media_assets` /
`media_versions` / `voice_profiles` / `render_jobs`（原计划 §12.8）；媒体服务能力矩阵实测
（2–3 家的时长/分辨率/参考图/价格/并发/出片率）；角色一致性 PoC（同一角色 10 个镜头的通过率）。

**必须产出**：小说转剧本、剧本上传解析、场景拆解、镜头拆解、镜头卡片编辑排序、
人物与场景视觉资料、镜头 Prompt、生成状态、人工审核、单镜头重 roll、故事板版本管理。

**验收判据**：上传剧本 → 自动生成场景与镜头结构 → 逐镜头编辑审核通过。

## 7. 阶段 6：AI 媒体生成

**交付**：媒体生产系统。

**前置**：FFmpeg **LGPL 构建**（不启用 GPL 组件）与许可确认；打包体积预算；
`media_assets`/`render_jobs`/`export_records` 等表（见阶段 5 前置）。

**必须产出**：图片/视频/TTS 模型接口、图片与视频生成任务、角色参考图、镜头视频生成、
音频与字幕生成、音频时间轴、FFmpeg 集成、视频拼接、转场、字幕合成、背景音乐、成片预览与导出。

**验收判据**：逐镜头生成素材 → 合成完整 MP4 → 可正常播放。

> 任务幂等：媒体任务带幂等键（`shot_id` + prompt 版本 + 参数哈希），重发前先查第三方任务状态，
> 否则断点续跑会重复计费。

## 8. 阶段 7：测试和打包

**交付**：MVP 安装包。

| 类别 | 任务 |
|---|---|
| 功能测试 | 多项目管理、大规模章节加载、长篇检索、增量索引、章节版本恢复 |
| 异常测试 | AI 生成异常、任务中断恢复、工作流执行失败、视频生成失败、合成失败 |
| 性能优化 | 前端渲染（`@tanstack/react-virtual` 已装未用）、数据库查询、素材缓存 |
| 工程化 | 日志管理、错误提示、Windows 打包与安装程序、用户文档 |

**验收基线（可执行，不接受"功能正常"这类描述）**：

| # | 命令（cwd） | 期望 |
|---|---|---|
| 1 | `backend\.venv\Scripts\python.exe -m pytest -q`（backend） | `60 passed` |
| 2 | `pnpm test`（desktop） | `Tests 29 passed (29)` / 4 个文件 |
| 3 | `pnpm typecheck`（desktop） | 无输出 |
| 4 | `pnpm build`（desktop） | `✓ built`，产出 `dist/` |
| 5 | `backend\.venv\Scripts\python.exe scripts\smoke_api.py`（仓库根） | `SMOKE PASSED: all checks green` |
| 6 | `cargo check`（desktop/src-tauri） | `Finished`，无 error |

> 基线数字只在 [../KnowledgeBase/INDEX.md](../KnowledgeBase/INDEX.md) §验证 与本节维护（2026-11-16 实跑：60 / 29）。
> `T-24` 的剩余部分不是数字，而是**没有 E2E 黄金路径与 500 章合成语料**。

**性能量化目标**（阶段 7 标定，先给初始靶子）：

| 指标 | 目标 |
|---|---|
| 冷启动到可交互 | ≤ 5s |
| 500 章项目打开 | ≤ 3s |
| 混合检索 P95 | ≤ 1s |
| 单章增量索引 | ≤ 30s |

**验收判据**：可安装的 Windows 桌面软件，核心创作流程完整运行。

## 9. 风险与对策

### 9.1 已偿还（不再是风险，保留证据）

| 原风险 | 现状 | 证据 |
|---|---|---|
| 软件异常退出 / 数据损失 | 已解决 | 自动保存 1200 ms 防抖 + 切章/关窗 flush + `beforeunload` |
| 迁移把老项目打不开 | 已解决 | `db/migrations.py`：拒绝降级 + 迁移前在线备份 + 单事务 |
| Python sidecar 装完打不开 | 已解决 | 动态端口 + 令牌 + 日志泵 + 45s 轮询 + 失败诊断 |
| SQLite 并发写锁 | 已解决 | WAL + 单写进程 + 复制前 checkpoint（`db/session.py:3-7,181-190`） |

### 9.2 仍然成立

| 风险 | 影响 | 对策 | 当前状态 |
|---|---|---|---|
| LLM 忘记剧情 / 长篇逻辑错误 | 前后矛盾 | 分层记忆（L0–L4）+ RAG | 表结构就绪，逻辑未实现 |
| 人物状态错误 / 人设不一致 | 角色崩坏 | 状态历史 + 事件来源 | `character_states` 就绪，零读写方 |
| 向量检索不准确 | 喂错资料 | 混合检索 + Reranker | 未实现 |
| 上下文过长 / Token 成本过高 | 报错或超预算 | 以 `context_window` 为基准动态缩放 | 只有字符截断（`T-12`） |
| 模型输出不稳定 / JSON 结构错误 | 解析失败 | JSON 模式 + 校验 + 重试 + 降级 | 未实现（`T-03`） |
| API 不稳定 / 任务失败 | 流水线停摆 | 超时、重试、断点恢复、主备 fallback | 重试与降级已实现，降级零测试（`T-06`） |
| 视频生成慢 / 任务积压 | 队列阻塞 | 异步队列 + 并发限制 + 优先级 | 未实现 |
| UI 卡顿 | 体验差 | 虚拟化 + 异步渲染 | `@tanstack/react-virtual` 已装未用 |
| 索引更新失败 / 记忆过期 | 检索失真 | 索引版本 + 任务恢复 | `indexed_hash` 脏标记就绪，消费方未实现 |
| 章节修改引发冲突 | 后续剧情不一致 | 依赖关系 + 受影响内容审核队列 | 未实现 |
| 重复计费（任务重发） | 直接经济损失 | 幂等键 + 重发前查第三方状态 | `generation_tasks.idempotency_key` 列就绪，查询逻辑未实现 |
| FFmpeg 许可问题 | 无法商用分发 | 选 LGPL 构建，不启用 GPL 组件 | 未评估 |
| 本地模型（BGE-M3）部署 | CPU 机器不可用 | 量化选型：本地小模型 / ONNX / API embedding | 未选型 |
| 跨镜头角色一致性 | 核心卖点不成立 | 定妆图锁定 + 图生视频 + 失败重 roll | 未 PoC |

### 9.3 新增风险（原计划未写）

| 风险 | 影响 | 对策 |
|---|---|---|
| **模型能力差异**（窗口/JSON 可靠性/中文文风/单价） | 换模型即塌方 | 模型能力画像进配置界面；预算以画像中的窗口为基准 |
| **Embedding 换代** | 向量空间不互通，检索静默错乱 | 向量带模型+版本戳；换模型触发全量重建，期间降级纯 FTS5 |
| **实体消歧**（林凡/小凡/那少年） | 记忆越攒越错，比没有记忆更糟 | 别名 → 主实体对齐表；新增人物时提示合并；决定可人工裁决 |
| **AI 产出无血缘** | 无法审计"这段谁写的" | 采纳路径写 `source="ai"` + `task_id`（`T-02`） |

## 10. 版本范围控制（MVP 收敛）

严格按版本切分，防止范围蔓延。

### 10.1 定位取舍（2026-11-16 定稿）

**产品定位收窄为「个人创作者 + 单机」**。原计划把「小说工作室和内容制作团队」列为目标用户，
但架构是纯本地单机、明确不做协作，两者矛盾。团队需求列 V3.0 展望，不在 V1.x 范围内。

### 10.2 V1.0 — AI 长篇小说创作

Tauri 2 桌面框架、项目管理、小说编辑器、LLM 接入、大纲生成、正文生成、
人物管理、章节摘要、FTS5、向量检索、混合检索、RAG 上下文组装、
记忆增量更新、章节版本管理、连贯性检查。

**验收目标**：用户可以持续创作一部数百章的小说，LLM 能通过索引获取正确的历史内容，
并辅助保持剧情一致性。

对应阶段：1、2、3 + 阶段 4 的连贯性检查部分。

### 10.3 V1.5 — AI 故事板与工作流

小说转剧本、剧本解析、场景拆解、镜头拆解、故事板编辑、角色视觉资料、
工作流可视化、任务状态追踪、批量任务调度。

对应阶段：4、5。

### 10.4 V2.0 — AI 影视化生产

AI 图片生成、AI 视频生成、TTS 配音、自动字幕、镜头视频管理、视频时间线、
FFmpeg 合成、成片导出、自动化影视生产工作流。

对应阶段：6。

### 10.5 明确不做（V1.x 范围内）

| 项 | 原因 | 处置 |
|---|---|---|
| 自由拖拽的多轨时间线 | 属视频编辑软件级工程量 | V2.0 降级为「镜头顺序 + 转场 + 音量」结构化列表 |
| 多人协作 / 审批 / 资产共享 | 纯本地单机 | 定位为个人创作者；团队需求列 V3.0 |
| 云端同步 | 本地优先 | 不做 |
| 自动更新器 | 非 MVP 必需 | V1.0 只做版本检查提示 |
| 国际化（i18n） | 非 MVP 必需 | V1.0 只做中文界面，文案走资源文件避免硬编码 |
| Tiptap 富文本编辑器 | 纯文本存储保真、IME、性能 | V1.x 用 `<textarea>`，理由见 §3.4 |
| WebSocket | 生成流已用 SSE 满足需求 | 生成流走 SSE；任务状态用轮询，不另建 WS（原计划 §13.9 的 4 个 WS 接口作废） |

## 11. 待决事项

| 事项 | 需要谁定 | 截止 |
|---|---|---|
| 混合检索命中率 X% 与 token 下降 Y% 的标定值 | 技术 | 阶段 3 开工前 |
| Embedding 选型（本地 BGE-M3 / ONNX 量化 / API） | 技术 | 阶段 3 开工前 |
| `generation_tasks` 由 AI 层与工作流共用还是拆分 | 技术 | 阶段 4 开工前 |
| FFmpeg 构建与许可 | 法务 + 技术 | 阶段 6 前 |
| 图片/视频服务选型 | 技术 | 阶段 5 前 |
| 性能指标最终数值 | 技术 | 阶段 7 标定 |

## 12. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-11-16 | 建立工作版计划；核对阶段 1 实际进度；补入不足清单中的 P0 前置项 |
| 2026-11-16 | 阶段 1 → ✅ 完成（duplicate 500、`name: null` 500、docs 需鉴权、版本号覆盖均已修复并复测）；新增 [rag.md](rag.md) 与 [workflow.md](workflow.md) 设计文档 |
| 2026-11-16 | **按代码现状大改**：① 阶段 2 拆为 2a（编辑器，✅）/ 2b（AI 可审计，🔄），补入 AI 层已实现清单与证据；② 原「AI 部分完全未开工」的判断作废；③ 阶段 3 增加开工前置（摘要管道 + Token 预算绑定 `context_window` + 标定值 + 合成语料）；④ 阶段 4/5/6 补"缺哪些表"；⑤ 阶段 7 验收改为可执行命令表；⑥ 风险表重写为「已偿还 4 / 仍成立 14 / 新增 4」；⑦ 定位收窄为个人创作者；⑧ Tiptap 与 WebSocket 明确不做并写入 §10.5；⑨ 新增 [plan-reconciliation.md](plan-reconciliation.md) 记录对账过程 |
