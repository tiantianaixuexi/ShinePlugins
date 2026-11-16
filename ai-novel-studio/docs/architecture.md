# 架构说明

本文描述 AI Novel Studio 的进程模型、职责划分、sidecar 协议与 SQLite 存储策略。
所有结论均以仓库内真实代码为准；尚未落地的部分会显式标注「未实现」。

- 代码基准：`backend/app/**`（`0.1.0`）
- 对应实现：`app/main.py`、`app/runtime.py`、`app/db/session.py`、`app/db/project_db.py`、
  `app/db/migrations.py`、`app/services/{project,novel,model_config}_service.py`
- 相关文档：[api.md](api.md)（接口契约）· [database.md](database.md)（表结构）·
  [rag.md](rag.md) · [workflow.md](workflow.md)（两份设计文档，均未实现）

## 1. 总体形态

```
┌──────────────────────────────────────────────────────────────┐
│                        Tauri 2 桌面壳                         │
│  ┌────────────────────────┐      ┌────────────────────────┐  │
│  │  WebView (React 19 UI) │      │  Rust 侧 (src-tauri)   │  │
│  │  desktop/ 构建产物      │      │  生命周期/窗口/菜单      │  │
│  └───────────┬────────────┘      └───────────┬────────────┘  │
│              │ HTTP (loopback)              │ spawn / kill   │
└──────────────┼──────────────────────────────┼────────────────┘
               │  Bearer token                │  python -m app
               ▼                              ▼
┌──────────────────────────────────────────────────────────────┐
│                Python sidecar (FastAPI + uvicorn)             │
│  127.0.0.1:<动态端口>  /api/*                                 │
│  app/main.py · app/runtime.py · app/services/*                │
└──────────────┬───────────────────────────────┬───────────────┘
               │                               │
      ┌────────▼─────────┐          ┌──────────▼───────────┐
      │ studio.db        │          │ NovelProjects/<项目>/ │
      │ 全局注册表        │          │   database/novel.db  │
      │ (模型/提示词/项目) │          │   项目正文与知识库      │
      └──────────────────┘          └──────────────────────┘
```

三条硬边界：

1. **Rust 不接触数据库。** Rust 只负责进程与窗口生命周期，所有数据读写经 HTTP 交给 Python。
   代码依据：`app/db/session.py` 模块注释明确「One process owns the writes…the Rust shell talks to it
   over HTTP and never opens `novel.db`」。
2. **前端不直连数据库**，也不持有令牌逻辑，只经 `/api` 调用后端。
3. **后端只监听环回地址**（默认 `127.0.0.1`，见 `app/core/config.py` 的 `Settings.host`）。

## 2. 为什么这样切分

| 关注点 | 归属 | 理由 |
|---|---|---|
| 窗口、菜单、托盘、文件选择、自动更新、进程守护 | Rust (Tauri 2) | 桌面系统集成是 Rust 侧强项；Tauri 2 的权限/能力模型需要原生的 `capabilities` 声明 |
| 长任务、RAG、结构化抽取、媒体编排、SQLite 事务 | Python (FastAPI) | 需要 SQLAlchemy、numpy、sqlite-vec、tiktoken、Pillow、PyMuPDF、python-docx 这类成熟库；Python 侧迭代速度更快 |
| 大文件与流式响应 | Python + ASGI | 中间件为纯 ASGI 实现（`TokenMiddleware`），不破坏 streaming 与 background task |
| 打包体积 | Rust 壳 + Python 运行时 | Python 依赖不编译进 Rust 二进制，但运行时需要随包分发（**打包方案未实现**） |

代价与对策：

- 多一个进程 → 端口与令牌握手、健康检查、优雅退出（见第 3 节）。
- 两个语言栈的依赖清单 → 各自独立锁定版本（`backend/pyproject.toml`、`requirements.txt`，前端 `package.json`）。

## 3. Sidecar 协议

协议的设计目标：桌面壳每次启动都能拿到一个干净的、别人猜不到的本地服务。

### 3.1 端口

- 后端**不自己找空闲端口**。`Settings.port` 默认 `8765`，但桌面壳在启动子进程时注入
  `NOVEL_STUDIO_PORT`，覆盖默认值。
- 壳侧实现（`desktop/src-tauri/src/sidecar.rs`）：
  1. `portpicker::pick_unused_port()` 让操作系统分配空闲端口；
  2. 若失败，回退到手动 `TcpListener::bind("127.0.0.1:0")` 读回端口号再释放；
  3. 把端口号写入子进程环境变量 `NOVEL_STUDIO_PORT`。
