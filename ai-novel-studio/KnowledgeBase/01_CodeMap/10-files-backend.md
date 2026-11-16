---
name: files-backend
description: 后端文件级清单：backend/app 下 56 个 .py 的归属、行数、职责、顶层符号。找后端代码用这页，不用扫目录。
status: 结构级（2026-11-16 逐文件取证）
---

# 后端文件级清单（`backend/app/**/*.py`，56 个）

> 结构级：只列"文件存在、归哪、约行数、导出符号"，不写行为结论。行号是取证时快照，动手前复核。
> 职责/边界见 `../../docs/api.md`、`docs/database.md`；坑见 `../05_Plan/TaskPitfalls.md`。

## api/routes/（8）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---:|---|---|
| `api/routes/ai.py` | 233 | AI/SSE/提示词/任务端点 | `router:26` `list_operations:44` `list_prompts:50` `update_prompt:69` `summarize_chapter:101` `generate_outline:121` `stream_summary:143` `stream_outline:167` `run_ai:190` `stream_ai:195` `list_tasks:214` |
| `api/routes/novels.py` | 183 | 卷/章/版本/采纳端点 | `router:26` `create_chapter:93` `accept_ai:157` `snapshot_version:169` `restore_version:180`（14 个端点） |
| `api/routes/projects.py` | 93 | 项目 CRUD/复制/统计 | `router:19` `create_project:32` `delete_project:63` `duplicate_project:78` `project_stats:91` |
| `api/routes/model_configs.py` | 61 | 模型配置 CRUD/设默认 | `router:12` `create_model:21` `set_default:59` |
| `api/routes/system.py` | 41 | 系统统计 | `router:11` `studio_stats:15` |
| `api/routes/health.py` | 40 | 健康/认证/系统信息 | `router:12` `health:16` `system_info:29` |
| `api/routes/agent_configs.py` | 32 | 每 Agent 模型绑定 | `router:15` `upsert_agent_config:28` |
| `api/routes/__init__.py` | 13 | 包声明 | — |

## api/（3）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---:|---|---|
| `api/deps.py` | 46 | FastAPI 依赖注入接线 | `get_runtime:17` `get_novel_service:33` `get_ai_service:37` |
| `api/router.py` | 16 | 汇总路由 | `api_router:9` |
| `api/__init__.py` | 5 | 包声明 | — |

## services/（6）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---:|---|---|
| `services/ai_service.py` | 1195 | AI 编排：上下文/模型解析/各操作/记账 | `AIService:177` `_Streamed:63` `_usage_dict:74` `_summary_payload:91` `_outline_payload:119` |
| `services/novel_service.py` | 536 | 卷/章/版本/记忆/大纲操作 | `NovelService:62` `_as_utc:51` `volumes_to_out:535` |
| `services/project_service.py` | 274 | 项目生命周期与目录/库 | `ProjectService:56` |
| `services/model_config_service.py` | 208 | 模型配置与密钥联动 | `ModelConfigService:61` `to_out:172` `ensure_default_model:181` |
| `services/agent_config_service.py` | 168 | Agent 绑定与操作映射 | `operation_agent_type:58` `AgentConfigService:63` |
| `services/__init__.py` | 7 | 包声明 | — |

## ai/（含 llm/、prompts/，11）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---:|---|---|
| `ai/llm/openai_compatible.py` | 299 | OpenAI 兼容适配器：重试/错误/SSE/用量 | `RETRYABLE_STATUS:37` `OpenAICompatibleAdapter:46` |
| `ai/prompts/builtin.py` | 250 | 内置提示词与操作映射 | `PROMPTS:77` `PROMPTS_BY_KEY:239` `OPERATIONS:242` `SUMMARY_PROMPT_KEY:68` `OUTLINE_PROMPT_KEY:75` |
| `ai/prompts/service.py` | 198 | 提示词落库/版本/渲染 | `render:24` `PromptService:42` |
| `ai/structured.py` | 155 | 结构化 JSON：宽松解析+一次修复 | `parse_json_object:39` `as_str_list:62` `StructuredReply:95` `complete_json:118` |
| `ai/llm/registry.py` | 136 | 适配器构建与降级链 | `_NATIVE_ONLY:25` `build_adapter:31` `ChatClient:43` |
| `ai/llm/errors.py` | 79 | 错误层级（带 retryable） | `LLMAdapterError:10` + 8 子类 |
| `ai/llm/types.py` | 65 | 供应商中立类型 | `ChatMessage:12` `LLMRequest:32` `LLMResponse:46` `StreamChunk:56` |
| `ai/llm/base.py` | 61 | 适配器抽象+token 估算 | `estimate_tokens:15` `BaseAdapter:30` |
| `ai/llm/__init__.py` | 28 | 导出 | `__all__:18` |
| `ai/__init__.py` | 17 | 导出 | `__all__:11` |
| `ai/prompts/__init__.py` | 13 | 导出 | `__all__:6` |

