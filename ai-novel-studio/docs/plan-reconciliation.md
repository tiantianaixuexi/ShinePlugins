# 原计划 × 代码现状：对账与补全

> 对账日期：2026-11-16
> 对账对象：《AI Novel Studio 项目完整开发计划》23 节（需求方持有）
> 依据：**仓库实际代码**，不是文档转述。凡标 △ 的是推断，标「待确认」的是缺证据。
> 相关文档：[development-plan.md](development-plan.md)（工作版，已按本文结论于同日重写）、
> [../KnowledgeBase/05_Plan/CurrentStatus.md](../KnowledgeBase/05_Plan/CurrentStatus.md)（状态真源）、
> [../../AI_Novel_Studio_Plan_Gaps.md](../../AI_Novel_Studio_Plan_Gaps.md)（上一轮纯文档评审）

---

## 0. 结论速览

原计划的**骨架成立**：分层记忆 L0–L4、混合检索、7 阶段划分、V1.0/V1.5/V2.0 收敛、12 条执行原则都不用改。
问题在三个系统性偏差：

| # | 偏差 | 后果 | 处置 |
|---|---|---|---|
| A | **阶段 1–2 完成度被严重低估** | 计划把「LLM 接入」排在第 3–5 周之后，实际已实现；进度判断全错，容易重复做已完成的东西 | 按 [CurrentStatus.md](../KnowledgeBase/05_Plan/CurrentStatus.md) 重排阶段 |
| B | **阶段 3 的前置条件没写**（摘要管道） | RAG 建在空数据上：`chapter_summaries` 只读不写，「前情提要」永远为空 | 摘要写入提前到阶段 2 收口（`T-01`） |
| C | **把「表已设计」当成「可开工」** | 35 张表里 **21 张零读写方**，按计划直接进阶段 3/4 会边写边发现底层是空的 | 每阶段开工前先过「读写方清单」 |

另一个必须先解决的事实问题：**`docs/development-plan.md` §3.2 写「AI 部分完全未开工」，与代码严重不符**
（`backend/app/ai/` 10 个 py、`api/routes/ai.py` 5 个端点、20 条 AI 测试：Python 15 + 前端 5）。这是 `T-16`。
> 该文已于同日按本文结论重写，此段保留为「当时为何要重写」的记录。

本轮的补全产出：**8 条新任务 `T-17`…`T-24`**，映射见 §4。

---

## 1. 逐节对账

图例：✅ 与计划一致/更好 · 🔄 部分实现 · ⬜ 未开始 · ⚠️ 计划本身有问题

