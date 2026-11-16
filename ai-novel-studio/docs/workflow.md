# 工作流引擎

> **设计完成，尚未实现。**
>
> 本文是设计文档，描述计划 §10 的自动创作引擎**应该**如何工作。截至本文写作时，
> 仓库里**不存在任何工作流代码**：
>
> - `backend/app` 下没有 `tasks/`、`workflows/`、`agents/` 包；
> - `generation_tasks` / `task_logs` 两张表**已建好但没有任何读写方**
>   （`grep` 全仓库，`GenerationTask` 与 `TaskLog` 只出现在 `models/studio.py`
>   和 `models/__init__.py` 的导出里）；
> - 工作流专属的表（`workflows`、`workflow_nodes`、`workflow_edges`、
>   `workflow_runs`、`workflow_node_runs`）**根本不存在**；
> - 前端 `@xyflow/react` 12.12.1 已安装，但 `desktop/src` 里**零引用**；
>   路由 `/workflows` 指向 `ComingSoonPage`。
>
> 所以：**不要把本文任何一段当作「现在就能用」的能力。**

## 1. 两条边界：编辑器是 React Flow，执行器是 Python

工作流系统最容易犯的错误是让前端承担执行职责（在浏览器里按拓扑序跑节点、
调 API、处理重试）。这在本项目里是**明确禁止**的，理由与 `docs/architecture.md` §1
的三条硬边界一致：

| 关注点 | 归属 | 理由 |
|---|---|---|
| 画布交互（拖拽、连线、缩放、参数面板、校验提示） | **React Flow**（`@xyflow/react`） | 只做「图的可视化编辑」，产出是一份 **JSON 图描述** |
| 图的持久化、拓扑校验、调度、重试、日志、断点续跑 | **Python 执行引擎** | 需要事务、需要进程存活、需要访问 SQLite 与模型 |
| 模型调用、嵌入、媒体生成 | **Python 服务层** | 需要 `openai` / `numpy` / `pillow` 等库；前端不持有密钥 |

**严格分离的含义**：

1. 前端**只能**提交「整张图的 JSON」，不能提交「要执行哪个节点」；
2. 执行进度**只能**由后端推送/轮询获得，前端不推断状态；
3. 前端刷新、关闭、崩溃**不影响**正在运行的工作流（后端进程独立存活）；
4. 后端**不假设**前端在线（无人值守的定时工作流必须能跑）。

数据流：

```
React Flow 画布
   │  用户拖拽/连线/填参数
   ▼
节点/边 JSON（{nodes:[{id,type,data,position}], edges:[{source,target}]}）
   │  POST /api/workflows（或 PUT 更新）
   ▼
后端校验（DAG/环检测、必填参数、节点类型白名单）
   │  存 workflow + workflow_nodes + workflow_edges
   ▼
POST /api/workflows/{id}/run
   │  建 workflow_runs 行（PENDING → QUEUED）
   ▼
Python 执行引擎（后台任务，非请求生命周期）
   │  逐节点：置 RUNNING → 调用服务层 → SUCCESS / FAILED / PAUSED
   │  每步写 workflow_node_runs + task_logs
   ▼
前端轮询 / WebSocket（/ws/workflows，未实现）刷新画布状态
```

## 2. 节点类型

节点分四大族，**族内可扩展，族间不互相调用**（retrieval 节点不能调 media 节点，
必须通过显式依赖边传递产物）。

### 2.1 basic（基础）

| 节点 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `start` | — | 触发上下文 | 工作流入口，唯一无入边的节点类型 |
| `end` | 任意 | 终止 | 唯一无出边的节点类型 |
| `text` | 文本模板 | 字符串 | 常量/拼接，用于注入固定提示片段 |
| `condition` | 布尔表达式 | 分支选择 | 求值后只激活一条出边 |
| `merge` | 多路输入 | 合并结果 | 等待所有入边完成（join 语义） |

### 2.2 novel（小说创作）

