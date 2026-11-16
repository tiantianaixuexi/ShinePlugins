//! Sidecar supervision for the Python backend.
//!
//! The desktop shell owns exactly one `python -m app` child process. This
//! module resolves where that process and its interpreter live, starts it on a
//! private port with a private auth token, proves it is healthy before the
//! window loads the UI, captures its logs, and guarantees it is never left
//! running after the window closes.
//!
//! Ownership model: the [`Child`] lives inside the waiter task. Dropping the
//! [`SidecarHandle`] drops a `tokio::sync::broadcast` sender, which makes the
//! waiter fall through to [`terminate`]: it waits out the grace period, then
//! force-kills and reaps. Nothing else ever touches the child, so no process
//! can be orphaned and no pid can be recycled out from under us.

use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use chrono::{SecondsFormat, Utc};
use serde::Serialize;
use tauri::Emitter;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::broadcast;
use tokio::task::JoinHandle;

use crate::error::StudioError;
use crate::process_job::ProcessJob;

/// Name of the diagnostic handshake file written into the data directory.
pub const SIDECAR_FILE: &str = "sidecar.json";

/// Event emitted once the backend answered its first healthy probe.
pub const SIDECAR_READY_EVENT: &str = "sidecar://ready";

/// How long we allow the backend to boot before giving up.
const HEALTH_TIMEOUT: Duration = Duration::from_secs(45);

/// How long a graceful shutdown may take before we force-kill.
const STOP_TIMEOUT: Duration = Duration::from_secs(5);

/// How long we keep polling when the backend answers with 5xx.
///
/// A backend that is merely slow to boot has not opened its socket yet (so the
/// poll fails to connect). Once it is answering with server errors it is
/// running but broken, and waiting out [`HEALTH_TIMEOUT`] only delays the
/// diagnosis.
const SERVER_ERROR_BUDGET: Duration = Duration::from_secs(8);

/// How often we poll `/api/health` while waiting for the backend.
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(250);

/// How many backend log lines we retain in memory.
const LOG_CAPACITY: usize = 500;

/// Capacity of the shutdown broadcast channel (one waiter, two pumps).
const SHUTDOWN_CAPACITY: usize = 4;

/// Public description of the running sidecar, serialised as camelCase JSON.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SidecarInfo {
    /// Base URL including scheme and port, e.g. `http://127.0.0.1:43117`.
    pub base_url: String,
    /// Shared secret the frontend must present on every `/api` call.
    pub token: String,
    /// Port the backend is bound to.
    pub port: u16,
    /// Operating-system process id of the backend.
    pub pid: u32,
    /// RFC 3339 timestamp of when the sidecar was spawned.
    pub started_at: String,
    /// Either `starting`, `ready`, `stopping` or `stopped`.
    pub status: String,
}

impl SidecarInfo {
    /// A placeholder snapshot used before the first successful spawn.
    pub fn stopped() -> Self {
        Self {
            base_url: String::new(),
            token: String::new(),
            port: 0,
            pid: 0,
            started_at: String::new(),
            status: "stopped".into(),
        }
    }
}

/// Where we decided the backend, interpreter and data directory live.
#[derive(Debug, Clone)]
pub struct ResolvedPaths {
    pub backend_dir: PathBuf,
    pub python: PathBuf,
    pub data_dir: PathBuf,
}

/// The live sidecar.
///
/// Dropping this value asks the waiter task to reap the child; see the module
/// documentation for the ownership rules.
pub struct SidecarHandle {
    info: SidecarInfo,
    /// Broadcasting shutdown signal for the waiter and the pipe pumps.
    shutdown: broadcast::Sender<()>,
    /// Set once the child has been reaped.
    exited: Arc<AtomicBool>,
    /// Windows job object owning the child: closing it kills the sidecar even
    /// when this process dies without running destructors.
    _job: Option<ProcessJob>,
    stdout_task: JoinHandle<()>,
    stderr_task: JoinHandle<()>,
}