| § | 原计划要求 | 现状（证据） | 判定 |
|---|---|---|---|
| 1.1 核心目标 12 条 | 构思→长篇→索引→剧本→故事板→媒体→合成 | 1–6、12 部分可达；7–11 未开始 | 🔄 |
| 1.3 目标用户 | 含「小说工作室和内容制作团队」 | 纯本地单机，无协作/审批/资产共享 | ⚠️ 定位自相矛盾 |
| 2.1 导航 9 个一级菜单 | 工作台/项目/创作/知识库/世界观/故事板/工作流/视频/设置 | 已落地 4 个（工作台、项目、编辑器、设置），其余为 `placeholder` 页 | 🔄 4/9 |
| 3.1 总体架构 | Tauri 2 + Rust + FastAPI sidecar | 一致；sidecar 动态端口 + 令牌 + 日志泵 + 45s 健康检查均已实现 | ✅ |
| 3.3 技术栈 | SQLite + FTS5 + sqlite-vec + BGE-M3 + BGE Reranker | WAL + 单写进程已实现（`db/session.py:3-7`）；`sqlite-vec` 加载就绪但**检索零实现**；FTS5 虚表未建 | ⚠️ 见 §2.1 |
| 3.5 Sidecar 注意事项 6 条 | 生命周期/端口/令牌/密钥 | 全部实现（`desktop/src-tauri/src/sidecar.rs`；密钥 DPAPI 存 `secrets.json`） | ✅ 超出计划细节 |
| 4.3 项目管理 12 项 | 建/开/关/删/复制/导入/导出/自动保存/自动备份/恢复/统计/资源 | 已实现 9 项（含复制、软删/硬删、row_version 并发）；**缺导入/导出/自动备份/项目恢复** | 🔄 9/12 |
| 5.2 正文编辑 17 项 | 含 Tiptap、导入导出、查找替换、撤销重做 | 卷章 CRUD/排序/自动保存/字数/版本齐；**编辑器是有意用 `<textarea>`**；无导入导出、无查找替换 | 🔄 见 §2.7 |
| 5.3 AI 写作操作 13 种 | 续写/扩写/缩写/改写/润色/文风/情绪/对白/冲突/细节/剧情/多版本/自定义 | 7 个 operation（5 个有 UI 入口）；**无多版本、无自定义 Prompt 入参** | 🔄 7/13 |
| 6 记忆系统 L0–L4 | 5 层 + 切分 + 混合检索 + 上下文组装 + 增量索引 + 检索记录 | 35 张表就绪；**切分/embedding/FTS5/检索/检索日志全未实现**；`chapter_summaries` 只读 | ⬜ 0% |
| 6.6 Token 预算 8 条优先级 | 大纲→人物→世界观→原文→伏笔→压缩 | 只有「最近章节截断」（`ai/services/ai_service.py:200-205`），未绑定 `context_window` | 🔄 见 §2.4 |
| 6.7 检索记录 10 项 | 条件/命中/分数/Token/模型/版本 | `retrieval_logs` 表存在、无写入方；`generation_tasks` 记了 token 与模型 | 🔄 |
| 7.1 模型接入 | 统一 Adapter + 项目级/任务级 + 主备 | Adapter ✅、重试 ✅、流式 ✅、主备降级 ✅（**零测试**）；项目级 ✅；**按 Agent 绑定 ❌** | 🔄 |
| 7.2 九个 Agent | Director/Outline/Writing/Character/Plot/Consistency/Polish/Memory/Review | **无 Agent 编排层**；只有 7 个 prompt 模板按单次 operation 调用 | ⬜ |
| 7.5 分段生成 10 步 | 大纲→检索→人物状态→组装→场景计划→分段→衔接→整章检查 | 单次整章调用，无分段、无衔接检查 | ⬜ |
| 7.6 自动质量检查 10 项 | 输出问题 + 证据，不改正文 | `review` 模板产出文本；结构化判定（JSON）未实现 | ⬜ |
| 8 人物与世界观 | 人物状态历史 + 关系图 + 8 类世界观表 | `characters`/`character_states`/`relationships`/`locations`/`factions`/`items`/`abilities`/`world_rules` **8 张表全零读写方**；无 API、无服务层、无页面 | ⬜ 0% |
| 9 故事板 | 剧本解析→场景→镜头→卡片 | **表都没建**（35 张里无 `storyboard_*`） | ⬜ 0% |
| 10 工作流 | React Flow UI 与执行引擎分离 + 状态机 + 10 个模板 | `@xyflow/react` 已装**零引用**；`workflow_*` 5 张表不存在；`generation_tasks`/`task_logs` 已被 AI 层占用 | ⬜ 0% |
| 11 媒体生产 | 图片/视频/TTS/字幕/FFmpeg 合成 | 0%；无 `media_*` / `render_jobs` / `export_records` 表 | ⬜ 0% |
| 12 数据库 | 8 大类共 48 张表 | **实际 35 张**（`novel.py` 27 + `studio.py` 8）：与计划重合 32，缺 16（`project_settings`/`project_assets`、`generation_results`/`context_snapshots`、`workflow_*` 5、`storyboard_*`/`media_*` 7），另有 3 张计划外（`app_meta`/`project_meta`/`timeline_entries`） | 🔄 32/48 |
| 13 API 9 组 | 项目/小说/AI/检索/人物/故事板/工作流/媒体 + 4 个 WS | 5 组（projects/novels/ai/model_configs/system）+ SSE；**无 WS** | 🔄 5/9 见 §2.6 |
| 14 目录结构 | `app/{api,core,db,models,schemas,services,ai,tasks}` | 一致，但 **`tasks/` 不存在**（任务调度未落地） | 🔄 |
| 15 七阶段 16 周 | 阶段 1–7 | 阶段 1 ✅；阶段 2 完成度**高于**计划（AI 层已实现），但记忆/血缘断裂 | ⚠️ 见 §3 |
| 16 UI 页面 23 个 | 按阶段铺开 | 6 个页面目录 + `placeholder`；故事板/工作流/媒体/知识库页均无 | 🔄 6/23 |
| 17 非功能 | 性能/稳定/安全/扩展 | 安全 ✅（DPAPI 密钥、路径沙箱、令牌、CSP）；**性能与虚拟化未做**（`@tanstack/react-virtual` 装着未用） | 🔄 |
| 18 验收 6 组 | 功能测试清单 | 有 pytest 8 个文件 + vitest；**无 E2E、无 500 章语料、无性能基线**；两处文档的 pytest 数字不一致 | ⚠️ 见 §2.8 |
| 19 风险表 11 条 | 分层记忆/状态历史/混合检索/预算/重试… | 8 条仍成立；3 条已由代码解决（迁移、sidecar、自动保存），见 §2.3 | 🔄 |
| 20 版本范围 | V1.0 / V1.5 / V2.0 | 不需要改 | ✅ |
| 21 技术选型 | 汇总表 | 与 `package.json` / `requirements.txt` 一致；**唯 Tiptap 装了未用** | ⚠️ 见 §2.7 |
| 22 交付清单 17 项 | 安装包/源码/文档/测试报告/用户手册 | 目前可交付：源码 + Schema + 编辑器；其余未开始 | 🔄 |
| 23 执行原则 12 条 | 含「AI 自动生成结果不能直接覆盖用户正式内容」 | **当前违反**：AI 面板「替换全文/替换选中」直接改 draft 并保存，无 `source="ai"` 记录 | ⚠️ 见 §2.5 |

