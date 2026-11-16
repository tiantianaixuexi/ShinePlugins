# AI Novel Studio

本地优先的 AI 长篇小说创作工作室：把项目管理、章节编辑、分层记忆、混合检索、
Agent 工作流、故事板与影视化生产收进一个桌面应用。数据默认全部留在本机，
只有调用模型时才把必要上下文发给你配置的模型服务。

- **形态**：Tauri 2 桌面应用（Windows 优先，打包 `msi` / `nsis`）
- **后端**：Python 3.13 + FastAPI，作为 sidecar 子进程
- **前端**：React 19 + TypeScript + Vite + Tailwind CSS 4 + shadcn/ui
- **存储**：SQLite（WAL），全局注册表 + 每项目独立数据库
- **版本**：`0.1.0` · **阶段**：2 / 7（编辑器 + AI 写作已可用，记忆检索未开工）

> **开发中。** 阶段 1 已完成；阶段 2 的创作闭环已打通
> （项目 → 卷 → 章节 → 写正文 → 自动保存 → 历史版本 → 恢复），
> 并且接入了模型配置、加密密钥与 AI 写作（7 个操作 + 流式输出 + AI 面板）。
> **长篇记忆检索、Agent 工作流、故事板、媒体生产尚未实现。**
> 详见 [development-plan.md](docs/development-plan.md) 与文末「当前状态」。

## 目录