impl SidecarHandle {
    /// Current info snapshot.
    pub fn info(&self) -> &SidecarInfo {
        &self.info
    }

    /// Whether the child has already been reaped.
    pub fn has_exited(&self) -> bool {
        self.exited.load(Ordering::SeqCst)
    }

    /// Stop tailing the pipes (the waiter is signalled by dropping the handle).
    fn abort_pumps(&mut self) {
        self.stdout_task.abort();
        self.stderr_task.abort();
    }
}

impl Drop for SidecarHandle {
    fn drop(&mut self) {
        // Broadcasting `()` wakes the waiter's select arm, so it proceeds to
        // `terminate()` and reaps the child. A send error just means every
        // receiver is already gone, which is fine.
        let _ = self.shutdown.send(());
        self.abort_pumps();
    }
}

/// Shared, cloneable supervisor state managed by Tauri.
#[derive(Clone, Default)]
pub struct SidecarState {
    inner: Arc<Mutex<Option<SidecarHandle>>>,
    logs: Arc<Mutex<VecDeque<String>>>,
    resolved: Arc<Mutex<Option<ResolvedPaths>>>,
}

impl SidecarState {
    /// Create empty supervisor state.
    pub fn new() -> Self {
        Self::default()
    }

    /// Resolve (and remember) the backend directory, interpreter and data dir.
    pub fn resolve(&self) -> Result<ResolvedPaths, StudioError> {
        if let Ok(guard) = self.resolved.lock() {
            if let Some(cached) = guard.as_ref() {
                return Ok(cached.clone());
            }
        }
        let backend_dir = resolve_backend_dir()?;
        let resolved = ResolvedPaths {
            python: resolve_python(&backend_dir)?,
            backend_dir,
            data_dir: resolve_data_dir()?,
        };
        if let Ok(mut guard) = self.resolved.lock() {
            *guard = Some(resolved.clone());
        }
        Ok(resolved)
    }

    /// Snapshot of the retained log tail.
    pub fn logs(&self) -> Vec<String> {
        self.logs
            .lock()
            .map(|guard| guard.iter().cloned().collect())
            .unwrap_or_default()
    }

    /// Last `count` log lines joined with newlines (used in error messages).
    pub fn log_tail(&self, count: usize) -> String {
        let all = self.logs();
        let start = all.len().saturating_sub(count);
        all[start..].join("\n")
    }

    fn push_log(&self, line: String) {
        if let Ok(mut guard) = self.logs.lock() {
            if guard.len() >= LOG_CAPACITY {
                guard.pop_front();
            }
            guard.push_back(line);
        }
    }

    fn clear_logs(&self) {
        if let Ok(mut guard) = self.logs.lock() {
            guard.clear();
        }
    }

    /// Snapshot of the current sidecar, if any.
    pub fn info(&self) -> Option<SidecarInfo> {
        self.inner
            .lock()
            .ok()
            .and_then(|guard| guard.as_ref().map(|handle| handle.info.clone()))
    }

    /// Start the sidecar, or return the already-running one.
    ///
    /// The state lock is never held across an `.await`: the child is spawned
    /// and probed first, and only a healthy process is stored.
    pub async fn start(&self) -> Result<SidecarInfo, StudioError> {
        if let Some(info) = self.info() {
            return Ok(info);
        }

        let resolved = self.resolve()?;
        self.clear_logs();
        self.push_log(format!(
            "[shell] starting sidecar from {}",
            resolved.backend_dir.display()
        ));

        let spawned = spawn_process(&resolved, self.clone()).await?;
        let info = self.wait_for_health(spawned).await?;

        let _ = write_handshake(&resolved.data_dir, &info);
        tracing::info!(port = info.port, pid = info.pid, "sidecar ready");
        Ok(info)
    }

