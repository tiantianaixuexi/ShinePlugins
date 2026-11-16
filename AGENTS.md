# 本项目

AI Novel Studio：Tauri 2 + React 19 桌面端，FastAPI + SQLite sidecar，做 AI 长篇小说创作。
代码在 `ai-novel-studio/`。当前进度：阶段 1 完成，**阶段 2 基本完成**（编辑器链路 + 模型配置 + AI 写作 7 操作 + 流式 AI 面板；TXT/DOCX 导入导出未做），
阶段 3（长篇记忆 RAG）未开工。详见 `ai-novel-studio/docs/development-plan.md`。

本文件只放"不知道就会踩坑"的常驻约定；技术细节见 `ai-novel-studio/KnowledgeBase/INDEX.md`（**文档唯一入口**）。

# 验证（改完必须跑，期望值写死）

| 命令（cwd） | 期望 |
|---|---|
| `backend\.venv\Scripts\python.exe -m pytest -q`（`ai-novel-studio/backend`） | 全绿 |
| `backend\.venv\Scripts\python.exe scripts\smoke_api.py`（`ai-novel-studio`） | `SMOKE PASSED: all checks green` |
| `pnpm test`（`ai-novel-studio/desktop`） | `29 passed (29)` |
| `pnpm typecheck`（`ai-novel-studio/desktop`） | 无输出 |
| `pnpm build`（`ai-novel-studio/desktop`） | `✓ built`，产出 `dist/` |
| `cargo check`（`ai-novel-studio/desktop/src-tauri`） | `Finished`，无 error |

没贴实际输出就别说"验证通过"；跑不了就写"无法验证 + 原因"。

# 硬规则

1. **用户数据不可破坏。** 小说数据是用户资产：不改 schema 语义、不做破坏性迁移、不动数据目录下的用户项目。
   这条优先于其它一切约定（上游参考项目 ShineEngine 的"开发期允许破坏性升级"在这里**不适用**）。
2. **数据库改动必须走 `backend/app/db/migrations.py`**：版本号递增 + 迁移前在线备份 + 拒绝降级。
3. **前端编辑器用 `<textarea>` 是有意选择**（保真 / 中文 IME / 性能），理由见 `development-plan.md` §3.3。
   要换 Tiptap 先讨论，不要顺手替换。
4. **只维护一套文档索引**：`ai-novel-studio/KnowledgeBase/INDEX.md`。不要在 `docs/` 下另建 README/INDEX。
5. **正文只写 `.agents/`**：`.codebuddy/` 下的 skills/commands 只放指针，不复制正文。
6. 不要删除 `.codebuddy/`（AI 会话数据）与 `.agents/`。

# 记忆分工

| 内容 | 放哪 |
|---|---|
| 工程事实（代码在哪、接口、表结构、怎么跑） | `ai-novel-studio/KnowledgeBase/` + `ai-novel-studio/docs/` |
| 决策 / 踩坑 / 进度（"为什么这么改"） | `.memsearch/memory/YYYY-MM-DD.md`（走 `.agents/commands/memory-save.md`） |
| 跨轮协作习惯 | 工具自带的 project memory |

会话收尾：有决策或踩坑时**主动落一条**（Stop hook 默认为挂，别假设自动写）。

# 常用入口

- 文档索引：`ai-novel-studio/KnowledgeBase/INDEX.md`
- **实现状态（别信开发计划，信这个）**：`ai-novel-studio/KnowledgeBase/05_Plan/CurrentStatus.md`
- 当前里程碑与验收判据：`ai-novel-studio/KnowledgeBase/05_Plan/CurrentMilestone.md`
- 任务账本 `T-xx`：`ai-novel-studio/KnowledgeBase/05_Plan/TaskRegister.md`
- 计划缺陷清单（P0/P1/P2）：`AI_Novel_Studio_Plan_Gaps.md`
- agent 资源（技能/命令/脚本/hook）：`.agents/README.md`

# 任务队列

待办都在 `TaskRegister.md`，通过脚本操作，**不要手改**：

```bash
python .agents/scripts/task_queue.py stats          # 队列概况
python .agents/scripts/task_queue.py pick           # 取一批
python .agents/scripts/task_queue.py row T-01       # 看单条
```

要连续推进待办就说 `/task-next`（流程见 `.agents/skills/task-next/SKILL.md`）。
`docs/development-plan.md` 已于 2026-11-16 按代码重写；判断"做完没有"仍以 `CurrentStatus.md` 为准。
