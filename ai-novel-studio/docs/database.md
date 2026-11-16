# 数据库设计

仓库中**真实存在**的 35 张表，按设计文档分组，含完整列、约束、迁移策略、软删除与级联规则。
所有列名/类型/约束均从 `app/models/studio.py`、`app/models/novel.py` 及 `Base.metadata`
实际导出核对，无虚构字段。

| 库 | 位置 | 逻辑归属 | 实际建了什么 |
|---|---|---|---|
| `studio.db` | 全局，进程内单例 | 8 张：`app_meta`、`model_configs`、`prompt_templates`、`agent_configs`、`projects`、`project_backups`、`generation_tasks`、`task_logs` | **35 张全部** |
| `novel.db` | 每项目一个 | 27 张：其余全部，含 `project_meta` | **35 张全部** |

⚠️ **重要事实**：两个库的**物理表集合完全相同（各 35 张）**。
原因是 `app/models/studio.py` 与 `app/models/novel.py` 的模型都注册在同一个
`Base.metadata` 上，而 `Base.metadata.create_all(engine)` 会建出**全部**已注册表——
`Runtime.start()` 对 `studio.db` 调一次，`create_project_database()` 对每个
`novel.db` 再调一次。

实测（全新安装，建一个项目后对比 `sqlite_master`）：

```
studio.db tables: 35
novel.db  tables: 35
identical: True
only in studio: []
only in novel : []
novel.db contains 'projects'?      -> True
novel.db contains 'model_configs'? -> True
studio.db contains 'chapters'?     -> True
studio.db contains 'characters'?   -> True
```

所以上表的「逻辑归属」才是**设计意图**：`studio.db` 只读写那 8 张，
每个 `novel.db` 只读写本项目那 27 张。多出来的空表不影响正确性
（`novel.db` 里的 `projects` 永远是空表，`studio.db` 里的 `chapters` 同理），
但代价是：**每建一个项目就多一份 35 表的空壳**，且新人容易误以为
`studio.db` 里的 `chapters` 有数据。

⚠️ 由此衍生的两个隐患（当前未修）：

1. **迁移会作用到不该作用的表**：`create_project_database()` 调
   `migrate("project_meta")`，只打戳 `project_meta`；但 `studio.db` 里也存在
   `project_meta` 表，如果有人误在 `studio.db` 上跑 `migrate("project_meta")`
   会写错地方。目前靠「表名参数」区分，没有物理隔离。
2. **统计可能读错库**：`collect_stats()` 接收的是 `Database` 实例，
   函数本身不校验 `label`。传错库不会报错，只会返回全 0。

后续若要收紧，正确做法是**拆 metadata**（`studio_db.Base` 与 `novel_db.Base` 分开），
但那会让 `create_all()` 的调用点变复杂，属于阶段 7 的工程化任务。

## 1. 通用约定

| Mixin | 列 | 说明 |
|---|---|---|
| `TimestampMixin` | `created_at` NOT NULL default `CURRENT_TIMESTAMP`（索引）、`updated_at` NOT NULL default `CURRENT_TIMESTAMP`、`onupdate=CURRENT_TIMESTAMP` | 数据库维护；所有表（含 `app_meta`/`project_meta`/`project_backups`）一律继承，无例外 |
| `RowVersionMixin` | `row_version` INT NOT NULL default 1 | 乐观并发计数，每次更新 +1 |
| `SoftDeleteMixin` | `deleted_at` NULL、`is_deleted` BOOL NOT NULL default 0（索引） | 软删除 |
| `SchemaVersionMixin` | `schema_version` INT NOT NULL default 1 | **已定义但无表使用** |

主键统一 `VARCHAR(40)`，形如 `proj_4f2a9c1b8e77`，由 `app/core/ids.py::new_id(prefix)`
生成（`prefix_` + uuid4 前 12 位十六进制）。

| 前缀 | 表 | 前缀 | 表 | 前缀 | 表 |
|---|---|---|---|---|---|
| `proj_` | projects | `chap_` | chapters | `vol_` | volumes |
| `para_` | paragraphs | `ver_` | chapter_versions | `sum_` | chapter_summaries |
| `out_` | outlines | `scn_` | scenes | `kno_` | knowledge_chunks |
| `emb_` | embeddings | `ret_` | retrieval_logs | `mst_` | memory_snapshots |
| `rel_` | knowledge_relations | `chr_` | characters | `cst_` | character_states |
| `rlt_` | relationships | `loc_` | locations | `fac_` | factions |
| `itm_` | items | `abi_` | abilities | `rul_` | world_rules |
| `evt_` | events | `prt_` | event_participants | `tml_` | timelines |
| `tme_` | timeline_entries | `frs_` | foreshadows | `frl_` | foreshadow_relations |
| `mdl_` | model_configs | `prm_` | prompt_templates | `agt_` | agent_configs |
| `bak_` | project_backups | `tsk_` | generation_tasks | `log_` | task_logs |

命名约定（`NAMING_CONVENTION`）：`ix_<表>_<列>`、`uq_<表>_<列>`、
`fk_<表>_<列>_<引用表>`、`pk_<表>`、`ck_<表>_<约束名>`。

## 2. 项目数据

### 2.1 `projects`（studio.db）— 项目注册表

