---
name: task-next
description: 任务队列自动驾驶：循环「取批 → 分诊 → 派 task-worker → 核对」直到队列清空。用户说「跑任务队列 / 接着做 / 把待办清掉」时使用。
---

本技能正文（唯一真源，工具无关）在：

`.agents/skills/task-next/SKILL.md`

立即读取该文件并严格执行。执行体见 `.agents/agents/task-worker.md`，
状态机脚本为 `.agents/scripts/task_queue.py`。

> 本文件是指针。改规则只改 `.agents/`，不要在这里写第二份正文。
