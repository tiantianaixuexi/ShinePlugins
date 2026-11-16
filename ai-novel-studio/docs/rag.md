# 长篇记忆与检索（RAG）

> **设计完成，尚未实现。**
>
> 本文是设计文档，描述计划 §6 的记忆系统**应该**如何工作。截至本文写作时，
> 仓库里**没有任何检索代码**：`backend/app` 下不存在 `memory/`、`retrieval/`、`ai/` 包，
> `knowledge_chunks` / `embeddings` / `retrieval_logs` / `memory_snapshots` /
> `knowledge_relations` 五张表**已建好但没有任何读写方**（唯一的引用是
> `project_db.py::collect_stats` 里的 `COUNT(*)`）。
>
> 唯一落地的相关代码是 `Chapter.indexed_hash` 列与 `novel_service` 里两处
> `chapter.indexed_hash = None`（正文变化/恢复时标记索引过期）——
> 写入有了，**消费方还没有**。
>
> 因此：**不要把本文任何一段当作「现在就能用」的能力**。

## 1. 问题：长篇小说装不进上下文

一部 300 章、每章 3000 字的网文约 90 万字。按中文「1 字 ≈ 1 token」粗算，
即使是最长的上下文窗口（当前 `model_configs.context_window` 上限 100_000_000，
实际模型多在 12 万–20 万）也**装不下两部**，而且：

- **成本**：每次调用都把全文发一遍，单价按 `input_price_per_1m` 线性增长；
- **注意力稀释**：无关章节占据窗口，模型反而更容易漏掉关键信息；
- **延迟**：prefill 90 万 token 的耗时无法接受；
- **不可行**：主流模型的硬上限就是几万到十几万 token。

所以正确的做法不是「塞更多」，而是**按需取回最小够用的事实**。
`app/core/config.py::Settings.default_embedding_batch_size`（默认 32）与
`max_upload_bytes`（64 MB）就是为这条路预留的。

## 2. 分层记忆 L0–L4

记忆不是一个向量库，而是**五个抽象层**，每层回答不同的问题、有不同的失效模式。
层号与仓库现有表的对应关系：

| 层 | 名称 | 回答什么 | 载体（已建表/列） | 粒度 |
|---|---|---|---|---|
| **L0** | 原文层 | 「第 37 章到底怎么写的？」 | `chapters.content`、`chapter_versions`、`paragraphs` | 章 / 段 |
| **L1** | 章节摘要层 | 「第 37 章发生了什么？」 | `chapter_summaries`（一对一 `chapter_id`） | 章 |
| **L2** | 场景层 | 「这场戏在哪、有谁、结果如何？」 | `scenes`（`chapter_id`、`characters` JSON、`goal`、`outcome`） | 场 |
| **L3** | 人物/设定层 | 「林凡现在什么状态？他和谁是什么关系？」 | `characters`、`character_states`、`relationships`、`locations`、`factions`、`items`、`abilities`、`world_rules` | 实体 |
| **L4** | 全局层 | 「整本书的主线、伏笔、时间线？」 | `outlines`、`events`、`event_participants`、`timelines`、`timeline_entries`、`foreshadows`、`memory_snapshots` | 书 |

**为什么必须分层**：每层的检索代价与更新频率差一个数量级。

- L0 变化最频繁（每次打字），但检索最精确（原文）；
- L4 变化最慢（几万字才动一次），但每次都要全量扫；
- 用 L0 回答「人物关系」会又慢又不准；用 L3 回答「第 37 章原句」会丢字。

**当前的实现状态**：L0 完整可用（章节 CRUD + 版本），L1–L4 全部只有表结构。
`chapter_summaries` 没有任何写入方，所以 L1 是空的；`scenes` 同理（L2 空）；
L3 的 `characters` 表存在但无 API（见 [api.md](api.md) §5）；
L4 的 `outlines`/`events`/`foreshadows` 表存在但无 API。

