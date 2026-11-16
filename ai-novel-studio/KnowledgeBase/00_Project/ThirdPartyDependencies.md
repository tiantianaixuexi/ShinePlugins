---
name: third-party-dependencies
description: 第三方依赖清单（backend/desktop/tauri）与"在册未用"依赖取证。回答"用了什么库/某依赖到底用没用"。
status: 现行（2026-11-16 取证）
---

# 第三方依赖清单

> 事实型文档。依赖对应的未实现功能写 `→ T-xx`（见 `../05_Plan/TaskRegister.md`），不在本页描述缺陷。

## backend（pyproject 与 requirements 运行时集合一致，共 22 项）

`backend/pyproject.toml:11-34` 与 `backend/requirements.txt:2-36` 逐项同名同版本。

| 分类 | 依赖==版本 | 证据 |
|---|---|---|
| web | `fastapi==0.163.1`、`uvicorn==0.54.0`、`pydantic==2.14.3`、`pydantic-settings==2.16.3`、`python-multipart==0.0.33`、`sse-starlette==3.7.0`、`httpx==0.28.1`、`orjson==3.13.0`、`jinja2==3.1.6` | `pyproject.toml:12-16,23,30-33` |
| orm/data | `sqlalchemy==2.1.8`、`alembic==1.20.1`、`aiosqlite==0.22.1`、`greenlet==3.5.6`、`sqlite-vec==0.1.9`、`numpy==2.5.5` | `pyproject.toml:17-22` |
| ai | `openai==3.51.0`、`tiktoken==0.14.0` | `pyproject.toml:24-25` |
| media/doc | `pillow==13.0.0`、`pymupdf==2.1`、`python-docx==1.2.0` | `pyproject.toml:26-28` |
| 可观测/工具 | `structlog==26.1.0`、`platformdirs==4.14.5` | `pyproject.toml:29,32` |
| test | `pytest==9.2.0`、`pytest-asyncio==1.5.0` | `pyproject.toml:38-39` |
| lint | `ruff==0.17.5`、`mypy==2.4.1`；dev-only `types-pyyaml==6.0.12.20261113` | `pyproject.toml:40-41`、`requirements-dev.txt:8-11` |

工具配置：pytest `testpaths/tests` / `addopts -q` / `asyncio_mode auto`（`pyproject.toml:47-53`）；ruff line-length 100、忽略 CJK 全角标点（`pyproject.toml:55-63`）；mypy strict + pydantic 插件（`pyproject.toml:65-69`）。

## desktop（npm）

| 分类 | 依赖（版本） | 证据 |
|---|---|---|
| 核心 | `react`/`react-dom` 19.3.1、`react-router-dom` 7.18.5 | `desktop/package.json:46-48` |
| 状态/数据 | `zustand` 5.1.0、`@tanstack/react-query` 5.107.1、`@tanstack/react-virtual` 3.14.26 | `desktop/package.json:35-36,53` |
| 桥接 | `@tauri-apps/api` 2.12.4 | `desktop/package.json:37` |
| UI/组件 | `@dnd-kit/*`、`@radix-ui/react-*`×14、`class-variance-authority` 0.7.1、`clsx` 2.1.1、`tailwind-merge` 3.7.0、`lucide-react` 1.73.0、`next-themes` 0.4.6、`recharts` 3.10.1、`sonner` 2.0.8 | `desktop/package.json:18-35,42-52` |
| devDeps | `@tailwindcss/vite` 4.3.5、`@tauri-apps/cli` 2.12.4、`@testing-library/*`、`@vitejs/plugin-react` 6.3.0、`jsdom` 31.0.1、`tailwindcss` 4.3.5、`typescript` 7.0.2、`vite` 8.3.8、`vitest` 5.1.0 | `desktop/package.json:55-69` |

## src-tauri（关键 crate）

| 分类 | crate（版本） | 证据 |
|---|---|---|
| 框架 | `tauri-build 2.7.4`、`tauri 2.12.5` | `Cargo.toml:14,17` |
| 插件 | `dialog 2.8.4`、`fs 2.7.1`、`shell 2.6.0`、`opener 2.7.3`、`notification 2.8.1` | `Cargo.toml:18-22` |
| 序列化/异步 | `serde 1.0.229`、`serde_json 1.0.154`、`tokio 1.54.1`、`thiserror 2.0.21` | `Cargo.toml:23-25,28` |
| 日志/系统 | `tracing 0.1.44`、`tracing-subscriber 0.3.23`、`sysinfo 0.38.4`（因 rustc 1.93 固定）、`directories 6.0.0` | `Cargo.toml:26-27,29-32` |
| sidecar 支撑 | `portpicker 0.1.1`、`uuid 1.29.2`、`chrono 0.4.45`、`reqwest 0.13.5`（rustls，仅 loopback） | `Cargo.toml:33-40` |
| Windows only | `windows-sys 0.61.2`（JobObjects 等） | `Cargo.toml:42-49` |
| release | `lto=true`、`opt-level="s"`、`strip=true`、`codegen-units=1` | `Cargo.toml:55-59` |

## "在册未用"依赖（源码零引用取证）

对 `*.py/*.ts/*.tsx/*.rs` 做大小写敏感检索（`import docx|import fitz|import openai|import alembic|@xyflow/react|@tiptap`）→ **0 命中**，仅文档与清单出现。

| 依赖 | 在册位置 | 未用证据 | 去向 |
|---|---|---|---|
| `python-docx 1.2.0` | `pyproject.toml:28` | 源码 0 引用 | 导入导出未实现 → `T-17` |
| `pymupdf 2.1` | `pyproject.toml:27` | `import fitz` 0 引用 | 文档解析未实现 → 计划层 |
| `openai 3.51.0` | `pyproject.toml:24` | `import openai` 0 引用 | 适配器走纯 HTTP（`ai/llm/openai_compatible` 是内部模块名，非 SDK） |
| `alembic 1.20.1` | `pyproject.toml:18` | `import alembic` 0 引用 | 迁移由 `app/db/migrations.py` 自研，alembic/ 目录未建 |
| `sqlite-vec 0.1.9` | `pyproject.toml:21` | 加载就绪、检索未实现 | → `T-11`（阶段 3 RAG） |
| `@tiptap/* 3.34.0` | `package.json:38-40` | ts/tsx 0 引用 | **有意未用**：V1.x 正文用 `<textarea>`，见 ADR/development-plan §3.4 |
| `@xyflow/react 12.12.1` | `package.json:41` | ts/tsx 0 引用 | `/workflows` 占位页 → `T-19`（阶段 4） |

> "在册未用"不等于 bug：Tiptap 是有意取舍，python-docx/@xyflow 是计划中的功能依赖。判定见 `../04_BugsAndLessons/DefectRegister.md` 收录口径。