---

## 2. 补全项（原计划缺失或与现状冲突的部分）

### 2.1 阶段 3 的前提：摘要管道必须先于检索（P0）

原计划 §6.8 把「更新章节摘要」排在增量索引流程中间，读起来像检索的副产品。
实际 RAG 的输入是摘要 + 人物状态 + 原文块，**摘要没有写入方，整套记忆就是空的**。

- 现状：`ai_service.py:260-280` 已经在把摘要当「前情提要」注入 prompt，但全仓无 insert →
  `_recent_summaries` 恒返回 `[]`。
- 补全：阶段 2 收口前完成 `T-01`（摘要写入）+ `T-12`（上下文用摘要而非纯截断）。
- 判据：写完一章关闭重开，`chapter_summaries` 有该章一行。

### 2.2 「表已设计」不等于「可开工」：21 张零读写方的表（P0）

| 类别 | 表 | 状态 |
|---|---|---|
| 记忆 | `knowledge_chunks` `embeddings` `retrieval_logs` `memory_snapshots` `knowledge_relations` | 仅建表（`db/project_db.py` 只做 `count(*)`） |
| 小说结构 | `paragraphs` `chapter_summaries` `outlines` `scenes` | 仅建表 |
| 人物世界观 8 张 | `characters` `character_states` `relationships` `locations` `factions` `items` `abilities` `world_rules` | 仅建表 |
| 剧情 | `events` `event_participants` `timelines` `timeline_entries` `foreshadows` `foreshadow_relations` | 仅建表 |
| AI | `agent_configs` | 仅建表 |

- 补全：每阶段开工前先跑一遍「读写方清单」（`grep` 模型类名，看除 `models/` 外有没有引用）。
- 已转任务：`T-19`（人物世界观）、`T-21`（paragraphs）、`T-04`（outlines）、`T-07`（agent_configs）。

### 2.3 风险表需要按现状重写（P1）

原计划 §19 的 11 条里，**3 条已经不是风险**（代码已解决），**8 条仍然成立**，另有 **4 条新风险**没有写：

| 已解决（应从风险表移到「已偿还」） | 证据 |
|---|---|
| 软件异常退出导致数据损失 | 自动保存 1200ms 防抖 + 切章/关窗 flush + `beforeunload` |
| 迁移把老项目打不开 | `db/migrations.py`：拒绝降级 + 迁移前在线备份 + 单事务 |
| Python sidecar 装完打不开 | 动态端口 + 令牌 + 日志泵 + 45s 轮询 + 失败诊断 |