| 列 | 类型 | 约束/默认 | 用途 |
|---|---|---|---|
| `id` | VARCHAR(40) | PK，`proj_*` | 项目 ID |
| `name` | VARCHAR(200) | NOT NULL | 显示名 |
| `slug` | VARCHAR(64) | NOT NULL，索引 | ASCII 短名；中文名退化为 `id` |
| `novel_type` | VARCHAR(64) | NOT NULL default `web` | 小说类型 |
| `synopsis` | TEXT | NOT NULL default `''` | 故事简介 |
| `target_word_count` / `target_chapter_count` | INTEGER | NOT NULL default 0 | 目标字数 / 章数 |
| `writing_style` / `target_reader` | TEXT / VARCHAR(200) | NOT NULL default `''` | 文风 / 目标读者 |
| `language` | VARCHAR(16) | NOT NULL default `zh-CN` | 创作语言 |
| `author` | VARCHAR(200) | NOT NULL default `''` | 作者 |
| `status` | VARCHAR(32) | NOT NULL default `active`，索引 | `active` / `deleted` / 业务态 |
| `path` | TEXT | NOT NULL | 项目目录绝对路径 |
| `schema_version` | INTEGER | NOT NULL default 1 | **该项目 novel.db 的文件格式版本**（≠应用版本） |
| `default_model_config_id` | VARCHAR(40) | NULL，FK→`model_configs.id` `SET NULL` | 默认写作模型 |
| `embedding_model_config_id` | VARCHAR(40) | NULL，FK→`model_configs.id` `SET NULL` | 嵌入模型 |
| `settings` | JSON | NOT NULL default `{}` | 自由扩展：写作纲要、Agent 选择、预算上限 |
| `row_version` | INTEGER | NOT NULL default 1 | 乐观锁 |
| `is_deleted` / `deleted_at` | BOOLEAN / DATETIME | 软删除 | — |
| `created_at` / `updated_at` | DATETIME | NOT NULL（前者索引） | 时间戳 |

索引：`ix_projects_slug`、`ix_projects_status`、`ix_projects_is_deleted`、`ix_projects_created_at`。
⚠️ **`slug` 无唯一约束** —— 同名项目可产生相同 slug（目录名靠追加 id 后缀区分）。

### 2.2 `project_backups`（studio.db）— 备份历史

`id` PK `bak_*` · `project_id` NOT NULL FK→`projects.id` `CASCADE`（索引） ·
`kind` NOT NULL default `manual`（`manual`/`auto`/`pre_migrate`） · `path` NOT NULL ·
`size_bytes` NOT NULL default 0 · `note` NOT NULL default `''` ·
`created_at` NOT NULL default `CURRENT_TIMESTAMP`（索引） ·
`updated_at` NOT NULL default `CURRENT_TIMESTAMP`。

✅ `created_at` / `updated_at` 均由 `TimestampMixin` 提供，**无「重声明且无默认值」问题**
（实测 `PRAGMA table_info(project_backups)`：两列均为 `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP`）。

### 2.3 `project_meta`（novel.db）/ `app_meta`（studio.db）— 键值表

两表结构完全一致：`key` VARCHAR(120) PK · `value` TEXT NOT NULL default `''`（数字/JSON 也存这里） ·
`created_at` DATETIME NOT NULL default `CURRENT_TIMESTAMP`（索引） ·
`updated_at` DATETIME NOT NULL default `CURRENT_TIMESTAMP`。

- `project_meta` 已知键：`schema_version`（`project_db.py::SCHEMA_VERSION_KEY`）。
  预留：迁移历史、计数器、功能开关。
- `app_meta` 唯一写入方：`app/runtime.py::_stamp_schema_version()`，键 `schema_version`，
  值 `app/core/config.py::SCHEMA_VERSION`（当前 `1`）；迁移执行器也会写它
  （`app/db/migrations.py::_stamp`）。

✅ 两表都**只继承 `TimestampMixin`**，不再自己重声明 `updated_at`。
早期版本里「重声明 `updated_at` 且无 default」导致插入时 NOT NULL 失败的缺陷已消失
（实测两表的 `created_at`/`updated_at` 都是 `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP`）。
见 [api.md](api.md) §8.1。

## 3. 小说结构

### 3.1 `volumes`（novel.db）— 卷

`id` PK `vol_*` · `project_id` NOT NULL（索引） · `title` NOT NULL ·
`summary` NOT NULL default `''` · `sort_order` NOT NULL default 0（索引） ·
`word_count` NOT NULL default 0 · `status` NOT NULL default `draft` · `row_version`。

### 3.2 `chapters`（novel.db）— 章节（L0 原文层）

| 列 | 类型 | 约束 | 用途 |
|---|---|---|---|
| `id` | VARCHAR(40) | PK，`chap_*` | — |
| `project_id` | VARCHAR(40) | NOT NULL，索引 | 所属项目 |
| `volume_id` | VARCHAR(40) | NULL，FK→`volumes.id` `SET NULL`，索引 | 所属卷 |
| `title` | VARCHAR(200) | NOT NULL | 章节标题 |
| `sort_order` | INTEGER | NOT NULL default 0，索引 | 全书排序 |
| `content` | TEXT | NOT NULL default `''` | 正文全文 |
| `word_count` | INTEGER | NOT NULL default 0，索引 | 字数 |
| `status` | VARCHAR(32) | NOT NULL default `draft`，索引 | `draft` / `done` / … |
| `pov_character_id` | VARCHAR(40) | NULL（**无 FK**） | 视角人物 |
| `summary` | TEXT | NOT NULL default `''` | 章节摘要 |
| `indexed_hash` | VARCHAR(64) | NULL，索引 | 上次索引内容哈希；不匹配即索引过期 |
| `row_version` / `is_deleted` / `deleted_at` | — | 乐观锁 + 软删除 | — |

### 3.3 `paragraphs`（novel.db）— 段落