## 3. 结构化切分：volume → chapter → scene → paragraph

### 3.1 切分原则

**不按固定 token 数切**，而是**按叙事结构切**。理由：

1. 固定窗口会把「一句对话」切成两半，检索出来是残句，喂给模型只会制造幻觉；
2. 场景是「一个地点、一段时间、一次冲突」的自然单位，检索时按场景返回最省 token；
3. 段落是最后一级，用于「原文引用」——回答「他当时说了什么」必须精确到段。

切分链条：

```
volume（卷，用户可命名）
  └─ chapter（章，sort_order 全局有序）
       └─ scene（场，scene_no 在章内递增）        ← 由 L2 摘要/LLM 切分产生
            └─ paragraph（段，char_start/char_end 指向章节正文偏移）
```

`paragraphs` 表的 `(chapter_id, sort_order)` 复合索引 `ix_paragraphs_chapter_order`
就是为「按章顺序读段」准备的；`char_start` / `char_end` 让片段能反查原文位置。

⚠️ 当前 `paragraphs` 与 `scenes` **都没有写入方**。切分逻辑尚未实现，
`app/utils/text.py::split_paragraphs()`（按空行切段）是唯一切分工具函数，
目前**没有任何调用方**。

### 3.2 `knowledge_chunks` 的行形态

检索的基本单位是**知识块**，不是章节。一张 `knowledge_chunks` 行 = 一个可独立检索、
可独立溯源、可独立失效的文本片段。

| 列 | 类型 | 作用 |
|---|---|---|
| `id` | VARCHAR(40) PK `kno_*` | — |
| `project_id` | VARCHAR(40) NOT NULL，索引 | 多租户隔离（每个项目一个库，但仍带 project_id） |
| `volume_id` | VARCHAR(40) NULL | 溯源：属于哪一卷（**无 FK**） |
| `chapter_id` | VARCHAR(40) NULL，索引 | 溯源：属于哪一章（**无 FK**） |
| `scene_id` | VARCHAR(40) NULL，索引 | 溯源：属于哪一场（**无 FK**） |
| `chunk_type` | VARCHAR(32) NOT NULL default `narrative` | `narrative`/`dialogue`/`summary`/`outline`/`character`/`event`/`worldbuilding`/`foreshadow` |
| `content` | TEXT NOT NULL | 块正文（检索命中的就是它） |
| `start_position` / `end_position` | INTEGER NOT NULL default 0 | 在**所属章节正文**中的字符区间，用于高亮与反查 |
| `characters` | JSON NOT NULL default `[]` | 本块出场人物 id 列表（实体过滤） |
| `entities` | JSON NOT NULL default `[]` | 其他实体（地点/物品/能力 id） |
| `keywords` | JSON NOT NULL default `[]` | 关键词（FTS5 与意图匹配用） |
| `embedding_status` | VARCHAR(32) NOT NULL default `pending`，索引 | `pending`/`running`/`completed`/`failed` |
| `embedding_model` | VARCHAR(120) NULL | 生成该向量时用的模型标识 |
| `embedding_version` | VARCHAR(40) NULL | 该模型版本戳；与当前不符即向量失效 |
| `content_hash` | VARCHAR(64) NOT NULL default `''`，索引 | 块内容哈希，**增量索引的唯一依据** |
| `row_version` / `is_deleted` / `deleted_at` | — | 乐观锁 + 软删除 |
| `created_at` / `updated_at` | DATETIME NOT NULL | `TimestampMixin` |

复合索引：`ix_knowledge_chunks_project_type (project_id, chunk_type)`、
`ix_knowledge_chunks_chapter (chapter_id)`、`ix_knowledge_chunks_project_id`、
`ix_knowledge_chunks_scene_id`、`ix_knowledge_chunks_embedding_status`、
`ix_knowledge_chunks_content_hash`、`ix_knowledge_chunks_is_deleted`。