- 代码依据：`app/core/config.py` 的 `model_config = SettingsConfigDict(env_prefix="NOVEL_STUDIO_")`；
  `app/__main__.py` 用 `uvicorn.run(host=settings.host, port=settings.port, ...)` 读取该值。

### 3.2 一次性令牌

- 壳用 `uuid::Uuid::new_v4().simple()` 生成 32 位十六进制令牌（`spawn_process()`），
  经 `NOVEL_STUDIO_AUTH_TOKEN` 注入；后端侧另有 `app/core/security.py::generate_token`
  提供 `secrets.token_urlsafe(32)`，两者格式不同但都是一次性随机串。
- 前端通过 Tauri 命令 `get_sidecar_info` 取到令牌，在每个请求带
  `Authorization: Bearer <token>`（`desktop/src/lib/api.ts`）。
- 令牌校验有两条路径：
  - ASGI 层 `TokenMiddleware`（`app/main.py`）：在路由之前拦截所有 `/api` 前缀请求，
    缺失/错误即返回 `401` 与 `{"error":{"code":"auth_required",...}}`。这一步同时保护未匹配的 404 路径。
    `OPTIONS` 预检请求例外：它按设计不带凭据，必须放行给 `CORSMiddleware` 回应，否则桌面端从
    `http://127.0.0.1:1420` 跨端口访问动态端口时，带 `Authorization` 的真实请求永远发不出去。
  - 依赖层 `app/core/security.py::require_token`：保留的 FastAPI 依赖，接受
    `Authorization: Bearer` **或** `X-Studio-Token` 头。后者供 WebSocket 客户端与 curl 冒烟测试使用。
- 比较使用 `hmac.compare_digest`（常量时间），避免计时侧信道。
- `Settings.auth_token` 为 `None` 时鉴权关闭（`is_auth_enabled == False`）。这只适用于本地测试；
  此时 `/api` 全部裸奔。
- **令牌不落盘**：`NOVEL_STUDIO_*` 只读环境变量，配置文件 `.env` 仅作本地开发兜底。
  唯一的例外是诊断握手文件 `sidecar.json`（见 3.7），它包含令牌明文。

### 3.3 健康检查

- `GET /api/health`（`app/api/routes/health.py`）是壳轮询的唯一探针。壳以 250ms 间隔轮询，
  单次请求超时 3s，总超时 45s（`HEALTH_TIMEOUT`）。返回体：

  ```json
  {
    "status": "ok",
    "app": "AI Novel Studio",
    "version": "0.1.0",
    "schema_version": 1,
    "environment": "development",
    "time": "2026-11-16T06:10:00.000000+00:00"
  }
  ```

- 壳侧解析规则（`sidecar.rs::parse_health`）：
  - `status == "ok"` → 就绪，发 `sidecar://ready` 事件
  - `status == "starting"` → 继续轮询
  - HTTP 401 → 立即失败「backend rejected the generated access token」
  - 其他/无法解析 → 记录并继续轮询
- 另有一个**免鉴权**的 `GET /healthz`（`include_in_schema=False`），固定返回 `{"status":"ok"}`。
  它在 `/api` 之外，不经过 `TokenMiddleware`。
- 启动顺序（壳侧已实现）：
  1. 解析后端目录与 Python 解释器（见 3.8）→ 选端口 → 生成令牌 → spawn `python -m app`；
  2. 轮询 `GET /api/health` 直到 `status == "ok"` 或超时；
  3. 若子进程中途退出 → 返回错误并附带最近 40 行输出（`log_tail(40)`）；
  4. 若 45s 超时 → 强杀进程树并返回诊断信息。

### 3.4 优雅退出

壳侧有三层保障（`sidecar.rs`）：

1. **正常退出**：`SidecarState::stop()` 取出 handle 后 `drop`，waiter 任务的 `select!`
   落到 `terminate()`：等 5s（`STOP_TIMEOUT`），超时则 `start_kill()` 并 `wait()` 回收。
2. **窗口关闭钩子**：`stop_blocking()` 在同一线程上最多阻塞 5s 等进程消失，否则强杀。
3. **兜底强杀**：`force_kill()` 在 Windows 用 `taskkill /PID <pid> /T /F`（`/T` 连子进程一起），
   Unix 用 `kill -TERM`。

后端 lifespan（`app/main.py::create_app`）在 `finally` 中调用 `runtime.stop()`：