`id` PK `para_*` · `project_id` NOT NULL（索引） ·
`chapter_id` NOT NULL，FK→`chapters.id` `CASCADE`（索引） ·
`sort_order` NOT NULL default 0 · `content` NOT NULL ·
`char_start` / `char_end` NOT NULL default 0（在章节正文中的偏移）。
复合索引 `ix_paragraphs_chapter_order (chapter_id, sort_order)`。

### 3.4 `chapter_versions`（novel.db）— 版本快照

`id` PK `ver_*` · `project_id` NOT NULL（索引） ·
`chapter_id` NOT NULL，FK→`chapters.id` `CASCADE`（索引） ·
`version_no` NOT NULL · `title` NOT NULL default `''` ·
`content` NOT NULL（不可变快照） · `word_count` NOT NULL default 0 ·
`source` NOT NULL default `user`（`user`/`ai`/`import`/`restore`） · `note` NOT NULL default `''`。
唯一约束 `uq_chapter_version (chapter_id, version_no)`。

### 3.5 `chapter_summaries`（novel.db）— L1 章节层摘要

`id` PK `sum_*` · `project_id` NOT NULL（索引） ·
`chapter_id` NOT NULL，**UNIQUE**，FK→`chapters.id` `CASCADE`（一对一） ·
`summary` NOT NULL default `''` · `characters` / `events` / `locations` / `keywords` /
`foreshadows` 均 JSON NOT NULL default `[]` · `plot_progress` NOT NULL default `''` ·
`model_config_id` NULL（**无 FK**） · `prompt_version` NULL。

### 3.6 `outlines`（novel.db）— 分层大纲

`id` PK `out_*` · `project_id` NOT NULL（索引） ·
`level` NOT NULL default `chapter`（索引；`story`/`volume`/`chapter`/`scene`） ·
`parent_id` NULL（索引，**无 FK**，自引用） · `title` VARCHAR(300) NOT NULL ·
`goal` / `conflict` / `twists` / `ending` NOT NULL default `''` ·
`characters` / `key_events` / `foreshadows` JSON NOT NULL default `[]` ·
`target_word_count` NOT NULL default 0 · `sort_order` NOT NULL default 0（索引） ·
`content` NOT NULL default `''` · `row_version`。

### 3.7 `scenes`（novel.db）— L2 场景层

`id` PK `scn_*` · `project_id` NOT NULL（索引） ·
`chapter_id` NULL，FK→`chapters.id` `CASCADE`（索引） ·
`scene_no` NOT NULL default 0 · `name` NOT NULL default `''` ·
`location_id` NULL（**无 FK**） · `time_of_day` / `weather` / `mood` NOT NULL default `''` ·
`characters` JSON NOT NULL default `[]` · `description` / `goal` / `outcome` NOT NULL default `''`。

## 4. 知识库

### 4.1 `knowledge_chunks`（novel.db）— 可检索文本块

| 列 | 类型 | 约束 | 用途 |
|---|---|---|---|
| `id` | VARCHAR(40) | PK，`kno_*` | — |
| `project_id` | VARCHAR(40) | NOT NULL，索引 | — |
| `volume_id` / `chapter_id` / `scene_id` | VARCHAR(40) | NULL；后两者有索引；**均无 FK** | 溯源 |
| `chunk_type` | VARCHAR(32) | NOT NULL default `narrative` | `narrative`/`dialogue`/`summary`/`outline`/`character`/`event`/`worldbuilding`/`foreshadow` |
| `content` | TEXT | NOT NULL | 块正文 |
| `start_position` / `end_position` | INTEGER | NOT NULL default 0 | 原文区间 |
| `characters` / `entities` / `keywords` | JSON | NOT NULL default `[]` | 元数据 |
| `embedding_status` | VARCHAR(32) | NOT NULL default `pending`，索引 | `pending`/`running`/`completed`/`failed` |
| `embedding_model` / `embedding_version` | VARCHAR(120)/(40) | NULL | 与当前不符即向量失效 |
| `content_hash` | VARCHAR(64) | NOT NULL default `''`，索引 | 增量索引依据 |
| `row_version` / `is_deleted` / `deleted_at` | — | 乐观锁 + 软删除 | — |

复合索引：`ix_knowledge_chunks_project_type (project_id, chunk_type)`、
`ix_knowledge_chunks_chapter (chapter_id)`。

### 4.2 `embeddings`（novel.db）— 向量

`id` PK `emb_*` · `project_id` NOT NULL（索引） ·
`chunk_id` NOT NULL，FK→`knowledge_chunks.id` `CASCADE`（索引） ·
`model` NOT NULL · `model_version` NOT NULL default `1` ·
`dimension` NOT NULL · `vector` LargeBinary NOT NULL（float32 原始字节）。

⚠️ 当前是**普通 BLOB 表**，未用 `sqlite-vec` 虚拟表。`_load_sqlite_vec()` 会尝试加载扩展，
失败仅告警，但检索侧尚未实现（无查询代码）。

### 4.3 `retrieval_logs`（novel.db）— 检索审计（漏斗）

`id` PK `ret_*` · `project_id` NOT NULL（索引） · `task_id` NULL（索引） ·
`query` NOT NULL · `query_type` NOT NULL default `hybrid`（`keyword`/`semantic`/`hybrid`） ·
`candidate_count` / `deduped_count` / `reranked_count` / `used_count` NOT NULL default 0 ·
`results` JSON NOT NULL default `[]`（`list[dict]`） ·
`token_estimate` NOT NULL default 0 · `latency_ms` FLOAT NOT NULL default 0.0。

「候选 → 去重 → rerank → 进上下文」四段漏斗的落点，对应计划 §6.9 效度评估。

### 4.4 `memory_snapshots`（novel.db）— 记忆快照

