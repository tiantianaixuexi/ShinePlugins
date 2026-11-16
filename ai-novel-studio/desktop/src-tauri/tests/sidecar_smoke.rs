//! End-to-end smoke test for the sidecar supervisor.
//!
//! The real Python backend depends on FastAPI and friends, which are not
//! installed in CI, so this test generates a tiny stdlib-only `app` package
//! that behaves like the real one: `python -m app` binds an ephemeral port,
//! requires `Authorization: Bearer <token>`, and answers `/api/health` with
//! `{"status": "ok"}`.
//!
//! That is exactly the contract `sidecar.rs` relies on, so the test exercises
//! the real spawn / poll / handshake / shutdown paths.

use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard, OnceLock};
use std::time::Duration;

use app_lib::sidecar::SidecarState;

/// The sidecar is configured through process-wide environment variables, so the
/// tests that set them must not run concurrently.
fn env_lock() -> MutexGuard<'static, ()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// A temporary directory that removes itself on drop.
struct TempDir(PathBuf);

impl TempDir {
    fn new(tag: &str) -> Self {
        let unique = format!(
            "novel-studio-sidecar-{tag}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or_default()
        );
        let path = std::env::temp_dir().join(unique);
        std::fs::create_dir_all(&path).expect("create temp dir");
        Self(path)
    }

    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// Write a minimal `python -m app` stand-in.
fn write_mock_backend(root: &Path) {
    let app_dir = root.join("app");
    std::fs::create_dir_all(&app_dir).expect("create app package");
    std::fs::write(app_dir.join("__init__.py"), "").expect("write __init__");

    std::fs::write(
        app_dir.join("__main__.py"),
        r#"
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("NOVEL_STUDIO_AUTH_TOKEN", "")
PORT = int(os.environ.get("NOVEL_STUDIO_PORT", "0"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {TOKEN}":
            self._send(401, {"error": {"code": "auth_required"}})
            return
        if self.path == "/api/health":
            self._send(200, {"status": "ok", "app": "AI Novel Studio", "version": "0.1.0"})
            return
        self._send(404, {"error": {"code": "not_found"}})


server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
print("mock backend listening", flush=True)
server.serve_forever()
"#,
    )
    .expect("write __main__");
}

/// Point the shell at a fake python + backend via the documented overrides.
fn use_mock_env(backend: &Path, python: &Path, data: &Path) {
    std::env::set_var("NOVEL_STUDIO_BACKEND_DIR", backend);
    std::env::set_var("NOVEL_STUDIO_PYTHON", python);
    std::env::set_var("NOVEL_STUDIO_DATA_DIR", data);
}

fn python_exe() -> PathBuf {
    std::env::var_os("NOVEL_STUDIO_TEST_PYTHON")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("python"))
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn sidecar_starts_becomes_healthy_and_stops_cleanly() {
    let _guard = env_lock();
    let temp = TempDir::new("happy");
    let backend = temp.path().join("backend");
    let data = temp.path().join("data");
    std::fs::create_dir_all(&backend).expect("create backend dir");
    std::fs::create_dir_all(&data).expect("create data dir");
    write_mock_backend(&backend);
    use_mock_env(&backend, &python_exe(), &data);

    let state = SidecarState::new();

    // -- start ------------------------------------------------------------
    let info = state
        .start()
        .await
        .expect("sidecar should start and become healthy");

    assert!(!info.base_url.is_empty(), "base_url should be set");
    assert_eq!(info.base_url, format!("http://127.0.0.1:{}", info.port));
    assert!(info.port > 0, "port should be allocated");
    assert_eq!(info.token.len(), 32, "uuid simple token is 32 hex chars");
    assert_eq!(info.status, "ready");
    assert!(info.pid > 0, "pid should be known");
    assert!(!info.started_at.is_empty(), "started_at should be RFC 3339");
    assert!(chrono::DateTime::parse_from_rfc3339(&info.started_at).is_ok());

    // -- the token actually authenticates against the backend -------------
    let client = reqwest::Client::new();
    let ok = client
        .get(format!("{}/api/health", info.base_url))
        .header(
            reqwest::header::AUTHORIZATION,
            format!("Bearer {}", info.token),
        )
        .send()
        .await
        .expect("health request");
    assert_eq!(ok.status().as_u16(), 200);
    let body: serde_json::Value = ok.json().await.expect("health json");
    assert_eq!(body["status"], "ok");

    // A request without the token must be rejected (proves the token is live).
    let denied = client
        .get(format!("{}/api/health", info.base_url))
        .send()
        .await
        .expect("unauthenticated health request");
    assert_eq!(denied.status().as_u16(), 401, "token must be enforced");

    // -- diagnostics handshake ------------------------------------------
    let handshake_path = data.join(app_lib::sidecar::SIDECAR_FILE);
    assert!(
        handshake_path.is_file(),
        "sidecar.json should be written to the data dir"
    );
    let handshake: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&handshake_path).expect("read sidecar.json"))
            .expect("parse sidecar.json");
    assert_eq!(handshake["port"].as_u64(), Some(info.port as u64));
    assert_eq!(handshake["token"].as_str(), Some(info.token.as_str()));

    // -- logs ------------------------------------------------------------
    let logs = state.logs();
    assert!(
        logs.iter().any(|line| line.contains("spawned")),
        "logs should mention the spawn, got: {logs:?}"
    );

    // -- stop ------------------------------------------------------------
    let pid = info.pid;
    state.stop().await.expect("stop should succeed");

    let deadline = std::time::Instant::now() + Duration::from_secs(10);
    while std::time::Instant::now() < deadline && app_lib::sidecar::pid_alive(pid) {
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    assert!(
        !app_lib::sidecar::pid_alive(pid),
        "backend process {pid} must not survive shutdown"
    );

    // State is cleared, so info() reports None and start() works again.
    assert!(state.info().is_none(), "state should be cleared after stop");
    assert!(
        !handshake_path.exists(),
        "sidecar.json should be removed on stop"
    );

    clear_mock_env();
}

/// Remove the overrides set by [`use_mock_env`] so they cannot leak.
fn clear_mock_env() {
    std::env::remove_var("NOVEL_STUDIO_BACKEND_DIR");
    std::env::remove_var("NOVEL_STUDIO_PYTHON");
    std::env::remove_var("NOVEL_STUDIO_DATA_DIR");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn start_fails_fast_when_the_process_dies_immediately() {
    let _guard = env_lock();
    let temp = TempDir::new("broken");
    let backend = temp.path().join("backend");
    let data = temp.path().join("data");
    std::fs::create_dir_all(&backend).expect("create backend dir");
    std::fs::create_dir_all(&data).expect("create data dir");

    // A package whose __main__ exits immediately with an error message.
    let app_dir = backend.join("app");
    std::fs::create_dir_all(&app_dir).expect("create app package");
    std::fs::write(app_dir.join("__init__.py"), "").expect("write __init__");
    std::fs::write(
        app_dir.join("__main__.py"),
        "import sys\nsys.stderr.write('boom: cannot start\\n')\nsys.exit(3)\n",
    )
    .expect("write __main__");

    use_mock_env(&backend, &python_exe(), &data);

    let state = SidecarState::new();
    let err = state
        .start()
        .await
        .expect_err("start must fail when the backend dies");

    // The error must be the SidecarExited variant, carrying the log tail.
    let message = err.to_string();
    assert!(
        message.contains("exited") || message.contains("healthy"),
        "unexpected error: {message}"
    );
    assert_eq!(err.code(), "sidecar_exited");
    assert!(
        message.contains("boom") || message.contains("Recent output"),
        "error should include the captured backend output, got: {message}"
    );

    // No stale state, and the diagnostic file was not left behind.
    assert!(state.info().is_none());
    assert!(!data.join(app_lib::sidecar::SIDECAR_FILE).exists());

    clear_mock_env();
}

#[test]
fn missing_backend_dir_reports_a_clear_error() {
    let _guard = env_lock();
    let temp = TempDir::new("nodir");
    std::env::set_var(
        "NOVEL_STUDIO_BACKEND_DIR",
        temp.path().join("does-not-exist"),
    );
    // The other overrides must not matter for this assertion.
    std::env::set_var("NOVEL_STUDIO_PYTHON", python_exe());
    std::env::set_var("NOVEL_STUDIO_DATA_DIR", temp.path().join("data"));

    let err = app_lib::sidecar::resolve_backend_dir().expect_err("must fail");
    assert_eq!(err.code(), "sidecar_start");
    assert!(
        err.to_string().contains("not a directory"),
        "unexpected message: {err}"
    );

    std::env::remove_var("NOVEL_STUDIO_BACKEND_DIR");
    std::env::remove_var("NOVEL_STUDIO_PYTHON");
    std::env::remove_var("NOVEL_STUDIO_DATA_DIR");
}