**为什么 `chunk_type` 是一等公民**：不同任务需要不同类型的块。
「继续写这一章」要 `narrative` + `dialogue`；「检查人物是否崩坏」要 `character` +
`chapter_summaries`；「检查伏笔回收」要 `foreshadow`。把类型放进索引，
可以在 SQL 层就把候选集缩小一个数量级，而不是取回后再过滤。

**为什么必须有 `content_hash`**：这是「改一章只重算变化块」的唯一实现手段。
写入前算哈希，与库里的比；相同则跳过（连 embedding 都不重算）。

## 4. 混合检索流水线

目标：给定一个写作意图，在 **1 秒内**（P95，见开发计划 §8 性能目标）
组装出一段**恰好够用**的上下文。

```
① 意图解析
   intent = classify(query)         → outline | continue | polish | review | character | foreshadow
        │
        ├─ 决定「要什么类型」：chunk_type 白名单 + 每层（L0–L4）的预算比例
        └─ 决定「要不要语义」：outline/character 偏语义；polish 偏原文精确匹配
② 实体与关键词抽取
   entities  = match_known_entities(query)   → characters.aliases 最长匹配 + 别名归并
   keywords  = tokenize(query)               → CJK bigram + 拉丁词
        │
        ├─ 实体用于「结构化过滤」：WHERE ... JSON 包含 <entity_id>
        └─ 关键词用于 FTS5 MATCH
③ 双路并行召回
   ├── FTS5：SELECT ... FROM knowledge_chunks_fts JOIN knowledge_chunks
   │         WHERE knowledge_chunks_fts MATCH :q
   │         AND is_deleted = 0
   │         AND embedding_status != 'failed'
   │         ORDER BY bm25(knowledge_chunks_fts) LIMIT k1        ← 精确、快、无需模型
   └── sqlite-vec：SELECT chunk_id, distance FROM vec_chunks
                  WHERE embedding MATCH :qvec AND k = k2          ← 语义、慢、需向量
        │
        │  两路各自取 top-k（k1 + k2 ≈ 40–60），并发执行
        ▼
④ 去重
   merge by chunk_id；同一 chunk 被两路命中时分数取加权（不是简单相加）
   相邻块（同 chapter 且 start_position 相接）可选「合并窗口」，
   避免召回半句话
        ▼
⑤ 重排（rerank）
   特征：FTS5 bm25、向量距离、chunk_type 与 intent 的匹配度、
        实体重合数、是否当前章（时效性加成）、word_count 惩罚（太长降权）
   输出 top-n（n 由 token 预算反推，见 §5）
        ▼
⑥ 溯源补全（provenance lookup）
   对每个入选块，用 (chapter_id, start_position) 回查
   chapters.title / volumes.title / scene 信息，
   组装成带「第 X 卷 · 第 Y 章 · 第 Z 段」标签的引用
        ▼
⑦ 上下文组装（context assembly）
   按 §5 的优先级顺序拼装，插入分隔标记，返回 {text, tokens, citations}
        │
        └─ ⑧ 检索日志：写 retrieval_logs 一行（见 §7）
```

### 4.1 为什么是「混合」而不是纯向量

| 场景 | 纯向量 | 纯 FTS5 | 混合 |
|---|---|---|---|
| 「林凡的师父是谁」 | 可能召回到「师父」二字附近的无关段落 | 精确命中「师父」但漏掉只用「师尊」的段落 | ✅ 别名归一 + 双路 |
| 「第 12 章那句『天地玄黄』」 | 向量可能给语义相近但字面不同的句子 | ✅ 精确命中 | ✅ |
| 「最近三章的冲突升级」 | ✅ 语义泛化强 | ❌ 无共同关键词 | ✅ |
| 索引缺失/嵌入模型未就绪 | ❌ 完全不可用 | ✅ 仍可用 | ✅ 降级 |