> 注意：`ai/__init__.py:1` 宣称 "retrieval-augmented context"，但 ai/ 下无 retrieval 模块 → `T-11`。

## models/（3）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---:|---|---|
| `models/novel.py` | 522 | 小说域 ORM（章/记忆/大纲/人物/世界观） | `Volume:36` `Chapter:48` `ChapterSummary:107` `Outline:128` `Character:287` `Event:434`（26 个类） |
| `models/studio.py` | 229 | 工作室域 ORM（配置/任务/备份） | `ModelConfig:25` `PromptTemplate:71` `AgentConfig:90` `Project:113` `GenerationTask:169` |
| `models/__init__.py` | 85 | 元数据导出 | — |

## db/（5）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---:|---|---|
| `db/session.py` | 197 | SQLite 引擎/会话/迁移入口 | `sqlite_path_from_url:40` `_configure_connection:53` `_load_sqlite_vec:67` `Database:85` |
| `db/migrations.py` | 184 | 双库迁移执行器（备份/版本/拒降级） | `latest_version:88` `read_version:93` `plan:123` `run:129` `backup_path_for:175` |
| `db/project_db.py` | 115 | 每项目库访问与注册表 | `create_project_database:35` `ProjectDatabaseRegistry:61` `collect_stats:92` |
| `db/base.py` | 74 | 声明基类与列 mixin | `Base:30` `RowVersionMixin:51` `SoftDeleteMixin:57` `SchemaVersionMixin:69` |
| `db/__init__.py` | 14 | 包声明 | — |

## core/（8）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---:|---|---|
| `core/keystore.py` | 189 | API Key 加密（DPAPI/文件） | `SECRETS_FILE:32` `protect:92` `unprotect:109` `SecretStore:126` |
| `core/errors.py` | 150 | 错误层级+FastAPI 处理器 | `StudioError:21` `register_error_handlers:87` |
| `core/config.py` | 135 | 应用配置 | `APP_NAME:24` `SCHEMA_VERSION:26` `Settings:50` `get_settings:128` |
| `core/logging.py` | 114 | 结构化日志 | `_redact:34` `configure_logging:40` |
| `core/paths.py` | 109 | 项目目录布局与路径安全 | `ensure_project_layout:46` `project_db_path:73` `ensure_within:103` |
| `core/security.py` | 64 | 本地 API 共享密钥鉴权 | `generate_token:22` `require_token:45` |
| `core/ids.py` | 63 | ID/slug/路径拼接 | `new_id:18` `slugify:33` `safe_join:51` |
| `core/__init__.py` | 5 | 包声明 | — |

## schemas/（6）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---:|---|---|
| `schemas/model_config.py` | 144 | 模型配置 DTO | `PROVIDERS:10` `ModelConfigCreate:71` `ModelConfigOut:108` |
| `schemas/novel.py` | 141 | 卷/章/版本 DTO | `CHAPTER_STATUSES:9` `ChapterCreate:39` `ChapterAcceptAi:111` |
| `schemas/ai.py` | 140 | AI 端点 DTO | `AIRequest:10` `AIResult:39` `OutlineResult:77` `PromptUpdate:111` `available_operations:139` |
| `schemas/project.py` | 119 | 项目 DTO | `ProjectCreate:11` `ProjectOut:79` |
| `schemas/__init__.py` | 49 | 导出 | — |
| `schemas/agent_config.py` | 40 | Agent 绑定 DTO | `AgentConfigUpsert:8` `AgentConfigOut:31` |

## utils/（2）+ 顶层（4）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---:|---|---|
| `utils/text.py` | 42 | 文本计数/分段/摘要 | `count_words:12` `split_paragraphs:25` `excerpt:32` |
| `utils/__init__.py` | 5 | 包声明 | — |
| `main.py` | 200 | 应用工厂与中间件 | `TokenMiddleware:31` `ErrorEnvelopeMiddleware:87` `create_app:139` |
| `runtime.py` | 86 | 运行时对象（装配服务） | — |
| `__main__.py` | 26 | `python -m app` 入口 | `main:11` |
| `__init__.py` | 3 | 包声明 | — |

## 统计

56 个 .py（app 下无测试文件）；`backend/tests/` 15 个测试文件、约 105 用例（AI 相关 8 文件 49 例：adapters 13 / fallback 9 / output 6 / stream_struct 4 / prompt 6 / summary 4 / outline 5 / stream_e2e 2；其余 7 文件 56 例：novels 12 / model_configs 11 / projects 10 / health 7 / migrations 6 / accept_ai 5 / agent_configs 5）。