`id` PK `mst_*` · `project_id` NOT NULL（索引） · `chapter_id` NULL（索引） ·
`label` NOT NULL default `''` · `payload` JSON NOT NULL default `{}`。

### 4.5 `knowledge_relations`（novel.db）— 实体关系边

`id` PK `rel_*` · `project_id` NOT NULL（索引） ·
`source_type` / `source_id`（索引）/ `target_type` / `target_id`（索引） NOT NULL ·
`relation` VARCHAR(64) NOT NULL · `weight` FLOAT NOT NULL default 1.0 ·
`source_event_id` NULL · `note` NOT NULL default `''`。
多态边表，两端均无 FK。

## 5. 人物与世界观

### 5.1 `characters`（novel.db）— L3 人物层

| 列 | 类型 | 约束 | 用途 |
|---|---|---|---|
| `id` | VARCHAR(40) | PK，`chr_*` | — |
| `project_id` | VARCHAR(40) | NOT NULL，索引 | — |
| `name` | VARCHAR(120) | NOT NULL | 主名 |
| `aliases` | JSON | NOT NULL default `[]` | 别名/昵称，用于实体消歧 |
| `gender` / `age` | VARCHAR(32)/(64) | NOT NULL default `''` | — |
| `appearance` / `personality` / `identity` / `background` / `goals` / `motivation` / `abilities` / `weaknesses` | TEXT | NOT NULL default `''` | 设定各维度 |
| `current_state` | JSON | NOT NULL default `{}` | 当前状态快照 |
| `first_chapter_id` | VARCHAR(40) | NULL（**无 FK**） | 首次出场章节 |
| `notes` | TEXT | NOT NULL default `''` | 备注 |
| `row_version` / `is_deleted` / `deleted_at` | — | 乐观锁 + 软删除 | — |

唯一约束：**部分唯一索引** `uq_characters_project_name_active`
（`models/novel.py::Character.__table_args__`）：

```sql
CREATE UNIQUE INDEX uq_characters_project_name_active
  ON characters (project_id, name)
  WHERE is_deleted = 0
```

✅ 含义：**只在未删除的行里唯一**。软删除的人物不再占用名字，
删掉「林凡」后可以再建一个「林凡」，这正是创作过程中的常见操作。

实测（`sqlite_master`）：

```
index uq_characters_project_name_active (unique=1, partial=1):
  CREATE UNIQUE INDEX uq_characters_project_name_active
  ON characters (project_id, name) WHERE is_deleted = 0
index ix_characters_project_id / ix_characters_is_deleted / ix_characters_created_at
```

⚠️ 设计取舍：部分唯一索引不是标准 SQL，目前只有 SQLite（以及 Postgres）支持；
换数据库时这条约束需要改写。此外 `is_deleted` 用 `0/1` 字面量而不用布尔参数，
是因为 SQLite 的部分索引谓词里不能绑定参数。

与旧版差异：早期是普通唯一约束 `uq_character_name (project_id, name)`，
软删行同样占位 → 软删后重建同名人物必然 `IntegrityError`。**该缺陷已修复。**

### 5.2 `character_states`（novel.db）— 人物状态时序

`id` PK `cst_*` · `project_id` NOT NULL（索引） ·
`character_id` NOT NULL，FK→`characters.id` `CASCADE`（索引） ·
`chapter_id` NULL（索引） · `event_id` NULL（索引） · `location_id` NULL（**无 FK**） ·
`state` JSON NOT NULL default `{}`（位置/伤势/能力/物品/认知/目标） ·
`summary` NOT NULL default `''` · `recorded_at` NOT NULL。

### 5.3 `relationships`（novel.db）— 人物关系

`id` PK `rlt_*` · `project_id` NOT NULL（索引） ·
`source_character_id` / `target_character_id` NOT NULL，均 FK→`characters.id` `CASCADE`（索引） ·
`relation_type` VARCHAR(64) NOT NULL（朋友/敌人/家人/师徒/上下级/盟友/恋人/商业） ·
`description` NOT NULL default `''` · `strength` FLOAT NOT NULL default 0.5 ·
`since_event_id` / `since_chapter_id` NULL（**无 FK**） · `ended_at` NULL。

### 5.4 `locations` / `factions` / `items`（novel.db）— 地点 / 势力 / 物品

同构模式：`id` PK（`loc_`/`fac_`/`itm_`） · `project_id` NOT NULL（索引） ·
`name` NOT NULL · `aliases` JSON NOT NULL default `[]` ·
类型列（`location_type`/`faction_type`/`item_type`）NOT NULL default `''` ·
描述列（`region`+`description` / `description` / `description`+`abilities`） ·
`notes` NOT NULL default `''` · `is_deleted` / `deleted_at`。

仅 `items` 与 `factions` 有属主列：`factions.leader_character_id`、`items.owner_character_id`，
均 NULL 且**无 FK**。

### 5.5 `abilities` / `world_rules`（novel.db）— 能力 / 世界规则（无软删除）

- `abilities`：`id` PK `abi_*` · `project_id` NOT NULL（索引） · `name` NOT NULL ·
  `system`（体系）· `level`（等级）· `description` · `rules`（规则）。
- `world_rules`：`id` PK `rul_*` · `project_id` NOT NULL（索引） · `name` NOT NULL ·
  `category` NOT NULL default `custom`（`geography`/`history`/`society`/`power`/`technology`/`magic`/`custom`） ·
  `description` NOT NULL default `''` · `constraints` JSON NOT NULL default `[]`（字符串列表）。

## 6. 剧情系统

### 6.1 `events`（novel.db）— 事件

