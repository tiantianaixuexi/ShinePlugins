---
name: codemap-index
description: 代码地图分区入口：目录→职责→关键文件，文件级清单覆盖 backend/desktop/tauri。回答"某功能/某文件在哪"。
status: 现行（2026-11-16 逐目录取证）
---

# 代码地图（`01_CodeMap/`）

> 导航层（文件级清单 + 结论 + 落点），不是详版。字段全表/完整推导进 `../../docs/`。
> 事实型文档：缺陷只写 `→ DEF-xx`，未实现功能只写 `→ T-xx`。

## 分册

| 文件 | 回答的问题 | 覆盖范围 |
|---|---|---|
| [`01-map.md`](01-map.md) | 目录→职责→关键文件（按层的总图） | 全项目 |
| [`02-lifecycle.md`](02-lifecycle.md) | sidecar 拉起、请求流、AI 流、保存链路 | 跨层调用链 |
| [`10-files-backend.md`](10-files-backend.md) | 后端每个 .py 在哪、归谁、关键符号 | 56 文件（逐文件，结构级） |
| [`11-files-desktop.md`](11-files-desktop.md) | 前端每个 .ts/.tsx 在哪、归谁 | 62 文件（逐文件，结构级） |
| [`12-files-tauri.md`](12-files-tauri.md) | Rust 壳每个 .rs 与 sidecar 生命周期 | 7 文件（逐文件，结构级） |

## 覆盖级别（全库统一，见 `INDEX.md`）

| 级别 | 含义 | 允许写什么 |
|---|---|---|
| 逐行 | 人工逐行读过 | 实现细节、边界行为、副作用 |
| 部分 | 只读声明面/骨架 | 只写接口契约 |
| 结构级 | 机器/取证提取的文件清单与顶层符号 | 只写"这文件存在、归哪、导出什么"，**不得**写职责行为结论 |

本分区的文件清单均为**结构级**；`02-lifecycle.md` 中带 `文件:行` 的调用链为**部分**级取证结论。

## 什么时候读哪页

| 任务 | 读 |
|---|---|
| 找某个类/功能在哪 | 本页 → 对应文件清单 |
| 改 AI 适配器/提示词/结构化输出 | `10-files-backend.md` + `../../docs/architecture.md` |
| 改编辑器自动保存/AI 面板 | `11-files-desktop.md` + `02-lifecycle.md` |
| 改 sidecar 拉起/端口/进程回收 | `12-files-tauri.md` |
| 新代码放哪层、能不能跨层 | `INDEX.md` 硬规则 + `../../docs/architecture.md` |
| 动手前有哪些坑、会不会撞车 | `../05_Plan/TaskPitfalls.md` |
