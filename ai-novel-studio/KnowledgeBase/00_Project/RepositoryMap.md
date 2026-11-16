---
name: repository-map
description: 仓库地图：顶层与关键子目录的职责、哪些是产物/缓存应排除、代码规模基线。回答"目录是干什么的"。
status: 现行（2026-11-16 取证）
---

# 仓库地图

## 顶层

```
e:\ShinePlugins/
├── AGENTS.md / CODEBUDDY.md     常驻约定（同源；改约定两边一起改）
├── AI_Novel_Studio_Plan_Gaps.md 计划缺陷清单 P0/P1/P2（计划层输入，非现状）
├── .agents/                     agent 资源：skills/commands/agents/scripts（正文唯一真源）
├── .codebuddy/                  CodeBuddy 指针层（skills/commands 只放指针，禁止删）
├── .memsearch/memory/           决策/踩坑记忆（YYYY-MM-DD.md）
└── ai-novel-studio/             项目根
```

## 项目根 `ai-novel-studio/`

```
ai-novel-studio/
├── backend/           FastAPI sidecar + 测试 + venv
├── desktop/           Tauri 2 + React 19 壳（src + src-tauri + Vite 配置）
├── docs/              详版层：architecture / api / database / development-plan /
│                      plan-reconciliation / rag / workflow（无自有入口，全从 INDEX.md 进）
├── KnowledgeBase/     导航层：本库（唯一入口 INDEX.md）
├── scripts/           smoke_api.py / smoke_ai.py / configure_model.py / dev 辅助
└── README.md          上手与命令速查
```

证据：`README.md:81-115`、`INDEX.md`。

## 关键子目录职责

| 目录 | 职责 | 证据 |
|---|---|---|
| `backend/app/api/routes/` | 8 个路由模块，39 个端点 | 文件级清单见 `../01_CodeMap/10-files-backend.md` |
| `backend/app/ai/` | 适配器（llm）/结构化输出/提示词（prompts）/编排 | 同上 |
| `backend/app/services/` | 6 个业务服务（ai/novel/project/model_config/agent_config） | 同上 |
| `backend/app/db/` | SQLite 引擎、自研迁移执行器、每项目库注册表 | 同上 |
| `backend/app/models/` | 全局 8 表（studio.py）+ 项目域表（novel.py） | 同上 |
| `desktop/src/components/editor/` | 编辑器四件套：ai-panel / chapter-editor / chapter-tree / version-history | `../01_CodeMap/11-files-desktop.md` |
| `desktop/src/lib/` | HTTP 客户端、SSE 解析、sidecar 握手、工具函数 | 同上 |
| `desktop/src-tauri/src/` | Rust 壳：窗口、命令、sidecar 生命周期 | `../01_CodeMap/12-files-tauri.md` |

## 代码规模基线（2026-11-16 取证）

| 层 | 文件数 | 说明 |
|---|---|---|
| `backend/app/**/*.py` | **56** | 排除 `__pycache__`；app 下无测试文件 |
| `backend/tests/*.py` | **15** | 用例约 105（AI 相关 8 文件 49 例 + 其余 7 文件 56 例） |
| `desktop/src/**/*.ts/.tsx` | **62** | ts 20 + tsx 42；CSS 另 1 |
| `desktop/src-tauri/src/**/*.rs` | **7** | — |
| 前端测试文件 | **5** | `lib/{ai,api,sidecar,text-edit,utils}.test.ts` |

> 这是**小体量应用**，不是引擎。参考项目的 `02_Modules` 逐模块逐行文档与 701 文件清单属其规模配套，本库不照搬（见 `INDEX.md` 分区说明）。

## 应排除的目录（扫描/检索时跳过）

`**/node_modules/`、`**/.venv/`、`**/__pycache__/`、`desktop/dist/`、`desktop/src-tauri/target/`（含大量 `.o/.rlib/.rmeta` 构建产物）、`NovelProjects/`（用户数据，只读）。