`id` PK `evt_*` · `project_id` NOT NULL（索引） · `name` VARCHAR(200) NOT NULL ·
`description` NOT NULL default `''` · `story_time`（故事内时间，非物理时间）NOT NULL default `''` ·
`chapter_id` NULL（索引，**无 FK**） · `location_id` NULL（**无 FK**） ·
`importance` NOT NULL default 1 · `sort_order` NOT NULL default 0 ·
`is_deleted` / `deleted_at`。

### 6.2 `event_participants`（novel.db）— 事件参与者

`id` PK `prt_*` · `project_id` NOT NULL（索引） ·
`event_id` NOT NULL，FK→`events.id` `CASCADE`（索引） ·
`character_id` NOT NULL，FK→`characters.id` `CASCADE`（索引） ·
`role` NOT NULL default `''`。唯一约束 `uq_event_participant (event_id, character_id)`。

### 6.3 `timelines` / `timeline_entries`（novel.db）— 时间线

- `timelines`：`id` PK `tml_*` · `project_id` NOT NULL（索引） · `name` NOT NULL ·
  `description` NOT NULL default `''` · `sort_order` NOT NULL default 0。
- `timeline_entries`：`id` PK `tme_*` · `project_id` NOT NULL（索引） ·
  `timeline_id` NOT NULL，FK→`timelines.id` `CASCADE`（索引） ·
  `event_id` NULL，FK→`events.id` `SET NULL`（索引） ·
  `time_label`（如「三年前」）NOT NULL default `''` · `sort_order` NOT NULL default 0。

### 6.4 `foreshadows` / `foreshadow_relations`（novel.db）— 伏笔

- `foreshadows`：`id` PK `frs_*` · `project_id` NOT NULL（索引） · `name` VARCHAR(200) NOT NULL ·
  `description` NOT NULL default `''` ·
  `planted_chapter_id`（索引）/ `planned_chapter_id` / `paid_chapter_id`（均 NULL，**无 FK**） ·
  `status` NOT NULL default `open`（索引；`open`/`paid`/`dropped`） ·
  `importance` NOT NULL default 1。
- `foreshadow_relations`：`id` PK `frl_*` · `project_id` NOT NULL（索引） ·
  `foreshadow_id` NOT NULL，FK→`foreshadows.id` `CASCADE`（索引） ·
  `related_type` NOT NULL · `related_id` NOT NULL（索引） · `note` NOT NULL default `''`。

## 7. AI 系统

### 7.1 `model_configs`（studio.db）— 模型配置

| 列 | 类型 | 默认 | 用途 |
|---|---|---|---|
| `id` | VARCHAR(40) | PK，`mdl_*` | — |
| `name` | VARCHAR(120) | NOT NULL | 显示名 |
| `provider` | VARCHAR(64) | `openai_compatible` | 提供方 |
| `base_url` | TEXT | `''` | API 基址 |
| `model_name` | VARCHAR(200) | NOT NULL | 模型 id |
| `api_key_ref` | VARCHAR(200) | NULL | **密钥引用标签**，不存明文 |
| `temperature` / `top_p` | FLOAT | 0.8 / 1.0 | 采样 |
| `max_tokens` / `timeout_s` / `retry_count` | INT/FLOAT/INT | 4096 / 120.0 / 2 | 限制 |
| `context_window` | INTEGER | 32768 | 上下文窗口（预算基准） |
| `max_output_tokens` | INTEGER | 4096 | 单次输出上限 |
| `supports_streaming` / `supports_json_mode` / `supports_vision` / `supports_tools` | BOOLEAN | true / false / false / false | 能力画像 |
| `input_price_per_1m` / `output_price_per_1m` | FLOAT | 0.0 | 单价（每百万 token） |
| `capabilities` | JSON | `{}` | 自由扩展能力描述 |
| `notes` | TEXT | `''` | 备注 |
| `is_active` / `is_default` | BOOLEAN | true / false（均索引） | 状态 |
| `fallback_ids` | JSON | `[]` | 降级链（有序 model_config id） |
| `row_version` | INTEGER | 1 | 乐观锁 |

无软删除。

### 7.2 `prompt_templates`（studio.db）— 提示词模板

`id` PK `prm_*` · `key` VARCHAR(120) NOT NULL（索引；如 `chapter_outline`） ·
`name` NOT NULL · `version` NOT NULL default 1（生成记录引用） ·
`content` NOT NULL · `variables` JSON NOT NULL default `[]` ·
`description` NOT NULL default `''` · `is_active` NOT NULL default true（索引） · `row_version`。

### 7.3 `agent_configs`（studio.db）— Agent 模型绑定

`id` PK `agt_*` · `agent_type` VARCHAR(64) NOT NULL（索引；总编/大纲/写作/人物/剧情/连贯性/润色/记忆） ·
`display_name` NOT NULL ·
`model_config_id` NULL，FK→`model_configs.id` `SET NULL`（绑定模型） ·
`temperature` / `max_tokens` NULL（覆盖模型默认） ·
`system_prompt` NOT NULL default `''` · `params` JSON NOT NULL default `{}` ·
`is_active` NOT NULL default true · `row_version`。

### 7.4 `generation_tasks`（studio.db）— 任务