| 节点 | 对应能力 | 状态 |
|---|---|---|
| `outline.generate` | 生成/扩写大纲（`outlines` 表） | ❌ 未实现 |
| `chapter.generate` | 生成整章正文（`chapters` 表） | ❌ 未实现 |
| `chapter.continue` | 续写（读当前章末尾 + 检索上下文） | ❌ 未实现 |
| `chapter.expand` | 扩写选中段落 | ❌ 未实现 |
| `chapter.rewrite` | 改写（换风格/换视角） | ❌ 未实现 |
| `chapter.polish` | 润色（保持情节，改进文字） | ❌ 未实现 |
| `consistency.check` | 连贯性检查（人物状态/伏笔/时间线冲突） | ❌ 未实现 |
| `memory.update` | 更新 L1–L4 记忆（摘要、状态、关系） | ❌ 未实现 |
| `character.extract` | 从正文抽取人物与状态变化 | ❌ 未实现 |

### 2.3 retrieval（检索）

| 节点 | 对应能力 | 状态 |
|---|---|---|
| `retrieval.search` | 混合检索（见 [rag.md](rag.md) §4） | ❌ 未实现 |
| `retrieval.fts` | 纯 FTS5 检索（降级路径） | ❌ 未实现 |
| `retrieval.vector` | 纯向量检索 | ❌ 未实现 |
| `context.assemble` | 按 token 预算组装上下文（rag.md §5） | ❌ 未实现 |

### 2.4 media（媒体）

| 节点 | 对应能力 | 状态 |
|---|---|---|
| `script.parse` | 小说/剧本转场景结构 | ❌ 未实现 |
| `shot.decompose` | 场景拆镜头 | ❌ 未实现 |
| `image.generate` | 文生图（角色定妆、场景概念图） | ❌ 未实现 |
| `video.generate` | 图生视频/文生视频 | ❌ 未实现 |
| `audio.generate` | TTS 配音 | ❌ 未实现 |
| `subtitle.generate` | 字幕与时间轴对齐 | ❌ 未实现 |
| `render.compose` | FFmpeg 合成成片 | ❌ 未实现 |

**节点契约**（设计约定，尚未落地为代码）：

每个节点必须声明 `inputs` / `outputs`（字段名 + 类型 + 是否必填），
执行引擎据此在**建图时**做静态校验（缺参数直接拒绝保存），
在**运行时**做动态校验（上游产出缺失则把该节点标 `FAILED` 并写明原因）。

## 3. 状态机

### 3.1 工作流运行（`workflow_runs.status`）

```
PENDING ──► QUEUED ──► RUNNING ──► SUCCESS
                         │  │
                         │  └──────► FAILED
                         ├──► PAUSED ──► (resume) ──► RUNNING
                         └──► CANCELLED
```

| 状态 | 含义 | 进入条件 |
|---|---|---|
| `PENDING` | 已创建，尚未入队 | `POST /{id}/run` 刚建记录 |
| `QUEUED` | 在队列里等执行槽 | 调度器取走前 |
| `RUNNING` | 至少有一个节点在执行 | 调度器开始执行 |
| `SUCCESS` | 所有必需节点成功 | 无待执行节点且无失败 |
| `FAILED` | 有节点失败且重试耗尽 | 节点 `FAILED` 且 `attempt >= max_attempts` |
| `PAUSED` | 人为暂停；在跑的节点跑完即停 | `POST /runs/{id}/pause` |
| `CANCELLED` | 人为取消；不再启动新节点 | `POST /runs/{id}/cancel` |

**PAUSED 与 CANCELLED 的区别**：PAUSED 可 `resume`（保留已完成节点的产物，
从断点继续）；CANCELLED 是终态，重启需要新建一次 run。

### 3.2 节点运行（`workflow_node_runs.status`）

```
PENDING ──► RUNNING ──► SUCCESS
               │
               ├──► FAILED ──(retry)──► PENDING
               ├──► SKIPPED        （上游失败/条件未命中）
               └──► CANCELLED
```

每个节点一次尝试一行，还是每次重试一行？——**每次尝试一行**
（`attempt` 列递增），这样 `task_logs` 才能完整还原「第几次为什么失败」。

## 4. 为什么必须支持环与条件，而不是强制 DAG

「工作流 = DAG」是最常见的简化，但它在本项目里**不成立**：

### 4.1 创作本身就是迭代的

真实的长篇创作流程是：

```
写一章 → 检查连贯性 → 发现问题 → 改写 → 再检查 → 通过 → 写下一章
                ↑__________________________________|
```

如果强制 DAG，「检查—改写」这条反馈边就无法表达，用户只能手工重跑，
而这恰恰是最需要自动化的部分。

