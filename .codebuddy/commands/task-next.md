---
name: task-next
description: 任务队列自动驾驶：从 TaskRegister 取批、分诊、派 task-worker、核对，跑到队列清空。
---

执行 `.agents/skills/task-next/SKILL.md` 的流程。参数 = 本轮最多跑几条（默认不设上限，跑到 QUEUE_EMPTY）。
