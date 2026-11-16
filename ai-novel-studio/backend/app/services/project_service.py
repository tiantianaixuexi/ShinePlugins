"""Project lifecycle: create, open, update, duplicate, delete.

The studio registry (``studio.db``) is the source of truth; the on-disk
``project.json`` is a portable mirror written on every change so a project
directory can be copied or archived without the registry.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.ids import new_id, project_dir_name, slugify
from app.core.logging import get_logger
from app.core.paths import (
    ensure_project_layout,
    ensure_within,
    project_db_path,
    remove_project_dir,
    write_manifest,
)
from app.db.project_db import ProjectDatabaseRegistry, collect_stats, create_project_database
from app.db.session import Database
from app.models.studio import Project
from app.schemas.project import ProjectCreate, ProjectUpdate

logger = get_logger(__name__)

#: Fields copied straight from a schema object onto the ORM row.
_COPYABLE_FIELDS = (
    "name",
    "novel_type",
    "synopsis",
    "target_word_count",
    "target_chapter_count",
    "writing_style",
    "target_reader",
    "language",
    "author",
    "status",
    "default_model_config_id",
    "embedding_model_config_id",
    "settings",
)

#: Columns that accept ``null``; every other column treats ``None`` as "no change".
NULLABLE_FIELDS = frozenset({"default_model_config_id", "embedding_model_config_id"})


class ProjectService:
    """All project mutations funnel through here so invariants stay in one place."""

    def __init__(
        self,
        studio_db: Database,
        projects_root: Path,
        registry: ProjectDatabaseRegistry,
    ) -> None:
        self.studio_db = studio_db
        self.projects_root = projects_root
        self.registry = registry

    # -- queries ----------------------------------------------------------
    def list(
        self, *, include_deleted: bool = False, limit: int = 200, offset: int = 0
    ) -> list[Project]:
        with self.studio_db.session() as session:
            statement = (
                select(Project).order_by(Project.updated_at.desc()).limit(limit).offset(offset)
            )
            if not include_deleted:
                statement = statement.where(Project.is_deleted.is_(False))
            return list(session.scalars(statement))

    def get(self, project_id: str, *, include_deleted: bool = False) -> Project:
        with self.studio_db.session() as session:
            project = session.get(Project, project_id)
            if project is None or (project.is_deleted and not include_deleted):
                raise NotFound(f"Project {project_id} not found")
            return project

    def find_by_slug(self, slug: str) -> Project | None:
        with self.studio_db.session() as session:
            return session.scalar(
                select(Project).where(Project.slug == slug, Project.is_deleted.is_(False))
            )

    def exists(self, project_id: str) -> bool:
        with self.studio_db.session() as session:
            project = session.get(Project, project_id)
            return project is not None and not project.is_deleted

    def count(self) -> int:
        with self.studio_db.session() as session:
            return int(
                session.scalar(
                    select(func.count()).select_from(Project).where(Project.is_deleted.is_(False))
                )
                or 0
            )

    # -- mutations --------------------------------------------------------
    def create(self, payload: ProjectCreate) -> Project:
        project_id = new_id("proj")
        directory = self.projects_root / project_dir_name(payload.name, project_id)
        if directory.exists():
            raise Conflict(f"Project directory already exists: {directory.name}")

        ensure_within(self.projects_root, directory)
        try:
            ensure_project_layout(directory)
            # Dispose immediately: on Windows an open SQLite handle would keep
            # the directory locked and break later copies or hard deletes.
            create_project_database(project_db_path(directory)).dispose()
        except OSError as exc:
            remove_project_dir(directory)
            raise ValidationFailed(f"Cannot create project directory: {exc}") from exc

        values: dict[str, Any] = {
            "id": project_id,
            "slug": slugify(payload.name) or project_id,
            "path": str(directory),
            "schema_version": 1,
        }
        for field in _COPYABLE_FIELDS:
            values[field] = getattr(payload, field, None)

        with self.studio_db.session() as session:
            project = Project(**values)
            session.add(project)
            session.flush()
            self._write_manifest(session, project)
            session.refresh(project)
            logger.info("project_created", project_id=project.id, name=project.name)
            return project

    def update(self, project_id: str, payload: ProjectUpdate) -> Project:
        with self.studio_db.session() as session:
            project = session.get(Project, project_id)
            if project is None or project.is_deleted:
                raise NotFound(f"Project {project_id} not found")

            if payload.row_version is not None and payload.row_version != project.row_version:
                raise Conflict(
                    "Project was modified by someone else; reload and try again.",
                    details={"expected": payload.row_version, "actual": project.row_version},
                )

            changes = payload.model_dump(exclude_unset=True, exclude={"row_version"})
            for field, value in changes.items():
                # ``None`` means "leave unchanged" for non-nullable columns;
                # only the two optional model links can be cleared explicitly.
                if field not in _COPYABLE_FIELDS:
                    continue
                if value is None and field not in NULLABLE_FIELDS:
                    continue
                setattr(project, field, value)

            project.row_version += 1
            project.updated_at = datetime.now(UTC)
            session.flush()
            self._write_manifest(session, project)
            session.refresh(project)
            logger.info("project_updated", project_id=project.id, fields=sorted(changes))
            return project

    def delete(self, project_id: str, *, hard: bool = False) -> None:
        """Soft delete by default; ``hard=True`` also removes the directory."""
        with self.studio_db.session() as session:
            project = session.get(Project, project_id)
            if project is None:
                raise NotFound(f"Project {project_id} not found")

            target = Path(project.path)
            ensure_within(self.projects_root, target)

            if hard:
                session.delete(project)
                session.flush()
                self.registry.close(project_id)
                remove_project_dir(target)
                logger.info("project_hard_deleted", project_id=project_id, path=str(target))
                return

            project.is_deleted = True
            project.deleted_at = datetime.now(UTC)
            project.status = "deleted"
            project.row_version += 1
            session.flush()
            self.registry.close(project_id)
            logger.info("project_soft_deleted", project_id=project_id)

    def duplicate(self, project_id: str, new_name: str) -> Project:
        source = self.get(project_id)
        source_dir = Path(source.path)
        if not source_dir.exists():
            raise ValidationFailed(f"Project directory is missing on disk: {source.path}")

        payload = ProjectCreate(
            name=new_name,
            novel_type=source.novel_type,
            synopsis=source.synopsis,
            target_word_count=source.target_word_count,
            target_chapter_count=source.target_chapter_count,
            writing_style=source.writing_style,
            target_reader=source.target_reader,
            language=source.language,
            author=source.author,
            settings=dict(source.settings or {}),
        )
        created = self.create(payload)

        # Fold the WAL into the main database file first, otherwise the copy
        # would drop the most recent chapters.
        try:
            self.database_for(source).checkpoint()
        except (OSError, RuntimeError) as exc:  # pragma: no cover - defensive
            logger.warning("checkpoint_failed", project_id=source.id, error=str(exc))

        self.registry.close(created.id)
        created_dir = Path(created.path)
        shutil.rmtree(created_dir, ignore_errors=True)
        shutil.copytree(source_dir, created_dir)
        logger.info("project_duplicated", source=project_id, target=created.id)
        return self.get(created.id)

    # -- per project database --------------------------------------------
    def database_for(self, project: Project) -> Database:
        root = Path(project.path)
        ensure_within(self.projects_root, root)
        return self.registry.open(project.id, root)

    def stats_for(self, project: Project) -> dict[str, int]:
        root = Path(project.path)
        if not root.exists():
            return {}
        try:
            database = self.registry.open(project.id, root)
        except OSError as exc:
            logger.warning("project_stats_failed", project_id=project.id, error=str(exc))
            return {}
        return collect_stats(database)

    # -- helpers ----------------------------------------------------------
    def _write_manifest(self, session: Session, project: Project) -> None:
        payload = {
            "id": project.id,
            "name": project.name,
            "slug": project.slug,
            "novel_type": project.novel_type,
            "synopsis": project.synopsis,
            "target_word_count": project.target_word_count,
            "target_chapter_count": project.target_chapter_count,
            "writing_style": project.writing_style,
            "target_reader": project.target_reader,
            "language": project.language,
            "author": project.author,
            "status": project.status,
            "schema_version": project.schema_version,
            "row_version": project.row_version,
            "settings": project.settings or {},
            "updated_at": datetime.now(UTC).isoformat(),
            "generator": "ai-novel-studio",
        }
        try:
            write_manifest(Path(project.path), payload)
        except OSError as exc:  # a read-only volume must not break editing
            logger.warning("manifest_write_failed", project_id=project.id, error=str(exc))