**关键设计**：FTS5 是**兜底**。`sqlite-vec` 扩展加载失败时
（`session.py::_load_sqlite_vec` 已经做了「失败只告警不中断启动」），
检索必须自动降级为纯 FTS5，而不是整体失败。
`Settings.default_embedding_batch_size` 也暗示了嵌入是批处理、可延后的。

## 5. Token 预算与优先级

### 5.1 预算来源

预算**不是**拍脑袋定的常数，而是从模型能力画像推导：

```
可用窗口   = model_config.context_window
输出预留   = model_config.max_output_tokens
安全边际   = 可用窗口 × (1 - SAFETY_RATIO)        # 例如 0.85，给系统提示与格式留余量
检索预算   = 安全边际 - 输出预留 - 系统提示开销
```

`model_configs` 里 `context_window`、`max_output_tokens`、`input_price_per_1m`、
`output_price_per_1m` 都已就绪（见 [database.md](database.md) §7.1），
**没有代码读它们**。`app/core/config.py` 也没有任何预算相关配置。

### 5.2 优先级顺序

预算不足时，**从后往前砍**。顺序即价值：

| 优先级 | 内容 | 典型占比 | 理由 |
|---|---|---|---|
| **P0** | 系统提示（角色、任务、输出格式） | 固定 | 少了它整次调用无意义 |
| **P0** | 当前章**已写全文**（续写场景） | 剩余预算的 40–60% | 续写必须接得上最后一句；这是 L0 的特例，不检索 |
| **P1** | 当前章摘要（L1） | ~10% | 提供本章脉络 |
| **P1** | 出场人物状态（L3：`character_states` 最新一条） | ~10% | 防止人物状态回退（受伤/死亡/位置） |
| **P2** | 检索命中的原文块（L0） | ~15% | 按 rerank 分数从高到低填 |
| **P3** | 相关场景摘要（L2） | ~5% | 补足上下文连续性 |
| **P4** | 全局大纲节点（L4：`outlines` 当前卷/章） | ~5% | 保证方向不跑偏 |
| **P5** | 伏笔状态（L4：`foreshadows` 中 `status='open'` 且与本章相关） | ~3% | 提醒埋点/回收 |
| **P6** | 时间线近期条目 | ~2% | 防止时间倒错 |

砍的顺序：P6 → P5 → P4 → P3 → P2（按分数从低到高丢块）→ P1。
**P0 永不砍。**

### 5.3 预算控制的具体手段

1. **按 token 估数**：`app/utils/text.py` 目前只有 `count_words`，
   前端的 `estimateTokens`（`desktop/src/lib/utils.ts`：CJK 1 token/字、拉丁 4 字符/token）
   是现成参考，但**后端没有对应实现**，需要补。
2. **块级裁剪**：单个块超过预算 20% 时，从中间截断并在两端加省略标记，
   同时保留 `start_position` 以便溯源。
3. **去重**：同一实体的重复描述只保留最新一条（L3 的时序特性）。
4. **预算耗尽即停**：拼装到 P1 之后如果剩余不足，直接停止，不返回半截的 P2。

## 6. 增量索引

### 6.1 「只重算变化的块」

改一章不应该重建整本书的索引。判定链：

```
章节保存（PUT /chapters/{id}）
  ├─ content 未变 → 什么都不做
  └─ content 变化 → chapter.indexed_hash = NULL        ← 已实现
        │
        └─ 索引任务（未实现）拾取 WHERE indexed_hash IS NULL
             ├─ 重新切分该章（paragraph → scene → chunk）
             ├─ 与旧块按 (chapter_id, start_position, end_position) 对齐
             ├─ 逐块比较 content_hash：
             │    ├─ 相同 → 保留旧块（含旧 embedding，不重算）
             │    ├─ 不同 → 重算 embedding，更新 content_hash
             │    └─ 新增 → 插入，embedding_status='pending'
             ├─ 旧块在新切分中消失 → is_deleted=1（软删，保留可追溯）
             └─ 全部成功后 chapter.indexed_hash = sha256(content)
```

