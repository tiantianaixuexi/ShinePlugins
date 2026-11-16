---
name: files-tauri
description: Tauri 壳文件级清单：src-tauri/src 下 7 个 .rs 与 sidecar 全生命周期（动态端口/令牌/日志泵/健康检查/进程回收）。
status: 部分级（2026-11-16 取证，sidecar.rs 逐段）
---

# Tauri 壳文件级清单（`desktop/src-tauri/src/**/*.rs`，7 个）

`T/` = `desktop/src-tauri/src/`。Rust 壳只做窗口/菜单/命令/sidecar 生命周期；业务全在 Python。

## 文件清单

| 文件 | 行数 | 职责 | 关键符号 |
|---|---:|---|---|
| `T/main.rs:4` | 6 | 入口（release 隐藏 Windows 控制台） | `main` |
| `T/lib.rs:27` | 134 | 应用构建/插件/命令注册/启动 sidecar/退出守卫 | `run`；5 命令注册 `:41-47`；`run_with_exit_guard:84`、`stop_once:103`、`install_menu:111` |
| `T/commands/mod.rs:12` | 79 | 静态主机信息（进程内缓存 `:53-56`） | `AppInfo`、`host_info`、`collect_host_info` |
| `T/commands/system.rs:14` | 77 | IPC 命令薄封装 | `get_sidecar_info:14`、`sidecar_logs:20`、`restart_sidecar:26`、`open_data_dir:37`、`app_info:47` |
| `T/error.rs:11` | 91 | 错误枚举→`{code,message}`（`:61-72`） | `StudioError`（8 变体）、`code():47` |
| `T/process_job.rs:28` | 103 | Windows Job Object 防孤儿（非 Windows no-op `:92-103`） | `ProcessJob`、`create:32`、`assign:58`、`Drop:71` |
| `T/sidecar.rs:1` | 965 | sidecar 全生命周期监管 | 见下 |

## 5 个前端可见命令（`T/lib.rs:41-47`）

`get_sidecar_info` · `sidecar_logs` · `restart_sidecar` · `open_data_dir` · `app_info`（实现在 `T/commands/system.rs`）。

## sidecar 拉起逻辑（`T/sidecar.rs`，部分级取证）

| 环节 | 结论 | 证据 |
|---|---|---|
| 动态端口 | `portpicker::pick_unused_port()`，失败回退绑 `127.0.0.1:0` 读临时端口后释放；经 `NOVEL_STUDIO_PORT` 注入 | `:468-481,:491` |
| 一次性令牌 | `Uuid::new_v4().simple()`，经 `NOVEL_STUDIO_AUTH_TOKEN` 注入；健康检查与前端 REST/SSE 都带 Bearer | `:539,:492,:775-781` |
| 启动命令 | `python -m app`，cwd=backend，另设 HOST/DATA_DIR/ENVIRONMENT/LOG_JSON/PYTHONUTF8；Windows `CREATE_NO_WINDOW\|CREATE_NEW_PROCESS_GROUP` | `:484-500,:505-512` |
| 解释器解析 | 后端 `.venv` 优先 → 随包 python → 仓库 venv → PATH；逐个 `-c` 探活，排除 WindowsApps 别名；退出码 9009 给中文提示 | `:341-389,:435-465,:762-768` |
| 日志泵 | stdout→`tracing::info`、stderr→`warn`，同时写 500 行环形缓冲；经 IPC `sidecar_logs` 暴露 | `:647-686,:57,:195-202` |
| 所有权 | `Child` 只由 waiter 任务持有，`select!` 监听退出/关闭广播；退出 `terminate()` 宽限 5s 再强杀；`SidecarHandle::drop` 广播关闭 | `:581-611,:928-938,:137-145` |
| 健康检查 | 45s 总预算 / 250ms 轮询 / 3s 单次超时 / 5xx 连续 8s 早失败 / 401 立即失败；失败带最近 40 行日志 | `:39-54,:730-863` |
| 握手/就绪 | 成功写 `sidecar.json`（baseUrl/token/port/pid/startedAt），停止删除；发 `sidecar://ready` | `:867-882,:885-889,:941-945` |

> **注意**：前端实际**只轮询** `get_sidecar_info`（`desktop/src/lib/sidecar.ts:57-65`），未监听 `sidecar://ready` 事件。这个错位是"空地址缓存→ECONNREFUSED 8765"历史坑的根源，见 `../04_BugsAndLessons/Lessons.md`。