```python
def stop(self) -> None:
    self.projects.close_all()   # 关闭所有项目库的 engine
    self.studio_db.dispose()    # 关闭注册表 engine
```

即：先停掉所有数据库连接，再让进程退出。**没有** HTTP 关闭端点，壳不依赖它。

进程组隔离：Windows 用 `CREATE_NEW_PROCESS_GROUP`，Unix 用 `pre_exec(setpgid)`，
确保孙进程不会在壳退出后残留。

### 3.5 CORS

`Settings.cors_origins` 默认包含 `tauri://localhost`、`http(s)://tauri.localhost`、
`http://localhost:1420`、`http://127.0.0.1:1420`（Vite 开发服务器）。
`allow_credentials=False`，`allow_methods=["*"]`，`allow_headers=["*"]`。

### 3.6 静态前端托管（可选）

`create_app()` 会查找 `<repo>/desktop/dist`；若目录存在，则用 `StaticFiles(html=True)` 挂到 `/`。
这意味着后端可以单独托管打包好的前端（开发或排障用）。该目录在构建前端前不存在。

### 3.7 握手文件

壳在健康检查通过后写 `<data_dir>/sidecar.json`：

```json
{
  "baseUrl": "http://127.0.0.1:43117",
  "token": "…",
  "port": 43117,
  "pid": 12345,
  "startedAt": "2026-11-16T06:10:00Z"
}
```

用途：外部工具（脚本、调试器）在冷启动后可以读到端口与令牌。
`stop()` / `stop_blocking()` 会尽力删除该文件。

⚠️ 该文件**包含令牌明文**，其安全边界等同于用户主目录的写权限。

### 3.8 后端与解释器定位

壳按下列顺序查找（`sidecar.rs::resolve_backend_dir` / `resolve_python`），
可用环境变量覆盖：

| 目标 | 环境变量 | 回退顺序 |
|---|---|---|
| 后端目录 | `NOVEL_STUDIO_BACKEND_DIR` | `CARGO_MANIFEST_DIR/../../backend`、`../backend`、可执行文件旁的 `backend`、`../backend`；判定依据是存在 `app/__main__.py` |
| Python | `NOVEL_STUDIO_PYTHON` | Windows：`<exe>/python/python.exe`、`<exe>/backend/.venv/Scripts/python.exe`、`../python/python.exe`、`../backend/.venv/Scripts/python.exe`；Unix 同构；最后 `python3` / `python` |
| 数据目录 | `NOVEL_STUDIO_DATA_DIR` | `directories::BaseDirs.data_dir()/AI Novel Studio`，不存在则创建 |

子进程还会注入 `NOVEL_STUDIO_HOST=127.0.0.1`、`NOVEL_STUDIO_ENVIRONMENT=desktop`、
`NOVEL_STUDIO_LOG_JSON=1`、`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。

## 4. 存储：两层 SQLite

```
<数据根目录>/
├── studio.db                 # 全局注册表（唯一，进程级单例）
├── studio.db-wal / -shm      # WAL 副产物
├── logs/backend.log          # RotatingFileHandler 8MB × 5
├── cache/
└── NovelProjects/
    ├── <slug>-<shortid>/
    │   ├── project.json      # 便携清单（可读镜像）
    │   ├── project.lock      # 预留（当前代码未使用）
    │   ├── database/novel.db # 该项目全部正文与知识库
    │   ├── novel/{outlines,volumes,chapters,drafts,versions}
    │   ├── knowledge/{characters,events,locations,timelines,foreshadows,worldbuilding,summaries}
    │   ├── indexes/{vector,fulltext,metadata}
    │   ├── storyboards/{scripts,scenes,shots}
    │   ├── assets/{characters,locations,images,videos,audio,subtitles}
    │   ├── renders/
    │   └── logs/
    └── ...
