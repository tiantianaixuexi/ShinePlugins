---
name: files-desktop
description: 前端文件级清单：desktop/src 下 62 个 .ts/.tsx 的归属、行数、导出符号。找前端代码用这页。
status: 结构级（2026-11-16 逐文件取证）
---

# 前端文件级清单（`desktop/src/**/*.ts(x)`，62 个）

> 结构级：只列存在/归属/行数/导出。行号是取证时快照。职责与边界见 `../../docs/api.md`；编辑器深度见 [`02-lifecycle.md`](02-lifecycle.md)；坑见 `../05_Plan/TaskPitfalls.md`。
> `S/` = `desktop/src/`。

## components/editor/（4）

| 文件 | 行数 | 职责 | 导出 |
|---|---:|---|---|
| `S/components/editor/ai-panel.tsx:94` | 586 | AI 面板：7 操作、流式进度、预览/应用/丢弃 | `AIPanel`、`ApplyMode` 重导出 |
| `S/components/editor/chapter-editor.tsx:74` | 179 | 正文编辑区（textarea + 保存指示 + 选区上报） | `ChapterEditor` |
| `S/components/editor/chapter-tree.tsx:82` | 240 | 分卷/章节树：新建/删除/选中 | `ChapterTree` |
| `S/components/editor/version-history-dialog.tsx:35` | 159 | 版本列表/快照/恢复 | `VersionHistoryDialog` |

## components/layout + settings（5）

| 文件 | 行数 | 职责 | 导出 |
|---|---:|---|---|
| `S/components/layout/app-shell.tsx:12` | 47 | 外壳组合 | `AppShell` |
| `S/components/layout/sidebar.tsx:17` | 153 | 导航侧栏 + 计数徽章 | `Sidebar`、`SidebarBadge:146` |
| `S/components/layout/topbar.tsx:14` | 64 | 顶栏标题/路由上下文 | `Topbar` |
| `S/components/layout/status-bar.tsx:14` | 47 | 后端状态栏 | `StatusBar` |
| `S/components/settings/model-config-panel.tsx:111` | 370 | 模型配置增删改与测试 | `ModelConfigPanel` |

## components/ui/（22，shadcn 封装）

`alert-dialog:126`(138) · `badge:40`(40) · `button:55`(55) · `card:75`(75) · `checkbox:31` · `collapsible:19` · `dialog:122`(133) · `dropdown-menu:214`(230) · `input:24` · `label:21` · `popover:44` · `progress:31` · `scroll-area:55` · `select:169`(180) · `separator:28` · `skeleton:15` · `sonner:33` · `switch:31` · `table:93`(102) · `tabs:56` · `textarea:23` · `tooltip:53`
（均在 `S/components/ui/`；导出对应 `Xxx*` 组件族。）

## pages/（9）

| 文件 | 行数 | 职责 | 导出 |
|---|---:|---|---|
| `S/pages/dashboard/dashboard-page.tsx:26` | 273 | 工作台总览与项目列表 | `DashboardPage` |
| `S/pages/errors/not-found-page.tsx:19` | 19 | 404 | `NotFoundPage` |
| `S/pages/novel-editor/novel-editor-page.tsx:335` | 347 | 编辑工作区（树+编辑器+AI 面板+恢复/删除） | `NovelEditorPage`、`NovelEditorByIdPage:343` |
| `S/pages/placeholder/coming-soon-page.tsx:14` | 71 | 占位页（含 `/workflows`） | `ComingSoonPage` |
| `S/pages/projects/project-detail-page.tsx:54` | 237 | 项目详情与统计 | `ProjectDetailPage` |
| `S/pages/projects/project-edit-dialog.tsx:27` | 171 | 项目编辑对话框 | `ProjectEditDialog` |
| `S/pages/projects/project-form-dialog.tsx:78` | 255 | 新建项目对话框 | `ProjectFormDialog`、`NOVEL_TYPES:28` |
| `S/pages/projects/projects-page.tsx:166` | 248 | 项目列表/搜索/操作 | `ProjectsPage` |
| `S/pages/settings/settings-page.tsx:26` | 149 | 设置页 | `SettingsPage` |

