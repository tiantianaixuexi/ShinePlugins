---
name: memory-index
description: 重建/增量更新会话记忆索引并报告统计（memsearch index + stats）。
---

执行步骤：

1. 增量索引：
   ```bash
   memsearch index .memsearch/memory
   ```
2. 统计：
   ```bash
   memsearch stats
   ```
3. 若用户明确要求"重建/全量"，才用：
   ```bash
   memsearch reset --yes
   memsearch index .memsearch/memory --force
   ```
   （md 是唯一真源，reset 安全；但先确认当前 collection 是 `novelstudio_memory`。）
4. 报告要给数字：本次新索引多少 chunk、当前总量多少、collection 名是什么。
5. 常见异常与处理：
   - `Collection 'memsearch_chunks' does not exist`：说明在错误的 collection 上查（项目配置没被读到）→ 检查 `.memsearch.toml` 是否存在、当前工作目录是不是仓库根。
   - 首次运行很慢：正在下载约 560 MB 的 `gpahal/bge-m3-onnx-int8`，告知用户等待，不要中断。
   - `memsearch` 命令找不到：`uv tool list` 确认，必要时 `uv tool install "memsearch[onnx]"`。
