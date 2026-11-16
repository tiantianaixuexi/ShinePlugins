"""Per-project database access.

Every project owns an isolated ``database/novel.db``. Connections are cached
per project id so a long editing session reuses one engine/pool, and closed
when the project is closed or the application shuts down.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from app.core.logging import get_logger
from app.core.paths import project_db_path
from app.db.base import Base
from app.db.session import Database
from app.models.novel import (
    Chapter,
    ChapterVersion,
    Character,
    Event,
    Foreshadow,
    KnowledgeChunk,
    Outline,
    ProjectMeta,
    Volume,
)

logger = get_logger(__name__)

SCHEMA_VERSION_KEY = "schema_version"


def create_project_database(path: Path) -> Database:
    """Create (or open) a project database and bring it up to date.

    The stored schema version is owned exclusively by the migration runner, so
    callers must never stamp it themselves: doing so would make an un-migrated
    file look current.
    """
    database = Database(f"sqlite+pysqlite:///{path.as_posix()}", label=path.name)
    Base.metadata.create_all(database.engine)
    # Migrations run inside the database's own transaction; a backup is taken
    # first so a failed upgrade never costs the author their chapters.
    database.migrate("project_meta", backup_root=path.parent.parent)
    return database


def read_schema_version(database: Database) -> int:
    with database.session() as session:
        meta = session.get(ProjectMeta, SCHEMA_VERSION_KEY)
        if meta is None:
            return 0
        try:
            return int(meta.value)
        except ValueError:
            return 0


class ProjectDatabaseRegistry:
    """Cache of open project databases keyed by project id."""

    def __init__(self) -> None:
        self._databases: dict[str, Database] = {}

    def open(self, project_id: str, root: Path) -> Database:
        existing = self._databases.get(project_id)
        if existing is not None:
            return existing
        path = project_db_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        database = create_project_database(path)
        self._databases[project_id] = database
        logger.info("project_db_opened", project_id=project_id, path=str(path))
        return database

    def get(self, project_id: str) -> Database | None:
        return self._databases.get(project_id)

    def close(self, project_id: str) -> None:
        database = self._databases.pop(project_id, None)
        if database is not None:
            database.dispose()
            logger.info("project_db_closed", project_id=project_id)

    def close_all(self) -> None:
        for project_id in list(self._databases):
            self.close(project_id)


def collect_stats(database: Database) -> dict[str, int]:
    """Cheap aggregate counters for the dashboard and project cards."""
    with database.session() as session:
        scalar = session.execute(
            select(
                func.coalesce(func.sum(Chapter.word_count), 0),
                func.count(func.distinct(Chapter.id)),
            )
        ).one()

        return {
            "volumes": session.scalar(select(func.count()).select_from(Volume)) or 0,
            "chapters": int(scalar[1]),
            "words": int(scalar[0] or 0),
            "words_total": int(
                session.scalar(select(func.coalesce(func.sum(Chapter.word_count), 0))) or 0
            ),
            "characters": session.scalar(select(func.count()).select_from(Character)) or 0,
            "outlines": session.scalar(select(func.count()).select_from(Outline)) or 0,
            "events": session.scalar(select(func.count()).select_from(Event)) or 0,
            "foreshadows": session.scalar(select(func.count()).select_from(Foreshadow)) or 0,
            "chunks": session.scalar(select(func.count()).select_from(KnowledgeChunk)) or 0,
            "versions": session.scalar(select(func.count()).select_from(ChapterVersion)) or 0,
        }
