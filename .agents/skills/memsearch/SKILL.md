---
name: memsearch
description: 用 memsearch 维护本工作区的「事件记忆」——把每次会话做过什么、为什么这么决定、踩了什么坑写成 markdown 并建语义索引，之后按自然语言召回。当用户说「我们之前/上次讨论过…」「为什么这么改的」「恢复一下进度」「记一下这件事」「以前踩过什么坑」，或你需要跨会话历史才能正确回答时使用。工程事实（代码在哪、接口怎么定、表结构）不要走这里，那些看 ai-novel-studio/KnowledgeBase/INDEX.md。
---

# memsearch：会话记忆的写入与召回

本技能把 [zilliztech/memsearch](https://github.com/zilliztech/memsearch) 接进本工作区。它**不是 MCP server**，就是
`CLI + markdown 目录 + 向量索引 + 一层 skill/command/hook`。CLI 已在 PATH（`memsearch`，v0.4.23），直接 shell 调用即可。

> **工具无关**：正文只写在 `.agents/skills/memsearch/` 这一份。Claude Code / Codex / DSH / CodeBuddy 各自读自己的入口目录，
> 入口目录里只放**指针**（一行"去读 `.agents/skills/memsearch/SKILL.md`"），不复制正文。改规则只改这里，别改镜像。

## 0. 分工（先读，否则会把东西记错地方）

| 内容类型 | 该放哪 | 例子 |
|---|---|---|
| **工程事实**（代码位置、接口契约、表结构、构建方式） | `ai-novel-studio/KnowledgeBase/` + `ai-novel-studio/docs/` | "章节自动保存在 `desktop/src/components/editor/chapter-editor.tsx`，1200 ms 防抖" |
| **事件记忆**（何时做了何事、当时为什么、踩了什么坑） | **本技能管理的 `.memsearch/memory/*.md`** | "2026-11-16 决定不搬 ShineEngine 那套缺陷流水线，先只做文档入口" |
| 用户偏好 / 长期协作习惯 | 工具自带的 project memory（如 CodeBuddy `MEMORY.md`） | "验证一律先跑 pytest -q 再跑 pnpm test" |

判据：**「下次还需要重新知道这件事吗？」** —— 需要静态查证的放文档，需要"回忆过程"的放 memsearch。

## 1. 本技能装了什么

| 组件 | 位置 | 作用 |
|---|---|---|
| 技能正文 | `.agents/skills/memsearch/SKILL.md`（本文件，唯一真源） | 何时/怎么召回与写入 |
| CLI 参考 | `.agents/skills/memsearch/references/cli.md` | 全量参数 + 实测坑 |
| 命令 | `.agents/commands/memory-{recall,save,index,doctor}.md` | `/memory-recall`、`/memory-save`、`/memory-index`、`/memory-doctor` 的步骤正文 |
| Hook 脚本 | `.agents/skills/memsearch/scripts/{capture,recall,_common,_dsh_session}.py` | 会话结束落盘 / 提问时召回，**永不 exit≠0** |
| Hook 配置样例 | `.agents/hooks/claude-hooks.json` | Stop + UserPromptSubmit 的事件名与超时；各工具自行注册 |

**为什么没有 `.mcp.json`**：上游没有 MCP server。硬造一个 MCP wrapper 只会多一层进程和协议往返，能力不会多。

### 目录与配置

| 项 | 值 |
|---|---|
| 记忆正文（唯一真源，建议入库） | `<工作区根>/.memsearch/memory/YYYY-MM-DD.md` |
| 项目配置 | `<工作区根>/.memsearch.toml` → `collection = "novelstudio_memory"` |
| 索引库（派生缓存，别备份） | `~/.memsearch/milvus.db`（**全局单文件**，多项目共用；隔离靠 collection） |
| embedding 模型 | `gpahal/bge-m3-onnx-int8`，缓存于 `~/.cache/huggingface/hub/`（首次约 560 MB） |

⚠️ 实测坑：项目级 `.memsearch.toml` 能覆盖 `collection`，**覆盖不了 `milvus.uri`**（换成绝对路径也不生效）。所以别指望"一项目一 db 文件"，只靠 collection 隔离。

## 2. 召回（read）

```bash
memsearch stats            # 先确认不是空库；报 "Collection ... does not exist" 说明还没 index 过
memsearch search "上次改章节版本遇到什么坑" -k 5
memsearch search "sidecar" --source-prefix .memsearch/memory/2026-11 -k 5
memsearch search "为什么不用 Tiptap" -k 5 --json-output
memsearch expand <chunk_hash>      # 结果是被切的 chunk，需要上下文时展开
memsearch transcript               # 原始对话轮次（含工具调用）
```

**分数怎么读**：score 是**分桶**的（上游同一套模型实测只出现 `1.0 / 0.984 / 0.50 / 0.4919 / 0.4841` 几档），
能区分「强命中（≈1.0）」与「其它」，**不能区分「相关」与「无关」**。所以：

- **不要用绝对阈值判断相关性**（`>0.5`、`>0.6`、`>0.8` 都会在某个语料上判错）；
- 用 **top-k 的相对排序**选候选，再 `memsearch expand <hash>` 看正文确认；
- top-1 是 0.50 时不要把"命中"说成"确定"，说"检索到的最接近的几条"。

> △ 上述分数档来自上游项目语料。本项目记忆库刚建立（2 chunk），首次攒到 10 条以上后要重新实测并改本节。

中文 / 中英混合查询都可用。

**工程问题想模糊定位（可选，尚未建立）**：`ai-novel-studio/KnowledgeBase/` 将来可以另建向量索引（`collection = novelstudio_kb`），
适合"这功能大概在哪"这类记不住关键词的查询；精确地点仍然先查 `KnowledgeBase/INDEX.md`。

```bash
memsearch index ai-novel-studio/KnowledgeBase --collection novelstudio_kb
memsearch search "章节版本回退" -k 5 --collection novelstudio_kb
```

## 3. 写入（write）

### 3.1 什么时候写

会话里出现**决策**、**踩坑与绕行**、**进度变更**时写。一次会话 **1~3 条**，只写"下次真会用到"的。

### 3.2 写之前先查重

```bash
memsearch search "<这次的主题>" -k 3
```

已有同主题段落 → 追加/修订那一段，不要新建重复文件。

### 3.3 手动写（推荐，质量最高）

追加到当天的文件 `.memsearch/memory/YYYY-MM-DD.md`：

```markdown
## 2026-11-16 阶段 2 的 AI 部分先不做，改为先补文档入口
- 决定：先建 KnowledgeBase/INDEX.md + 文档导航 skill，AI 能力留在阶段 2 未完成表里。
- 理由：LLM 适配器、大纲、Prompt 模板全都还没开工，没有文档入口时每次会话都要重新扫仓库。
- 代价：多维护一份索引，需随代码同步。
- 验证：`pytest -q` 与 `pnpm test` 全绿，未触碰任何源码。
- 指针：见 `ai-novel-studio/docs/development-plan.md`
```

然后增量索引：

```bash
memsearch index .memsearch/memory     # 正常输出 "Indexed N chunks."
```

### 3.4 自动落盘（Stop hook）

`.agents/skills/memsearch/scripts/capture.py` 在收到 Stop 事件时：

1. 读 stdin payload 的 `transcript_path`，取最近若干条 **用户提问 + 助手文字节选**（丢弃工具调用与超长内容）；
2. 以 `<!-- session:<id> -->` 锚点追加到当天文件；**同一 session 只写一次**（幂等）；
3. 跑一次 `memsearch index .memsearch/memory`。

它**不生成摘要**（hook 是 shell 进程，没有 LLM）。看到 `## 会话片段（自动落盘，待补充）` 这类小节时，
若这轮确实有值得留存的结论，用 §3.3 补写一条真正的决策记录。

**默认没挂。** 各工具的注册方式见 `.agents/README.md`；没挂之前，会话收尾一律手动走 `memory-save` 的步骤。
关闭自动落盘：临时设 `MEMSEARCH_CAPTURE=0`；永久关则从所注册的 hooks 配置里删掉 Stop 项。

## 4. 维护

```bash
memsearch stats                       # 已索引 chunk 数
memsearch reset --yes                 # 丢索引（md 不动，安全，之后重跑 index）
memsearch watch .memsearch/memory     # 长驻监听；不要在 agent 普通命令里起（会挂住）
memsearch compact                     # 用 LLM 压缩记忆（需配 key；本项目默认没配）
```

`.memsearch/*.md` 是唯一真源 → **索引随时可重建**，不要为了"保护索引"不敢 reset。

## 5. 硬规则

1. **不要改 `.memsearch.toml` 的 `collection` 名**（本项目为 `novelstudio_memory`）：改了等于把历史切到另一个 collection，召回立刻"失忆"。
2. **记忆里不写密钥/token/内网地址**。`compact` 会把内容发给 LLM（若启用远端 provider）。
3. **不复制工程文档正文**，只写指针（如"见 `ai-novel-studio/KnowledgeBase/INDEX.md` §验证"）。
4. **hooks 脚本必须永远 exit 0 且只往 stdout 打一个 JSON**，否则会卡住/污染会话；改脚本后先本地喂假 payload 测。
5. `memsearch` 不在 PATH 时：`uv tool list` 确认，再 `uv tool install "memsearch[onnx]"` 重装；**不要** `pip install --user` 混装出两份。
6. **记忆写工作区根 `.memsearch/`，工程事实写 `ai-novel-studio/KnowledgeBase/`**，两者不要互相替代。
7. **正文只写 `.agents/`**。`.codebuddy/`、`.claude/`、`.codex/` 下的同名文件只能是指针，否则多份副本必然分叉。

## 6. 排错

| 现象 | 原因 / 处理 |
|---|---|
| `Collection 'memsearch_chunks' does not exist` | 没 index 过，或 collection 名不对（本项目应为 `novelstudio_memory`） |
| 召回"失忆"但 md 还在 | 换了 collection / 换了 `~/.memsearch/milvus.db` → `memsearch index .memsearch/memory` 重建 |
| 首次 index 卡很久 | 在下 560 MB 模型，等 `~/.cache/huggingface/hub` 出现 `models--gpahal--bge-m3-onnx-int8` |
| hook 没生效 | 先在工作区根跑 `python .agents/skills/memsearch/scripts/capture.py --selftest`，再确认该工具已注册 Stop 事件 |
| hook 报错但会话正常 | 符合设计：脚本吞异常并 exit 0，错误打到 stderr |

CLI 全量参数与实测输出见 `references/cli.md`。