    /// Stop the sidecar if it is running.
    pub async fn stop(&self) -> Result<(), StudioError> {
        let handle = self.inner.lock().ok().and_then(|mut guard| guard.take());

        if let Some(handle) = handle {
            let pid = handle.info.pid;
            // Dropping the handle signals the waiter to reap the child.
            drop(handle);

            wait_for_exit(pid, STOP_TIMEOUT).await;
            if pid_alive(pid) {
                force_kill(pid);
            }
            self.push_log(format!("[shell] sidecar (pid {pid}) stopped"));
            tracing::info!(pid, "sidecar stopped");
        }

        let _ = remove_handshake();
        Ok(())
    }

    /// Stop then start, returning the fresh info.
    pub async fn restart(&self) -> Result<SidecarInfo, StudioError> {
        self.stop().await?;
        self.start().await
    }

    /// Stop the sidecar synchronously, from an exit hook.
    ///
    /// Dropping the handle triggers the reaper; this then blocks the thread for
    /// up to [`STOP_TIMEOUT`] until the process is gone, force-killing it if it
    /// ignores the request.
    pub fn stop_blocking(&self) {
        let handle = self.inner.lock().ok().and_then(|mut guard| guard.take());
        let Some(handle) = handle else {
            let _ = remove_handshake();
            return;
        };
        let pid = handle.info.pid;
        drop(handle);

        let deadline = Instant::now() + STOP_TIMEOUT;
        while Instant::now() < deadline && pid_alive(pid) {
            std::thread::sleep(Duration::from_millis(50));
        }
        if pid_alive(pid) {
            force_kill(pid);
        }
        let _ = remove_handshake();
    }
}

/// Everything produced by [`spawn_process`], ready to be probed.
struct Spawned {
    pid: u32,
    port: u16,
    token: String,
    handle: Option<SidecarHandle>,
    exit_code: Arc<AtomicI32>,
}

/// Resolve the backend source directory.
///
/// Priority: `NOVEL_STUDIO_BACKEND_DIR`, then the compiled-in repo checkout for
/// debug builds, then a `backend` folder next to the installed executable.
pub fn resolve_backend_dir() -> Result<PathBuf, StudioError> {
    if let Some(dir) = env_path("NOVEL_STUDIO_BACKEND_DIR") {
        return ensure_dir(&dir, "NOVEL_STUDIO_BACKEND_DIR");
    }

    // `CARGO_MANIFEST_DIR` is `desktop/src-tauri`, so the repo backend sits two up.
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let exe_dir = current_exe_dir();
    let candidates = [
        manifest_dir.join("../../backend"),
        manifest_dir.join("../backend"),
        exe_dir.join("backend"),
        exe_dir.join("../backend"),
    ];

    for candidate in candidates {
        if candidate.join("app").join("__main__.py").is_file() {
            return Ok(candidate);
        }
    }

    Err(StudioError::SidecarStart(format!(
        "could not locate the backend directory (looked for app/__main__.py in {} and next to the executable)",
        manifest_dir.display()
    )))
}