| 列 | 类型 | 约束 | 用途 |
|---|---|---|---|
| `id` | VARCHAR(40) | PK，`tsk_*` | — |
| `project_id` | VARCHAR(40) | NULL，FK→`projects.id` `CASCADE`（索引） | 所属项目（可为全局任务） |
| `kind` | VARCHAR(64) | NOT NULL，索引 | 任务类型 |
| `status` | VARCHAR(32) | NOT NULL default `pending`，索引 | `pending`/`running`/`done`/`failed`/`paused` |
| `model_config_id` | VARCHAR(40) | NULL，FK→`model_configs.id` `SET NULL` | 实际使用的模型 |
| `prompt_version` | INTEGER | NULL | 使用的提示词版本 |
| `payload` / `result` | JSON | NOT NULL default `{}` | 入参 / 出参 |
| `error` | TEXT | NULL | 错误信息 |
| `progress` | FLOAT | NOT NULL default 0.0 | 0.0–1.0 |
| `priority` | INTEGER | NOT NULL default 0，索引 | 数值大者优先 |
| `attempt` / `max_attempts` | INTEGER | NOT NULL default 0 / 3 | 重试 |
| `idempotency_key` | VARCHAR(128) | NULL，索引 | 幂等键，防重复计费 |
| `input_tokens` / `output_tokens` / `cost` | INTEGER/INTEGER/FLOAT | NOT NULL default 0 / 0 / 0.0 | 用量与成本 |
| `started_at` / `finished_at` | DATETIME | NULL | 起止时间 |
| `row_version` | INTEGER | NOT NULL default 1 | 乐观锁 |

### 7.5 `task_logs`（studio.db）— 任务日志

`id` PK `log_*` ·
`task_id` NOT NULL，FK→`generation_tasks.id` `CASCADE`（索引） ·
`level` VARCHAR(16) NOT NULL default `info` · `message` NOT NULL ·
`context` JSON NOT NULL default `{}`。

## 8. 迁移策略

### 8.1 两个独立的版本号

| 版本 | 存储位置 | 含义 | 写入方 |
|---|---|---|---|
| 应用 schema 版本 | `studio.db` → `app_meta["schema_version"]` | **studio.db 的表结构版本** | `Runtime._stamp_schema_version()` |
| 项目文件格式版本 | `novel.db` → `project_meta["schema_version"]`，镜像到 `projects.schema_version` 与 `project.json` | **单个项目 novel.db 的格式版本** | `create_project_database()` |

两者都来自 `app/core/config.py::SCHEMA_VERSION = 1`，**与 `Settings.app_version`（`0.1.0`）分离**。
设计意图：软件从 0.1.0 升到 0.2.0 时，未改表结构的老项目仍可读；只有文件格式真正变化时才提升
`SCHEMA_VERSION`。`Project.schema_version` 是 `studio.db` 对同一事实的缓存，
便于列表页不打开每个项目库就能判断「老项目是否需要迁移」。

### 8.2 当前实现与风险

`create_project_database()` 现在只做两件事，版本号**不由它写**：

```python
database = Database(f"sqlite+pysqlite:///{path.as_posix()}", label=path.name)
Base.metadata.create_all(database.engine)          # 只建缺失的表，不改已有表
database.migrate("project_meta", backup_root=path.parent.parent / "backups")
```

`Database.migrate()`（`app/db/session.py`）在**一个事务**里调用
`app/db/migrations.py::run()`，语义有四条硬规则（模块 docstring 明确）：

1. **拒绝降级**：库里版本 > 本构建认识的版本 → 抛 `RuntimeError`
   （`"Refusing to open to avoid data loss"`），绝不半读。
2. **改前必备份**：有待执行迁移时，先调 `backup()` → `Database.backup_to()`（SQLite 在线备份 API）
   写到 `<backup_root>/backups/<label>-<timestamp>.db`。
3. **单事务**：任一迁移失败则整体回滚，版本号停在原地，下次启动重试同一步。
4. **逐步打戳**：每步成功后立刻 `_stamp(version)`，只有全部成功才到达 `latest_version()`。

`studio.db` 走同一条路（`Runtime._migrate_studio()`，`backup_root = data_dir`，
表名 `app_meta`）。

⚠️ 仍然存在的风险：`Base.metadata.create_all()` 只补缺失的**表**，不会给已有表加**列**。
如果以后给 `chapters` 加一列而不写迁移步骤，老项目打开后不会报错，但新代码读写该列会失败。
新增列必须同时写 `@migration(2)` 步骤（`migrations.MIGRATIONS` 里追加一条
`(2, "add chapters.foo", fn)`）。

### 8.3 迁移流程（已实现，无 alembic）

```
打开项目
  ├─ Base.metadata.create_all()          # 只补缺失的表
  └─ Database.migrate("project_meta")
       ├─ read_version() → 0 表示全新库
       │    └─ 无待执行步骤时直接 _stamp(target) 并返回
       ├─ current > target → RuntimeError（拒绝降级）
       ├─ 有待执行步骤 → backup()（SQLite 在线备份 API）
       ├─ 逐个执行 + 逐步 _stamp，全部在 engine.begin() 的单一事务内
       └─ 返回已应用的版本列表
```

`alembic==1.20.1` 仍在依赖里，但仓库**无 `alembic/` 目录、无 `alembic.ini`、无版本脚本**；
当前建表与迁移均由自研的 `app/db/migrations.py` 完成（v1 是 baseline 空步骤，
存在的意义是让「版本」有真实指向，后续改动沿同一路径追加）。

### 8.4 备份机制（已实现，仅迁移使用）

`Database.backup_to(target)` 用 `sqlite3.Connection.backup()`（SQLite 在线备份 API，
非文件拷贝）——即使章节正在写入，得到的也是一致性快照。配套
`integrity_check()`（`PRAGMA integrity_check`）、`vacuum()`、`checkpoint()`
（`PRAGMA wal_checkpoint(TRUNCATE)`，把 WAL 折回主文件）。

调用方：`backup_to()` 仅被 `Database.migrate()` 用于「迁移前快照」；
`checkpoint()` 被 `ProjectService.duplicate()` 调用（复制前折回 WAL，
否则拷走的主库文件会丢最近章节）；`integrity_check()` 与 `vacuum()` **无调用方**
（无备份 API、无定时任务、无「数据库维护」入口）。
`project_backups` 表目前**没有任何写入方**。

