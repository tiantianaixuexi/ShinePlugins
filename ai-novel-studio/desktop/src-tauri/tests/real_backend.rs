//! Optional end-to-end test against the *real* Python backend.
//!
//! This is opt-in because it needs the backend's dependencies installed.
//! Run it with:
//!
//! ```text
//! NOVEL_STUDIO_TEST_PYTHON=<path to a python with the backend deps installed>
//! cargo test --test real_backend -- --nocapture --ignored
//! ```
//!
//! It is `#[ignore]`d by default so `cargo test` stays fast and hermetic.

use std::path::{Path, PathBuf};
use std::time::Duration;

use app_lib::sidecar::SidecarState;

/// Temporary directory that cleans itself up.
struct TempDir(PathBuf);

impl TempDir {
    fn new(tag: &str) -> Self {
        let unique = format!(
            "novel-studio-real-{tag}-{}-{}",
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

fn repo_backend_dir() -> PathBuf {
    // tests/ -> src-tauri/ -> desktop/ -> repo root
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../backend")
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
#[ignore = "requires the backend's Python dependencies; set NOVEL_STUDIO_TEST_PYTHON"]
async fn real_backend_becomes_healthy_and_stops_cleanly() {
    let python = std::env::var_os("NOVEL_STUDIO_TEST_PYTHON")
        .map(PathBuf::from)
        .expect("set NOVEL_STUDIO_TEST_PYTHON to a python that can import the backend");

    let backend = repo_backend_dir();
    assert!(
        backend.join("app/__main__.py").is_file(),
        "backend not found at {}",
        backend.display()
    );

    let data = TempDir::new("data");
    std::env::set_var("NOVEL_STUDIO_PYTHON", &python);
    std::env::set_var("NOVEL_STUDIO_BACKEND_DIR", &backend);
    std::env::set_var("NOVEL_STUDIO_DATA_DIR", data.path());

    let state = SidecarState::new();

    let info = state
        .start()
        .await
        .expect("the real backend should start and report healthy");

    println!("sidecar info: {info:?}");

    // The real /api/health is authenticated; unauthenticated calls are rejected.
    let client = reqwest::Client::new();
    let healthy = client
        .get(format!("{}/api/health", info.base_url))
        .header(
            reqwest::header::AUTHORIZATION,
            format!("Bearer {}", info.token),
        )
        .send()
        .await
        .expect("authenticated health request");
    assert_eq!(healthy.status().as_u16(), 200);
    let body: serde_json::Value = healthy.json().await.expect("health body");
    assert_eq!(body["status"].as_str(), Some("ok"));
    assert_eq!(body["app"].as_str(), Some("AI Novel Studio"));

    let denied = client
        .get(format!("{}/api/health", info.base_url))
        .send()
        .await
        .expect("unauthenticated health request");
    assert_eq!(
        denied.status().as_u16(),
        401,
        "the shell must pass a valid bearer token"
    );

    // The unauthenticated liveness marker must not need a token.
    let live = client
        .get(format!("{}/healthz", info.base_url))
        .send()
        .await
        .expect("healthz request");
    assert_eq!(live.status().as_u16(), 200);

    // The data dir the shell injected must be the one the backend used.
    let system: serde_json::Value = client
        .get(format!("{}/api/system/info", info.base_url))
        .header(
            reqwest::header::AUTHORIZATION,
            format!("Bearer {}", info.token),
        )
        .send()
        .await
        .expect("system info request")
        .json()
        .await
        .expect("system info body");
    assert_eq!(
        system["data_dir"].as_str(),
        Some(data.path().to_string_lossy().as_ref()),
        "the backend must honour NOVEL_STUDIO_DATA_DIR"
    );
    assert_eq!(system["auth_required"].as_bool(), Some(true));

    // sidecar.json is the fallback handshake for a cold-starting frontend.
    let handshake = data.path().join(app_lib::sidecar::SIDECAR_FILE);
    assert!(handshake.is_file(), "sidecar.json must be written");
    let raw = std::fs::read_to_string(&handshake).expect("read sidecar.json");
    let parsed: serde_json::Value = serde_json::from_str(&raw).expect("parse sidecar.json");
    assert_eq!(parsed["port"].as_u64(), Some(info.port as u64));
    assert_eq!(parsed["baseUrl"].as_str(), Some(info.base_url.as_str()));

    let logs = state.logs();
    println!("captured {} log lines", logs.len());
    assert!(!logs.is_empty(), "backend logs must be captured");

    let pid = info.pid;
    state.stop().await.expect("stop must succeed");

    let deadline = std::time::Instant::now() + Duration::from_secs(15);
    while std::time::Instant::now() < deadline && app_lib::sidecar::pid_alive(pid) {
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    assert!(
        !app_lib::sidecar::pid_alive(pid),
        "the backend process {pid} must not survive shutdown"
    );

    std::env::remove_var("NOVEL_STUDIO_PYTHON");
    std::env::remove_var("NOVEL_STUDIO_BACKEND_DIR");
    std::env::remove_var("NOVEL_STUDIO_DATA_DIR");
}