/// Resolve the Python interpreter that can import the backend.
///
/// Order matters: the backend's own virtualenv is the only interpreter that is
/// *guaranteed* to have the dependencies installed, so it comes first. Bare
/// names such as `python` are probed rather than trusted — on Windows `python3`
/// is often a Microsoft Store alias that exits with code 9009, which otherwise
/// surfaces as "backend exited before becoming healthy" with no useful clue.
pub fn resolve_python(backend_dir: &Path) -> Result<PathBuf, StudioError> {
    if let Some(path) = env_path("NOVEL_STUDIO_PYTHON") {
        if is_usable_python(&path) {
            return Ok(path);
        }
        return Err(StudioError::SidecarStart(format!(
            "NOVEL_STUDIO_PYTHON points at {}, which is not a runnable interpreter",
            path.display()
        )));
    }

    let exe_dir = current_exe_dir();
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let mut candidates: Vec<PathBuf> = Vec::new();

    #[cfg(windows)]
    {
        // 1. the backend's virtualenv, wherever the backend was found
        candidates.push(backend_dir.join(".venv/Scripts/python.exe"));
        // 2. a Python bundled alongside the executable (release builds)
        candidates.push(exe_dir.join("python/python.exe"));
        // 3. the repository layout, relative to this crate
        candidates.push(manifest_dir.join("../../backend/.venv/Scripts/python.exe"));
    }

    #[cfg(not(windows))]
    {
        candidates.push(backend_dir.join(".venv/bin/python"));
        candidates.push(exe_dir.join("python/bin/python3"));
        candidates.push(manifest_dir.join("../../backend/.venv/bin/python"));
    }

    // 4. anything on PATH, probed (not assumed)
    candidates.push(PathBuf::from("python"));
    candidates.push(PathBuf::from("python3"));

    let mut attempted: Vec<String> = Vec::new();
    for candidate in &candidates {
        attempted.push(candidate.display().to_string());
        if is_usable_python(candidate) {
            return Ok(candidate.clone());
        }
    }

    Err(StudioError::SidecarStart(format!(
        "could not find a runnable Python interpreter.\nLooked at:\n  {}\nInstall Python 3.13+ or set NOVEL_STUDIO_PYTHON to the full path of python.exe.",
        attempted.join("\n  ")
    )))
}

/// Resolve the per-user data directory, creating it if needed.
pub fn resolve_data_dir() -> Result<PathBuf, StudioError> {
    let dir = match env_path("NOVEL_STUDIO_DATA_DIR") {
        Some(dir) => dir,
        None => {
            let base = directories::BaseDirs::new().ok_or_else(|| {
                StudioError::SidecarStart("could not determine the user data directory".into())
            })?;
            base.data_dir().join("AI Novel Studio")
        }
    };
    std::fs::create_dir_all(&dir)
        .map_err(|e| StudioError::SidecarStart(format!("cannot create {}: {e}", dir.display())))?;
    Ok(dir)
}

fn current_exe_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(Path::to_path_buf))
        .unwrap_or_else(|| PathBuf::from("."))
}

fn env_path(name: &str) -> Option<PathBuf> {
    std::env::var_os(name)
        .map(PathBuf::from)
        .filter(|path| !path.as_os_str().is_empty())
}

fn ensure_dir(dir: &Path, what: &str) -> Result<PathBuf, StudioError> {
    if !dir.is_dir() {
        return Err(StudioError::SidecarStart(format!(
            "{what} points at {}, which is not a directory",
            dir.display()
        )));
    }
    Ok(dir.to_path_buf())
}

