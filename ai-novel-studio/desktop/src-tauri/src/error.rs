//! Shared error type for the desktop shell.
//!
//! Every error the shell can surface is representable here and serialises to a
//! compact `{ code, message }` object so the frontend can branch on a stable
//! machine-readable string instead of parsing human text.

use serde::Serialize;

/// Error type used across the desktop shell.
#[derive(Debug, thiserror::Error)]
pub enum StudioError {
    /// The Python sidecar failed to start.
    #[error("failed to start the AI Novel Studio service: {0}")]
    SidecarStart(String),

    /// The sidecar process started but never reported healthy.
    #[error("the AI Novel Studio service did not become ready in time: {0}")]
    SidecarUnhealthy(String),

    /// The sidecar process exited while we were waiting for it.
    #[error("the AI Novel Studio service exited unexpectedly: {0}")]
    SidecarExited(String),

    /// Generic I/O failure.
    #[error("io error: {0}")]
    Io(String),

    /// Failed to spawn the sidecar process.
    #[error("could not spawn the service process: {0}")]
    Spawn(String),

    /// Could not allocate a local TCP port for the sidecar.
    #[error("could not allocate a port for the service: {0}")]
    PortAllocation(String),

    /// JSON (de)serialisation failure.
    #[error("serialization error: {0}")]
    Serialization(String),

    /// The sidecar was not running when an operation required it.
    #[error("the AI Novel Studio service is not running")]
    NotRunning,
}

impl StudioError {
    /// Stable machine-readable code exposed to the frontend.
    pub fn code(&self) -> &'static str {
        match self {
            StudioError::SidecarStart(_) => "sidecar_start",
            StudioError::SidecarUnhealthy(_) => "sidecar_unhealthy",
            StudioError::SidecarExited(_) => "sidecar_exited",
            StudioError::Io(_) => "io",
            StudioError::Spawn(_) => "spawn",
            StudioError::PortAllocation(_) => "port_allocation",
            StudioError::Serialization(_) => "serialization",
            StudioError::NotRunning => "not_running",
        }
    }
}

impl Serialize for StudioError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        use serde::ser::SerializeStruct;

        let mut state = serializer.serialize_struct("StudioError", 2)?;
        state.serialize_field("code", self.code())?;
        state.serialize_field("message", &self.to_string())?;
        state.end()
    }
}

impl From<std::io::Error> for StudioError {
    fn from(value: std::io::Error) -> Self {
        StudioError::Io(value.to_string())
    }
}

impl From<serde_json::Error> for StudioError {
    fn from(value: serde_json::Error) -> Self {
        StudioError::Serialization(value.to_string())
    }
}

impl From<tauri::Error> for StudioError {
    fn from(value: tauri::Error) -> Self {
        StudioError::Io(value.to_string())
    }
}
