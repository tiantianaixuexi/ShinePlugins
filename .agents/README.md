# `.agents/` —— 工具无关的 agent 资源

这里的文件**不绑定任何一家工具**。任何支持 Agent Skills（`SKILL.md`）或"读 `AGENTS.md` + 执行命令"的
agent 都能直接用：Claude Code / Codex / DSH / CodeBuddy / Cursor 等。

## 布局

```
.agents/
├── skills/
│   ├── memsearch/SKILL.md            ← 会话记忆正文（唯一真源）
│   │   ├── references/cli.md          CLI 全量参数 + 实测坑
│   │   └── scripts/                   capture.py / recall.py / _common.py / _dsh_session.py
│   ├── novel-studio-docs/SKILL.md     ← 工程文档导航正文（唯一真源）
│   └── task-next/SKILL.md             ← 任务队列调度器正文（唯一真源）
├── agents/
│   └── task-worker.md                 ← 任务执行体纪律（唯一真源）
├── commands/                          ← 斜杠命令的步骤正文
│   └── memory-{recall,save,index,doctor}.md
├── scripts/
│   └── task_queue.py                  ← 任务账本状态机（唯一允许写 TaskRegister.md 的程序）
├── hooks/
│   └── claude-hooks.json              ← Stop / UserPromptSubmit 事件配置样例
└── task-state.json                    ← 任务租约/尝试次数（运行时生成，别手改）
```

**规则：正文只写在这里。** 各工具自己的入口目录（`.codebuddy/`、`.claude/`、`.codex/` …）只放**指针**，
写一句"去读 `.agents/skills/<名>/SKILL.md`"。复制正文 = 早晚分叉。

## 各工具怎么接

### 技能（`.agents/skills/`）

| 工具 | 入口 | 做法 |
|---|---|---|
| Claude Code | `.claude/skills/<名>/SKILL.md` | 放指针文件即可（已在本仓库验证：指针被当作技能加载） |
| CodeBuddy | `.codebuddy/skills/<名>/SKILL.md` | 同上，已是本仓库现状 |
| Codex / 其他 | 按该工具的 skills 目录约定 | 同样放指针 |
| DSH | 直接读 `.agents/skills/` | 无需镜像 |

### 命令（`.agents/commands/`）

| 工具 | 入口 | 做法 |
|---|---|---|
| CodeBuddy | `.codebuddy/commands/<名>.md` | 已建 4 个指针，正文在 `.agents/commands/` |
| Claude Code | `.claude/commands/<名>.md` | 同样放指针 |
| 无命令机制的工具 | —— | 直接对 agent 说「按 `.agents/commands/memory-save.md` 做」 |

### Hook（会话结束自动落盘，可选）

脚本是**工具无关**的：从 stdin 读事件 JSON，往 stdout 打一个 `{}`，**永远 exit 0**。
各工具只负责把 Stop 事件接上它。

| 工具 | 做法 | 验证状态 |
|---|---|---|
| Claude Code | 把 `.agents/hooks/claude-hooks.json` 的 `hooks` 键并进 `.claude/settings.json` | 配置格式同上游，未在本机实测 |
| CodeBuddy | 需在 `.codebuddy/settings.json` 里注册 hooks（或用插件机制）；本工作区**未配置** | 未验证 |
| DSH | 需挂 `@deepseek-ai/dsh-hooks-claude-code` 桥，脚本会自动走 zstd 日志分支 | 脚本逻辑已具备，未验证 |

没挂之前**不影响使用**，只是少了自动落盘：会话收尾手动走 `.agents/commands/memory-save.md`。

手工验证脚本能不能跑（不依赖任何 hook 注册）：

```powershell
Set-Location e:\ShinePlugins
python .agents\skills\memsearch\scripts\capture.py --selftest
```

## 任务队列（task-next）

三层分工，缺一层跑不起来：

| 层 | 文件 | 职责 |
|---|---|---|
| 账本 | `ai-novel-studio/KnowledgeBase/05_Plan/TaskRegister.md` | `T-xx` 唯一真源，**只允许脚本写** |
| 状态机 | `scripts/task_queue.py` | `pick`/`claim`/`done`/`park`/`release`/`stale`/`check` + `.agents/task-state.json` 租约 |
| 流程 | `skills/task-next/SKILL.md`（调度器）+ `agents/task-worker.md`（执行体） | 取批 → 分诊 → 派活 → 核对 |

```bash
python .agents/scripts/task_queue.py stats      # 队列概况
python .agents/scripts/task_queue.py pick        # 取一批（已排除租约/尝试≥3）
python .agents/scripts/task_queue.py context T-01,T-02   # 生成 worker 载荷
python .agents/scripts/task_queue.py check       # 账本与状态文件一致性
```

设计要点（照抄了 ShineEngine 的教训）：

- **状态只在脚本里**，不在会话上下文里 → 换会话、隔夜都能续跑。
- **必须 `park` 而不是"跳过"**：不判 `real` 的条目只跳过会一直占着队头。
- **worker 不判真伪**：分诊是调度器的活，worker 只在"证据对不上"时 `release`。
- **同时只跑一个 worker**，并行会互相踩文件。

## 与 `AGENTS.md` 的关系

仓库根 `AGENTS.md` 是**每轮都该在上下文里的常驻约定**（验证命令、目录边界、硬规则），
它只放"不知道就会踩坑"的东西，细节链接到 `ai-novel-studio/KnowledgeBase/INDEX.md` 与本目录。