/// Whether `path` names an interpreter we can actually run.
///
/// Existence is not enough: Windows ships `python3.exe` app-execution aliases in
/// `%LOCALAPPDATA%\\Microsoft\\WindowsApps` that exist on disk and exit with
/// code 9009. Probing with `-c` rejects them (and any broken install) up front.
fn is_usable_python(path: &Path) -> bool {
    if is_windows_store_alias(path) {
        return false;
    }
    std::process::Command::new(path)
        .arg("-c")
        .arg("import sys; print(sys.executable)")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

/// The Microsoft Store leaves `python.exe` / `python3.exe` stubs in WindowsApps.
#[cfg(windows)]
fn is_windows_store_alias(path: &Path) -> bool {
    path.components().any(|component| {
        component
            .as_os_str()
            .to_string_lossy()
            .to_lowercase()
            .contains("windowsapps")
    })
}

#[cfg(not(windows))]
fn is_windows_store_alias(_path: &Path) -> bool {
    false
}

/// Pick an unused local TCP port, with a manual fallback.
fn pick_port() -> Result<u16, StudioError> {
    if let Some(port) = portpicker::pick_unused_port() {
        return Ok(port);
    }
    let listener = std::net::TcpListener::bind("127.0.0.1:0").map_err(|e| {
        StudioError::PortAllocation(format!("could not bind an ephemeral port: {e}"))
    })?;
    let port = listener
        .local_addr()
        .map_err(|e| StudioError::PortAllocation(format!("could not read the local port: {e}")))?
        .port();
    drop(listener);
    Ok(port)
}

/// Build the `tokio::process::Command` for the backend.
fn build_command(resolved: &ResolvedPaths, port: u16, token: &str) -> Command {
    let mut command = Command::new(&resolved.python);
    command
        .arg("-m")
        .arg("app")
        .current_dir(&resolved.backend_dir)
        .env("NOVEL_STUDIO_HOST", "127.0.0.1")
        .env("NOVEL_STUDIO_PORT", port.to_string())
        .env("NOVEL_STUDIO_AUTH_TOKEN", token)
        .env("NOVEL_STUDIO_DATA_DIR", &resolved.data_dir)
        .env("NOVEL_STUDIO_ENVIRONMENT", "desktop")
        .env("NOVEL_STUDIO_LOG_JSON", "1")
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    // On Windows, keep the backend from flashing a console window and put it in
    // its own process group so we can signal (and reap) the whole tree instead
    // of leaving orphaned grandchildren behind.
    #[cfg(windows)]
    {
        // tokio's `Command` exposes `creation_flags` directly (and deprecates
        // the `std::os::windows::process::CommandExt` route).
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
        command.creation_flags(CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP);
    }

    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        unsafe {
            command.pre_exec(|| {
                setpgid(0, 0);
                Ok(())
            });
        }
    }

    command
}

#[cfg(unix)]
unsafe extern "C" {
    fn setpgid(pid: u32, pgid: u32) -> i32;
}

/// Spawn the backend and start the log/exit pumps.
async fn spawn_process(
    resolved: &ResolvedPaths,
    state: SidecarState,
) -> Result<Spawned, StudioError> {
    let port = pick_port()?;
    let token = uuid::Uuid::new_v4().simple().to_string();
    let mut command = build_command(resolved, port, &token);

    let mut child = command.spawn().map_err(|e| {
        StudioError::Spawn(format!(
            "could not start {} in {}: {e}",
            resolved.python.display(),
            resolved.backend_dir.display()
        ))
    })?;

    let pid = child.id().unwrap_or_default();
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();

    // Bind the child to a job object so it cannot outlive a crash, a force-kill
    // or a task-manager "end task". Without this, Windows keeps the Python
    // process (and its port) alive and the next launch fails.
    let job = ProcessJob::create();
    if let Some(job) = &job {
        if !job.assign(pid) {
            tracing::warn!(pid, "could not assign the sidecar to a job object");
        }
    }

    let (shutdown_tx, _) = broadcast::channel::<()>(SHUTDOWN_CAPACITY);
    let exited = Arc::new(AtomicBool::new(false));
    let exit_code = Arc::new(AtomicI32::new(-1));

    let stdout_task = spawn_pump(
        stdout,
        PumpKind::Stdout,
        shutdown_tx.subscribe(),
        state.clone(),
    );
    let stderr_task = spawn_pump(
        stderr,
        PumpKind::Stderr,
        shutdown_tx.subscribe(),
        state.clone(),
    );

    // The waiter owns the `Child`: it polls for exit while also listening for
    // the shutdown signal, and it is the only place the child is reaped.
    let waiter_exited = exited.clone();
    let waiter_exit_code = exit_code.clone();
    let waiter_state = state.clone();
    let mut waiter_shutdown = shutdown_tx.subscribe();
    tokio::spawn(async move {
        let status = tokio::select! {
            _ = waiter_shutdown.recv() => None,
            status = child.wait() => Some(status),
        };

        let final_status = match status {
            Some(status) => status,
            None => terminate(&mut child).await,
        };

        waiter_exited.store(true, Ordering::SeqCst);
        match final_status {
            Ok(status) => {
                // `code()` is None when the process was killed by a signal.
                waiter_exit_code.store(status.code().unwrap_or(-1), Ordering::SeqCst);
                waiter_state.push_log(format!("[shell] backend exited with {status}"));
                tracing::info!(pid, %status, "sidecar process exited");
            }
            Err(err) => {
                waiter_state.push_log(format!("[shell] backend wait failed: {err}"));
                tracing::warn!(pid, "waiting for sidecar failed: {err}");
            }
        }
    });

    state.push_log(format!("[shell] spawned pid {pid} on port {port}"));

    let handle = SidecarHandle {
        info: SidecarInfo {
            base_url: format!("http://127.0.0.1:{port}"),
            token: token.clone(),
            port,
            pid,
            started_at: Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true),
            status: "starting".into(),
        },
        shutdown: shutdown_tx,
        exited: exited.clone(),
        _job: job,
        stdout_task,
        stderr_task,
    };

    Ok(Spawned {
        pid,
        port,
        token,
        handle: Some(handle),
        exit_code,
    })
}

