"""Application runtime object.

A single :class:`Runtime` owns the studio database, the per-project database
registry and the services built on top of them. It is created once per process
and attached to ``app.state`` so every request handler shares it.
"""

from __future__ import annotations

from app.ai.prompts.service import PromptService
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.migrations import read_version
from app.db.project_db import ProjectDatabaseRegistry
from app.db.session import Database
from app.services.agent_config_service import AgentConfigService
from app.services.ai_service import AIService
from app.services.model_config_service import ModelConfigService, ensure_default_model
from app.services.project_service import ProjectService

logger = get_logger(__name__)


class Runtime:
    """Process-wide service container."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_directories()

        self.studio_db = Database(self.settings.studio_db_url, label="studio")
        self.projects = ProjectDatabaseRegistry()
        self.project_service = ProjectService(
            self.studio_db,
            self.settings.projects_root,
            self.projects,
        )
        self.model_configs = ModelConfigService(self.studio_db, self.settings.data_dir)
        self.agent_configs = AgentConfigService(self.studio_db)
        self.prompts = PromptService(self.studio_db)
        self.ai = AIService(
            self.studio_db,
            self.project_service,
            self.model_configs,
            self.prompts,
            self.agent_configs,
        )
        self._started = False

    # -- lifecycle --------------------------------------------------------
    def start(self) -> None:
        """Create tables when missing and stamp the schema version."""
        from app.db.base import Base

        Base.metadata.create_all(self.studio_db.engine)
        self._migrate_studio()
        with self.studio_db.session() as session:
            ensure_default_model(session, self.model_configs)
        self.prompts.ensure_builtins()
        self._started = True
        logger.info(
            "runtime_started",
            data_dir=str(self.settings.data_dir),
            studio_db=str(self.settings.studio_db_path),
        )

    def stop(self) -> None:
        self.projects.close_all()
        self.studio_db.dispose()
        self._started = False
        logger.info("runtime_stopped")

    # -- helpers ----------------------------------------------------------
    def _migrate_studio(self) -> None:
        """Bring the registry database up to this build's schema."""
        applied = self.studio_db.migrate("app_meta", backup_root=self.settings.data_dir)
        if applied:
            logger.info("studio_migrations_applied", versions=applied)

    @property
    def is_started(self) -> bool:
        return self._started

    def schema_version(self) -> int:
        with self.studio_db.engine.begin() as connection:
            return read_version(connection, "app_meta")