**关键点**：`content_hash` 的比较是**块级**的，不是章级的。
改动一段对话，只有那一段（及可能受影响的相邻段）会被重新嵌入。

### 6.2 已实现的部分

- ✅ `Chapter.indexed_hash` 列（VARCHAR(64)，索引）
- ✅ 正文变化时置 `NULL`（`novel_service.update_chapter`）
- ✅ 恢复版本时置 `NULL`（`novel_service.restore_version`）
- ❌ 索引任务本身、切分、embedding 调用、`content_hash` 计算全部未实现

所以现状是：**「脏标记」有了，「读脏标记并重建」没有**。
`indexed_hash` 目前恒为 `NULL`（除了手工写入），不会造成错误，只是没人消费。

### 6.3 删除的一致性

`knowledge_chunks.chapter_id` **没有外键**（见 [database.md](database.md) §10.2），
所以删章（软删）时数据库**不会**清理块与向量。检索侧必须自己过滤：

```sql
WHERE k.is_deleted = 0
  AND NOT EXISTS (
      SELECT 1 FROM chapters c
      WHERE c.id = k.chapter_id AND c.is_deleted = 1
  )
```

或者由索引任务在删章时把对应块一并软删。**这一条尚未实现，是当前最明确的正确性缺口。**

## 7. 嵌入模型变更 ⇒ 全量重建

### 7.1 为什么必须重建

不同 embedding 模型的向量空间**不互通**。同一段文本在模型 A 下的向量与模型 B 下的向量
做余弦相似度是无意义的数字。混用会导致检索**静默错乱**——不报错，但结果随机。

### 7.2 判定与流程

每条 `knowledge_chunks` 行都带 `embedding_model` + `embedding_version`，
`embeddings` 行也带 `model` + `model_version`（`NOT NULL`）。
换模型时：

```
检测到 model_configs.embedding_model_config_id 变更
  ├─ 1. 写入新模型的标识到「期望值」
  ├─ 2. 扫描 embeddings / knowledge_chunks：
  │       WHERE embedding_model != :new_model OR embedding_version != :new_version
  ├─ 3. 这些块进入 degraded 状态：
  │       - 向量检索**跳过**它们（WHERE embedding_model = :new_model）
  │       - FTS5 检索**仍然可用**（纯文本索引，与模型无关）
  ├─ 4. 后台按 batch（Settings.default_embedding_batch_size，默认 32）重算
  └─ 5. 全部完成后，degraded 清零
```

### 7.3 降级：FTS5-only

**重建期间检索不得不可用**。降级策略：

- 向量路返回空集（不是错误），FTS5 路正常返回；
- 结果标注 `degraded: true`，前端提示「语义检索重建中，当前为关键词检索」；
- 重建完成后自动恢复，`degraded` 转 `false`。

这样「索引重建」从一次**停机**变成一次**性能下降**，对正在写作的用户不可见。

### 7.4 触发点

- 用户在设置里改 `embedding_model_config_id`（**该字段已在 `projects` 表，但无 UI**）；
- `model_configs.embedding_model` / `embedding_version` 升级；
- 手动触发 `POST /api/memory/rebuild`（**该端点不存在**）。

## 8. 检索日志与「AI 到底读了什么」

### 8.1 `retrieval_logs` 一行 = 一次检索

| 列 | 含义 |
|---|---|
| `id` | `ret_*` |
| `project_id` | 所属项目 |
| `task_id` | 触发这次检索的任务（`generation_tasks.id`），可为 NULL（交互式检索） |
| `query` | 原始查询文本 |
| `query_type` | `keyword` / `semantic` / `hybrid` |
| `candidate_count` | 双路召回总数（去重前） |
| `deduped_count` | 去重后 |
| `reranked_count` | 重排后 |
| `used_count` | **实际进入上下文**的块数 |
| `results` | JSON 数组：每块的 `chunk_id`、`score`、`chunk_type`、`chapter_id`、`start_position`、来源路（fts/vec/两者） |
| `token_estimate` | 这次上下文占用的估算 token |
| `latency_ms` | 端到端耗时 |