[快速开始](#快速开始) · [技术栈](#技术栈与固定版本) · [目录结构](#目录结构) ·
[开发环境](#开发环境) · [运行后端](#运行后端) · [运行前端](#运行前端) ·
[运行桌面应用](#运行桌面应用) · [运行测试](#运行测试) · [验证](#验证) ·
[当前状态](#当前状态) · [文档](#文档)

### 模块入口

| 路由 | 页面 | 说明 |
|---|---|---|
| `/` | 工作台 | 项目总览、创作进度、系统状态 |
| `/projects` | 项目管理 | 列表、新建、编辑、删除、复制 |
| `/projects/:projectId` | 项目详情 | 元数据、统计、「开始创作」入口 |
| `/projects/:projectId/editor` | 小说编辑器 | 绑定指定项目的编辑器 |
| `/editor` | 小说编辑器 | 不带项目时提示先选项目（`?project=<id>` 可直接带入） |
| `/settings` | 系统设置 | 运行环境、**模型配置**、主题、关于 |
| `/knowledge` `/characters` `/storyboard` `/workflows` `/media` | 占位页 | 未实现模块的说明页（列出计划能力） |

## 快速开始

前置：**Python 3.13+**、**Node.js 20+**、**pnpm**、**Rust 1.93+**（Tauri 构建需要）。

```powershell
# 1. 后端依赖
cd E:\ShinePlugins\ai-novel-studio\backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements-dev.txt

# 2. 前端依赖
cd E:\ShinePlugins\ai-novel-studio\desktop
pnpm install

# 3. 启动桌面应用（自动拉起 Python 后端）
pnpm tauri dev
```

首次 `pnpm tauri dev` 需编译 Rust 依赖，耗时数分钟。

## 技术栈与固定版本

以下版本为 2026-11-16 的稳定版，已锁定在清单文件中，**不要随意升级**。

| 层 | 包（版本） |
|---|---|
| **前端核心** | `react` / `react-dom` 19.3.1 · `vite` 8.3.8 · `typescript` 7.0.2 · `@vitejs/plugin-react` 6.3.0 |
| **样式** | `tailwindcss` / `@tailwindcss/vite` 4.3.5 · `tailwind-merge` 3.7.0 · `class-variance-authority` 0.7.1 |
| **状态与数据** | `zustand` 5.1.0 · `@tanstack/react-query` 5.107.1 · `@tanstack/react-virtual` 3.14.26 |
| **功能组件** | `@tiptap/react` 3.34.0（已装，**编辑器有意未用**，见下） · `@xyflow/react` 12.12.1（已装，**未使用**） · `recharts` 3.10.1 · `sonner` 2.0.8 · `lucide-react` 1.73.0 |
| **路由与桥接** | `react-router-dom` 7.18.5 · `@tauri-apps/api` / `@tauri-apps/cli` 2.12.4 |
| **Rust** | `tauri` 2.12.5 · `tauri-build` 2.7.4 · `serde` 1.0.229 · `serde_json` 1.0.154 · `tokio` 1.54.1 |
| **Web 框架** | `fastapi` 0.163.1 · `uvicorn` 0.54.0 · `pydantic` 2.14.3 · `pydantic-settings` 2.16.3 · `httpx` 0.28.1 |
| **数据层** | `sqlalchemy` 2.1.8 · `alembic` 1.20.1（依赖在册，`alembic/` 目录未建，迁移由自研 `app/db/migrations.py` 完成） · `sqlite-vec` 0.1.9（加载就绪，检索未实现） |
| **AI / 媒体** | `openai` 3.51.0（依赖在册，**未使用**） · `tiktoken` 0.14.0 · `numpy` 2.5.5 · `pillow` 13.0.0 · `pymupdf` 2.1 · `python-docx` 1.2.0（后两者**未使用**） |
| **可观测 / 测试** | `structlog` 26.1.0 · `pytest` 9.2.0 · `pytest-asyncio` 1.5.0 |

## 目录结构

```
ai-novel-studio/
├── desktop/                      # Tauri 2 + React 19 桌面端
│   ├── src/
│   │   ├── main.tsx              # React 入口
│   │   ├── router.tsx            # 路由表（hash 路由）
│   │   ├── config/navigation.ts  # 侧边导航（含 milestone 与 implemented 标记）
│   │   ├── components/
│   │   │   ├── layout/           # app-shell / sidebar / topbar / status-bar
│   │   │   ├── editor/           # chapter-tree / chapter-editor / version-history-dialog
│   │   │   ├── settings/         # model-config-panel（模型配置）
│   │   │   └── ui/               # shadcn/ui 组件（22 个）
│   │   ├── pages/                # dashboard / projects / novel-editor / settings / placeholder / errors
│   │   ├── hooks/                # use-projects / use-novel / use-backend / use-theme
│   │   ├── stores/               # zustand
│   │   ├── lib/{api.ts,sidecar.ts,utils.ts}   # 类型化 HTTP 客户端 / sidecar 握手 / 工具
│   │   └── types/api.ts          # API 类型定义
│   ├── src-tauri/
│   │   ├── src/{main.rs,lib.rs,sidecar.rs,error.rs}
│   │   ├── src/commands/{mod.rs,system.rs}   # Tauri 命令
│   │   ├── capabilities/  icons/  tauri.conf.json  Cargo.toml
│   ├── vite.config.ts  tsconfig.json  components.json  package.json
│
├── backend/                      # FastAPI 服务（sidecar）
│   ├── app/
│   │   ├── main.py               # 应用工厂、TokenMiddleware、错误信封
│   │   ├── runtime.py            # 进程级服务容器
│   │   ├── __main__.py           # `python -m app` 入口
│   │   ├── api/{deps.py,router.py,routes/}   # health / projects / novels / model_configs / system
│   │   ├── core/                 # config / errors / logging / security / ids / paths / keystore
│   │   ├── db/{base.py,session.py,project_db.py,migrations.py}   # WAL、迁移执行器、项目库注册表
│   │   ├── models/{studio.py,novel.py}   # 逻辑上 8 张全局表 / 27 张项目表（物理上两库各 35 张）
│   │   ├── schemas/{project.py,novel.py,model_config.py}
│   │   ├── services/{project_service.py,novel_service.py,model_config_service.py}
│   │   └── utils/text.py         # count_words / split_paragraphs / excerpt
│   ├── tests/                    # pytest（health / projects / novels / model_configs / migrations）
│   └── pyproject.toml  requirements.txt
│
├── scripts/smoke_api.py          # 端到端冒烟（自带临时数据目录）
├── docs/                         # 见文末「文档」
└── README.md  LICENSE
```

## 开发环境

### 一次性准备

```powershell
cd E:\ShinePlugins\ai-novel-studio\backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements-dev.txt

cd E:\ShinePlugins\ai-novel-studio\desktop
pnpm install

rustup default stable          # Tauri 需要，rustc 应为 1.93+
```

### 环境变量

后端全部配置走 `NOVEL_STUDIO_` 前缀（`backend/app/core/config.py`）。

| 变量 | 默认 | 说明 |
|---|---|---|
| `NOVEL_STUDIO_HOST` | `127.0.0.1` | 监听地址（壳强制 `127.0.0.1`） |
| `NOVEL_STUDIO_PORT` | `8765` | 端口（壳注入动态空闲端口） |
| `NOVEL_STUDIO_AUTH_TOKEN` | 空 | 共享密钥；空则不鉴权（仅本地开发） |
| `NOVEL_STUDIO_DATA_DIR` | 平台用户数据目录 | 数据根目录 |
| `NOVEL_STUDIO_ENVIRONMENT` | `development` | 环境标识 |
| `NOVEL_STUDIO_LOG_LEVEL` | `INFO` | 日志级别 |
| `NOVEL_STUDIO_LOG_JSON` | `false` | 控制台是否输出 JSON |
| `NOVEL_STUDIO_API_PREFIX` | `/api` | 路由前缀 |
| `NOVEL_STUDIO_BACKEND_DIR` / `NOVEL_STUDIO_PYTHON` | — | 仅壳使用：覆盖后端目录 / 解释器 |

数据目录默认位置（`platformdirs.user_data_dir("AI Novel Studio", roaming=True)`，与桌面端一致）：

```
C:\Users\<你>\AppData\Roaming\AI Novel Studio\
├── studio.db            # 全局注册表
├── secrets.json         # 加密后的模型密钥（Windows 用 DPAPI；勿提交、勿拷贝）
├── logs\backend.log
├── sidecar.json         # 壳写的握手文件（含令牌）
├── cache\
└── NovelProjects\       # 每个项目一个目录
```

## 运行后端

### 方式一：独立运行（开发调试推荐）

用固定端口与固定令牌，浏览器/curl 可直接访问：

```powershell
cd E:\ShinePlugins\ai-novel-studio\backend
.\.venv\Scripts\Activate.ps1

$env:NOVEL_STUDIO_HOST = "127.0.0.1"
$env:NOVEL_STUDIO_PORT = "8765"
$env:NOVEL_STUDIO_AUTH_TOKEN = "dev-token"
$env:NOVEL_STUDIO_DATA_DIR = "$env:USERPROFILE\ai-novel-studio-dev"
$env:NOVEL_STUDIO_LOG_LEVEL = "DEBUG"

python -m app
```

| 入口 | 地址 |
|---|---|
| 免鉴权存活探针 | <http://127.0.0.1:8765/healthz> |
| 就绪探针 | <http://127.0.0.1:8765/api/health> |
| Swagger UI | <http://127.0.0.1:8765/api/docs> |
| OpenAPI | <http://127.0.0.1:8765/api/openapi.json> |

`/api/docs` 与 `/api/openapi.json` 已加入 `TokenMiddleware.OPEN_PATHS` 白名单，**无需令牌**。

```powershell
$h = @{ Authorization = "Bearer dev-token" }

Invoke-RestMethod http://127.0.0.1:8765/api/health -Headers $h

$body = @{ name = "我的小说"; target_word_count = 1000000 } | ConvertTo-Json
$p = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/projects `
     -Headers $h -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body))
$p.id

Invoke-RestMethod http://127.0.0.1:8765/api/projects -Headers $h
```

> PowerShell 5.1 的 `Invoke-RestMethod` 对 UTF-8 请求体处理不一致，中文可能乱码。
> 涉及中文时优先用 `curl.exe`，或升级到 PowerShell 7。

```bash
export TOKEN=dev-token
B=http://127.0.0.1:8765

curl -s -H "Authorization: Bearer $TOKEN" $B/api/health
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"我的小说","target_word_count":1000000}' $B/api/projects
```

### 方式二：由桌面壳拉起

直接 `pnpm tauri dev`，壳会自动选端口、生成令牌、注入环境变量并轮询 `/api/health`。
此模式下**不需要**手动设置任何环境变量。

## 运行前端

### 推荐：一条命令起前后端（浏览器调试）

```powershell
cd E:\ShinePlugins\ai-novel-studio
pwsh -File scripts\dev.ps1
```

它会依次做三件事：首次运行按 `.env.example` 生成 `desktop/.env`（开发 token `dev-token`）、
启动 Python 后端（`:8765`，端口被占用则复用现有进程）、启动 Vite（`:1420`）。
关掉前端时自动停掉后端，不会留孤儿进程。

### 仅调试 UI（后端需另行启动）

```powershell
cd E:\ShinePlugins\ai-novel-studio\backend
$env:NOVEL_STUDIO_AUTH_TOKEN = "dev-token"
$env:NOVEL_STUDIO_PORT = "8765"
.\.venv\Scripts\python.exe -m app

# 另开一个终端
cd E:\ShinePlugins\ai-novel-studio\desktop
pnpm dev
```

Vite 固定监听 <http://127.0.0.1:1420>，把 `/api` 代理到 `http://127.0.0.1:8765`。
纯浏览器环境下前端还会读 `desktop/.env` 里的 `VITE_API_TOKEN` 作为回退令牌。

> **常见坑**：如果界面提示「请求失败 HTTP 502」，那不是模型或密钥的问题 ——
> Vite 代理在**后端没启动**时返回纯文本 502。先确认后端在跑（`scripts\dev.ps1`），
> 界面顶部也会同时出现「无法连接后端服务」的横幅。

| 脚本 | 作用 |
|---|---|
| `scripts/dev.ps1`（仓库根） | 同时起后端 + Vite，退出时清理后端 |
| `pnpm dev` | 仅 Vite 开发服务器 |
| `pnpm typecheck` | `tsc --noEmit` |
| `pnpm test` / `pnpm test:watch` | vitest 单次 / 监听 |
| `pnpm build` | 类型检查 + 构建到 `desktop/dist` |
| `pnpm preview` | 预览构建产物 |

## 运行桌面应用

```powershell
cd E:\ShinePlugins\ai-novel-studio\desktop
pnpm tauri dev      # 开发（首次编译 Rust 较慢）
pnpm tauri build    # 构建安装包 -> desktop/src-tauri/target/release/bundle/
```

`tauri.conf.json` 关键配置：窗口 1440×900（最小 1024×640）· 标识
`com.ainovelstudio.desktop` · 开发 URL `http://localhost:1420` ·
前端产物 `desktop/dist` · 打包目标 `msi`、`nsis`。

## 运行测试

### 后端

```powershell
cd E:\ShinePlugins\ai-novel-studio\backend
.\.venv\Scripts\Activate.ps1

pytest                              # 全部
pytest -q                           # 静默
pytest tests/test_projects.py -v
pytest -k health
pytest --cov=app                    # 需先 pip install pytest-cov
```

配置在 `pyproject.toml`：`testpaths=["tests"]`、`addopts="-q"`、`asyncio_mode="auto"`、
`filterwarnings=["error::DeprecationWarning:app.*"]`。测试用 `tmp_path` 隔离数据目录，
**不会**碰你的真实项目库。

### 前端

```powershell
cd E:\ShinePlugins\ai-novel-studio\desktop
pnpm test          # 单次运行
pnpm test:watch    # 监听
```

配置在 `vite.config.ts` 的 `test` 段：jsdom 环境、globals、`./src/test/setup.ts`。

### 端到端冒烟

```powershell
cd E:\ShinePlugins\ai-novel-studio
.\backend\.venv\Scripts\python.exe scripts\smoke_api.py
```

脚本自己选一个空闲端口、建临时数据目录、拉起真实后端，
走完「项目 → 卷 → 章节 → 保存 → 冲突 → 版本 → 恢复 → 模型配置 → 密钥加密」，
每项打印 PASS/FAIL，全部通过时输出 `SMOKE PASSED: all checks green`。
它**不会**碰你的真实数据目录。

### 手动端到端

```bash
# 启动后端（另开终端），然后：
B=http://127.0.0.1:8765
T=dev-token
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $T" $B/api/health   # 期望 200
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Authorization: Bearer $T" \
  -H "Content-Type: application/json" -d '{"name":"端到端"}' $B/api/projects           # 期望 201
curl -s -o /dev/null -w "%{http_code}\n" $B/api/health                                # 期望 401
```

## 验证

以下命令与结果于 **2026-11-16** 在本仓库实测，可原样复现。

```powershell
# 1. 后端单元测试
cd E:\ShinePlugins\ai-novel-studio\backend
.\.venv\Scripts\python.exe -m pytest -q
# 期望：60 passed
#   分布：ai_adapters 13 · ai_stream_e2e 2 · health 6 · migrations 6
#         model_configs 11 · novels 12 · projects 10
```

```powershell
# 2. 前端单元测试
cd E:\ShinePlugins\ai-novel-studio\desktop
pnpm test
# 期望：Test Files 4 passed (4) · Tests 29 passed (29)
#   分布：utils 14 · ai 5 · api 4 · text-edit 6
```

```powershell
# 3. 前端类型检查
cd E:\ShinePlugins\ai-novel-studio\desktop
pnpm typecheck
# 期望：无任何输出（tsc --noEmit 干净通过）
```

```powershell
# 4. 前端生产构建
cd E:\ShinePlugins\ai-novel-studio\desktop
pnpm build
# 期望：✓ built in <n>ms，产出 dist/index.html 与 dist/assets/*
```

```powershell
# 5. 端到端冒烟
cd E:\ShinePlugins\ai-novel-studio
.\backend\.venv\Scripts\python.exe scripts\smoke_api.py
# 期望：最后一行 SMOKE PASSED: all checks green
```

```powershell
# 6. Rust 侧类型检查
cd E:\ShinePlugins\ai-novel-studio\desktop\src-tauri
cargo check
# 期望：Finished `dev` profile ... 无 error / 无 warning
```

| # | 命令 | 期望结果 |
|---|---|---|
| 1 | `backend/.venv/Scripts/python.exe -m pytest -q` | `60 passed` |
| 2 | `desktop/pnpm test` | `25 passed (25)` |
| 3 | `desktop/pnpm typecheck` | 无输出（干净） |
| 4 | `desktop/pnpm build` | `✓ built`，产出 `dist/` |
| 5 | `backend/.venv/Scripts/python.exe scripts/smoke_api.py` | `SMOKE PASSED: all checks green`（27 项检查） |
| 6 | `desktop/src-tauri` `cargo check` | `Finished`，无 error |
| 7 | `scripts/smoke_ai.py --from-store` | `AI SMOKE PASSED`（需要已配置的模型） |

第 1 项的 60 个用例分布：`test_ai_adapters.py` 13 · `test_ai_stream_e2e.py` 2 ·
`test_health.py` 6 · `test_migrations.py` 6 · `test_model_configs.py` 11 ·
`test_novels.py` 12 · `test_projects.py` 10。
（历史上文档出现过「31 / 37 / 44 / 58 passed」，分别对应迁移测试、章节缺陷测试、
AI 适配器、模型配置测试加入之前的基线；以实际收集数为准。）

## 当前状态

### 已实现（已实测验证）

| 模块 | 内容 |
|---|---|
| 桌面壳 | Tauri 2 主窗口、菜单、侧边导航、顶栏、状态栏、深色主题、路由、5 个 Tauri 命令 |
| 前端页面 | 仪表盘、项目列表/详情、新建/编辑对话框、**小说编辑器**、**系统设置（含模型配置）**、404、未实现模块占位页 |
| Sidecar 监督 | 动态端口、一次性令牌、`/api/health` 轮询（250ms × 45s）、日志环形缓冲、优雅退出与强杀 |
| 后端 API | **39 个端点**（`/healthz` + 38 个 `/api/*`，含 AI 8）、统一错误信封、乐观并发 |
| 数据层 | 35 张表、WAL、外键级联、软删除、路径沙箱、**迁移执行器**（拒绝降级 + 迁移前在线备份） |
| 项目生命周期 | 创建、读取、更新、软删、硬删、复制、统计 |
| **卷与章节** | 卷增/删/改（删卷保留章节）、章节增/删/改/排序、章节树按卷分组、软删除 |
| **编辑器** | `<textarea>` 正文编辑（有意为之，见下）、1.2 s 防抖自动保存、`Ctrl/Cmd+S`、切章/关窗前 flush、409 冲突提示、实时字数 |
| **字数统计** | 后端 `count_words` 与前端 `countWords` 同一算法：CJK 每字 1、拉丁/数字连续段 1、标点空白不计 |
| **章节版本** | 自动快照（300 s 限流）、手动快照（`snapshot: true` 强制）、每章最多 60 版、恢复前先存档当前正文 |
| **模型配置** | 6 个端点；**通用「自带端点」形态**：只填 Base URL + Key + 模型名即可，不按厂商写适配器；密钥**只写**（`secrets.json`，Windows DPAPI 加密），响应仅 `has_api_key`；首次启动自动建模板并设为默认 |
| **AI 写作** | 7 个操作（outline / write / continue / expand / rewrite / polish / review）；`POST /api/ai/{op}` 非流式、`POST /api/ai/{op}/stream` SSE 流式；OpenAI 兼容适配器带超时、指数退避重试、失败切换备用模型；每次生成落 `generation_tasks`（token / 成本 / 耗时），`GET /api/ai/tasks` 可查 |
| **Prompt 模板** | 7 套内置模板首次启动播种进 `prompt_templates`，数据库优先，可在设置里改；生成记录关联 prompt 版本 |
| 配置与日志 | `NOVEL_STUDIO_*` 环境变量、structlog（控制台 + 8MB×5 滚动 JSON）、敏感字段脱敏 |

### 部分完成：阶段 2 剩余部分

| 项 | 状态 |
|---|---|
| 大纲生成 | ⚠️ 端点可用（`POST /api/ai/outline`），大纲持久化与大纲编辑页未做 |
| 审稿 | ⚠️ 端点可用（`POST /api/ai/review`），结论不落库、只做展示 |
| TXT / DOCX 导入导出 | ❌ `python-docx` / `pymupdf` 在册但未使用 |
| Tiptap 富文本 | ❌ **故意未做**：正文以纯文本存储，`<textarea>` 保真、对 IME 友好、几十万字仍流畅；`@tiptap/*` 已安装但零引用，将来换编辑器不需迁移数据 |
| 生成结果的版本化 | ⚠️ 正文接受后即自动保存并可手动存版本，但「AI 草稿 → 正式稿」的双轨未建模 |

### 未实现

- **AI**：大纲持久化与编辑页、生成结果版本化、模型 A/B 对比、Token 用量面板
- **记忆与检索**：知识块索引、FTS5、Embedding、sqlite-vec、混合检索、Reranker、上下文组装、Token 预算
  （表结构全部就绪，代码零实现；设计见 [docs/rag.md](docs/rag.md)）
- **Agent 与工作流**：8 类 Agent、React Flow 画布、任务队列与调度
  （`generation_tasks` / `task_logs` 表就绪但无读写方；设计见 [docs/workflow.md](docs/workflow.md)）
- **故事板与媒体**：剧本解析、镜头拆解、图片/视频/TTS 生成、FFmpeg 合成
- **人物与世界观**：`characters` / `locations` / `events` / `foreshadows` 表就绪，但无 API、无 UI
- **工程化**：自动更新、打包签名、国际化

### 已知缺陷

`POST /chapters` 传不存在的 `volume_id` 返回 500（应为 422） ·
`PUT /chapters` 无法把章节移出卷（`volume_id: null` 被当作「不修改」） ·
`PUT /model-configs` 传 `null` 给 `base_url`/`notes`/`capabilities`/`fallback_ids` 返回 500 ·
`POST /chapters/reorder` 传部分 id 时不归一化 `sort_order` ·
`volumes.word_count` 恒为 0、`volumes.status` 恒为 `draft` ·
`stats.chapters` / `stats.words` 统计含软删章节 ·
删章不清理 `knowledge_chunks` / `embeddings`（对 `chapter_id` 无 FK） ·
`project.json` 无反向导入 ·
`create_project_database` 无条件覆盖 `schema_version`（**已修复**，见下）。

完整清单与根因分析见 [docs/api.md](docs/api.md) §8。

### 已修复（本轮核对确认）

`POST /duplicate` 的 500（`Database` 未 `dispose()`） ·
`PUT /projects` 传 `"name": null` 的 500（改为 422） ·
`/api/docs`、`/api/openapi.json` 需鉴权（已加入 `OPEN_PATHS` 白名单） ·
`characters(project_id, name)` 唯一约束含软删行（改为部分唯一索引 `... WHERE is_deleted = 0`） ·
`app_meta`/`project_meta`/`project_backups` 的 `updated_at` 重声明无默认值（改继承 `TimestampMixin`） ·
`create_project_database` 无条件覆盖 `schema_version`（新增 `app/db/migrations.py`）。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | 进程模型、职责划分、sidecar 协议、存储策略、并发规则、数据流 |
| [docs/database.md](docs/database.md) | 35 张表的完整字段、迁移策略、软删除、级联规则、部分唯一索引 |
| [docs/api.md](docs/api.md) | HTTP 契约：39 个已实现端点 + 未实现端点 + 错误信封 + 字数与版本语义 + 已知缺陷 |
| [docs/development-plan.md](docs/development-plan.md) | 7 阶段计划、进度标记、验收判据、风险表、版本范围 |
| [docs/rag.md](docs/rag.md) | **设计完成，尚未实现**：L0–L4 分层、结构化切分、混合检索流水线、Token 预算、增量索引、换模型重建、检索审计 |
| [docs/workflow.md](docs/workflow.md) | **设计完成，尚未实现**：React Flow 编辑 vs Python 执行、节点类型、状态机、环与条件、断点续跑、幂等键、优先级 |

## License

MIT，见 [LICENSE](LICENSE)。