```

数据根目录解析顺序：`NOVEL_STUDIO_DATA_DIR` → `platformdirs.user_data_dir("AI Novel Studio", appauthor=False, roaming=True)`。
Windows 上必须带 `roaming=True`，才能与 Rust 侧 `directories::BaseDirs.data_dir()`（即 `%APPDATA%`，Roaming）指向同一个库；
否则桌面端和独立 Python 工具会各用一套数据目录，UI 里保存的模型脚本读不到。
目录创建见 `Settings.ensure_directories()`（`data_dir`/`projects_root`/`logs_dir`/`cache_dir`）。
例外：`scripts/dev-backend.ps1` 默认把数据放进 `Local\AI Novel Studio\dev`，这是刻意隔离的浏览器开发 profile，不属于上述统一。

### 4.1 studio.db（注册表）

`app/runtime.py::Runtime` 在 `start()` 里先 `Base.metadata.create_all(studio_db.engine)`，
再调 `_migrate_studio()`（即 `studio_db.migrate("app_meta", backup_root=data_dir)`）
推进 `app_meta.schema_version`；最后 `ensure_default_model()` 在全新安装时插入一条
`本地 / OpenAI 兼容` 的模型配置模板。表清单见 [database.md](database.md) 第 1 节。
它是**跨项目**的：模型配置、提示词模板、Agent 绑定、项目注册、任务队列。

⚠️ 注意：`Base.metadata.create_all()` 建的是**全部 35 张表**（两个 models 模块共用一个
`Base`），所以 `studio.db` 里也会出现空的 `chapters` / `characters` 等表。
逻辑归属不变，但物理上两库表集合相同——详见 [database.md](database.md) 开头。

### 4.2 novel.db（每项目一个）

由 `app/db/project_db.py::create_project_database()` 建库：先 `create_all`，
再调 `Database.migrate("project_meta", backup_root=<项目>/backups)`。
**版本号只由迁移执行器写**（`app/db/migrations.py`），`create_project_database()`
自己不写——否则一个未迁移的老库会被误标为当前版本。
`ProjectDatabaseRegistry` 按 `project_id` 缓存 `Database` 实例，
同一个项目在整个会话内复用同一个 engine/连接池。

⚠️ `create_all()` 会在这个 `novel.db` 里也建出 `studio.db` 的 8 张表（空壳），
原因同上。读写的仍然只有项目那 27 张。

项目目录由 `ProjectService.create()` 创建，目录名规则：

```python
# app/core/ids.py
def project_dir_name(name, project_id):
    stem = slugify(name)                                  # NFKD → ASCII，非 ASCII 字符被丢弃
    return f"{stem}-{project_id.split('_')[-1]}" if stem else project_id
```

中文项目名会 slug 成空串，因此目录名退化为纯 `proj_xxxxxxxxxxxx`。
`slugify` 上限 48 字符，保证跨 Windows/macOS/Linux 可移植。

### 4.3 project.json 清单

`app/core/paths.py::write_manifest` 写入，`ProjectService._write_manifest` 每次 create/update 后调用。
内容：`id`、`name`、`slug`、`novel_type`、`synopsis`、`target_word_count`、`target_chapter_count`、
`writing_style`、`target_reader`、`language`、`author`、`status`、`schema_version`、`row_version`、
`settings`、`updated_at`（ISO8601）、`generator`（固定 `"ai-novel-studio"`）。
写失败只告警不抛错（只读卷不应阻断编辑）。

设计含义：`studio.db` 是权威源，`project.json` 是可移植镜像——拷走目录就能带走元数据。
但**当前代码没有从 `project.json` 重建注册表的导入路径**（未使用 `read_manifest`/`is_project_dir`）。

## 5. WAL 与单写者

每条新连接执行（`app/db/session.py::SQLITE_PRAGMAS`）：

```sql
PRAGMA journal_mode=WAL;      -- 读写不互相阻塞
PRAGMA synchronous=NORMAL;    -- 掉电可能丢最近事务，但不损坏库
PRAGMA foreign_keys=ON;       -- SQLite 默认关闭外键，必须显式开启
PRAGMA busy_timeout=5000;     -- 冲突时等 5s，而不是立刻 "database is locked"
PRAGMA temp_store=MEMORY;
```

connect_args 另有 `check_same_thread=False` 与 `timeout=5`（pysqlite 层）。
实测确认：`foreign_keys=1`、`journal_mode=wal`、`busy_timeout=5000`。

单写者规则的三层含义：

1. **进程内只有一个写入者**：FastAPI 进程。Rust 壳与 WebView 都不打开 SQLite 文件。
2. **项目级独占**：`ProjectDatabaseRegistry` 保证同一项目复用一个 engine；
   `ProjectLocked`（HTTP 423）为「项目已被另一进程打开」预留了错误码，但**跨进程文件锁尚未实现**
   （`paths.PROJECT_LOCK_NAME = "project.lock"` 只是常量，无代码读写它）。
3. **备份走在线备份 API**：`Database.backup_to()` 用 `sqlite3.Connection.backup()`，
   而不是复制文件——章节正在写时拷文件会得到撕裂的副本。

已知限制：没有全局写队列/串行化层，并发写依赖 `busy_timeout` + 短事务，
长事务仍可能撞上 5 秒超时。

## 6. 并发与一致性规则

| 规则 | 实现 | 位置 |
|---|---|---|
| 乐观并发 | 每行 `row_version`，更新时比对；不匹配返回 409 `conflict` | `ProjectUpdate.row_version` + `ProjectService.update` |
| 软删除 | `is_deleted` + `deleted_at`，查询默认 `is_deleted IS NOT 0` 过滤 | `SoftDeleteMixin`、`ProjectService.list/get/count` |
| 路径沙箱 | 所有由外部输入拼出的路径必须过 `ensure_within()` / `safe_join()` | `app/core/paths.py`、`app/core/ids.py` |
| 项目根校验 | `database_for()` 与 `delete()` 都先 `ensure_within(projects_root, ...)` | `ProjectService` |
| 崩溃恢复 | 章节自动保存（前端 1.2 s 防抖 + 切章/关窗前 flush）+ 乐观并发 409 | `chapter-editor.tsx`、`ChapterUpdate.row_version` |
| 事务边界 | `Database.session()` 上下文管理器：成功 commit，异常 rollback | `app/db/session.py` |
| 索引失效 | 章节目录存 `indexed_hash`，与内容哈希不符即视为过期 | `Chapter.indexed_hash`；写入侧已实现（正文变化/恢复置 `NULL`），**消费侧未实现** |
| 迁移安全 | 拒绝降级、迁移前在线备份、单事务、逐步打戳 | `app/db/migrations.py`、`Database.migrate()` |

`ProjectService.update` 的关键片段：

```python
if payload.row_version is not None and payload.row_version != project.row_version:
    raise Conflict(
        "Project was modified by someone else; reload and try again.",
        details={"expected": payload.row_version, "actual": project.row_version},
    )
