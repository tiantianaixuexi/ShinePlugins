# HTTP API 契约

**第 1–4 节已实现并实测验证**（代码 `backend/app/api/`，验证方式见 §7）；
**第 5 节是计划中但尚未实现的接口**，调用会返回 404，请勿当作已完成。

- 基础路径 `/api`（`Settings.api_prefix`）· 默认 `http://127.0.0.1:8765` · 实际端口由桌面壳动态注入
- Swagger UI `/api/docs` · OpenAPI `/api/openapi.json`（`redoc_url` 已禁用）
- 这两个文档端点位于 `TokenMiddleware.OPEN_PATHS` 白名单内，**无需令牌**
  （实测：带令牌 200，不带令牌同样 200）。
  `/healthz` 在 `/api` 之外，也是免鉴权的。

## 1. 通用约定

### 1.1 认证

所有 `/api` 请求需带共享密钥（`/api/docs`、`/api/openapi.json` 除外），两种写法等价：

```
Authorization: Bearer <token>
X-Studio-Token: <token>
```

`<token>` 由桌面壳每次启动生成并经 `NOVEL_STUDIO_AUTH_TOKEN` 注入；
未设置时**鉴权完全关闭**（仅限本地开发）。比较用 `hmac.compare_digest`（常量时间）。

两道校验：ASGI 层 `TokenMiddleware`（`app/main.py`，拦所有 `/api` 含未匹配 404）
+ FastAPI 依赖 `require_token`（`app/core/security.py`，保留给 WebSocket 等场景）。

### 1.2 错误信封

所有失败响应统一为：

