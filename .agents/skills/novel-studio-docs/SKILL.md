---
name: novel-studio-docs
description: Use the AI Novel Studio project's documentation index to navigate its FastAPI backend, React/Tauri desktop client, SQLite schema, and verification commands. Applies to work in the ai-novel-studio repository.
---

# AI Novel Studio 文档导航

在处理本仓库的代码、架构、数据库、API 或验证任务时，先读 `ai-novel-studio/KnowledgeBase/INDEX.md`——它是**唯一入口**，同时索引 `docs/` 详版层（架构 / API / 数据库 / RAG / 工作流 / 开发计划）。按任务选择相关页，不要凭记忆回答「某功能在哪 / 某字段叫什么」。

规则：

- 不要在 `docs/` 下新建 README/INDEX，不要建第二套索引；一次性产物放 `docs/archive/<年-月>/` 并标注「历史快照，非现状」。
- 文档可能落后于代码：作出具体判断前先核对当前实现；发现不符**以代码为准并改文档**。
- 改完代码按 `INDEX.md` 的「验证」表跑对应命令；没贴实际输出就别说「验证通过」。
- **用户数据不可破坏**：不改数据库 schema 语义、不做破坏性迁移、不动数据目录下的用户项目。这条优先于其它一切约定。
