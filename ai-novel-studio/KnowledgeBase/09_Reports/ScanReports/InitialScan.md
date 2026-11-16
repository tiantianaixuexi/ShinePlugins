---
name: initial-scan
description: 知识库初始扫描基线：2026-11-16 对代码规模、文档缺口的初次盘点结论。历史快照，现状看 Progress.md。
status: 归档（历史快照）
---

# 初始扫描报告（2026-11-16）

> ⚠️ 历史快照：记录本次补全前的起点。现状看 [`Progress.md`](Progress.md) 与 `../../INDEX.md`。

## 起点：本库与参考库的差距

对照 `E:\c++\ShineEngine\KnowledgeBase`（59 篇、8 分区），本库补全前只有 `INDEX.md` + `05_Plan/`（共 8 篇、1 分区）。差距分两类：

| 类型 | 分区 | 处理 |
|---|---|---|
| 真结构性缺口 | `00_Project`、`01_CodeMap`、`04_BugsAndLessons`、`09_Reports` | 本次补全 |
| 规模可解释（不照搬） | `02_Modules` 逐模块逐行文档、`_StructuralInventory` 701 文件清单 | 本库是小应用（后端 56 py / 前端 62 ts(x) / Rust 7 rs），不建引擎级逐行文档 |
| 两边都缺 | `03_ADR`、`08_AI_Memory` | 待建 |

## 关键发现

1. **悬空规则**：`INDEX.md:97` 早写"缺陷只有一个真源（04_BugsAndLessons/DefectRegister.md 建好后）"，但目录不存在 → 本次补建 `04_BugsAndLessons/`。
2. **数字漂移**：验证数字在 AGENTS/CODEBUDDY/INDEX/CurrentStatus/README 五处互相矛盾（60/29、96/32、104/36）→ 实测权威值记在 `Progress.md` §3。
3. **坑位与任务混淆**：`05_Plan/TaskPitfalls.md` 把"未实现功能"和"代码缺陷"揉在一起 → 定性后分别迁到 `T-xx` 与 `DEF-xx`（本次建 DefectRegister）。
4. **行号/路径漂移**：账本与坑位文档的 `文件:行` 大量过期 → 全库统一"证据是快照，动手前复核"口径（Lessons L-07）。

## 本次产出

- `00_Project/`：4 篇（客观基线）
- `01_CodeMap/`：6 篇（导航 + 三层文件清单 + 调用链）
- `04_BugsAndLessons/`：3 篇（缺陷真源 + 教训）
- `09_Reports/ScanReports/`：2 篇（本页 + Progress）
- 后续待办：更新 `INDEX.md` / `05_Plan/README.md` 分区表、统一验证数字、补 `03_ADR`。