### 4.2 批量章节生成本质是循环

「把第 1 章到第 300 章都生成一遍」不是 300 个节点，而是**一个 `chapter.generate`
节点 + 一个迭代作用域**。用 DAG 表达要么画 300 个节点（不可维护），
要么在节点内部偷偷循环（把控制流藏进节点，等于没有工作流）。

### 4.3 所以引擎需要的能力

| 能力 | 实现要点 |
|---|---|
| **环检测** | 不是「禁止环」，而是「检测环 + 要求显式的退出条件」。保存时对每个强连通分量做静态分析：必须存在 `condition` 节点能以有限步退出 |
| **条件边** | `condition` 节点的每条出边带 `when` 表达式；求值为假则不激活 |
| **迭代上限** | 每个环必须有 `max_iterations`（默认 100），防止死循环烧钱 |
| **迭代作用域** | `loop` 节点对子图执行 N 次，每次迭代有独立的 `iteration` 上下文 |
| **访问计数** | `workflow_node_runs.iteration` 记录这是第几次执行该节点 |
| **环内状态隔离** | 每次迭代的变量作用域独立，避免上一轮的脏数据污染下一轮 |

### 4.4 与 DAG 的关系

**DAG 是特例，不是通用情况。** 引擎内部用「事件驱动 + 入边计数」而非「拓扑排序」：

- 每个节点维护「未完成的入边集合」；
- 上游成功 → 从下游的集合里移除该边；集合空 → 该节点就绪；
- 环的存在不影响这个模型（迭代时重置集合）；
- 条件未命中的边**直接从未完成集合里移除**（等价于「已完成」）。

这样同一套调度逻辑既能跑 DAG 也能跑带环图，不需要两条代码路径。

## 5. 持久化与断点续跑

### 5.1 表结构（全部**不存在**，需新建）

#### `workflows`（工作流定义）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | VARCHAR(40) PK `wf_*` | — |
| `project_id` | VARCHAR(40) NULL，索引 | 归属项目；NULL = 全局模板 |
| `name` | VARCHAR(200) NOT NULL | 显示名 |
| `description` | TEXT NOT NULL default `''` | — |
| `version` | INTEGER NOT NULL default 1 | 每次保存 +1 |
| `graph` | JSON NOT NULL | 画布全量 JSON（节点/边/视口） |
| `is_template` | BOOLEAN NOT NULL default false | 模板不可直接运行，需先另存 |
| `created_at` / `updated_at` | DATETIME NOT NULL | `TimestampMixin` |
| `row_version` | INTEGER NOT NULL default 1 | 乐观锁（两人同改一张图时 409） |

#### `workflow_runs`（一次运行）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | VARCHAR(40) PK `wfr_*` | — |
| `workflow_id` | VARCHAR(40) NOT NULL，FK→`workflows.id` `CASCADE`，索引 | 用的是哪一版定义 |
| `workflow_version` | INTEGER NOT NULL | **快照**：运行时锁定的定义版本 |
| `project_id` | VARCHAR(40) NULL，索引 | 本次运行作用于哪个项目 |
| `status` | VARCHAR(32) NOT NULL default `pending`，索引 | 见 §3.1 |
| `graph_snapshot` | JSON NOT NULL | 运行时图的完整快照（定义被改也不影响本次） |
| `variables` | JSON NOT NULL default `{}` | 运行级变量（初始章节号、目标字数…） |
| `started_at` / `finished_at` | DATETIME NULL | — |
| `error` | TEXT NULL | 失败原因 |
| `created_at` / `updated_at` | DATETIME NOT NULL | — |

#### `workflow_node_runs`（节点级状态，断点续跑的依据）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | VARCHAR(40) PK `wnr_*` | — |
| `run_id` | VARCHAR(40) NOT NULL，FK→`workflow_runs.id` `CASCADE`，索引 | 属于哪次运行 |
| `node_id` | VARCHAR(64) NOT NULL | 图里的节点 id（非数据库 id） |
| `node_type` | VARCHAR(64) NOT NULL | 节点类型（冗余，便于统计） |
| `attempt` | INTEGER NOT NULL default 0 | 第几次尝试 |
| `iteration` | INTEGER NOT NULL default 0 | 环内第几轮 |
| `status` | VARCHAR(32) NOT NULL default `pending`，索引 | 见 §3.2 |
| `input` | JSON NOT NULL default `{}` | 本次实际入参（可复现） |
| `output` | JSON NOT NULL default `{}` | 本次产出 |
| `error` | TEXT NULL | — |
| `task_id` | VARCHAR(40) NULL，索引 | **关联 `generation_tasks.id`**（耗时任务的实际执行者） |
| `started_at` / `finished_at` | DATETIME NULL | — |
| `created_at` / `updated_at` | DATETIME NOT NULL | — |

