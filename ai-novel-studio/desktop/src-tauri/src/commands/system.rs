//! Commands the frontend can invoke over the Tauri IPC bridge.
//!
//! Every command is a thin wrapper around [`crate::sidecar`]; the heavy lifting
//! (process supervision, port selection, health checks) lives there.

use tauri::{AppHandle, State};

use crate::commands::AppInfo;
use crate::error::StudioError;
use crate::sidecar::{self, SidecarInfo, SidecarState};

/// Return the current sidecar info, or a `stopped` snapshot.
#[tauri::command]
pub async fn get_sidecar_info(state: State<'_, SidecarState>) -> Result<SidecarInfo, StudioError> {
    Ok(state.info().unwrap_or_else(SidecarInfo::stopped))
}

/// Return the retained backend log tail.
#[tauri::command]
pub async fn sidecar_logs(state: State<'_, SidecarState>) -> Result<Vec<String>, StudioError> {
    Ok(state.logs())
}

/// Stop the sidecar and start a fresh one.
#[tauri::command]
pub async fn restart_sidecar(
    state: State<'_, SidecarState>,
    app: AppHandle,
) -> Result<SidecarInfo, StudioError> {
    let info = state.restart().await?;
    sidecar::emit_ready(&app, &info);
    Ok(info)
}

/// Reveal the per-user data directory in the system file manager.
#[tauri::command]
pub async fn open_data_dir(app: AppHandle) -> Result<(), StudioError> {
    let dir = sidecar::resolve_data_dir()?;
    open_path(&app, &dir).await
}

/// Report shell, host and environment information for the About panel.
///
/// The host details are collected once and cached: reading them is cheap but
/// not free, and the About panel never needs live values.
#[tauri::command]
pub async fn app_info(state: State<'_, SidecarState>) -> Result<AppInfo, StudioError> {
    let resolved = state.resolve()?;
    let host = crate::commands::host_info();
    Ok(AppInfo {
        version: env!("CARGO_PKG_VERSION").to_string(),
        tauri_version: tauri::VERSION.to_string(),
        data_dir: resolved.data_dir.to_string_lossy().into_owned(),
        backend_dir: resolved.backend_dir.to_string_lossy().into_owned(),
        python_path: resolved.python.to_string_lossy().into_owned(),
        os: host.os,
        os_version: host.os_version,
        arch: std::env::consts::ARCH.to_string(),
        cpu: host.cpu,
        total_memory_bytes: host.total_memory_bytes,
        logical_cpus: host.logical_cpus,
    })
}

/// Open a path with the system handler, preferring the opener plugin.
async fn open_path(app: &AppHandle, path: &std::path::Path) -> Result<(), StudioError> {
    let path = path.to_path_buf();
    let display = path.display().to_string();
    let app = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        use tauri_plugin_opener::OpenerExt;
        app.opener().reveal_item_in_dir(&path)
    })
    .await
    .map_err(|e| StudioError::Io(format!("open task failed: {e}")))?
    .map_err(|e| StudioError::Io(format!("could not open {display}: {e}")))
}