| 新风险（原计划没写） | 影响 | 对策 |
|---|---|---|
| **模型能力差异**（上下文窗口 / JSON 可靠性 / 中文文风） | 换模型即塌方 | 模型能力画像 + 预算以 `context_window` 为基准 |
| **Embedding 换代** | 换模型 → 全部向量失效 | 向量带模型+版本戳，不匹配即重建，重建期降级为纯 FTS5 |
| **SQLite 并发写** | `database is locked` | WAL + 写操作收敛到单写队列；Rust 侧不直连库 |
| **实体消歧**（林凡/小凡/那少年） | 记忆越攒越错 | 别名 → 主实体对齐表 + 人工裁决 |

（前三条在原计划评审文档里已提；这里的问题是它们**至今没进原计划的 §19**。）

### 2.4 Token 预算必须绑定模型窗口（P0）

原计划 §6.6 给了 8 条优先级规则，但没有「以当前所选模型的 `context_window` 为基准自动缩放」。
现状更弱：只有按字符数截断（`ai_service.py:200-205`）。

- 补全：`model_configs.context_window` 已存在，预算器读它；超窗时按 §6.6 的优先级压缩。
- 已转任务：`T-12`。

### 2.5 执行原则 6 当前是违反状态（P0）

原计划 §23 第 6 条「AI 自动生成结果不能直接覆盖用户正式内容」。
现状：`ai-panel.tsx:293-311` 的「替换全文/替换选中」直接改本地 draft，随后按普通保存落库，
`chapter_versions.source` 只会是 `user`，**没有"这是 AI 产出的"这条信息**。

- 补全：采纳路径写 `source="ai"` + `generation_tasks.id`，并提供"拒绝/丢弃"（`T-02`、`T-08`）。

### 2.6 实时通信：WS 还是 SSE，计划需二选一并写死（P2）

原计划 §13.9 要求 4 个 WebSocket（tasks / workflows / generation / render），实际实现是
**SSE（`EventSourceResponse`）+ 前端 fetch 流读取**，且已验证可用（含断帧容错、AbortSignal）。

- 补全：把「生成流用 SSE」写进计划；任务/工作流状态二选一——要么补 WS，要么明确用轮询，
  不要留 4 个 WS 接口悬空。已转 `T-22`。

### 2.7 编辑器格式：Tiptap vs `<textarea>` 必须在计划里定稿（P2）

原计划 §5.2/§21 写 Tiptap；实际实现是 `<textarea>`，理由（保真 / 中文 IME / 长文性能 / 存储格式不迁移）
写在 `development-plan.md` §3.3，但**原计划里没有这条决策**，后来人看到会以为要补 Tiptap。

- 补全：在 §5.2 与 §21 标注「V1.x 用纯文本 textarea，Tiptap 留作可选增强」。已转 `T-23`。

### 2.8 验收要可执行，不是清单（P0）

原计划 §18 是「测试内容/验收标准」的文字描述（"功能正常""能够合成完整视频"），不可回归。
现状更糟：同一份 README 内部就写着 `37 passed` 与 `44 passed` 两个值（**实际实跑为 60**）。

> 进度更新（同日）：数字已统一到 `KnowledgeBase/INDEX.md` §验证 与 `development-plan.md` §8（pytest 60 / vitest 29），
> 本条剩余的部分是「没有 E2E 黄金路径、没有 500 章合成语料」，仍在 `T-24`。

- 补全：每条验收给「命令 + 期望输出/指标」，优先覆盖——项目 CRUD、章节版本回退、AI 流式（已有）、
  摘要写入、检索 recall@k、索引重建、断点恢复、FFmpeg 产物可播放。
- 已转任务：`T-24`。

### 2.9 定位取舍（P1）

§1.3 写「小说工作室和内容制作团队」，§20 又是纯本地单机、明确不做协作。
补全：二选一并写进 §1.3——(a) 收窄为「个人创作者 + 单机」，团队需求列 V3.0；
(b) 补最小协作（项目交接包：导出/导入 + 版本交接）。**建议 (a)**，成本最低。

---

## 3. 修正后的阶段计划

只写与原计划**不同**的部分；未列出的阶段/任务保持原样。