## 9. 软删除与检索过滤

### 9.1 哪些表有软删除

| 有 `is_deleted`（8） | 无 `is_deleted`（27） |
|---|---|
| `projects`、`chapters`、`knowledge_chunks`、`characters`、`locations`、`factions`、`items`、`events` | `volumes`、`paragraphs`、`chapter_versions`、`chapter_summaries`、`outlines`、`scenes`、`embeddings`、`retrieval_logs`、`memory_snapshots`、`knowledge_relations`、`character_states`、`relationships`、`abilities`、`world_rules`、`event_participants`、`timelines`、`timeline_entries`、`foreshadows`、`foreshadow_relations`、`model_configs`、`prompt_templates`、`agent_configs`、`generation_tasks`、`task_logs`、`app_meta`、`project_meta` |

设计含义：只有「用户可删除的业务实体」才软删；派生物（向量、关系边、状态、日志）随主体
**级联物理删除**，否则检索会命中已删内容的衍生数据。

### 9.2 已实现的过滤

软删除过滤目前已实现三处（`ProjectService` 与 `NovelService`）：

```python
# ProjectService.list()
if not include_deleted:
    statement = statement.where(Project.is_deleted.is_(False))
# ProjectService.get()
if project is None or (project.is_deleted and not include_deleted):
    raise NotFound(...)
# ProjectService.count() / find_by_slug() / exists()  同样硬编码排除已删行

# NovelService.list_chapters()
if not include_deleted:
    statement = statement.where(Chapter.is_deleted.is_(False))
# NovelService._require_chapter()   # get / update / delete / versions 全走这里
if chapter is None or chapter.is_deleted or chapter.project_id != project_id:
    raise NotFound(...)
```

`ProjectUpdate` 无法修改 `is_deleted`，只能经 `delete()` 置位；
`ChapterUpdate` 同样不含 `is_deleted`。
`find_by_slug()` 与 `exists()` 同样硬编码排除已删行。

### 9.3 尚未实现的过滤（重要）

`novel.db` 的**派生表**查询侧完全没有实现 —— `knowledge_chunks`、`characters`、`events`
等表的软删除过滤规则**目前只存在于文档层面**。将来实现检索时必须遵守：

| 规则 | 现状 |
|---|---|
| 章节列表 | ✅ 已实现（`NovelService.list_chapters` 默认 `is_deleted = 0`；`?include_deleted=true` 可看软删行） |
| 知识块检索 | ❌ 未实现（无检索代码）；必须 `WHERE is_deleted = 0`，并提供「含已删」开关给回收站 |
| 向量检索 | ❌ 未实现；须先过滤 `knowledge_chunks.is_deleted`，再排除 `embedding_model/version` 不匹配的向量 |
| 关联展开 | ❌ 未实现；`characters`/`locations`/`events` 被引用时，主体已软删则跳过该关联 |
| 唯一约束 | ✅ 已由部分唯一索引解决：`characters` 只在 `is_deleted = 0` 的行里唯一；`locations`/`items`/`factions` 的 `name` 目前**没有任何唯一约束**，重名是允许的 |
| 删章后的孤儿块 | ❌ 未清理；`knowledge_chunks.chapter_id` 无 FK，需检索侧显式过滤（见 [api.md](api.md) §8 缺陷 6） |

## 10. 级联规则

### 10.1 有外键的级联（数据库层强制）

所有连接执行 `PRAGMA foreign_keys=ON`，下列 `ON DELETE` 真实生效。
实测确认：`PRAGMA foreign_keys` = `1`，`journal_mode` = `wal`，`busy_timeout` = `5000`。

| 子表.列 | 父表 | 策略 | 效果 |
|---|---|---|---|
| `chapters.volume_id` | `volumes` | `SET NULL` | 删卷 → 章节保留，变无卷 |
| `paragraphs.chapter_id` | `chapters` | `CASCADE` | 删章 → 段落全删 |
| `chapter_versions.chapter_id` | `chapters` | `CASCADE` | 删章 → 版本全删 |
| `chapter_summaries.chapter_id` | `chapters` | `CASCADE` | 删章 → 摘要全删 |
| `scenes.chapter_id` | `chapters` | `CASCADE` | 删章 → 场景全删 |
| `embeddings.chunk_id` | `knowledge_chunks` | `CASCADE` | 删块 → 向量全删 |
| `character_states.character_id` | `characters` | `CASCADE` | 删人物 → 状态史全删 |
| `relationships.source_character_id` / `target_character_id` | `characters` | `CASCADE` | 删人物 → 关系全删 |
| `event_participants.event_id` / `character_id` | `events` / `characters` | `CASCADE` | 删事件或人物 → 参与记录全删 |
| `timeline_entries.timeline_id` | `timelines` | `CASCADE` | 删时间线 → 条目全删 |
| `timeline_entries.event_id` | `events` | `SET NULL` | 删事件 → 条目保留但无事件 |
| `foreshadow_relations.foreshadow_id` | `foreshadows` | `CASCADE` | 删伏笔 → 关联全删 |
| `project_backups.project_id` | `projects` | `CASCADE` | 删项目 → 备份记录全删 |
| `generation_tasks.project_id` | `projects` | `CASCADE` | 删项目 → 任务全删 |
| `task_logs.task_id` | `generation_tasks` | `CASCADE` | 删任务 → 日志全删 |
| `projects.default_model_config_id` / `embedding_model_config_id` | `model_configs` | `SET NULL` | 删模型 → 项目仍可用 |
| `agent_configs.model_config_id` | `model_configs` | `SET NULL` | 删模型 → Agent 回落默认 |
| `generation_tasks.model_config_id` | `model_configs` | `SET NULL` | 删模型 → 任务保留历史 |

