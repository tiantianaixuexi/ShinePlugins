//! Commands the frontend can invoke over the Tauri IPC bridge.

pub mod system;

use std::sync::OnceLock;

use serde::Serialize;

/// Static information about the running desktop shell.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AppInfo {
    /// Version of the desktop shell.
    pub version: String,
    /// Version of the Tauri runtime the shell was built against.
    pub tauri_version: String,
    /// Per-user data directory the backend writes into.
    pub data_dir: String,
    /// Directory holding the Python backend (`app/` package).
    pub backend_dir: String,
    /// Interpreter used to start the backend.
    pub python_path: String,
    /// Operating system name, e.g. `windows`.
    pub os: String,
    /// Operating system version string.
    pub os_version: String,
    /// Machine architecture, e.g. `x86_64`.
    pub arch: String,
    /// Human-readable CPU brand, when available.
    pub cpu: Option<String>,
    /// Total physical memory in bytes.
    pub total_memory_bytes: u64,
    /// Number of logical CPU cores.
    pub logical_cpus: usize,
}

/// Host facts collected once per process.
#[derive(Debug, Clone)]
pub struct HostInfo {
    pub os: String,
    pub os_version: String,
    pub cpu: Option<String>,
    pub total_memory_bytes: u64,
    pub logical_cpus: usize,
}

/// Collect host information, caching the result.
///
/// `sysinfo` is intentionally asked for as little as possible: refreshing
/// everything (`refresh_all`) walks the process table, which is wasted work for
/// a static About panel. `MemoryRefreshKind::nothing()` plus a single CPU
/// refresh gives us the brand string without any of that.
pub fn host_info() -> HostInfo {
    static HOST: OnceLock<HostInfo> = OnceLock::new();
    HOST.get_or_init(collect_host_info).clone()
}

fn collect_host_info() -> HostInfo {
    let mut system = sysinfo::System::new_with_specifics(
        sysinfo::RefreshKind::nothing().with_cpu(sysinfo::CpuRefreshKind::nothing()),
    );
    system.refresh_memory();

    let cpu = system
        .cpus()
        .first()
        .map(|cpu| cpu.brand().trim().to_string())
        .filter(|brand| !brand.is_empty());

    HostInfo {
        os: sysinfo::System::name().unwrap_or_else(|| std::env::consts::OS.to_string()),
        os_version: sysinfo::System::long_os_version()
            .or_else(|| sysinfo::System::os_version())
            .unwrap_or_else(|| "unknown".to_string()),
        cpu,
        total_memory_bytes: system.total_memory(),
        logical_cpus: system.cpus().len(),
    }
}
