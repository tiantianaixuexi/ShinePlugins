---
name: project-overview
description: AI Novel Studio 客观基线：定位、技术栈锁定版本、各层职责、数据目录。回答"这是什么项目/用了什么版本/数据在哪"。
status: 现行（随配置更新）
---

# 项目概览（客观基线）

> 事实型文档。缺陷只写 `→ DEF-xx`（见 [`../04_BugsAndLessons/DefectRegister.md`](../04_BugsAndLessons/DefectRegister.md)）；进度见 [`../05_Plan/CurrentStatus.md`](../05_Plan/CurrentStatus.md)。

## 定位

本地优先的 AI 长篇小说创作桌面应用，Windows 优先，打包 msi/nsis（`README.md:3-7`）。技术取舍：**正文用 `<textarea>` 而非 Tiptap**（保真/中文 IME/性能，理由见 `../../docs/development-plan.md` §3.3；决策归 ADR）。

## 技术栈与锁定版本

| 层 | 版本 | 证据 |
|---|---|---|
| Tauri | crate `tauri 2.12.5`、`tauri-build 2.7.4`，配置 schema config/2 | `desktop/src-tauri/Cargo.toml:14,17`；`tauri.conf.json:2` |
| React | `react`/`react-dom` 19.3.1；Vite 8.3.8、TS 7.0.2、pnpm 12.5.1 | `desktop/package.json:4-7,46-47,63,66-67` |
| FastAPI | `fastapi 0.163.1` + `uvicorn 0.54.0`；Python `>=3.13` | `backend/pyproject.toml:9,12-13` |
| SQLite | SQLAlchemy 2.1.8 + aiosqlite 0.22.1 + sqlite-vec 0.1.9；全局库 WAL + 每项目独立库 | `backend/pyproject.toml:17,19,21`；`README.md:10,109` |
| Rust | `rust-version = "1.93"`；sysinfo 固定 0.38.4（避免要求 rustc 1.95） | `desktop/src-tauri/Cargo.toml:7,30-32` |
| 版本一致 | 四处均 `0.1.0` | `backend/pyproject.toml:7`、`desktop/package.json:4`、`Cargo.toml:3`、`tauri.conf.json:4` |

## 各层职责

| 层 | 职责 | 证据 |
|---|---|---|
| `desktop/src`（React） | 路由/页面/编辑器/设置，类型化 HTTP 客户端与 sidecar 握手 | `README.md:82-95` |
| `desktop/src-tauri`（Rust） | 主窗口、菜单、5 个 Tauri 命令、sidecar 生命周期（选端口/令牌/轮询/日志/强杀） | `README.md:96-99,403-405` |
| `backend/app`（Python） | 39 个端点、统一错误信封、35 张表、迁移执行器、AI 适配与密钥管理 | `README.md:103-113,406-416` |
| 分工原则 | 长任务/RAG/结构化抽取/媒体编排放 Python；SQLite 事务与成熟库在 Python 侧 | `../../docs/architecture.md:51` |

## 数据目录

数据根 Windows 为 `C:\Users\<你>\AppData\Roaming\AI Novel Studio\`：platformdirs `roaming=True`，**必须与 Tauri `BaseDirs::data_dir()` 一致**（`backend/app/core/config.py:40-47`、`README.md:155-158`、`desktop/src-tauri/src/sidecar.rs:391-399`）。

| 路径（相对数据根） | 用途 | 证据 |
|---|---|---|
| `studio.db` | 全局注册表；sqlite URL 由此派生 | `core/config.py:73,98-103`；`README.md:159` |
| `NovelProjects/` | 每项目一个独立数据库目录 | `core/config.py:74,105-107`；`README.md:164` |
| `secrets.json` | API Key 密文（Windows DPAPI） | `core/keystore.py:32,126` |

**硬约束**：`NovelProjects/` 下的项目目录与 `studio.db`/项目库是用户资产，一律只读或走迁移脚本（`AGENTS.md` 硬规则 1）。
