---
name: lessons
description: 做法层教训（真实踩过、有来源为证），非缺陷。回答"这个坑以前踩过吗/为什么当时这么做"。
status: 现行（2026-11-16 建档）
---

# 踩坑教训（Lessons）

> 收录口径：必须有明确来源（日期记忆 / 交接文档 / 测试失败输出 / 已修复的代码），不接受臆测。
> 缺陷本体在 [`DefectRegister.md`](DefectRegister.md)；本页只记"做法层"的经验。

## 工程/环境类

### L-01 · HTTP 502 不是模型故障，是后端没起
- **来源**：`.memsearch/memory/2026-11-16.md:28-34`（真实发生）
- Vite 代理上游不可达时返回 **纯文本 502**，前端曾误显示为模型错误；`desktop/.env` 缺失还会叠加 401。起 `scripts/dev.ps1` 后恢复正常；前端补了 4 条 502/503/504 分类用例。落点：`README.md:254`、`INDEX.md` 常见故障表。

### L-02 · sidecar 空地址缓存导致 ECONNREFUSED 8765
- **来源**：`INDEX.md:61`（标注"已修复"）
- 前端曾缓存 `stopped` 态的空地址，请求落回 Vite 固定代理 8765，而 sidecar 实际用动态端口。修法：`desktop/src/lib/sidecar.ts` 轮询 `get_sidecar_info` 到 `ready` 才缓存。相关：`12-files-tauri.md` 记前端只轮询、不监听 `sidecar://ready` 事件。

### L-03 · OPTIONS 被 TokenMiddleware 拦截致预检 401
- **来源**：`INDEX.md:62`（已修复）
- CORS 中间件没机会回应 OPTIONS。修法：`backend/app/main.py` 放行 OPTIONS；真实请求仍需 token。

### L-04 · 新端点必须四处同步
- **来源**：`.memsearch/memory/2026-11-16.md:70-76`（T-27 发现）
- T-27 时发现 api.md §5 把整个 AI router 写成"未实现"，而 T-01~T-05 已做出多个端点。总览表/详情/未实现表/README 计数漏一处就自相矛盾。新增端点后要全表核对。

## 协作/取证类

### L-05 · worker 报的 pytest 数字不可信
- **来源**：`.memsearch/memory/2026-11-16.md:61-67`
- 两次出现"worker 说 87 collected"这类措辞与实数差异。**以自己跑出的点数为准**；配套纪律：任务 done 后必跑 `row` + 自己复跑 pytest。

### L-06 · 非 git 仓库 + 并行改动，改文件前必须先 read
- **来源**：`.memsearch/memory/2026-11-16.md:53-59`
- README、INDEX.md 曾在写入前后被更新，无法用 diff 核对是否覆盖他人编辑。本仓库无 git，改文件前先 `read_file` 取当前内容。

### L-07 · 行号与路径双重漂移，按症状重新定位
- **来源**：`TaskPitfalls.md:11,45` + 2026-11-16 实测
- 账本写 `ai_service.py:200-205`，真逻辑已移到 `:915-997`；且坑位文档曾把路径写成 `backend/app/ai/services/ai_service.py`（不存在），真实是 `backend/app/services/ai_service.py`。**证据行号是快照，动手前复核**。

### L-08 · 旧结论会被新对账推翻
- **来源**：`.memsearch/memory/2026-11-16.md:45-51`
- 上一轮 Plan_Gaps 的 P0 里 SQLite 并发/schema 迁移/sidecar 运维其实都已实现；`docs/plan-reconciliation.md` 才是新鲜真源。别拿旧缺陷清单当现状。

### L-09 · 文档"AI 完全未开工"与代码严重不符
- **来源**：`05_Plan/handoffs/2026-11-16-ai-layer-audit.md:7-8` + 记忆 `:36-43`
- 文档曾写 AI 部分完全未开工，实际已有 10 个 py、5 端点、17 条测试。由此才建了 TaskRegister 唯一真源和 task-next 流水线。**判断现状以代码为准，改文档**。

## 验证类

### L-10 · 全 PASS 的 mock 测试不能替代真实模型冒烟
- **来源**：T-30 验证栏 `TaskRegister.md`（`AI SMOKE FAILED: 1`）+ T-28 的 18 项真实检查
- mock 覆盖的降级路径在真实模型上暴露了空内容缺陷（DEF-03）。涉及模型行为的改动，必须跑 `scripts/smoke_ai.py --from-store`（需已配置模型）。

### L-11 · 撞车分析前先复核"未实现"前提
- **来源**：`TaskPitfalls.md:86-93`
- T-30 账本写"POST /ai/outline 无流式"时，代码里流式已落地（路由 `routes/ai.py:161-184`、服务 `ai_service.py:728-822`）。**分诊前先看代码现状**，否则在已实现的东西上"重新实现"。