## lib/（10）

| 文件 | 行数 | 职责 | 导出 |
|---|---:|---|---|
| `S/lib/ai.ts:44` | 310 | SSE 解析 + 三类流式客户端 | `parseFrame`、`interpretFrame`、`applyStreamOutcome`、`streamAI:216`、`streamSummary:246`、`streamOutline:281` |
| `S/lib/ai.test.ts:47` | 255 | AI 流协议单测（9 例） | — |
| `S/lib/api.ts:161` | 294 | 带 token 的 REST 客户端/错误归一化 | `ApiError:40`、`isUnreachableStatus:75`、`api`、`errorMessage:286` |
| `S/lib/api.test.ts:9` | 37 | 不可达状态单测（4 例） | — |
| `S/lib/sidecar.ts:67` | 96 | sidecar 握手：Tauri 轮询+浏览器回退+缓存 | `resolveSidecar`、`resetSidecarCache:93` |
| `S/lib/sidecar.test.ts:43` | 75 | 握手单测（3 例） | — |
| `S/lib/text-edit.ts:28` | 51 | 纯文本应用（替换选区/追加/全文） | `ApplyMode:7`、`applyText` |
| `S/lib/text-edit.test.ts:8` | 43 | 文本编辑单测（6 例） | — |
| `S/lib/utils.ts:5` | 83 | 格式化/字数/token 工具 | `countWords:60`、`estimateTokens:41`、`formatNumber:10` 等 |
| `S/lib/utils.test.ts:14` | 91 | 工具单测（14 例） | — |

## hooks / stores / types / test（8）

| 文件 | 行数 | 职责 | 导出 |
|---|---:|---|---|
| `S/hooks/use-backend.ts:20` | 73 | 后端健康/系统信息/统计查询 | `useBackendHealth`、`useSystemInfo:42`、`useStudioStats:50` |
| `S/hooks/use-chapter-draft.ts:38` | 148 | 草稿状态机 + 防抖自动保存 + 并发版本 | `SaveState:10`、`ChapterDraft:12`、`useChapterDraft` |
| `S/hooks/use-novel.ts:6` | 110 | 卷/章/版本 Query 与 mutation | `useChapters`、`useChapter`、`useCreateChapter:61`、`useRestoreChapter:99` |
| `S/hooks/use-projects.ts:13` | 67 | 项目 CRUD/复制 | `useProjects`、`useDuplicateProject:59` |
| `S/hooks/use-theme.ts:20` | 38 | 主题切换 | `useTheme` |
| `S/stores/ui.ts:13` | 17 | Zustand 纯视图状态（不落库） | `useUiStore` |
| `S/types/api.ts:9` | 378 | 后端全部 DTO/枚举 | `Chapter:163`、`AIResult:293`、`AIOperation:371` 等 30+ |
| `S/test/setup.ts:1` | 1 | Vitest jest-dom 匹配器 | — |

## config / router / 入口 / 样式（5）

| 文件 | 行数 | 职责 | 导出 |
|---|---:|---|---|
| `S/config/navigation.ts:31` | 154 | 导航项/分组定义与路径反查 | `NAV_ITEMS`、`NAV_GROUPS:145`、`findNavItem:147` |
| `S/router.tsx:19` | 38 | Hash 路由表（自定义协议深链兼容） | `router` |
| `S/main.tsx:28` | 37 | React 挂载/QueryClient/RouterProvider/Toaster | — |
| `S/index.css:1` | 233 | Tailwind v4 +「纸墨」主题变量 | — |
| `S/vite-env.d.ts:3` | 10 | 环境类型声明 | — |

## 统计

`.ts` 20 + `.tsx` 42 = **62**（CSS 另 1）；测试 5 文件 / 36 例（2026-11-16 实测）。