唯一约束：`(run_id, node_id, iteration, attempt)` —— 同一轮次同一次尝试只有一行。

### 5.2 为什么重启能续跑

进程重启后：

```
Runtime.start()
  ├─ 扫描 workflow_runs WHERE status IN ('QUEUED','RUNNING')
  ├─ 对每条：
  │    ├─ 读 graph_snapshot（不是读 workflows 表——定义可能已改）
  │    ├─ 读 workflow_node_runs 里 status='SUCCESS' 的节点 → 直接复用 output
  │    ├─ 把 status='RUNNING' 的节点标 FAILED（进程死了，这次尝试作废）
  │    └─ 从「入边集合」里扣除已完成的边，继续调度
  └─ 恢复 QUEUED
```

**关键设计**：`graph_snapshot` 而不是 `workflow_id` 关联。如果运行时读取的是
「当前定义」，那么用户在运行中改了图，重启后会按新图续跑——旧节点的产物可能对不上新节点。
快照保证「一次运行 = 一份不可变的定义」。

### 5.3 断点的粒度

- **节点级**：完成的节点不重复执行（这是「断点续跑」的核心）；
- **节点内**：不支持。`chapter.generate` 生成到一半被杀，重启后整节点重跑
  （但它必须幂等，见 §6）；
- **代价**：重跑一个昂贵节点会重复付费。所以 §6 的幂等键是必需项，不是优化项。

## 6. 幂等：让重跑不重复计费

### 6.1 问题

媒体生成是**按次收费**的（文生图、文生视频、TTS）。场景：

1. 节点调用第三方 API，图片生成成功；
2. 回写数据库前进程崩溃；
3. 重启后节点被重跑 → **再生成一次 → 再付一次费**；
4. 用户拿到两张一样的图，账单翻倍。

这是不足清单里点名的「重复计费」风险（`AI_Novel_Studio_Plan_Gaps.md` §六）。

### 6.2 `generation_tasks.idempotency_key`

现有 `generation_tasks` 表已有这一列：

```sql
idempotency_key VARCHAR(128) NULL,   -- 索引
```

设计上它是**幂等键**，不是唯一约束（允许多行同键以便审计），但执行前**必须先查**：

```
执行前：
  SELECT id, status, result FROM generation_tasks
   WHERE idempotency_key = :key AND status = 'done' LIMIT 1
    │
    ├─ 命中 → 直接复用 result，跳到「写回结果」（不调用第三方）
    └─ 未命中 → 调用第三方
```

### 6.3 键的构造

键必须**确定性**（同一逻辑工作，无论重跑多少次都得到同一个键）：

```
idempotency_key = sha256(
    project_id
  + workflow_run_id
  + node_id
  + iteration
  + canonical_json(node.input)        # 键排序后的 JSON，消除字段顺序差异
) 取前 128 字符
```

**不含**：时间戳、随机数、`attempt`。含了就失去幂等性。

**含 `node.input`**：同一个节点在不同输入下是不同的工作，必须分别计费。
比如「生成第 12 章的章纲」与「生成第 13 章的章纲」是两个键。

### 6.4 局限（诚实说明）

幂等键只能防「同一进程重跑」。它**不能**防：

- 第三方服务自己重复扣费（需要在第三方侧查任务状态）；
- 用户手工重跑同一节点但**故意**想生成不同结果（此时应提供 `force_refresh` 参数
  显式改变输入，从而改变键）。

## 7. 优先级：交互任务高于批量媒体

### 7.1 问题

视频生成是**慢且贵**的（几分钟到几十分钟，单价高）。如果一个批量媒体工作流
占满执行槽，用户在编辑器里点「续写」会排队等半小时——这是不可接受的。

### 7.2 `generation_tasks.priority`

现有列：`priority INTEGER NOT NULL default 0`（**索引**）。
数值约定：