```

注意：`row_version` 是**可选**的。不传就是最后写入者获胜（last-write-wins）。

## 7. 请求生命周期

```
WebView (React)
   │  fetch('/api/projects', { headers: { Authorization: 'Bearer …' } })
   ▼
uvicorn (127.0.0.1:PORT)
   │
   ├─ TokenMiddleware        ── 无令牌 → 401 auth_required
   ├─ CORSMiddleware         ── 校验 Origin
   ├─ 路由 (APIRouter prefix=/api)
   │     ├─ deps.get_runtime()          → request.app.state.runtime
   │     └─ deps.get_project_service()  → runtime.project_service
   │
   ├─ ProjectService          ── 业务规则、路径沙箱、清单同步
   │     ├─ studio.db         ── 注册表读写
   │     └─ ProjectDatabaseRegistry.open(project_id) → novel.db
   │
   └─ register_error_handlers → StudioError / RequestValidationError / HTTPException / Exception
                               统一 {"error": {code, message, details}}
```

## 8. 错误模型

所有错误都是 `{"error": {code, message, details}}`，客户端按 `code` 分支、不解析文案。
未捕获异常只返回 `{"type": "ExceptionName"}`，**不外泄堆栈**；堆栈进 structlog。

完整错误码表（含 4 个预留码）见 [api.md](api.md) §1.2。处理链路：

```
异常源                      处理器                                输出
StudioError              → _studio_error                  → exc.status + 信封
RequestValidationError   → _request_validation            → 422 + details.errors
StarletteHTTPException   → _http                          → 映射 code（401/403/404/409/423→…）
其他 Exception           → ErrorEnvelopeMiddleware        → 500 internal_error
                         → _unhandled（第二道防线）
