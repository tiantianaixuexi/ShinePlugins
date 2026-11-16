---
name: bugs-and-lessons
description: 缺陷与踩坑层入口。所有"要修的东西"只在 DefectRegister.md 写一份（DEF-xx）；事实型文档最多留一行 → DEF-xx。
status: 现行
---

# 缺陷与踩坑层（`04_BugsAndLessons/`）

## 为什么单独一层

事实型文档（`00_Project/`、`01_CodeMap/`）职责是描述现状、供人按它改代码。把缺陷写进去会造成：同一缺陷散落多处、修好要改每一处；读者分不清"这是设计"还是"这是 bug"。所以**缺陷只有一个真源** → [`DefectRegister.md`](DefectRegister.md)。

## 目录

| 文件 | 内容 |
|---|---|
| [`DefectRegister.md`](DefectRegister.md) | 唯一缺陷清单：`DEF-xx`，证据/影响/修法/验收四列 + 状态机 |
| [`Lessons.md`](Lessons.md) | 真实踩过的坑（有来源为证），做法层教训，非缺陷 |

## 收录口径

| 类型 | 收不收 | 归哪 |
|---|---|---|
| 源码可验证的缺陷（逻辑错、静默失效、数据错） | ✅ 收 | `DefectRegister.md`，标 `静态`，可信度 ✅/△ |
| 真实发生过的故障（有记忆/交接/测试失败输出为证） | ✅ 收 | `DefectRegister.md`，标 `已发生`，必须给证据链接 |
| 未实现的功能（feature gap） | ❌ 不收 | 计划层 `05_Plan/TaskRegister.md`（T-xx） |
| 设计取舍（有意为之，如 textarea vs Tiptap） | ❌ 不收 | ADR / `docs/development-plan.md` |
| 看起来可疑、无证据 | ❌ 不收 | `09_Reports/ScanReports/Progress.md` 未解决问题 |
| 做法层教训（"当时怎么踩的"） | ❌ 不进 DEF | `Lessons.md` |

**重要区分**：本项目的待办大多属"未实现功能"（T-11 RAG、T-17 导入导出、T-19 工作流…），**不进 DefectRegister**。DefectRegister 只收"代码写错了"的那部分（如 DEF-01 摘要泄漏未来章）。

## 状态机

`待修` → `修复中` → `待验证` → `已关闭`（必写回归验证方式）；`不修`（必写理由 + 谁决定）。**编号只增不改号**，关闭只改状态列。

## 与其它层的关系

- `05_Plan/TaskPitfalls.md`：坑位清单是"发现现场"，定性后——确认缺陷迁到本层（留 `→ DEF-xx`）、未实现功能留在 T-xx、设计取舍进 ADR。
- `05_Plan/TechnicalDebt.md`：技术债视图，条目引用 `DEF-xx`/`T-xx` 不重复描述。
- `09_Reports/ScanReports/Progress.md`：只记未定性疑点，定性后迁入。