#[derive(Copy, Clone)]
enum PumpKind {
    Stdout,
    Stderr,
}

/// Stream one pipe into `tracing` and the in-memory ring buffer.
fn spawn_pump<R>(
    reader: Option<R>,
    kind: PumpKind,
    mut shutdown: broadcast::Receiver<()>,
    state: SidecarState,
) -> JoinHandle<()>
where
    R: tokio::io::AsyncRead + Unpin + Send + 'static,
{
    tokio::spawn(async move {
        let Some(reader) = reader else {
            return;
        };
        let mut lines = BufReader::new(reader).lines();
        loop {
            let next = tokio::select! {
                _ = shutdown.recv() => break,
                line = lines.next_line() => line,
            };
            match next {
                Ok(Some(line)) => {
                    let line = line.trim().to_string();
                    if line.is_empty() {
                        continue;
                    }
                    match kind {
                        PumpKind::Stdout => tracing::info!(target: "sidecar::stdout", "{line}"),
                        PumpKind::Stderr => tracing::warn!(target: "sidecar::stderr", "{line}"),
                    }
                    state.push_log(line);
                }
                Ok(None) => break,
                Err(err) => {
                    tracing::warn!(target: "sidecar", "failed reading backend output: {err}");
                    break;
                }
            }
        }
    })
}

thread_local! {
    /// Kept for diagnostics only: the pump tasks receive `state` explicitly,
    /// because a thread-local set on the setup thread is invisible to the
    /// multi-threaded runtime workers that run the pumps.
    static STATE: std::cell::RefCell<Option<SidecarState>> = const { std::cell::RefCell::new(None) };
}

/// Record the state on the calling thread. The pumps do not rely on this; it
/// exists so a debugging session can inspect the live supervisor.
pub fn install_state(state: SidecarState) {
    STATE.with(|slot| {
        *slot.borrow_mut() = Some(state);
    });
}

/// Return the state recorded on the calling thread, if any.
pub fn current_state() -> Option<SidecarState> {
    STATE.with(|slot| slot.borrow().clone())
}

/// What a `/api/health` body means.
enum Health {
    Ok,
    Starting,
    Other(String),
}

fn parse_health(body: &str) -> Health {
    match serde_json::from_str::<serde_json::Value>(body) {
        Ok(value) => match value.get("status").and_then(|status| status.as_str()) {
            Some("ok") => Health::Ok,
            Some("starting") => Health::Starting,
            Some(other) => Health::Other(other.to_string()),
            None => Health::Other("missing status".into()),
        },
        Err(_) => Health::Other("unparsable body".into()),
    }
}

