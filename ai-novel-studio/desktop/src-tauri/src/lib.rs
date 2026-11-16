//! AI Novel Studio desktop shell.
//!
//! The shell is deliberately thin: it owns a single Python sidecar process
//! (see [`sidecar`]), waits until that process answers an authenticated
//! `/api/health` probe, and only then lets the webview load the UI. The
//! sidecar's port and access token reach the frontend through the
//! `sidecar://ready` event and the `get_sidecar_info` command, so the webview
//! never has to guess either.

pub mod commands;
pub mod error;
pub mod process_job;
pub mod sidecar;

use std::sync::atomic::{AtomicBool, Ordering};

use tauri::menu::{Menu, MenuItem};
use tauri::{RunEvent, Runtime};
use tracing_subscriber::EnvFilter;

use crate::sidecar::SidecarState;

/// Set once the exit guard has run, so a duplicate exit event is harmless.
static EXIT_GUARDED: AtomicBool = AtomicBool::new(false);

/// Build and run the Tauri application. Does not return on success.
pub fn run() {
    setup_tracing();

    let state = SidecarState::new();
    sidecar::install_state(state.clone());

    let setup_state = state.clone();
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .manage(state.clone())
        .invoke_handler(tauri::generate_handler![
            commands::system::get_sidecar_info,
            commands::system::sidecar_logs,
            commands::system::restart_sidecar,
            commands::system::open_data_dir,
            commands::system::app_info,
        ])
        .setup(move |app| {
            let app_handle = app.handle().clone();

            // Best-effort window menu: cosmetic, but it gives the window a sane
            // system menu on Windows.
            if let Err(err) = install_menu(app) {
                tracing::warn!("could not install the application menu: {err}");
            }

            // Spawn the backend in the background so the window paints
            // immediately; the UI polls `get_sidecar_info` (or listens for
            // `sidecar://ready`) until the status flips to `ready`.
            let state_for_task = setup_state.clone();
            tauri::async_runtime::spawn(async move {
                match state_for_task.start().await {
                    Ok(info) => sidecar::emit_ready(&app_handle, &info),
                    Err(err) => {
                        // Also surfaced to the UI via `sidecar_logs`.
                        tracing::error!(%err, "sidecar failed to start");
                    }
                }
            });

            Ok(())
        });

    let app = builder
        .build(tauri::generate_context!())
        .expect("error while building the AI Novel Studio desktop shell");

    // Take ownership of the event loop so we can guarantee the Python sidecar
    // is stopped no matter how the application exits.
    run_with_exit_guard(app, state);
}

/// Run the event loop, stopping the sidecar on every exit path.
fn run_with_exit_guard<R: Runtime>(app: tauri::App<R>, state: SidecarState) {
    app.run(move |handle, event| match event {
        RunEvent::ExitRequested { .. } | RunEvent::Exit => {
            stop_once(&state);
        }
        RunEvent::WindowEvent {
            label,
            event: tauri::WindowEvent::Destroyed,
            ..
        } => {
            tracing::debug!(label, "window destroyed");
        }
        _ => {
            let _ = handle;
        }
    });
}

/// Stop the sidecar at most once per process.
fn stop_once(state: &SidecarState) {
    if EXIT_GUARDED.swap(true, Ordering::SeqCst) {
        return;
    }
    state.stop_blocking();
}

/// Install a minimal application menu.
fn install_menu<R: Runtime>(app: &tauri::App<R>) -> tauri::Result<()> {
    let quit = MenuItem::with_id(app, "quit", "Quit AI Novel Studio", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&quit])?;
    app.set_menu(menu)?;
    app.on_menu_event(|app, event| {
        if event.id().as_ref() == "quit" {
            app.exit(0);
        }
    });
    Ok(())
}

/// Initialise `tracing` with an env filter, defaulting to the shell's own logs.
fn setup_tracing() {
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| {
        EnvFilter::new("info,sidecar=info,sidecar::stdout=info,sidecar::stderr=info")
    });

    let _ = tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(true)
        .with_writer(std::io::stderr)
        .try_init();
}