这四个字段（`candidate_count` → `deduped_count` → `reranked_count` → `used_count`）
构成**漏斗**：一眼能看出是「召回太少」还是「重排砍太狠」还是「预算太小」。
对应计划 §6.9「效度评估」的埋点位置。

### 8.2 「AI 到底读了什么」视图

设计意图：写作的人需要能回答「它凭什么这么写」。视图数据全部来自 `retrieval_logs.results`：

- 按章节/时间点列出每次生成的检索记录；
- 每条展开为「引用卡片」：`第 12 卷 · 第 3 章 · 第 2 段`，点击跳到编辑器对应位置
  （靠 `chapter_id` + `start_position` 定位）；
- 高亮「命中但**未**进入上下文」的块（`reranked` 被砍掉的），
  用于判断是预算不足还是排序错误；
- 标注 `degraded` 与 `embedding_model`，避免把「换模型后」的结果与之前对比。

### 8.3 `memory_snapshots`

`memory_snapshots`（`project_id`、`chapter_id`、`label`、`payload` JSON）
用于**序列化某一时刻的记忆状态**，支持：

- 前后对比（改一章前后，L1 摘要与 L3 状态有什么变化）；
- 回滚（「我觉得改坏了，把记忆恢复到昨天的状态」）；
- 调试（复现一次错误的检索结果）。

它与 `chapter_versions` 的区别：后者是**正文**快照，前者是**结构化记忆**快照。

### 8.4 `knowledge_relations`

多态边表：`source_type` / `source_id` → `relation` → `target_type` / `target_id`，
带 `weight` 与 `source_event_id`（这条关系的**来源事件**，可追溯到具体章节）。

用途：

- 检索扩展：「命中林凡」→ 沿 `knows` / `enemy_of` / `master_of` 边展开一跳，
  把师父、仇人一并召回（解决「代词/别称」召回不到的问题）；
- 一致性检查：「林凡的师父」在图中必须唯一，出现两个 `master_of` 入边即冲突；
- 与 `relationships` 表的区别：后者是**人物之间**的强类型关系
  （`relation_type`、`strength`、`since_event_id`、`ended_at`），
  前者是**任意实体之间**的弱类型边。

## 9. 与现有代码的边界

| 能力 | 表/列是否就绪 | 代码是否实现 |
|---|---|---|
| 章节原文（L0） | ✅ | ✅ 完整 CRUD + 版本 |
| 分段（`paragraphs`） | ✅ | ❌ 无写入方 |
| 场景（`scenes`） | ✅ | ❌ 无写入方 |
| 章节摘要（L1） | ✅ | ❌ 无写入方 |
| 人物/状态/关系（L3） | ✅ | ❌ 无 API |
| 大纲/事件/伏笔（L4） | ✅ | ❌ 无 API |
| 知识块（`knowledge_chunks`） | ✅ | ❌ 只有 `COUNT(*)` 统计 |
| 向量（`embeddings`） | ✅（BLOB） | ❌ 无写入、无查询 |
| sqlite-vec 扩展 | ✅ 加载就绪 | ⚠️ 仅加载，未建虚拟表、未查询 |
| FTS5 虚拟表 | ❌ | ❌ 一个都没有 |
| 检索日志 | ✅ | ❌ 无写入方 |
| 记忆快照 | ✅ | ❌ 无写入方 |
| 关系边 | ✅ | ❌ 无写入方 |
| 索引脏标记 | ✅ `indexed_hash` | ⚠️ 只写 `NULL`，无消费方 |
| Token 预算 | ⚠️ 字段就绪 | ❌ 无读取方 |

**结论**：数据模型设计完成且已落库，检索与索引**一行都没写**。
本文描述的是目标形态，不是当前行为。任何「现在就能语义检索」的说法都是错的。