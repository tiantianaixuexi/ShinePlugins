---
name: code-map
description: 代码地图总图：目录→职责→关键文件，按层组织。回答"某功能大概在哪一层/哪个目录"。
status: 现行（2026-11-16 取证）
---

# 代码地图总图

> 找具体文件进 [`10-files-backend.md`](10-files-backend.md) / [`11-files-desktop.md`](11-files-desktop.md) / [`12-files-tauri.md`](12-files-tauri.md)。
> 跨层调用链见 [`02-lifecycle.md`](02-lifecycle.md)。硬规则与分层约束见 `../INDEX.md`。

## 30 秒模型

- 桌面壳（Tauri）拉起 Python sidecar（`python -m app`），注入动态端口 + 一次性令牌，写 `sidecar.json` 握手文件。
- 前端 React 通过 `lib/api.ts`（REST，带 Bearer）和 `lib/ai.ts`（自解析 SSE，带 Bearer）访问后端 39 个端点。
- 后端 `main.py:139 create_app` 装配中间件（token 鉴权 + 错误信封），`runtime.py` 装配各 service；分两个 SQLite 库：全局 `studio.db` + 每项目独立库。
- AI 层：统一适配器 `BaseAdapter` → 唯一实现 `OpenAICompatibleAdapter` → `ChatClient` 负责重试/降级 → `AIService` 编排 7 写作操作 + 摘要/大纲。

## 分层与落点

| 层 | 目录 | 关键文件 | 找什么来这 |
|---|---|---|---|
| 入口/中间件 | `backend/app/main.py`、`runtime.py` | `create_app:139`、`TokenMiddleware:31` | 鉴权、错误信封、静态托管 |
| HTTP 路由 | `backend/app/api/routes/` | `ai.py`、`novels.py`、`projects.py` | 端点定义与参数校验 |
| 依赖注入 | `backend/app/api/deps.py` | `get_*_service` | service 怎么拿到的 |
| 业务服务 | `backend/app/services/` | `ai_service.py`(1195)、`novel_service.py` | 编排逻辑、上下文、记账 |
| AI 子系统 | `backend/app/ai/` | `llm/`、`structured.py`、`prompts/` | 适配器/降级/JSON/提示词 |
| DTO | `backend/app/schemas/` | `ai.py`、`novel.py` | 请求响应结构 |
| ORM | `backend/app/models/` | `studio.py`(8 表)、`novel.py`(26 类) | 表结构、关系、mixin |
| 数据访问 | `backend/app/db/` | `session.py`、`migrations.py`、`project_db.py` | 引擎、迁移、每项目库 |
| 横切核心 | `backend/app/core/` | `keystore.py`、`config.py`、`errors.py`、`security.py` | 密钥、配置、错误、鉴权 |
| 前端 UI | `desktop/src/components/`、`pages/` | `editor/ai-panel.tsx`、`novel-editor-page.tsx` | 界面与交互 |
| 前端数据层 | `desktop/src/lib/`、`hooks/` | `api.ts`、`ai.ts`、`use-chapter-draft.ts` | HTTP/SSE/草稿自动保存 |
| 桌面壳 | `desktop/src-tauri/src/` | `sidecar.rs`(965)、`lib.rs` | 窗口、命令、sidecar 生命周期 |

## 跨层约束（动手前必读）

1. **正文用 `<textarea>` 是有意选择**，中文 IME/保真/性能；换 Tiptap 先讨论（`INDEX.md` 硬规则 3）。
2. **数据库改动走 `backend/app/db/migrations.py`**：版本递增 + 迁移前备份 + 拒绝降级（硬规则 2）。
3. **不动用户数据**：`NovelProjects/` 与 `studio.db`/项目库只读或走迁移（硬规则 1）。
4. **生成流用 SSE，任务状态用轮询**，4 个 WS 接口已作废（决策见 `../05_Plan/TaskRegister.md` T-22）。
5. **提示词 DB 优先**：`prompt_templates` 表覆盖代码内置模板（`../../docs/architecture.md`）。
