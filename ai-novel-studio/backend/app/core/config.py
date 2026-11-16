"""Application configuration.

Everything the backend needs to know at start-up comes from :class:`Settings`.
Values are read from environment variables prefixed with ``NOVEL_STUDIO_`` so
the Tauri sidecar can inject its port and access token without touching disk:

    NOVEL_STUDIO_PORT=43117
    NOVEL_STUDIO_AUTH_TOKEN=<one-shot token>

User data (studio registry, per-project novels, logs) always lives under
``data_dir``; the desktop app passes an explicit directory when it wants an
isolated profile (tests, portable mode).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from platformdirs import user_data_dir
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "AI Novel Studio"
APP_SLUG = "ai-novel-studio"
SCHEMA_VERSION = 1

#: Origins the embedded webview is served from. Tauri 2 uses ``tauri://localhost``
#: on Windows/Android and ``http://tauri.localhost`` on some platforms.
DEFAULT_CORS_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
]


def default_data_dir() -> Path:
    """Platform specific per-user application data directory.

    On Windows this must be the *roaming* profile to match the Tauri shell's
    ``directories::BaseDirs::data_dir()``. Otherwise the desktop app and
    standalone Python tools (smoke scripts, CLI) silently use two different
    libraries, and a model saved in the UI is invisible to the latter.
    """
    return Path(user_data_dir(APP_NAME, appauthor=False, roaming=True))


class Settings(BaseSettings):
    """Runtime settings, overridable through ``NOVEL_STUDIO_*`` env vars."""

    model_config = SettingsConfigDict(
        env_prefix="NOVEL_STUDIO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- identity ---------------------------------------------------------
    app_name: str = APP_NAME
    app_version: str = "0.1.0"
    environment: str = Field(default="development")

    # -- http -------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8765
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))

    # -- storage ----------------------------------------------------------
    data_dir: Path = Field(default_factory=default_data_dir)
    studio_db_name: str = "studio.db"
    projects_dir_name: str = "NovelProjects"
    logs_dir_name: str = "logs"
    cache_dir_name: str = "cache"

    # -- security ---------------------------------------------------------
    #: Shared secret the desktop shell must present on every ``/api`` request.
    #: ``None`` disables auth, which is only acceptable for local tests.
    auth_token: str | None = Field(default=None)

    # -- limits -----------------------------------------------------------
    max_upload_bytes: int = 64 * 1024 * 1024
    default_embedding_batch_size: int = 32

    # -- logging ----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False

    @field_validator("data_dir", mode="after")
    @classmethod
    def _expand_data_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    # -- derived paths ----------------------------------------------------
    @property
    def studio_db_path(self) -> Path:
        return self.data_dir / self.studio_db_name

    @property
    def studio_db_url(self) -> str:
        return f"sqlite+pysqlite:///{self.studio_db_path.as_posix()}"

    @property
    def projects_root(self) -> Path:
        return self.data_dir / self.projects_dir_name

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / self.logs_dir_name

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / self.cache_dir_name

    @property
    def is_auth_enabled(self) -> bool:
        return bool(self.auth_token)

    def ensure_directories(self) -> None:
        """Create the data directories, tolerating concurrent creation."""
        for directory in (self.data_dir, self.projects_root, self.logs_dir, self.cache_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


def reset_settings_cache() -> None:
    """Drop the cached settings (tests only)."""
    get_settings.cache_clear()
