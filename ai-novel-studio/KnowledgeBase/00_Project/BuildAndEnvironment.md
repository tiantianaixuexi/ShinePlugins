---
name: build-and-environment
description: 构建与环境：怎么装/跑/打包/验证，命令的 cwd 与期望输出（实测数字），Windows 特有约束。
status: 现行（2026-11-16 实测）
---

# 构建与环境

## 前置

Python 3.13+、Node.js 20+、pnpm、Rust 1.93+（`README.md:40`）。

## 安装

| 目标 | 命令（cwd） | 证据 |
|---|---|---|
| 后端 venv | `py -3.13 -m venv .venv` → `.\.venv\Scripts\Activate.ps1` → `python -m pip install -U pip` → `pip install -r requirements-dev.txt`（`backend/`） | `README.md:43-48,126-131` |
| 前端 | `pnpm install`（`desktop/`） | `README.md:50-52,133-134` |
| Rust | `rustup default stable`（rustc ≥1.93） | `README.md:136` |

## 运行

| 方式 | 命令（cwd） | 结果 | 证据 |
|---|---|---|---|
| 一条命令起前后端 | `pwsh -File scripts\dev.ps1`（可带 `-Port`/`-Token`）（仓库根） | 首次复制 `.env.example`→`desktop/.env`；起后端 `:8765` + Vite `:1420`；前端退出自动 `taskkill /T /F` 后端 | `scripts/dev.ps1:14-22,32-35,41-55,70-75` |
| 仅后端 | `pwsh -File scripts\dev-backend.ps1` | 输出 URL/Token/DataDir；数据目录 `%LOCALAPPDATA%\AI Novel Studio/dev` | `scripts/dev-backend.ps1:19-23,34-52` |
| 仅前端 | `pnpm dev`（`desktop/`） | Vite `127.0.0.1:1420` | `desktop/package.json:9`、`vite.config.ts:24-27` |
| 桌面开发 | `pnpm tauri dev`（`desktop/`） | Rust 自动注入动态端口/令牌并管理后端；首次编译数分钟 | `tauri.conf.json:7-8`、`README.md:54-58,220-223` |
| 打包 | `pnpm tauri build`（`desktop/`） | msi/nsis → `src-tauri/target/release/bundle/` | `tauri.conf.json:9-10,30-32`、`README.md:272` |

## 验证（2026-11-16 18:16 快照；权威数字见 `../09_Reports/ScanReports/Progress.md` §3）

| 命令（cwd） | 实测结果 | 证据 |
|---|---|---|
| `.venv\Scripts\python.exe -m pytest -o addopts='' -q --tb=no`（`backend/`） | **117 passed in 55.45s** | 本次实测（叠加 -q 会静默到无汇总行，须覆盖 addopts） |
| `pnpm test`（`desktop/`） | **37 passed (5 文件)**：utils 14 · ai 10 · text-edit 6 · api 4 · sidecar 3 | 本次实测 |
| `pnpm typecheck`（`desktop/`） | 无输出（`tsc --noEmit` 干净） | 本次实测 |
| `scripts\smoke_api.py`（仓库根，用 backend venv） | `SMOKE PASSED: all checks green` | 另一会话 T-36 验证栏记录 PASSED |
| `scripts\smoke_ai.py --from-store`（仓库根） | `AI SMOKE PASSED`（需已配置模型） | 另一会话 T-36 验证栏记录 PASSED（真实模型） |
| `cargo check`（`desktop/src-tauri/`） | `Finished`，无 error | `README.md:374-379`；本轮未跑 |

> **数字持续变化**（测例随任务推进增加）：本表是快照，判别以 `Progress.md` §3 为准。旧文档（README 349 写 29 / 384 写 25、AGENTS 写 29）已是过期值。

## Windows 特有约束

| 约束 | 事实 | 证据 |
|---|---|---|
| DPAPI 加密 | `crypt32.CryptProtectData/CryptUnprotectData` 绑定当前用户；不可用时仅混淆并告警 | `core/keystore.py:7-8,52-72,94-122,131-135` |
| 密钥文件 | `secrets.json` 禁止提交/拷贝 | `README.md:160`、`.gitignore:57` |
| Vite 代理 | 固定 `1420` + strictPort，host `127.0.0.1`；`/api`→`127.0.0.1:8765`。后端未起时代理返回纯文本 **502（不是模型故障，是后端没起）** | `vite.config.ts:22-36`、`README.md:251-256` |
| 浏览器令牌 | 读 `desktop/.env` 的 `VITE_API_TOKEN=dev-token` | `.env.example:1-10`、`README.md:252` |
| sidecar 端口 | `portpicker::pick_unused_port()`（失败回退 `:0`），注入 `NOVEL_STUDIO_PORT`，强制 `NOVEL_STUDIO_HOST=127.0.0.1` | `sidecar.rs:467-480,484-496` |
| 握手/健康轮询 | `sidecar.json` 握手；`/api/health` 每 250ms 轮询、45s 超时；5xx 预算 8s | `sidecar.rs:34-54` |
| 进程回收 | Windows job object 防孤儿；`CREATE_NO_WINDOW`/新进程组 | `Cargo.toml:42-49`、`sidecar.rs:502-512` |
| 编码 | 壳注入 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`；PS 5.1 `Invoke-RestMethod` 中文体可能乱码，建议 `curl.exe`/PS7 | `sidecar.rs:496-497`、`README.md:208-209` |