impl SidecarState {
    /// Poll `/api/health` until the backend reports `ok`, the process dies, or
    /// the deadline passes.
    async fn wait_for_health(&self, spawned: Spawned) -> Result<SidecarInfo, StudioError> {
        let started = Instant::now();
        let base_url = format!("http://127.0.0.1:{}", spawned.port);
        let url = format!("{base_url}/api/health");

        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(3))
            .build()
            .map_err(|e| {
                StudioError::SidecarUnhealthy(format!("could not build http client: {e}"))
            })?;

        let mut last_detail = String::from("no response yet");
        let mut attempts: u32 = 0;
        // A backend that answers but is broken (e.g. an unhandled exception in
        // a middleware) returns 5xx forever. Waiting out the full boot budget
        // only delays a clear error, so abort once the failures persist.
        let mut failing_since: Option<Instant> = None;

        // The handle is kept alive here so the child is reaped on every exit.
        let mut handle = spawned.handle;

        while started.elapsed() < HEALTH_TIMEOUT {
            attempts += 1;

            if handle
                .as_ref()
                .map(|handle| handle.exited.load(Ordering::SeqCst))
                .unwrap_or(false)
            {
                let tail = self.log_tail(40);
                let code = spawned.exit_code.load(Ordering::SeqCst);
                // 9009 is the Windows cmd.exe errorlevel for "program not found".
                // It almost always means the interpreter resolved to a Microsoft
                // Store alias stub, which is useless to diagnose without saying so.
                let hint = match code {
                    9009 => "\n\n提示：退出码 9009 表示解释器无法执行（Windows 上常见于 Microsoft Store 的 python 占位符）。请安装 Python 3.13+ 并确保在 PATH 中，或把 NOVEL_STUDIO_PYTHON 设为真实 python.exe 的完整路径。",
                    _ => "",
                };
                return Err(StudioError::SidecarExited(format!(
                    "backend exited before becoming healthy (pid {}, code {}). Recent output:\n{tail}{hint}",
                    spawned.pid, code
                )));
            }

            match client
                .get(&url)
                .header(
                    reqwest::header::AUTHORIZATION,
                    format!("Bearer {}", spawned.token),
                )
                .send()
                .await
            {
                Ok(response) if response.status().is_success() => {
                    let body = response.text().await.unwrap_or_default();
                    match parse_health(&body) {
                        Health::Ok => {
                            let mut info = handle
                                .as_ref()
                                .map(|handle| handle.info.clone())
                                .unwrap_or_else(|| SidecarInfo {
                                    base_url: base_url.clone(),
                                    token: spawned.token.clone(),
                                    port: spawned.port,
                                    pid: spawned.pid,
                                    started_at: Utc::now()
                                        .to_rfc3339_opts(SecondsFormat::Secs, true),
                                    status: "ready".into(),
                                });
                            info.status = "ready".into();
                            self.push_log(format!(
                                "[shell] health check passed after {} attempts",
                                attempts + 1
                            ));

                            if let Some(mut handle) = handle.take() {
                                handle.info.status = "ready".into();
                                if let Ok(mut guard) = self.inner.lock() {
                                    *guard = Some(handle);
                                }
                            }
                            return Ok(info);
                        }
                        // The backend reports `starting` until its runtime is
                        // up; keep polling while the process is alive.
                        Health::Starting => last_detail = "starting".into(),
                        Health::Other(detail) => last_detail = detail,
                    }
                }
                Ok(response) if response.status().as_u16() == 401 => {
                    return Err(StudioError::SidecarUnhealthy(
                        "backend rejected the generated access token".into(),
                    ));
                }
                Ok(response) => {
                    let status = response.status();
                    if status.is_server_error() {
                        // Remember when the run of server errors began.
                        failing_since.get_or_insert(started);
                        last_detail = format!("http {status}");
                        if started.elapsed() >= SERVER_ERROR_BUDGET {
                            let tail = self.log_tail(40);
                            drop(handle.take());
                            force_kill(spawned.pid);
                            return Err(StudioError::SidecarUnhealthy(format!(
                                "backend kept returning {status} for {}s (pid {}). Recent output:\n{tail}",
                                SERVER_ERROR_BUDGET.as_secs(),
                                spawned.pid
                            )));
                        }
                    } else {
                        // Any non-5xx answer (including 401, handled above, and
                        // 4xx routing errors) resets the failure clock.
                        failing_since = None;
                        last_detail = format!("http {status}");
                    }
                }
                Err(err) if err.is_timeout() => last_detail = "request timed out".into(),
                Err(err) => last_detail = err.to_string(),
            }

            tokio::time::sleep(HEALTH_POLL_INTERVAL).await;
        }

