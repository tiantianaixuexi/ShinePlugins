# 交接：AI 层现状核查（2026-11-16）

> 本文是**当时快照**，不改正文；后续进展写进 `../CurrentStatus.md`。

## 背景

`docs/development-plan.md` §3.2 写"AI 部分完全未开工"，与代码不符。本轮做了一次只读核查，
结论写进 `../CurrentStatus.md`，并把缺口转成 `../TaskRegister.md` 的 `T-01`…`T-16`。

## 核查结论（摘要）

- **已实现**：LLM 适配器抽象与 OpenAI 兼容实现、重试与错误分类、SSE 流式、提示词双源（内置 + DB）、
  生成任务记账（token/成本/失败）、主备降级链代码、前端 SSE 客户端与 AI 面板。
- **部分实现**：提示词版本恒为 1（无升版端点）；降级链与 PromptService 零测试；操作入口只暴露 5/7。
- **未实现**：结构化输出（`json_mode` 硬编码 false）、`chapter_summaries` 写入、`source="ai"` 版本、
  `agent_configs` 读写、`outlines` 落库、`knowledge_chunks` 检索、拒绝/丢弃交互、三个只读端点的消费方。

## 测试现状

| 文件 | 用例数 |
|---|---|
| `backend/tests/test_ai_adapters.py` | 13 |
| `backend/tests/test_ai_stream_e2e.py` | 2 |
| `desktop/src/lib/ai.test.ts` | 5 |

## 当时未确认

- `tests/test_ai_adapters.py:3` 提到 `scripts/smoke_ai.py` 覆盖真实 provider 调用，本轮**未核实该脚本是否存在**。
- 全量 `pytest` 实际条数（README 写 44、development-plan 写 37）未实跑核对。