```json
{"error": {"code": "auth_required", "message": "Missing or invalid access token.", "details": null}}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | string | 稳定机器可读错误码，客户端据此分支 |
| `message` | string | 人类可读，**不要**用于逻辑判断 |
| `details` | object \| array \| null | 结构化补充，可能为空 |

| code | HTTP | 触发条件 | 状态 |
|---|---|---|---|
| `auth_required` | 401 | 令牌缺失或错误 | ✅ |
| `validation_failed` | 422 | Pydantic 校验失败；业务前置条件不满足 | ✅ |
| `not_found` | 404 | 项目/卷/章节/版本/模型配置不存在；路由不存在 | ✅ |
| `conflict` | 409 | `row_version` 不匹配；目标目录已存在 | ✅ |
| `http_error` | 4xx/5xx | 未映射的 Starlette `HTTPException`（如 405） | ✅ |
| `internal_error` | 500 | 未捕获异常，`details.type` 为异常类名 | ✅ |
| `forbidden` / `project_locked` / `provider_error` / `task_failed` | 403 / 423 / 502 / 500 | 预留，当前**无任何代码路径抛出** | ⚠️ |

三层保障：`ErrorEnvelopeMiddleware`（最外层，捕获逃逸异常）→
`@app.exception_handler(Exception)`（第二道）→ 专用处理器（`StudioError` /
`RequestValidationError` / `StarletteHTTPException`）。`internal_error` **不外泄堆栈**，
只给异常类名；堆栈进 structlog。

### 1.3 状态码与格式

| 场景 | 码 | 响应体 |
|---|---|---|
| 读取成功 | 200 | 资源或**裸数组**（无 `{items,total}` 包装，无分页元信息） |
| 创建成功 | 201 | 创建后的资源 |
| 删除成功 | 204 | **空** |
| 校验失败 | 422 | 错误信封 |
| 未认证 / 不存在 / 并发冲突 / 方法不允许 / 异常 | 401 / 404 / 409 / 405 / 500 | 错误信封 |

- 时间戳格式**不统一**，客户端必须容忍三种形式：
  - ORM 默认值（`CURRENT_TIMESTAMP`）产生**无时区后缀、无微秒**：
    `2026-11-16T06:58:51`（如 `POST` 卷/章节响应里的 `created_at`、`updated_at`）；
  - 服务层用 `datetime.now(UTC)` 显式赋值时带 `Z` 与微秒：
    `2026-11-16T06:58:51.705535Z`（如 `PUT` 章节后的 `updated_at`、所有版本 `created_at`）；
  - `health.time` 与 `/api/system/stats` 为带 `+00:00` 的 UTC。
  根因：`TimestampMixin.updated_at` 有 `onupdate=CURRENT_TIMESTAMP`，但服务层
  （`novel_service._now()`、`project_service.update`）会显式覆盖成带时区的值。
- 空值一律 JSON `null`，不是空字符串。
- 所有 `PATCH`/`PUT` 请求体遵循「**字段缺失或 `null` 都表示不修改**」；显式清空只有
  `model_configs.api_key: ""` 一个例外（见 3.12.4），而 `model_configs` 的
  `base_url`/`capabilities`/`notes`/`fallback_ids` 传 `null` 会 500（见 §8 缺陷 13）。

## 2. 已实现端点总览

实测共 **39 个**（`/healthz` + 38 个 `/api/*`），按 router 分布：
`ai` 8 · `novels` 14 · `projects` 7 · `model_configs` 6 · `health` 2 · `system` 1。
`/healthz` 为 `include_in_schema=False`，不在 OpenAPI schema 中。

| 方法 | 路径 | 说明 | 成功码 |
|---|---|---|---|
| GET | `/healthz` | 免鉴权存活探针（不在 schema 中） | 200 |
| GET | `/api/health` | 带构建信息的就绪探针 | 200 |
| GET | `/api/system/info` | 安装信息 | 200 |
| GET | `/api/system/stats` | 跨项目聚合统计 | 200 |
| GET | `/api/projects` | 项目列表 | 200 |
| POST | `/api/projects` | 创建项目 | 201 |
| GET | `/api/projects/{project_id}` | 单个项目（含 stats） | 200 |
| PUT | `/api/projects/{project_id}` | 更新项目 | 200 |
| DELETE | `/api/projects/{project_id}` | 删除（默认软删） | 204 |
| POST | `/api/projects/{project_id}/duplicate` | 复制项目目录 | 201 |
| GET | `/api/projects/{project_id}/stats` | 项目计数器 | 200 |
| GET | `/api/projects/{project_id}/volumes` | 卷列表 | 200 |
| POST | `/api/projects/{project_id}/volumes` | 新建卷 | 201 |
| PATCH | `/api/projects/{project_id}/volumes/{volume_id}` | 更新卷 | 200 |
| DELETE | `/api/projects/{project_id}/volumes/{volume_id}` | 删卷（章节保留） | 204 |
| GET | `/api/projects/{project_id}/chapters` | 章节列表（无正文） | 200 |
| POST | `/api/projects/{project_id}/chapters` | 新建章节 | 201 |
| POST | `/api/projects/{project_id}/chapters/reorder` | 章节排序 | 200 |
| GET | `/api/projects/{project_id}/chapters/{chapter_id}` | 读单章（含正文） | 200 |
| PUT | `/api/projects/{project_id}/chapters/{chapter_id}` | 保存章节 | 200 |
| DELETE | `/api/projects/{project_id}/chapters/{chapter_id}` | 删章（软删） | 204 |
| GET | `/api/projects/{project_id}/chapters/{chapter_id}/versions` | 版本列表 | 200 |
| POST | `/api/projects/{project_id}/chapters/{chapter_id}/versions` | 强制快照 | 201 |
| POST | `/api/projects/{project_id}/chapters/{chapter_id}/versions/{version_id}/restore` | 恢复版本 | 200 |
| GET | `/api/model-configs` | 模型配置列表 | 200 |
| POST | `/api/model-configs` | 新建模型配置 | 201 |
| GET | `/api/model-configs/{model_id}` | 读单个模型配置 | 200 |
| PUT | `/api/model-configs/{model_id}` | 更新模型配置 | 200 |
| DELETE | `/api/model-configs/{model_id}` | 删除模型配置 | 204 |
| POST | `/api/model-configs/{model_id}/default` | 设为默认模型 | 200 |
| GET | `/api/ai/operations` | 可用写作操作名列表 | 200 |
| GET | `/api/ai/prompts` | Prompt 模板列表（含版本） | 200 |
| PATCH | `/api/ai/prompts/{key}` | 覆盖模板（写即新版本） | 200 |
| POST | `/api/ai/summary/{chapter_id}` | 生成并落库 L1 章节摘要 | 200 |
| POST | `/api/ai/outline/{chapter_id}` | 生成并落库章节大纲 | 200 |
| POST | `/api/ai/{operation}` | 执行写作操作（非流式） | 200 |
| POST | `/api/ai/{operation}/stream` | 执行写作操作（SSE 流） | 200 |
| GET | `/api/ai/tasks` | 最近生成任务（token/成本/错误） | 200 |
| POST | `/api/projects/{project_id}/chapters/{chapter_id}/accept-ai` | 采纳 AI 正文并留血缘 | 200 |

## 3. 端点详情

### 3.1 `GET /healthz`

免鉴权、不在 OpenAPI schema 中。

```bash
curl -s http://127.0.0.1:8765/healthz
# {"status":"ok"}
```

### 3.2 `GET /api/health`

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | `ok` / `starting`（`runtime.start()` 前） |
| `app` / `version` | string | `Settings.app_name` / `app_version` |
| `schema_version` | int | `studio.db` 的 schema 版本（`app_meta.schema_version`） |
| `environment` | string | 桌面壳注入 `desktop`，默认 `development` |
| `time` | string | 当前 UTC，带 `+00:00` |

```json
{"status":"ok","app":"AI Novel Studio","version":"0.1.0","schema_version":1,
 "environment":"development","time":"2026-11-16T06:25:04.579834+00:00"}
```

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/api/health
```

### 3.3 `GET /api/system/info`

| 字段 | 类型 | 说明 |
|---|---|---|
| `app` / `version` / `schema_version` / `environment` | — | 同上 |
| `data_dir` / `projects_dir` | string | 绝对路径 |
| `projects` | int | **未软删除**的项目数（`ProjectService.count()`） |
| `auth_required` | bool | 是否启用令牌鉴权 |

```json
{"app":"AI Novel Studio","version":"0.1.0","schema_version":1,"environment":"development",
 "data_dir":"C:\\Users\\<你>\\AppData\\Local\\AI Novel Studio",
 "projects_dir":"C:\\Users\\<你>\\AppData\\Local\\AI Novel Studio\\NovelProjects",
 "projects":3,"auth_required":true}
```

### 3.4 `GET /api/system/stats`

遍历所有项目（`limit=500`、`include_deleted=False`），逐个打开 `novel.db` 汇总。

| 字段 | 类型 | 说明 |
|---|---|---|
| `totals.projects` / `words` / `chapters` / `characters` / `chunks` | int | 汇总（`projects` = 列表长度） |
| `projects[].id` / `name` / `status` / `updated_at` | — | 项目摘要 |
| `projects[].words` / `chapters` | int | 该项目计数 |

```json
{"totals":{"projects":3,"words":0,"chapters":0,"characters":0,"chunks":0},
 "projects":[{"id":"proj_79033510e35e","name":"副本","status":"active",
              "updated_at":"2026-11-16T06:25:34","words":0,"chapters":0}]}
```

⚠️ 对每个项目都执行 `stats_for()`，逐个打开数据库，无缓存，项目多时较慢。

### 3.5 `GET /api/projects`

**查询参数**

| 参数 | 类型 | 默认 | 约束 |
|---|---|---|---|
| `limit` | int | 200 | `1 ≤ limit ≤ 500`，超出 422 |
| `offset` | int | 0 | `≥ 0` |
| `include_deleted` | bool | false | 是否含软删除项目 |

按 `updated_at DESC` 排序，响应为**裸数组**，元素为精简投影：
`id`、`name`、`novel_type`、`status`、`language`、`target_word_count`、
`target_chapter_count`、`updated_at`、`created_at`。

```json
[{"id":"proj_79033510e35e","name":"副本","novel_type":"web","status":"active",
  "language":"zh-CN","target_word_count":0,"target_chapter_count":0,
  "updated_at":"2026-11-16T06:25:34","created_at":"2026-11-16T06:25:34"}]
```

```bash
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/projects?limit=50&offset=0"
```

### 3.6 `POST /api/projects`

**请求体**（`ProjectCreate`）

| 字段 | 类型 | 必填 | 默认 | 约束 |
|---|---|---|---|---|
| `name` | string | ✅ | — | 1–200，去首尾空白后不得为空 |
| `novel_type` | string | | `web` | ≤64 |
| `synopsis` | string | | `""` | ≤20000 |
| `target_word_count` | int | | `0` | `0 ≤ n ≤ 1_000_000_000` |
| `target_chapter_count` | int | | `0` | `0 ≤ n ≤ 100_000` |
| `writing_style` | string | | `""` | ≤4000 |
| `target_reader` | string | | `""` | ≤200 |
| `language` | string | | `zh-CN` | ≤16 |
| `author` | string | | `""` | ≤200 |
| `default_model_config_id` / `embedding_model_config_id` | string \| null | | `null` | 无 FK 校验 |
| `settings` | object | | `{}` | 自由扩展 |

**响应 201** — 完整 `ProjectOut`：

| 字段 | 类型 | 新建时 |
|---|---|---|
| `id` | string | `proj_<12 hex>` |
| `name` / `slug` | string | `slug` 为 ASCII slug；中文名回退为 `id` |
| `novel_type` / `synopsis` / `writing_style` / `target_reader` / `language` / `author` | string | 同请求 |
| `target_word_count` / `target_chapter_count` | int | 同请求 |
| `status` | string | `active` |
| `path` | string | 项目目录绝对路径 |
| `schema_version` | int | `1` |
| `default_model_config_id` / `embedding_model_config_id` | string \| null | `null` |
| `settings` | object | `{}` |
| `row_version` | int | `1` |
| `created_at` / `updated_at` | string | 当前时间 |
| `stats` | object | 见 3.11，全为 0 |

实测（中文项目名，`slug` 因中文名 slug 为空而回退为 `id`）：

```json
{"id":"proj_42da528da1db","name":"验证小说","slug":"proj_42da528da1db",
 "novel_type":"web","synopsis":"中文简介","target_word_count":500000,
 "target_chapter_count":0,"writing_style":"","target_reader":"","language":"zh-CN",
 "author":"verify","status":"active",
 "path":"C:\\Users\\<你>\\AppData\\Local\\AI Novel Studio\\NovelProjects\\proj_42da528da1db",
 "schema_version":1,"default_model_config_id":null,"embedding_model_config_id":null,
 "settings":{},"row_version":1,"created_at":"2026-11-16T06:25:04",
 "updated_at":"2026-11-16T06:25:04",
 "stats":{"volumes":0,"chapters":0,"words":0,"characters":0,"outlines":0,
          "events":0,"foreshadows":0,"chunks":0,"versions":0}}
```

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"验证小说","synopsis":"中文简介","target_word_count":500000}' \
  http://127.0.0.1:8765/api/projects
```

**副作用**（`ProjectService.create`）：① 建目录 `<slug>-<shortid>` 或 `proj_<id>`；
② 建标准子目录树（`core/paths.py::PROJECT_SUBDIRECTORIES`）；③ 建 `database/novel.db`
并跑迁移写 `project_meta.schema_version`；④ 插 `projects` 行；⑤ 写 `project.json`。
任一步 `OSError` 会回滚目录并抛 `validation_failed`(422)。

**422 示例**（空名）：

```json
{"error":{"code":"validation_failed","message":"Request payload is invalid.",
 "details":{"errors":[{"type":"value_error","loc":["body","name"],
   "msg":"Value error, name must not be blank","input":"   ",
   "ctx":{"error":"name must not be blank"}}]}}}
```

### 3.7 `GET /api/projects/{project_id}`

**200** — 与 3.6 相同的 `ProjectOut`（含实时 `stats`）。

**404**

```json
{"error":{"code":"not_found","message":"Project proj_deadbeefcafe not found","details":null}}
```

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/api/projects/proj_42da528da1db
```

### 3.8 `PUT /api/projects/{project_id}`

**请求体**（`ProjectUpdate`）——所有字段可选，**只更新显式提供的字段**（`exclude_unset=True`）：

| 字段 | 类型 | 约束 |
|---|---|---|
| `name` | string \| null | 1–200；**显式 `null` 触发 422**（见下） |
| `novel_type` | string \| null | ≤64 |
| `synopsis` | string \| null | ≤20000 |
| `target_word_count` | int \| null | `0 ≤ n ≤ 1_000_000_000` |
| `target_chapter_count` | int \| null | `0 ≤ n ≤ 100_000` |
| `writing_style` | string \| null | ≤4000 |
| `target_reader` | string \| null | ≤200 |
| `language` | string \| null | ≤16 |
| `author` | string \| null | ≤200 |
| `status` | string \| null | ≤32 |
| `default_model_config_id` / `embedding_model_config_id` | string \| null | 显式 `null` = 清空 |
| `settings` | object \| null | — |
| `row_version` | int \| null | `≥ 1`，乐观锁，**不参与赋值** |

可更新字段受 `_COPYABLE_FIELDS` 白名单限制。传 `row_version` 且与库中不一致 → **409**：

```json
{"error":{"code":"conflict",
 "message":"Project was modified by someone else; reload and try again.",
 "details":{"expected":1,"actual":2}}}
```

不传 `row_version` 即最后写入者获胜。**200** 返回更新后的 `ProjectOut`，
`row_version` **+1**，`updated_at` 刷新。

```bash
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"验证小说改名","row_version":1}' \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db
# -> "name":"验证小说改名","row_version":2,"updated_at":"2026-11-16T06:25:08.032031"
```

未知字段被静默忽略（Pydantic `extra="ignore"`）。传 `"name": null` 会被
`ProjectUpdate._name_not_null` 拦下并返回 **422**（实测已确认，不再是 500）。

### 3.9 `DELETE /api/projects/{project_id}`

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `hard` | bool | false | `false` 软删；`true` 硬删（删行 + 删目录） |

**软删除**：置 `is_deleted=1`、`deleted_at=now`、`status="deleted"`、`row_version+1`，
关闭该项目已打开的数据库连接，**磁盘不动**。
**硬删除**：删注册表行（级联清 `project_backups` / `generation_tasks`）→ 关闭连接 →
`ensure_within()` 校验路径 → `shutil.rmtree` 整个目录树。

**204**，空响应体。

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8765/api/projects/proj_42da528da1db"          # 204

curl -s -o /dev/null -w "%{http_code}\n" -X DELETE -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8765/api/projects/proj_42da528da1db?hard=true"  # 204
```

删除后 `GET` 返回 404；列表默认不含该项，`?include_deleted=true` 仍可见（`status: "deleted"`）。

### 3.10 `POST /api/projects/{project_id}/duplicate`

**请求体**：`{"name": string}` — 必填，去空白后不得为空。

**响应 201** — 新项目的 `ProjectOut`。实现：先 `create()` 生成新项目 → `close()` 释放
SQLite 句柄 → 对源库 `checkpoint()` 把 WAL 折回主文件 → `rmtree` 新目录 →
`copytree` 源目录。只复制元数据字段
（`novel_type`/`synopsis`/目标字数/文风/语言/作者/`settings`）。

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"副本"}' \
  http://127.0.0.1:8765/api/projects/proj_b21e34ca90ba/duplicate
```

实测（2026-11-16）：**201**，目录内容一致，对应 `test_duplicate_copies_the_directory` 通过。
原先的 500 缺陷已修复（`create()` 现在显式 `dispose()`）。

### 3.11 `GET /api/projects/{project_id}/stats`

| 字段 | 类型 | 说明 |
|---|---|---|
| `volumes` | int | 卷数 |
| `chapters` | int | 章数（`COUNT(DISTINCT id)`，**含软删行**） |
| `words` | int | 总字数（`SUM(word_count)`，含软删行） |
| `characters` | int | 人物数 |
| `outlines` | int | 大纲节点数 |
| `events` | int | 事件数 |
| `foreshadows` | int | 伏笔数 |
| `chunks` | int | 知识块数 |
| `versions` | int | 章节版本数 |

```json
{"volumes":0,"chapters":0,"words":0,"characters":0,"outlines":0,
 "events":0,"foreshadows":0,"chunks":0,"versions":0}
```

注：`collect_stats()` 实际返回 10 个键（多一个 `words_total`，与 `words` 等价），
被 `ProjectStats` 丢弃，**不会**出现在响应中。

### 3.12 模型配置 `/api/model-configs`

密钥**只写不读**：数据库 `model_configs.api_key_ref` 存的是密钥标签，真实密钥在
`<data_dir>/secrets.json`（Windows 上 DPAPI 加密，其他平台仅 base64 + 0600）。
任何响应都**不含** `api_key` 字段，只有一个布尔 `has_api_key`。

#### 3.12.1 `POST /api/model-configs` — 201

**请求体**（`ModelConfigCreate`）

| 字段 | 类型 | 必填 | 默认 | 约束 |
|---|---|---|---|---|
| `name` | string | ✅ | — | 1–120，去空白后不得为空 |
| `provider` | string | | `openai_compatible` | 枚举，见下 |
| `base_url` | string | | `""` | ≤500 |
| `model_name` | string | ✅ | — | 1–200，去空白后不得为空 |
| `api_key` | string \| null | | `null` | ≤2000，**只写**，入库前加密 |
| `temperature` | float | | `0.8` | `0.0 ≤ n ≤ 2.0` |
| `top_p` | float | | `1.0` | `0.0 ≤ n ≤ 1.0` |
| `max_tokens` | int | | `4096` | `1 ≤ n ≤ 4_000_000` |
| `timeout_s` | float | | `120.0` | `0 < n ≤ 3600` |
| `retry_count` | int | | `2` | `0 ≤ n ≤ 10` |
| `context_window` | int | | `32768` | `1 ≤ n ≤ 100_000_000` |
| `max_output_tokens` | int | | `4096` | `1 ≤ n ≤ 4_000_000` |
| `supports_streaming` | bool | | `true` | — |
| `supports_json_mode` | bool | | `false` | — |
| `supports_vision` | bool | | `false` | — |
| `supports_tools` | bool | | `false` | — |
| `input_price_per_1m` | float | | `0.0` | `≥ 0` |
| `output_price_per_1m` | float | | `0.0` | `≥ 0` |
| `capabilities` | object | | `{}` | 自由扩展 |
| `notes` | string | | `""` | ≤4000 |
| `is_active` | bool | | `true` | — |
| `fallback_ids` | string[] | | `[]` | 降级链，有序 model_config id |

`provider` 合法值（`schemas/model_config.py::PROVIDERS`，其他值 422）：
`openai_compatible`、`openai`、`anthropic`、`gemini`、`ollama`、`deepseek`、
`azure_openai`、`custom`。

**响应 201** — `ModelConfigOut`（无 `api_key`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `mdl_<12 hex>` |
| `name` / `provider` / `base_url` / `model_name` | string | 同请求 |
| `temperature` / `top_p` / `max_tokens` / `timeout_s` / `retry_count` | — | 同请求 |
| `context_window` / `max_output_tokens` | int | 能力画像 |
| `supports_streaming` / `supports_json_mode` / `supports_vision` / `supports_tools` | bool | 能力画像 |
| `input_price_per_1m` / `output_price_per_1m` | float | 单价（每百万 token） |
| `capabilities` | object | 自由扩展 |
| `notes` | string | 备注 |
| `is_active` | bool | 是否可用 |
| `is_default` | bool | 是否默认；新建恒为 `false` |
| `fallback_ids` | string[] | 降级链 |
| `has_api_key` | bool | **是否已存密钥**（密钥本身永不返回） |
| `row_version` | int | 乐观锁 |
| `created_at` / `updated_at` | string | 时间戳 |

实测响应（`api_key` 已写入）：

```json
{"id":"mdl_d1595ebffc2e","name":"文档示例模型","provider":"openai_compatible",
 "base_url":"http://127.0.0.1:9/v1","model_name":"demo-model","temperature":0.7,
 "top_p":1.0,"max_tokens":4096,"timeout_s":120.0,"retry_count":2,
 "context_window":32768,"max_output_tokens":4096,"supports_streaming":true,
 "supports_json_mode":false,"supports_vision":false,"supports_tools":false,
 "input_price_per_1m":0.0,"output_price_per_1m":0.0,"capabilities":{},
 "notes":"","is_active":true,"is_default":false,"fallback_ids":[],
 "has_api_key":true,"row_version":1,
 "created_at":"2026-11-16T06:58:43","updated_at":"2026-11-16T06:58:43"}
```

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"本地模型","provider":"openai_compatible",
       "base_url":"http://127.0.0.1:11434/v1","model_name":"qwen2.5:14b",
       "api_key":"sk-local-123","context_window":32768}' \
  http://127.0.0.1:8765/api/model-configs
```

**首个模型模板**：`ensure_default_model()` 在 `Runtime.start()` 中运行，
当 `model_configs` 为空时自动插入一条 `name="本地 / OpenAI 兼容"`、
`provider=openai_compatible`、`base_url=http://127.0.0.1:11434/v1`、
`model_name=qwen2.5:14b` 的模板（无密钥，`is_active=true`、`is_default=false`）。
所以全新安装的 `GET /api/model-configs` 至少返回 1 条。

#### 3.12.2 `GET /api/model-configs` — 200

裸数组，排序 `is_default DESC, name ASC`。

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/api/model-configs
```

#### 3.12.3 `GET /api/model-configs/{model_id}` — 200

单个 `ModelConfigOut`；不存在 → 404 `not_found`。

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/api/model-configs/mdl_d1595ebffc2e
```

#### 3.12.4 `PUT /api/model-configs/{model_id}` — 200

**请求体**（`ModelConfigUpdate`）：3.12.1 的全部可写字段均可选，另加：

| 字段 | 类型 | 说明 |
|---|---|---|
| `api_key` | string \| null | **省略或 `null` = 密钥不变**；`""` = **清除**密钥；其他值 = 覆盖 |
| `row_version` | int \| null | 乐观锁；不匹配 → 409 |

其余字段的 `null` 语义（`model_config_service.update`）：只有 `_NULLABLE` 中的
`base_url`、`capabilities`、`notes`、`fallback_ids` 会被真的赋值为 `null`，
**其他字段传 `null` 视为「不修改」**（`continue`）。

⚠️ 但这四个「可空」字段在数据库里其实是 `NOT NULL`，所以传 `null` 会在 flush 时
抛 `IntegrityError` / `ValidationError` → **500**（实测，见 §8 缺陷 13）。
**当前没有任何字段可以用 `null` 清空**：要清空请用 `""`（`base_url`/`notes`）、
`{}`（`capabilities`）、`[]`（`fallback_ids`）。

成功时 `row_version` **+1**，`updated_at` 刷新。

```bash
# 轮换密钥
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"api_key":"sk-rotated-9876543210","row_version":1}' \
  http://127.0.0.1:8765/api/model-configs/mdl_d1595ebffc2e

# 清除密钥（has_api_key 变 false）
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"api_key":"","row_version":2}' \
  http://127.0.0.1:8765/api/model-configs/mdl_d1595ebffc2e
```

**409**（过期 `row_version`）：

```json
{"error":{"code":"conflict",
 "message":"Model configuration was modified elsewhere; reload and retry.",
 "details":{"expected":99,"actual":2}}}
```

#### 3.12.5 `DELETE /api/model-configs/{model_id}` — 204

删行并删除 `secrets.json` 中对应标签的密钥；引用它的 `projects.default_model_config_id`、
`agent_configs.model_config_id`、`generation_tasks.model_config_id` 走 `SET NULL`。
空响应体。

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/api/model-configs/mdl_d1595ebffc2e   # 204
```

#### 3.12.6 `POST /api/model-configs/{model_id}/default` — 200

把该模型设为唯一默认（其余全部 `is_default=false`），返回更新后的 `ModelConfigOut`。
无请求体。

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/api/model-configs/mdl_d1595ebffc2e/default
```

⚠️ `is_default` 只影响列表排序与「默认」标记；**当前没有代码读取它来决定调用哪个模型**
（LLM 适配器未实现）。

### 3.13 卷 `/api/projects/{project_id}/volumes`

#### 3.13.1 `GET /volumes` — 200

裸数组，按 `sort_order ASC, created_at ASC`。元素为 `VolumeOut`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `vol_<12 hex>` |
| `project_id` | string | 所属项目 |
| `title` | string | 卷标题 |
| `summary` | string | 卷简介 |
| `sort_order` | int | 排序 |
| `word_count` | int | **恒为 0**（服务层从不维护卷字数，见 §8 缺陷 9） |
| `status` | string | 恒为 `draft`（无接口可改） |
| `created_at` / `updated_at` | string | 时间戳 |

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/volumes
```

#### 3.13.2 `POST /volumes` — 201

**请求体**（`VolumeCreate`）

| 字段 | 类型 | 必填 | 默认 | 约束 |
|---|---|---|---|---|
| `title` | string | ✅ | — | 1–200（服务层再 `strip()`） |
| `summary` | string | | `""` | ≤20000 |

`sort_order` 由服务层置为 `MAX(sort_order) + 1`。

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"第一卷 开端","summary":"主角离开故乡"}' \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/volumes
```

```json
{"id":"vol_e97b8555fe10","project_id":"proj_42da528da1db","title":"第一卷 开端",
 "summary":"主角离开故乡","sort_order":1,"word_count":0,"status":"draft",
 "created_at":"2026-11-16T06:58:51","updated_at":"2026-11-16T06:58:51"}
```

#### 3.13.3 `PATCH /volumes/{volume_id}` — 200

**请求体**（`VolumeUpdate`，全部可选）

| 字段 | 类型 | 约束 |
|---|---|---|
| `title` | string \| null | 1–200 |
| `summary` | string \| null | ≤20000 |
| `sort_order` | int \| null | `≥ 0` |
| `row_version` | int \| null | 乐观锁 |

`title` / `summary` / `sort_order` 传 `null` 表示不修改（无法用本接口清空 `title`；
`summary` 传 `""` 可清空）。`row_version` 不匹配 → 409，`details` 为 `null`。

```bash
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"第一卷 缘起","row_version":1}' \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/volumes/vol_e97b8555fe10
```

#### 3.13.4 `DELETE /volumes/{volume_id}` — 204

删卷，**其下章节不删**：服务层先把 `chapters.volume_id` 置 `NULL`
（`volume_id` 为 `SET NULL` 外键，但服务层仍显式 UPDATE 一次以刷新 `updated_at`），
再删卷行。实测：删卷后 `GET /chapters` 仍返回该章，且 `volume_id` 为 `null`。

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/volumes/vol_e97b8555fe10  # 204
```

卷或章节不存在（或章节属于别的项目）→ 404 `not_found`。

### 3.14 章节 `/api/projects/{project_id}/chapters`

#### 3.14.1 `GET /chapters` — 200

**查询参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `volume_id` | string \| null | `null` | 只看某一卷；不传则返回全书 |
| `include_deleted` | bool | `false` | 是否包含软删章节 |

按 `sort_order ASC, created_at ASC` 排序，返回 `ChapterListItem` **裸数组**——
**不含 `content`**（列表必须廉价，见 §4.1）。

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8765/api/projects/proj_42da528da1db/chapters?volume_id=vol_e97b8555fe10"
```

#### 3.14.2 `POST /chapters` — 201

**请求体**（`ChapterCreate`）

| 字段 | 类型 | 必填 | 默认 | 约束 |
|---|---|---|---|---|
| `title` | string | ✅ | — | 1–200（服务层再 `strip()`） |
| `volume_id` | string \| null | | `null` | **必须指向本项目存在的卷**，否则 500（见 §8 缺陷 7） |
| `content` | string | | `""` | ≤5_000_000 |
| `status` | string | | `draft` | `draft`/`writing`/`review`/`done`/`archived` |

服务层置 `sort_order = MAX(sort_order) + 1`，用 `count_words(content)` 算 `word_count`；
`content` 非空时立即写一条 `source="user"`、`note="创建章节"` 的版本，
`content` 为空时**不写版本**。

响应 **201** 为完整 `ChapterOut`（含 `content`）：

```json
{"id":"chap_07a0b2f5b0d1","project_id":"proj_42da528da1db",
 "volume_id":"vol_e97b8555fe10","title":"第一章 启程","sort_order":1,
 "word_count":4,"status":"draft","summary":"",
 "updated_at":"2026-11-16T06:58:51.705535Z","content":"天地玄黄。",
 "row_version":1,"created_at":"2026-11-16T06:58:51Z"}
```

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"第一章 启程","volume_id":"vol_e97b8555fe10","content":"天地玄黄。"}' \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/chapters
```

#### 3.14.3 `POST /chapters/reorder` — 200

**请求体**（`ChapterReorder`）：`{"chapter_ids": ["chap_a", "chap_b", ...]}`
（`0 ≤ 长度 ≤ 10000`）。按数组下标重写这些章节的 `sort_order`（从 0 开始），
并返回重排后的完整 `ChapterListItem` 数组。

校验（任一不满足 → **422 `validation_failed`**）：

- 存在不属于本项目（或已软删）的 id → `details.unknown` 列出这些 id
- 数组内有重复 id → `details` 为 `null`
- 空数组是合法的，等于「什么都不做」，返回 200

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"chapter_ids":["chap_b","chap_a"]}' \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/chapters/reorder
```

**422 示例**：

```json
{"error":{"code":"validation_failed","message":"Unknown chapter ids in reorder payload",
 "details":{"unknown":["chap_nope000000"]}}}
```

⚠️ 只传部分章节时，未列出的章节保持原 `sort_order`，可能与新序号冲突（当前不做归一化）。

#### 3.14.4 `GET /chapters/{chapter_id}` — 200

完整 `ChapterOut`（含 `content`、`row_version`、`created_at`）。
章节不存在、**已软删**、或属于别的项目 → 404 `not_found`。

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/chapters/chap_07a0b2f5b0d1
```

#### 3.14.5 `PUT /chapters/{chapter_id}` — 200

自动保存与手动保存共用同一接口。

**请求体**（`ChapterUpdate`，全部可选）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `title` | string \| null | 1–200 | `null` = 不修改 |
| `volume_id` | string \| null | — | `null` = **不修改**（无法把章节移出卷，只能挂到另一个卷） |
| `content` | string \| null | ≤5_000_000 | `null` = 不修改；`""` = 清空正文 |
| `status` | string \| null | 枚举同上 | `null` = 不修改；非法值 422 |
| `sort_order` | int \| null | `≥ 0` | `null` = 不修改 |
| `snapshot` | bool | `false` | 强制写一条历史版本（见 §4.3） |
| `row_version` | int \| null | `≥ 1` | 乐观锁 |

`content` 与库中不同时，服务层重算 `word_count` 并把 `indexed_hash` 置 `NULL`
（标记记忆索引过期）。`row_version` 不匹配 → **409**，`details` 含 `expected`/`actual`：

```json
{"error":{"code":"conflict",
 "message":"Chapter changed elsewhere; reload before saving.",
 "details":{"expected":1,"actual":2}}}
```

成功时 `row_version` **+1**，`updated_at` 刷新，返回完整 `ChapterOut`。

```bash
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"content":"天地玄黄，宇宙洪荒。","row_version":1}' \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/chapters/chap_07a0b2f5b0d1
```

#### 3.14.6 `DELETE /chapters/{chapter_id}` — 204

**软删除**：置 `is_deleted=1`、`deleted_at=now`、`row_version+1`，正文与版本**留在库里**。
删除后 `GET /chapters/{id}` 返回 404，列表默认不含；`?include_deleted=true` 仍可见。

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/chapters/chap_07a0b2f5b0d1  # 204
```

### 3.15 章节版本 `/api/projects/{project_id}/chapters/{chapter_id}/versions`

#### 3.15.1 `GET /versions` — 200

裸数组，**按 `version_no DESC`（最新在前）**。元素为 `ChapterVersionOut`：
`id`、`chapter_id`、`version_no`、`title`、`word_count`、`source`、`note`、`created_at`。
**没有 `content` 字段**——正文只能通过 3.15.3 恢复到章节后再读。

`source` 取值：`user`（写作/手动快照）、`ai`（接受 AI 结果，当前无写入方）、
`import`（导入，当前无写入方）、`restore`（恢复前存档）。

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/chapters/chap_07a0b2f5b0d1/versions
```

```json
[{"id":"ver_05b73e8d87e6","chapter_id":"chap_07a0b2f5b0d1","version_no":1,
  "title":"第一章 启程","word_count":4,"source":"user","note":"创建章节",
  "created_at":"2026-11-16T06:58:51.707622Z"}]
```

#### 3.15.2 `POST /versions` — 201

无条件为当前正文写一条快照（`source="user"`、`note="手动快照"`），
返回**更新后的完整版本列表**（不是单条）。

空章节也允许快照（正文为空串），实测返回 201 且列表长度为 1。

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/chapters/chap_07a0b2f5b0d1/versions
```

#### 3.15.3 `POST /versions/{version_id}/restore` — 200

先把**当前正文**存成一条 `source="restore"`、
`note="恢复前快照（来自 v<目标版本号>）"` 的版本，再把目标版本的
`title`（为空则保留原标题）与 `content` 写回章节，重算 `word_count`、
置 `indexed_hash=NULL`、`row_version+1`。返回恢复后的完整 `ChapterOut`。

`version_id` 不属于该章节（或不存在）→ 404 `not_found`。

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8765/api/projects/proj_42da528da1db/chapters/chap_07a0b2f5b0d1/versions/ver_05b73e8d87e6/restore
```

## 3.16 AI 与采纳端点

全部需要令牌，失败走 §1.2 错误信封。`operation` 取值见 `GET /api/ai/operations`。
`/summary/{id}`、`/outline/{id}`、`/prompts/{key}` 均**注册在 `/{operation}` 之前**——
后者是单段通配，注册顺序错了会被它吃掉。

### 3.16.1 `GET /api/ai/operations`

返回 `{"operations": ["continue", "expand", "outline", "polish", ...]}`。

### 3.16.2 `GET /api/ai/prompts`

`PromptSummary[]`：`key` / `name` / `version` / `description` / `variables` / `is_active`。

### 3.16.3 `PATCH /api/ai/prompts/{key}`

body：`{"content": "...", "name?": "...", "variables?": [...]}`。
`content` 用 `### system` / `### user` 分段；纯文本按 user prompt 处理。
**不覆盖旧行**：取该 key 当前最大 version，写入 version+1，历史版本保留，
以便旧生成任务记录的 `prompt_version` 仍能定位到当时的正文。未知 key → 404。
返回新的 `PromptSummary`。

### 3.16.4 `POST /api/ai/summary/{chapter_id}`

body：`{"project_id": "...", "force": false}`；
返回 `{"chapter_id", "summary", "cached", "skipped"}`。

- 显式付费调用，**不进自动保存路径**（1200 ms 防抖会让每次停笔都烧 token）。
- 空正文 → `skipped="empty"`，不写库。
- 已有非空摘要且 `force=false` → `cached=true`，不调模型。
- 模型返回非 JSON → 降级为「整段文本当摘要」，其余结构化字段留空。

### 3.16.5 `POST /api/ai/outline/{chapter_id}`

body：`{"project_id": "...", "force": false, "instruction": "..."}`；返回 `OutlineResult`：
`chapter_id` / `outline_id` / `level` / `parent_id` / `title` / `goal` / `conflict` /
`characters` / `key_events` / `twists` / `foreshadows` / `ending` /
`target_word_count` / `content` / `degraded` / `cached` / `row_version`。

- 落库约定：`level="chapter"`、`parent_id=chapter_id`，按 `(project_id, level, parent_id)` upsert。
- 模型返回非 JSON → `degraded=true`，原文进 `content`，其余字段为空。
- 未知 chapter → 404。

### 3.16.6 `POST /api/ai/{operation}`

非流式执行写作操作，返回 `AIResult`：
`task_id` / `operation` / `text` / `model` / `prompt_key` /
`input_tokens` / `output_tokens` / `cost`。

### 3.16.7 `POST /api/ai/{operation}/stream`

SSE 流，事件 `delta` / `done` / `error`。前端 `desktop/src/lib/ai.ts` 用 `fetch` 自行解析帧
（`EventSource` 不能发 POST），支持 `AbortSignal` 中止与断帧容错。

### 3.16.8 `GET /api/ai/tasks`

最近 `generation_tasks`，可按 `project_id` 过滤；含 token、成本、错误。

### 3.16.9 `POST /api/projects/{project_id}/chapters/{chapter_id}/accept-ai`

body `ChapterAcceptAi`：`content`（必填，1–5,000,000 字）/ `title?` / `task_id?` / `note?`。
前端发送的是**合并后的完整正文**，服务端不猜片段如何应用。
返回 `{"chapter": ChapterOut, "version": ChapterVersionOut}`。

语义顺序固定：

1. 把采纳前正文存为 `source="user"` 快照（保住可回滚的原文）；
2. 更新章节正文（`title` 传了才覆盖）；
3. 写一条 `source="ai"` 且带 `task_id` 的版本。

空 `content` → 422；未知章节 → 404。前端入口 `api.chapters.acceptAi`，在
`novel-editor-page.tsx` 的 `handleApply` 中调用。

## 4. 字段与语义补充

### 4.1 章节字段

`ChapterOut`（`schemas/novel.py::ChapterOut`，继承 `ChapterListItem`）：

| 字段 | 类型 | 出现在 |
|---|---|---|
| `id` | string | 两者 |
| `project_id` | string | 两者 |
| `volume_id` | string \| null | 两者 |
| `title` | string | 两者 |
| `sort_order` | int | 两者 |
| `word_count` | int | 两者 |
| `status` | string | 两者 |
| `summary` | string | 两者 |
| `updated_at` | string | 两者 |
| `content` | string | **仅 `ChapterOut`** |
| `row_version` | int | **仅 `ChapterOut`** |
| `created_at` | string | **仅 `ChapterOut`** |

即：`ChapterListItem` = `Chapter` 去掉 `content`、`row_version`、`created_at`。
列表接口（3.14.1、3.14.3）永远不返回正文。

`status` 枚举：`draft` · `writing` · `review` · `done` · `archived`
（`schemas/novel.py::CHAPTER_STATUSES`）。请求里给其他值 → 422。

`volume_id` 与 `Chapter.volume_id` 外键一致：卷被删除时数据库 `SET NULL`，
服务层再显式置空一次。

### 4.2 字数统计 `count_words`

实现：`backend/app/utils/text.py::count_words`。

- 每个 CJK 字符算 **1** 个字（正则 `[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]`，
  覆盖 CJK 扩展 A、基本区、兼容区、日文假名）；
- 每段连续的拉丁字母/数字算 **1** 个字（`[A-Za-z0-9]+`，先剔除 CJK 再匹配）；
- 标点与空白**一律不计**。

实测：

| 输入 | `word_count` |
|---|---|
| `天地玄黄` | 4 |
| `hello world` | 2 |
| `abc, def!` | 2 |
| `第 3 章 Chapter` | 4 |
| `天地玄黄。` | 4 |
| `……` | 0 |
| `""` | 0 |

前端 `desktop/src/lib/utils.ts::countWords` 是同一算法的镜像（同样的 CJK 与拉丁正则），
保证编辑器右下角实时字数与落库的 `word_count` 一致。

写入时机：新建章节（3.14.2）、保存章节且正文变化（3.14.5）、恢复版本（3.15.3）。

### 4.3 版本策略

实现在 `services/novel_service.py`，三个常量决定一切：

| 常量 | 值 | 含义 |
|---|---|---|
| `SNAPSHOT_INTERVAL_SECONDS` | `300` | 自动快照的最小间隔（秒） |
| `MAX_VERSIONS_PER_CHAPTER` | `60` | 每章最多保留的版本数 |

规则：

1. **显式保存永远留痕**：`PUT` 带 `snapshot: true` 时一定写一条版本，
   即使 300 秒内已经写过（`force=True` 绕过间隔检查）。
   若正文与最新版本完全相同，则按「手动快照」语义仍写一条（`note="手动快照"`）。
2. **自动保存限流**：不带 `snapshot` 的 `PUT` 只在「正文变化」且
   「距最新版本 ≥ 300 秒」时写一条（`note="自动保存"`）；
   正文没变化则一条都不写。
3. **裁剪**：每次写完版本后，删除该章 `version_no` 排名 60 之后的所有版本。
4. **创建即有基线**：`POST /chapters` 在 `content` 非空时写 v1
   （`note="创建章节"`）；正文为空则一章版本都没有。
5. **恢复先存档**：`restore` 先把被替换掉的当前正文存成一条 `source="restore"` 的版本，
   再写回目标版本。所以恢复永远不会丢内容。

实测（同一章）：创建 1 条 → 300 秒内连续两次自动保存仍是 1 条 →
带 `snapshot: true` 变 2 条 → 恢复 v1 后变 3 条，且被替换的长文本可在列表首位看到
（`word_count` 更大）。

前端对应行为（`components/editor/chapter-editor.tsx`）：停止输入 1200 ms 后自动保存，
`Ctrl/Cmd+S` 立即保存，切章/关窗前 flush；保存时携带当前 `row_version`，
收到 `conflict` 会提示并重新拉取最新内容。「存为版本」按钮直接调 3.15.2。

## 5. 未实现（计划中，调用一律 404）

以下来自开发计划 §13.4–§13.8。**当前代码中不存在这些路由**，调用得到 404 `not_found`。
列出仅为排期与联调依据，**不承诺任何字段**。

> §13.3 的 AI 写作已实现，`ai` router 已挂载（8 个端点见 §2 与 §3.16）。
> 但**原计划的 7 条顶层路径不等于实现**：实际只有一条通配 `POST /api/ai/{operation}`，
> 操作名从 `GET /api/ai/operations` 取；`outline` 的落库走 `POST /api/ai/outline/{chapter_id}`。

| 计划 | 模块 | 路径 | 状态 |
|---|---|---|---|
| §13.4 | 检索 / 记忆 | `POST /api/retrieval/search` · `POST /api/retrieval/hybrid` · `POST /api/retrieval/semantic` · `POST /api/retrieval/keyword` · `GET /api/retrieval/logs` · `GET /api/retrieval/context/{id}` · `POST /api/memory/update` · `POST /api/memory/rebuild` · `GET /api/memory/status` | ❌ 未实现 |
| §13.6 | 故事板 | `POST /api/storyboards/parse` · `POST /api/storyboards/scenes` · `POST /api/storyboards/shots` · `GET /api/storyboards/{id}` · `PUT /api/storyboards/{id}` · `POST /api/storyboards/shots/{id}/generate` · `POST /api/storyboards/shots/{id}/regenerate` | ❌ 未实现 |
| §13.7 | 工作流 | `POST /api/workflows` · `GET /api/workflows` · `GET /api/workflows/{id}` · `PUT /api/workflows/{id}` · `POST /api/workflows/{id}/run` · `POST /api/workflows/runs/{id}/pause` · `POST /api/workflows/runs/{id}/resume` · `POST /api/workflows/runs/{id}/cancel` · `GET /api/workflows/runs/{id}` · `GET /api/workflows/runs/{id}/logs` | ❌ 未实现 |
| §13.8 | 媒体 | `POST /api/media/image/generate` · `POST /api/media/video/generate` · `POST /api/media/audio/generate` · `POST /api/media/subtitle/generate` · `POST /api/media/render` · `GET /api/media/tasks/{id}` · `GET /api/media/assets` | ❌ 未实现 |

同样未实现、但不属于上表五节的还有：

| 计划 | 模块 | 路径 | 状态 |
|---|---|---|---|
| §13.2 | 项目内小说/章节（旧路径） | `POST /api/novels` · `GET /api/chapters/{id}` 等顶层路径 | ⚠️ 已由 3.13–3.15 的 `/api/projects/{project_id}/...` 取代，顶层路径不存在 |
| §13.5 | 人物 | `POST /api/characters` · `GET /api/characters` · `GET/PUT /api/characters/{id}` · `GET /api/characters/{id}/states` · `GET /api/characters/{id}/relationships` | ❌ 未实现（表 `characters` 等已建） |
| §13.9 | WebSocket | `/ws/tasks` · `/ws/workflows` · `/ws/generation` · `/ws/render` | ❌ 无任何 WebSocket 路由 |

`require_token` 的 `X-Studio-Token` 回退已为 WebSocket 预留，但路由本身不存在。
`generation_tasks` / `task_logs` 表已建且无 worker 消费（见 [workflow.md](workflow.md)）。

## 6. 桌面壳 IPC（非 HTTP）

前端经 Tauri IPC 调用 Rust 命令（`desktop/src-tauri/src/commands/system.rs`）：

| 命令 | 返回 | 说明 |
|---|---|---|
| `get_sidecar_info` | `SidecarInfo` | 端口、令牌、pid、状态 |
| `sidecar_logs` | `string[]` | 后端日志尾部（环形缓冲，上限 500 行） |
| `restart_sidecar` | `SidecarInfo` | 重启后端并广播就绪事件 |
| `open_data_dir` | `null` | 文件管理器中显示数据目录 |
| `app_info` | `AppInfo` | 版本、Tauri 版本、数据目录、Python 路径、OS/架构 |

`SidecarInfo` 序列化为 camelCase：`baseUrl`、`token`、`port`、`pid`、`startedAt`、`status`
（`starting`/`ready`/`stopping`/`stopped`）。前端在非 Tauri 环境（`vite` 开发服务器）下降级
读取 `VITE_API_BASE_URL` / `VITE_API_TOKEN`，由 Vite 把 `/api` 代理到 `http://127.0.0.1:8765`。

前端调用封装在 `desktop/src/lib/api.ts`：所有请求经 `request()` 附带
`Authorization: Bearer`，把 `{"error":{...}}` 信封还原为 `ApiError`
（带 `code` / `status` / `details`，并提供 `isAuthError` / `isNotFound` / `isConflict`）。
端点分组：`api.health`、`api.systemInfo`、`api.studioStats`、`api.projects.*`、
`api.volumes.*`、`api.chapters.*`、`api.modelConfigs.*`。

## 7. 验证方式

响应体均来自实际运行：Python 3.13.5 + `requirements.txt` 锁定依赖、全新
`NOVEL_STUDIO_DATA_DIR`、固定令牌、用 `httpx` / `urllib` 逐端点断言。

| 断言 | 结果 |
|---|---|
| 无令牌 / 错误令牌 → 401 `auth_required` | ✅ |
| `/healthz` 免鉴权 → 200 | ✅ |
| `/api/openapi.json`、`/api/docs` 免鉴权 → 200 | ✅ |
| `POST /api/projects` 中文名 → 201，`name` 正确往返（UTF-8） | ✅ |
| `GET /api/projects/{id}` / `/{id}/stats` → 200，含 9 字段 `stats` | ✅ |
| `PUT` 正确 `row_version` → 200，1→2 | ✅ |
| `PUT` 过期 `row_version` → 409，含 `expected`/`actual` | ✅ |
| `PUT` 传 `"name": null` → 422 | ✅ |
| `DELETE` 软删 / `?hard=true` → 204；随后 GET 404；硬删移除目录 | ✅ |
| 列表排除已删 / `include_deleted=true` | ✅ |
| `POST /duplicate` → 201，目录内容一致 | ✅ |
| 未知项目 / 卷 / 章节 / 版本 / 模型配置 / 路由 → 404 `not_found` | ✅ |
| 空名 / `limit=999` → 422 `validation_failed`（含明细） | ✅ |
| `PATCH /api/projects` → 405 `http_error` | ✅ |
| 未捕获异常 → 500 `internal_error` | ✅（中间件隔离测试） |
| `POST /model-configs` 带 `api_key` → 201，`has_api_key=true`，响应体不含密钥明文 | ✅ |
| `secrets.json` 存在且不含密钥明文 | ✅ |
| `PUT /model-configs` `api_key: ""` → `has_api_key=false` | ✅ |
| `PUT /model-configs` 过期 `row_version` → 409 | ✅ |
| `POST /model-configs/{id}/default` → 200，且只有一个 `is_default` | ✅ |
| 未知 `provider` / `temperature=5` → 422 | ✅ |
| 卷 CRUD；`PATCH` 带过期 `row_version` → 409 | ✅ |
| 删卷 → 204，其下章节仍在且 `volume_id=null` | ✅ |
| 章节 CRUD；`word_count` 与 `count_words` 一致 | ✅ |
| 保存带过期 `row_version` → 409，含 `expected`/`actual` | ✅ |
| `reorder` 未知 id → 422（`details.unknown`）；重复 id → 422 | ✅ |
| 版本列表最新在前、无 `content` 字段 | ✅ |
| `POST /versions` → 201，返回完整列表 | ✅ |
| 300 秒内连续自动保存只留一条版本 | ✅ |
| `snapshot: true` 强制留痕 | ✅ |
| `restore` 先存档再写回，版本数 +1 | ✅ |
| 软删章节后 `GET` → 404，`include_deleted=true` 可见 | ✅ |

一键复现：`backend/.venv/Scripts/python.exe scripts/smoke_api.py`
（自带临时数据目录与随机端口，输出 `SMOKE PASSED: all checks green`）。

## 8. 已知缺陷

实测发现，已报告后端负责人。**按现状记录，不粉饰**。

| # | 缺陷 | 位置 | 后果 |
|---|---|---|---|
| 1 | `POST /chapters` 传不存在的 `volume_id` → 500 | 已修复 | 现在返回 422 `validation_failed`（`novel_service._require_volume`） |
| 2 | `PUT /chapters/{id}` 无法把章节移出卷 | 已修复 | 改用 `model_fields_set` 区分「未提供」与「显式 null」，`volume_id: null` 可解绑 |
| 3 | `PUT /chapters/{id}` 的 `volume_id` 改动不校验卷归属 | 已修复 | 同第 15 条 |
| 4 | `POST /chapters/reorder` 传部分 id 时不归一化 `sort_order` | 已修复 | 未列出的章节按原相对顺序接在后面，序号保持 0..n-1 密集 |
| 5 | `volumes.word_count` 恒为 0，`volumes.status` 恒为 `draft` | `novel_service`（从不维护） | 卷卡片显示 0 字；无接口可改卷状态 |
| 6 | 删章不清理 `knowledge_chunks` / `embeddings` | `models/novel.py`（对 `chapter_id` 无 FK） | 孤儿数据，检索可能命中已删内容（检索本身未实现） |
| 7 | 章节 `summary` / `pov_character_id` 无写入路径 | `Chapter` 列存在，`ChapterUpdate` 无这两个字段 | 字段就绪但永远为空 |
| 8 | `characters(project_id, name)` 唯一约束 | 已修复 | 现为部分唯一索引 `... WHERE is_deleted = 0`，软删不再占位（见 [database.md](database.md) §5.1） |
| 9 | `app_meta`/`project_meta` 的 `updated_at` | 已修复 | 改为继承 `TimestampMixin`，不再有「重声明无默认值」问题 |
| 10 | `project.json` 无反向导入 | `core/paths.py` | `read_manifest`/`is_project_dir` 无调用方，拷走的项目目录无法导回注册表 |
| 11 | `collect_stats` 多返回 `words_total` | `db/project_db.py` | 被 `ProjectStats` 丢弃，无实际影响 |
| 12 | `stats.chapters` / `stats.words` 统计含软删章节 | `db/project_db.py::collect_stats` | 删章后计数不减 |
| 13 | `PUT /model-configs/{id}` 传 `null` 给 `base_url`/`notes`/`capabilities`/`fallback_ids` → 500 | 已修复 | `model_config_service._NULL_DEFAULTS` 把 `null` 映射成 `""` / `{}` / `[]`；未传字段保持原值 |
| 14 | `GET /chapters?include_deleted=true` 返回的软删章节无法与正常章节区分 | 已修复 | `ChapterListItem` 增加 `is_deleted` / `deleted_at` |
| 15 | `POST/PUT /chapters` 传别的项目的 `volume_id` → 500 | 已修复 | 归属校验失败返回 422 `validation_failed` |
| 16 | 时间戳格式三种混用（无后缀 / `Z` / `+00:00`） | `TimestampMixin` + 服务层 `_now()` | 数据库默认值给无后缀，服务层显式赋值给带时区；客户端必须同时容忍。根治办法是统一在 ORM 层用 Python 侧 `default`/`onupdate` |

### 8.1 已修复的缺陷（保留记录）

文档编写期间修复并已重新实测确认通过：

- `app_meta`/`project_meta`/`ProjectBackup` 的 `updated_at`（`created_at`）重声明导致 NOT NULL 失败
  → 应用无法启动。**已修复**（删除冗余声明，改继承 `TimestampMixin`）
- `ProjectService.create` 中 `setattr(values, ...)` 作用于 `dict` → 创建项目 500。**已修复**
- 未捕获异常返回空 body 而非 JSON 信封。**已修复**（新增 `ErrorEnvelopeMiddleware`）
- `HTTP_422_UNPROCESSABLE_ENTITY` 常量弃用告警。**已修复**（改用数值 `422`）
- `POST /api/projects/{id}/duplicate` 500（`Database` 未 `dispose()`）。
  **已修复**：`create()` 显式 `dispose()`，复制前 `checkpoint()`。
- `PUT /api/projects/{id}` 传 `"name": null` 返回 500。**已修复**：`ProjectUpdate` 增加校验器 → 422。
- `/api/docs`、`/api/openapi.json` 需鉴权。**已修复**：`TokenMiddleware.OPEN_PATHS` 白名单。
- `characters` 唯一约束含软删行。**已修复**：改为部分唯一索引
  `uq_characters_project_name_active (project_id, name) WHERE is_deleted = 0`。
- `create_project_database` 无条件覆盖 `schema_version`。**已修复**：
  新增 `app/db/migrations.py` 迁移执行器（拒绝降级 + 迁移前在线备份 + 单事务 + 逐步打戳），
  `create_project_database()` 不再自己写版本号。
- `POST/PUT /chapters` 的 `volume_id` 校验与解绑。**已修复**：
  新增 `novel_service._require_volume`（跨项目/不存在 → 422）；
  `update_chapter` 改用 `model_fields_set` 区分「未提供」与「显式 null」，`volume_id: null` 可解绑。
- `POST /chapters/reorder` 序号归一化。**已修复**：未列出的章节按原相对顺序接在后面，
  `sort_order` 保持 0..n-1 密集。
- `PUT /model-configs` 传 `null` 到 NOT NULL 列。**已修复**：`_NULL_DEFAULTS` 把 `null`
  映射为 `""` / `{}` / `[]`，未传字段保持原值。
- `include_deleted` 无法区分软删行。**已修复**：`ChapterListItem` 增加 `is_deleted` / `deleted_at`。