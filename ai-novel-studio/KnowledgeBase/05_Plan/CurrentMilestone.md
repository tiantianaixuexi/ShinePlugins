---
name: current-milestone
description: 当前里程碑与验收判据。回答"下一步做什么、做到什么算完"。
status: 现行（里程碑切换时整篇重写）
---

# 当前里程碑：阶段 2 收口

- 起点：2026-11-16
- 状态取值见 [`README.md`](README.md)

## 为什么是这一步

阶段 2 的编辑器链路早已可用，AI 层也已落地（适配器 / 流式 / 提示词 / 记账 / 前端面板），
但**记忆与血缘是断的**：`chapter_summaries` 只读不写（前情提要恒为空）、AI 产出被采纳后记成
`source=user`（血缘丢失）、`agent_configs` 与 `outlines` 是死表。这三处不补，"AI 写长篇"这个
卖点无法自证，后面阶段 3 的 RAG 也没有可复用的摘要管道。

## 本轮范围（只做 P0）

| 任务 | 一句话 | 完成标志 |
|---|---|---|
| `T-01` | `chapter_summaries` 写入方 | 保存章节后表里有行，`_recent_summaries` 非空 |
| `T-02` | 采纳 AI 结果写 `source="ai"` + `task_id` | 版本列表出现 `source=ai` 的条目 |
| `T-03` | 结构化输出（JSON 模式 + 解析 + 一次修复） | 新测试覆盖解析成功与降级路径 |
| `T-04` | `outlines` 落库 | 生成大纲后 `outlines` 有行 |
| `T-05` | `PromptService` 测试 + `PATCH` 升版端点 | `GET /prompts` 出现 `version=2` |
| `T-06` | 主备降级补测试 | 主模型 5xx → 备模型成功的用例通过 |

## 验收判据（全部可执行）

| # | 判据 | 期望 |
|---|---|---|
| ① | `pytest -q`（backend） | 全绿，且新增用例数 ≥ 8 |
| ② | `pnpm test` + `pnpm typecheck`（desktop） | 全绿 / 无输出 |
| ③ | `scripts/smoke_api.py` | `SMOKE PASSED: all checks green` |
| ④ | 手工：写一章 → 关窗重开 | `chapter_summaries` 有该章一行 |
| ⑤ | 手工：AI 面板生成 → 应用 | `chapter_versions` 有 `source=ai` 行且带 `task_id` |

## 明确不在本轮

- 阶段 3 的检索与向量（`T-11`）：需要先有摘要管道，别提前做。
- 打包、i18n、自动更新：阶段 7 / 之后。
