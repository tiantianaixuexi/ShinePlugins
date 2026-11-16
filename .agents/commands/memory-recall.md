---
name: memory-recall
description: 按自然语言问题召回本项目的会话记忆（memsearch search），带来源与行号输出，不做推测。
---

用户想回忆过去的会话内容。参数 = 查询语句（可能为空，为空时用最近的对话主题推断）。

执行步骤：

1. 先确认索引非空：`memsearch stats`。若报 `Collection ... does not exist`，转去执行 `commands/memory-index.md` 的步骤后继续。
2. 检索：
   ```bash
   memsearch search "<查询>" -k 5
   ```
   需要限定时间/来源时加 `--source-prefix .memsearch/memory/YYYY-MM`；需要精确字段时加 `--json-output`。
3. 结果被截断或需要上下文时，对目标 chunk 执行 `memsearch expand <chunk_hash>`。
4. 回答要求：
   - 每条结论后标注来源文件与标题（如 `.memsearch/memory/2026-11-12.md` › "CodeBuddy 侧接入 memsearch"）；
   - **只陈述检索结果里真的写着的内容**，不要用工程常识补齐；
   - 检索结果为空或 top-1 分数很低（<0.6）时，直接说"记忆里没有相关记录"，并建议用户下一次用 `/memory-save` 记录；
   - 不要用绝对分数阈值判断相关性（同领域不同主题的分数只差 0.01~0.02）。

不要顺手修改任何记忆文件；本命令只读。