```

## 9. 日志与可观测性

- `app/core/logging.py`：structlog + 标准库双写。
  - 控制台：`ConsoleRenderer`（TTY 才上色）。
  - 文件：`logs/backend.log`，`RotatingFileHandler(maxBytes=8MB, backupCount=5)`，**强制 JSON**。
  - 脱敏：`_SENSITIVE_KEYS` = api_key/apikey/authorization/password/secret/token/prompt/content/text/completion/messages
    → 命中即替换为 `"***"`。
  - 意图：提示词、补全、正文永不落盘。
  - 模型密钥另有独立通道：`app/core/keystore.py::SecretStore` 写 `<data_dir>/secrets.json`
    （Windows DPAPI 加密），日志里只会出现 `model_id` 与字段名，不出现密钥。
- 日志内容只有 id、计数、耗时（如 `project_created`、`chapter_saved`、`model_config_created`）。
- 版本与构建信息通过 `/api/health` 与 `/api/system/info` 暴露。

**未实现**：诊断包导出、日志下载端点、token 用量面板。

## 10. 目录结构

计划（§14）与仓库现状对照：

| 计划 | 实际 | 说明 |
|---|---|---|
| `backend/app/database/` | `backend/app/db/` | 实际包名为 `app.db`，含 `base.py`/`session.py`/`project_db.py`/`migrations.py` |
| —（计划无此文件） | `backend/app/runtime.py` | 新增进程级服务容器，持有 studio.db、项目库注册表与三个服务 |
| `backend/app/services/{novel,character,memory,retrieval,...}` | `project_service.py` · `novel_service.py` · `model_config_service.py` | 卷/章/版本与模型配置已实现；character / memory / retrieval 未实现 |
| `backend/app/ai/**` | 不存在 | LLM/Agent/Embedding/RAG 全部未实现 |
| `backend/app/tasks/` | 不存在 | 任务队列未实现（`GenerationTask` 表已在册） |
| `backend/tests/` | `tests/{conftest,test_health,test_projects,test_novels,test_model_configs,test_migrations}.py` | pytest 已就绪（37 通过） |
| `desktop/src/app/` | `desktop/src/`（`router.tsx`、`main.tsx`、`config/`） | 用 `react-router-dom` 集中路由，无 `app/` 目录 |
| `desktop/src/services/` | `desktop/src/lib/api.ts` | 命名不同，职责相同 |
| `desktop/src-tauri/src/services/` | 无 | sidecar 逻辑直接在 `sidecar.rs` |
| `shared/`、`assets/` | 不存在 | 未创建（`scripts/smoke_api.py` 已存在） |
| `docs/rag.md`、`docs/workflow.md` | **已存在** | 两份设计文档（均标注「设计完成，尚未实现」） |

已实现的桌面侧文件（`desktop/src-tauri/src/`）：`main.rs`、`lib.rs`、`sidecar.rs`、
`error.rs`、`commands/{mod,system}.rs`。

## 11. 已知缺陷与缺口

阶段 1 的骨架已就位（Tauri 壳 + sidecar 监督 + FastAPI + 项目 CRUD）。
下表是与计划目标之间的真实差距。

| 项 | 影响 | 现状 |
|---|---|---|
| 鉴权关闭端点 | 壳无法优雅通知后端退出 | 无 HTTP 端点；`SidecarState::stop()` 靠 drop handle + `taskkill`/`kill` |
| 跨进程项目锁 | 两个后端实例可同时打开同一项目 | 仅预留 `ProjectLocked`(423) 与 `paths.PROJECT_LOCK_NAME` 常量，`project.lock` 无代码读写 |
| 全局写队列 | 高频索引任务与用户保存竞争同一写者 | 依赖 `busy_timeout=5000` |
| `alembic` 冗余依赖 | 依赖在册但目录未建 | 迁移已由自研 `app/db/migrations.py` 承担（v1 baseline）；新增列必须手写迁移步骤，`create_all()` 不会给已有表加列 |
| sqlite-vec 虚拟表 | 向量仍存 `LargeBinary` 普通表 | 扩展加载逻辑在 `_load_sqlite_vec`（失败只告警），**检索未实现** |
| `project.json` 反向导入 | 拷走的项目目录无法导回注册表 | `read_manifest`/`is_project_dir` 已写但无调用方 |
| 任务队列消费 | `generation_tasks` 只存不跑 | 表已建，无 worker（见 [workflow.md](workflow.md)） |
| 章节 `volume_id` 外键错误码 | 传不存在的卷 → 500 而非 422 | `novels.py` 无归属校验，仅靠数据库外键 |
| `volumes.word_count` / `status` | 卷卡片显示 0 字 | `novel_service` 从不维护这两列 |
| 前端测试覆盖 | 仅 1 个工具函数单测（14 个用例） | `src/lib/utils.test.ts`，vitest 已配置；组件级测试未开始 |

✅ 本轮已修复（详见 [api.md](api.md) §8.1）：`POST /duplicate` 的 500 ·
`PUT /projects` 传 `"name": null` 的 500 · `/api/docs` 与 `/api/openapi.json` 需鉴权 ·
`characters` 唯一约束含软删行 · `app_meta`/`project_meta`/`project_backups` 的 `updated_at`
重声明无默认值 · `create_project_database` 无条件覆盖 `schema_version`。