**实测**（插入 1 章 + 1 段落 + 1 版本 + 1 场景 + 1 知识块 + 1 向量后 `DELETE FROM chapters`）：

```
BEFORE                {'chapters':1,'paragraphs':1,'chapter_versions':1,'scenes':1,
                       'knowledge_chunks':1,'embeddings':1,'characters':2}
AFTER_CHAPTER_DELETE  {'chapters':0,'paragraphs':0,'chapter_versions':0,'scenes':0,
                       'knowledge_chunks':1,'embeddings':1,'characters':2}
```

CASCADE 对段落/版本/场景生效，但**知识块与向量残留** —— 见 10.2。

### 10.2 无外键的逻辑引用（需应用层维护）

以下列**没有 FK**，删除主体时数据库**不会**清理引用：

| 引用列 | 指向 | 风险 |
|---|---|---|
| `chapters.pov_character_id` | `characters` | 人物删除后视角悬空 |
| `scenes.location_id`、`character_states.location_id`、`events.location_id` | `locations` | 地点删除后悬空 |
| `knowledge_chunks.chapter_id` / `scene_id` / `volume_id` | 对应表 | 章节删除后知识块变孤儿，**不会被 CASCADE 清理** |
| `chapter_summaries.model_config_id` | `model_configs` | 仅作历史记录，允许悬空 |
| `characters.first_chapter_id` | `chapters` | 悬空 |
| `outlines.parent_id` | `outlines` | 自引用无 FK，父节点删除后子节点孤立 |
| `relationships.since_event_id` / `since_chapter_id` | `events` / `chapters` | 悬空 |
| `foreshadows.planted_chapter_id` / `planned_chapter_id` / `paid_chapter_id` | `chapters` | 悬空 |
| `events.chapter_id` / `events.location_id` | `chapters` / `locations` | 悬空 |
| `knowledge_relations.source_id` / `target_id` | 多态 | 悬空 |

⚠️ **最重要的缺口**：删除章节时 `paragraphs`/`chapter_versions`/`chapter_summaries`/`scenes`
会被 CASCADE 清掉，但 **`knowledge_chunks` 与 `embeddings` 不会** —— 它们对 `chapter_id`
只有普通索引，没有外键。直接导致两个已识别风险：检索命中已删章节的原文；库体积持续膨胀。
服务层的删除逻辑必须显式删除对应 `knowledge_chunks`（`embeddings` 会随 CASCADE 一起删）。

### 10.3 项目硬删除时的目录清理

`ProjectService.delete(hard=True)` 顺序：

```python
target = Path(project.path)
ensure_within(self.projects_root, target)   # 路径沙箱，防越界删除
session.delete(project)                      # 删注册表行
session.flush()                              # 触发 project_backups / generation_tasks CASCADE
self.registry.close(project_id)              # 关闭该项目已打开的 engine
remove_project_dir(target)                   # shutil.rmtree 整个目录树
```

顺序正确（先关连接再删目录）。但 `remove_project_dir` 失败（文件被占用、权限不足）时，
注册表行已删而目录残留，产生**孤儿目录**，当前无补偿逻辑。

软删除（`hard=False`）只改 `is_deleted`/`deleted_at`/`status="deleted"` 并 `row_version += 1`，
**不碰磁盘**，项目目录仍可被 `is_project_dir()` 识别。

## 11. 实现缺口汇总

✅ 已修复（保留记录）：
`app_meta`/`project_meta`/`project_backups` 的 `updated_at` 重声明缺陷（改继承 `TimestampMixin`）·
`characters` 唯一约束含软删行（改部分唯一索引 `... WHERE is_deleted = 0`）·
`create_project_database` 无条件覆盖 `schema_version`（改由 `app/db/migrations.py` 独占打戳，
拒绝降级 + 迁移前在线备份）· `POST /duplicate` 的 500（`create()` 显式 `dispose()` + 复制前 `checkpoint()`）。

仍存在：

`SchemaVersionMixin` 定义但无表继承（`schema_version` 只在 `projects` 列与两个 meta 表） ·
`create_all()` 负责建新表、`migrations.run()` 负责版本推进（**已有真实迁移执行器**，
v1 为 baseline 空步骤；新增表结构改动需手写 `@migration(2)` 之类的步骤） ·
`alembic` 依赖在册但 `alembic/` 目录与 `alembic.ini` 都不存在（自研执行器已够用，
alembic 属冗余依赖） ·
`embeddings` 是普通 BLOB 表，未用 sqlite-vec 虚拟表、无向量检索 ·
无 FTS5 / sqlite-vec 虚拟表（`indexes/fulltext`、`indexes/vector` 目录已建但无对应表，
实测 `sqlite_master` 中 `VIRTUAL TABLE` 为 0 条） ·
无服务层删除逻辑（`knowledge_chunks` 对章节无 FK，删章后残留） ·
`ProjectBackup` 无写入方（迁移执行器写的是文件系统备份，不写这张表） ·
`backup_to()` / `integrity_check()` / `vacuum()` / `checkpoint()` 中，
只有 `checkpoint()` 被 `duplicate()` 调用，其余无调用方 ·
`read_manifest` / `is_project_dir` 无调用方（无 project.json 反向导入） ·
`volumes.word_count` / `volumes.status` 无维护逻辑 ·
`chapters.summary` / `chapters.pov_character_id` 无写入路径 ·
`retrieval_logs` / `memory_snapshots` / `knowledge_relations` 三张表已建但无任何读写代码。