        // Timeout: drop the handle (which reaps the child) and report the tail.
        drop(handle.take());
        force_kill(spawned.pid);
        let tail = self.log_tail(40);
        Err(StudioError::SidecarUnhealthy(format!(
            "backend did not report healthy within {}s (last status: {last_detail}, {attempts} attempts). Recent output:\n{tail}",
            HEALTH_TIMEOUT.as_secs()
        )))
    }
}

/// Persist a small handshake file the frontend can read on a cold start.
fn write_handshake(data_dir: &Path, info: &SidecarInfo) -> Result<(), StudioError> {
    let payload = serde_json::json!({
        "baseUrl": info.base_url,
        "token": info.token,
        "port": info.port,
        "pid": info.pid,
        "startedAt": info.started_at,
    });
    let path = data_dir.join(SIDECAR_FILE);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).ok();
    }
    std::fs::write(&path, serde_json::to_vec_pretty(&payload)?)
        .map_err(|e| StudioError::SidecarStart(format!("cannot write {}: {e}", path.display())))?;
    Ok(())
}

/// Best-effort removal of the handshake file.
fn remove_handshake() {
    if let Ok(data_dir) = resolve_data_dir() {
        let _ = std::fs::remove_file(data_dir.join(SIDECAR_FILE));
    }
}

/// Wait until `pid` is gone, or the timeout elapses.
async fn wait_for_exit(pid: u32, timeout: Duration) {
    if pid == 0 {
        return;
    }
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if !pid_alive(pid) {
            return;
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
}

/// Ask the OS to terminate a pid and its children.
fn force_kill(pid: u32) {
    if pid == 0 {
        return;
    }
    #[cfg(windows)]
    {
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .and_then(|mut child| child.wait());
    }
    #[cfg(unix)]
    {
        let _ = std::process::Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .status();
    }
}

/// Stop a child: wait out the grace period, then force-kill and reap.
async fn terminate(child: &mut Child) -> std::io::Result<std::process::ExitStatus> {
    match tokio::time::timeout(STOP_TIMEOUT, child.wait()).await {
        Ok(result) => result,
        Err(_) => {
            tracing::warn!("sidecar did not exit in time, killing it");
            let _ = child.start_kill();
            child.wait().await
        }
    }
}

/// Emit the ready event so the UI can swap off its splash screen.
pub fn emit_ready<R: tauri::Runtime>(app: &tauri::AppHandle<R>, info: &SidecarInfo) {
    if let Err(err) = app.emit(SIDECAR_READY_EVENT, info) {
        tracing::warn!("could not emit {SIDECAR_READY_EVENT}: {err}");
    }
}

/// Confirm a process is still alive (used by shutdown paths and tests).
pub fn pid_alive(pid: u32) -> bool {
    if pid == 0 {
        return false;
    }
    #[cfg(windows)]
    {
        std::process::Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/NH"])
            .stdin(Stdio::null())
            .output()
            .map(|out| String::from_utf8_lossy(&out.stdout).contains(&pid.to_string()))
            .unwrap_or(false)
    }
    #[cfg(unix)]
    {
        std::path::Path::new(&format!("/proc/{pid}")).exists()
    }
}
