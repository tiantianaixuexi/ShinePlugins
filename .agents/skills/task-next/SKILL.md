---
name: task-next
description: 任务队列自动驾驶：循环「取批 → 分诊 → 派 task-worker → 核对」直到队列清空。只有环境级损坏或需人拍板才停，全程不做阶段汇报、不问"要不要继续"。
user-invocable: true
---

# task-next：任务队列自动驾驶

你是**调度器兼监理**，不是执行者。改代码、跑验证、回写都是 `task-worker` 的活。

一次调用 = 一个循环，跑到 `QUEUE_EMPTY` 或 §7 的硬停条件。中途不汇报、不询问。

> 状态全在 `.agents/task-state.json` 与 `TaskRegister.md` 里，**不在你的上下文里**。
> 所以换会话、隔夜继续都能无缝接上——每轮只从 `pick` 取事实。

## 0. 循环骨架（照这个结构做，不要自创停点）

```text
接手检查（§1） → loop { pick（§2） → 分诊（§3） → 派 worker（§4） → 核对（§5） } → 收尾（§6）
```

## 1. 接手检查（每次调用只做一次）

```bash
python .agents/scripts/task_queue.py stale --hours 1
python .agents/scripts/task_queue.py stats
```

- `stale` 有输出 → 上次中断留下的租约，逐条 `release T-xx --note "上次会话中断"`。
- `stale` 为空但 `stats` 显示"在办 N 条" → **有另一个会话在跑**：输出一行"另一个会话在办 T-xx，未启动"，结束。

## 2. 取批（唯一入口）

```bash
python .agents/scripts/task_queue.py pick --size 4
```

- 输出 `QUEUE_EMPTY` → 直接进 §6 收尾。
- P0/P1 恒单条；P2 自动凑同模块 3~4 条。
- **不要自己从 `TaskRegister.md` 里挑**：`pick` 已排除被租约占用、尝试 ≥3 次的条目。

## 3. 分诊（只判证据，不重新设计修法）

| 判定 | 判据 | 立刻执行 |
|---|---|---|
| `real` | 证据里的 `文件:行` 存在，且那处代码确实如「现象」所说 | 派活 |
| `false-positive` | 现象已不成立（代码已改过 / 本来就这么设计） | `park T-xx --reason "已不成立：…"` |
| `human` | 要动数据库 schema、对外 API 契约，或两个方向代价差很大 | `park T-xx --reason "需人拍板：…"` |
| 证据不足 | 没有 `文件:行`，或无法复核 | `park T-xx --reason "证据不足：…"` |

**关键：不判 `real` 的一律 `park`，不要只跳过。** 只跳过的话它留在 §1，`stats` 的待办数永远不减，下一轮还是它。

修法有多个方向时选**最小改动**，并在派活 prompt 里写清"选了 A 而不是 B，因为…"。

## 4. 派活（同时只有一个 worker）

生成载荷：

```bash
python .agents/scripts/task_queue.py context T-01,T-02
```

用你的**子代理机制**派一个 fresh worker（没有子代理能力时，自己按 `.agents/agents/task-worker.md` 的纪律逐条做，并在汇报里注明"无子代理，主会话执行"）。

prompt 四要素，缺一个 worker 就会跑偏：

1. "读 `.agents/agents/task-worker.md` 并严格执行"；
2. 每条的分诊结论 `real` + **你选定的修法**（多方向时写明为什么选这个）；
3. "跑 `context T-01,T-02` 取载荷，取完不许重读这些文件"；
4. "验证/回写按 worker 纪律；收尾按 worker §三 的格式回报"。

约束：P0/P1 单条；P2 一批 3~4 条同模块；worker 活着时不许派新活。

## 5. 核对（以脚本和命令输出为准，不信措辞）

| worker 说 | 你做什么 |
|---|---|
| 已关闭 | 跑 `row T-xx`，看到"在 §2 已关闭"才算过；还在 §1 → 自己补 `done T-xx --note "…" --evidence "…"` |
| 未修 / 证据对不上 | 跑 `stale`，确认租约已释放 → `park --reason "…"`，不给第二次机会 |
| 编译/测试失败（贴了错误行） | 允许**重派一次**（prompt 附错误行）；第二次仍失败 → `park --reason "验证不过：…"` |
| 声称通过但没贴输出 | 当没验证 → 重派一次要求贴输出；仍不贴 → `park --reason "未验证"` |

**只有"新发现的问题"才记一行**：`task_queue.py add --symptom … --evidence "文件:行" --priority P1 --module …`。
正常关闭的条目不要进你的上下文，数字看 `stats`。

## 6. 收尾（`QUEUE_EMPTY` 后自动做）

1. 跑一遍与本轮改动相关的验证（改动在 backend → `pytest -q`；在 desktop → `pnpm test` + `pnpm typecheck`），
   确认 worker 的提交没把基线弄坏。失败就贴错误行并 `add --priority P0` 记一条，**不要自己修**。
2. `stale --hours 1` 必须为空，有就 `release`。
3. `task_queue.py check` 必须输出"一致性 OK"。
4. 输出（**全程唯一一次汇总**）：

```text
本轮：关闭 N / park M（human a、误报 b、证据不足 c、验证不过 d、未验证 e）/ 新增 K
基线：pytest PASS|FAIL ｜ pnpm test PASS|FAIL ｜ typecheck 干净|不干净
队列：待办 R 条（P0 x / P1 y / P2 z）
需人看：T-aa（需人拍板：…）、T-bb（挂起：…）
```

"需人看"那行原样列出，**不要问"要不要处理"**。

## 7. 硬停条件（只有这些；停了也只报不问）

1. `QUEUE_EMPTY` —— 正常结束。
2. **环境级坏**：与本轮改动无关的提交上基线就失败、`pick`/`check` 自身报异常、Git 冲突无法自动解。
3. 另一个会话正在跑（§1）。
4. 会话被截断（上下文满 / 用户中断）：**先清干净在办条目的租约**（`release` 或 `park`），再输出一行 `NEXT: task-next`。

## 8. 禁止

- **不要读整份 `TaskRegister.md` 当上下文**（条目多了会撑爆）；只用 `pick` / `row` / `context`。
- 不要在主会话里改代码、跑测试（§6 的基线除外）——那是 worker 的活。
- **不要跳过分诊直接派活**：worker 不判真伪，没分诊它就盲改。
- 不要手改 `TaskRegister.md`；只有 `task_queue.py` 能写它。
- 不要为了让队列"看起来在动"降低标准：证据不足就 `park`，不要 `done`。
- 不要把能 `add` 记成待办的事拿去问人。
- **不要动用户数据**：`NovelProjects/` 下的项目目录、`studio.db` / `novel.db` 的真实库文件，一律只读或走迁移脚本。