| 阶段 | 原计划 | 修正后 |
|---|---|---|
| 1 桌面框架 | 第 1–2 周 | ✅ 已达成，含迁移执行器与 sidecar 运维（原计划只在 §3.5 提注意事项） |
| 2 编辑器 + AI | 第 3–5 周，含 Tiptap/导入导出/预览接受 | 🔄 **拆成 2a / 2b**：2a 编辑器（已完成，Tiptap 改为 textarea 决策）；2b AI 可审计（`T-01`–`T-06`，含摘要管道、AI 版本身份、结构化输出、Prompt 升版、降级测试） |
| 3 记忆与 RAG | 第 6–8 周 | ⏸ **前置**：`T-01` 摘要管道、`T-11` 检索；开工前先定 X%（recall@k）与 Y%（token 下降） |
| 4 Agent 与工作流 | 第 9–10 周 | 修正：先做 Agent 编排层（9 个角色），再做 React Flow；`generation_tasks` 已被 AI 层占用，#需先理清表归属 |
| 5 故事板 | 第 11–12 周 | 前置：建 `storyboard_*` 表（原计划 6 张）+ 媒体服务能力矩阵实测 |
| 6 媒体生产 | 第 13–14 周 | 前置：FFmpeg LGPL 构建与许可；`media_*` 表 4 张 |
| 7 测试打包 | 第 15–16 周 | 修正：验收基线从阶段 1 就持续维护（`T-24`），不堆到最后 |

### 阶段 2b 验收判据（可执行）

| # | 命令 / 操作 | 期望 |
|---|---|---|
| ① | `pytest -q`（backend） | 全绿，新增 ≥8 用例 |
| ② | `pnpm test` + `pnpm typecheck`（desktop） | 全绿 / 无输出 |
| ③ | 写一章 → 关闭重开 | `chapter_summaries` 有该章一行 |
| ④ | AI 面板生成 → 应用 | `chapter_versions` 出现 `source=ai` 且带 `task_id` |
| ⑤ | `GET /api/ai/prompts`（改过模板后） | 出现 `version=2` |

---

## 4. 缺口 → 任务映射

账本：[`../KnowledgeBase/05_Plan/TaskRegister.md`](../KnowledgeBase/05_Plan/TaskRegister.md)。
`T-01`…`T-16` 为本轮之前已登记；下表是本轮补全新增的 8 条。

| 任务 | 优先级 | 缺口 | 对应原计划节 |
|---|---|---|---|
| `T-17` | P1 | TXT/DOCX/Markdown 导入导出全未实现（`append_chapters` 无调用方） | §5.2、§15.2 |
| `T-18` | P1 | 人物/世界观 8 张表零 API 零服务层 | §8 |
| `T-19` | P1 | 工作流 5 张表不存在，React Flow 零引用 | §10 |
| `T-20` | P2 | 编辑器无查找替换，撤销依赖原生行为 | §5.2 |
| `T-21` | P2 | `paragraphs` 表无写入方（只有切分函数） | §12.2 |
| `T-22` | P2 | 无 WebSocket，原计划要求 4 个 | §13.9 |
| `T-23` | P2 | Tiptap 已装未用，计划未记录 textarea 决策 | §5.2、§21 |
| `T-24` | P1 | 验收不可执行：无 E2E、无 500 章语料、pytest 数字自相矛盾 | §18 |

> 上一轮评审文档（`AI_Novel_Studio_Plan_Gaps.md`）里的 P0 条目，现状核对：
> **3.2 schema 迁移**已实现（`db/migrations.py`）、**3.4 sidecar 运维**已实现（`src-tauri/src/sidecar.rs`）、
> **3.1 SQLite 并发**已实现（WAL + 单写进程 + 复制前 checkpoint，`db/session.py:3-7,30-34,181-190`）——
> 这三条应从「待补」移出，其余条目仍成立。

---

## 5. 一句话

计划的**视觉与模块划分不用改**；要补的是三件事——**把阶段 1–2 的真实完成度写对**（否则会重复劳动）、
**把摘要管道提到 RAG 之前**（否则记忆系统建在空数据上）、**给每条验收配可执行命令**
（否则"做完了"没有判据）。三条落地后，原计划可以直接当施工图用。
