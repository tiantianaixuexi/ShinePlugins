---
name: memory-doctor
description: 自检 memsearch 记忆层是否可用（CLI、配置、collection、索引、模型缓存、hook 脚本），输出问题定位表。
---

逐项检查并把结果整理成表格报给用户。**只做检查，不擅自修改配置。**

```powershell
Set-Location <工作区根>
memsearch --version
memsearch config list
memsearch stats
Test-Path .memsearch.toml
Get-ChildItem .memsearch\memory -File
Get-ChildItem "$env:USERPROFILE\.cache\huggingface\hub" -Directory -Filter "models--gpahal--bge-m3-onnx-int8"
python .agents\skills\memsearch\scripts\capture.py --selftest
python -c "import json;json.load(open(r'.agents/hooks/claude-hooks.json',encoding='utf-8'));print('hooks.json OK')"
```

判定标准：

| 检查项 | 通过 | 不通过时的结论与建议 |
|---|---|---|
| `memsearch --version` | `0.4.23` 或更高 | 未安装：`uv tool install "memsearch[onnx]"` |
| `config list` 的 `milvus.collection` | `novelstudio_memory` | 项目 `.memsearch.toml` 没被读到 → 确认在工作区根 `e:/ShinePlugins` 执行 |
| `stats` | 输出 `Total indexed chunks: N`（N>0） | 报 collection 不存在 → 执行 `/memory-index` |
| `.memsearch.toml` | 存在 | 缺了会退回全局 collection（与其它项目混索引） |
| `.memsearch/memory/*.md` | 至少一个文件 | 空 → 还没有记忆，用 `/memory-save` 写第一条 |
| 模型缓存目录 | 存在 | 不存在 → 首次 index 会下载约 560 MB，属正常 |
| `capture.py --selftest` | 最后一行 `selftest OK` | 说明 hook 脚本在本机跑不起来（Python 缺失/路径含空格） |
| `claude-hooks.json` | 能被 JSON 解析 | 语法错会导致整套 hook 不加载 |

报告格式：一个表格（检查项 / 实际值 / 结论），最后给"下一步该做什么"的一句话结论。不要写"可能""大概"。