| 优先级 | 场景 | 说明 |
|---|---|---|
| `100` | 交互式写作（续写/扩写/润色/检查） | 用户正在等，秒级响应 |
| `50` | 章节摘要 / 记忆更新 | 后台但影响后续检索质量 |
| `0` | 批量媒体生成（图片/视频/TTS） | 可长时间排队 |
| `-10` | 索引重建、全量嵌入 | 最不紧急 |

### 7.3 调度规则

1. **单队列 + 优先级出队**：`ORDER BY priority DESC, created_at ASC`；
2. **交互任务抢占**：交互任务到达时，若有媒体任务在跑，**不中断**它（已付费/已耗时），
   但**不再启动新的媒体任务**，把槽让给交互任务；
3. **并发上限**：媒体任务的并发数应可配（第三方 API 有 QPS 限制），
   交互任务不受此限；
4. **饿死保护**：低优先级任务等待超过阈值时提升有效优先级，避免永远排不上。

### 7.4 当前状态

`generation_tasks.priority` 列已存在且有索引，但**没有任何代码读写它**
（无 worker、无入队逻辑）。所以「优先级」目前是一个**预留字段**。

## 8. 与现有代码的边界

| 能力 | 表/列 | 代码 |
|---|---|---|
| 任务记录（通用） | ✅ `generation_tasks`（35 列，含 `priority`、`idempotency_key`、`attempt`、`cost`） | ❌ 无读写方 |
| 任务日志 | ✅ `task_logs`（`task_id` FK CASCADE、`level`、`message`、`context` JSON） | ❌ 无读写方 |
| 工作流定义 | ❌ 表不存在 | ❌ |
| 工作流运行 | ❌ 表不存在 | ❌ |
| 节点运行 | ❌ 表不存在 | ❌ |
| 前端画布 | ✅ `@xyflow/react` 12.12.1 已安装 | ❌ 零引用；`/workflows` 路由指向占位页 |
| Agent 模型绑定 | ✅ `agent_configs`（`agent_type`、`model_config_id`、`temperature`、`system_prompt`、`params`） | ❌ 无 API、无读取方 |
| Prompt 模板版本化 | ✅ `prompt_templates`（`key`、`version`、`content`、`variables`） | ❌ 无 API、无读取方 |
| 模型调用 | ✅ `model_configs`（含 `fallback_ids`、`supports_*`、`context_window`） | ❌ 无适配器 |

**关于 `generation_tasks` 的语义重叠**：它是为「单次 AI 或媒体工作」设计的通用任务表
（`kind`、`payload`、`result`、`progress`、`model_config_id`、`prompt_version`、
`input_tokens`/`output_tokens`/`cost`）。设计上工作流节点**不直接**做重活，
而是**创建一个 `generation_tasks` 行**并把它记在 `workflow_node_runs.task_id` 上。
这样：

- 单个节点的重试/观测复用现有任务表（不重复造轮子）；
- 工作流层只关心「编排」，不关心「怎么调模型」；
- 任务表能被非工作流场景（编辑器里单次续写）直接复用。

**`task_logs` 与 `retrieval_logs` 的分工**：前者是「任务执行日志」（给人看，
按 `task_id` 归属），后者是「检索审计」（给检索质量评估用，见 [rag.md](rag.md) §8）。
两者不互相替代。

## 9. 验收标准（设计目标，非当前状态）

按计划 §5（阶段 4）与不足清单 §六：

| # | 判据 | 当前 |
|---|---|---|
| 1 | 跑一条工作流：大纲生成 → 章节生成 → 连贯性检查 → 记忆更新，全链路成功 | ❌ |
| 2 | 中途暂停再恢复，结果与不中断一致 | ❌ |
| 3 | 运行中杀掉进程，重启后从断点继续，已完成节点不重复执行 | ❌ |
| 4 | 媒体节点重跑不重复扣费（幂等键命中） | ❌ |
| 5 | 交互式续写在批量视频任务积压时仍秒级响应 | ❌ |
| 6 | 画布上的环（检查↔改写）能配置退出条件并正确终止 | ❌ |
| 7 | 节点失败有重试、有日志、有明确的失败原因 | ❌ |

**结论**：设计完成，代码零实现。`generation_tasks` / `task_logs` 是唯二的现成基建，
而它们目前也没有任何调用方。