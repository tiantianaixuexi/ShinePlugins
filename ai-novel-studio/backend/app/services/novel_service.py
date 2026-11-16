"""Volume / chapter / version operations for one project.

Every method takes the project id because each novel lives in its own
``novel.db``; the project registry resolves it to a cached
:class:`~app.db.session.Database`.

Versioning policy (keeps history useful without unbounded growth):

* an explicit save with ``snapshot=true`` always writes a version;
* autosaves snapshot at most once every :data:`SNAPSHOT_INTERVAL_SECONDS`;
* only the newest :data:`MAX_VERSIONS_PER_CHAPTER` versions are kept per chapter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.ids import new_id
from app.core.logging import get_logger
from app.db.project_db import collect_stats
from app.db.session import Database
from app.models.novel import Chapter, ChapterVersion, Volume
from app.schemas.novel import (
    ChapterAcceptAi,
    ChapterAcceptAiResult,
    ChapterCreate,
    ChapterListItem,
    ChapterOut,
    ChapterUpdate,
    ChapterVersionOut,
    VolumeCreate,
    VolumeOut,
    VolumeUpdate,
)
from app.services.project_service import ProjectService
from app.utils.text import count_words

logger = get_logger(__name__)

#: Minimum gap between automatic snapshots of the same chapter.
SNAPSHOT_INTERVAL_SECONDS = 300
#: Hard cap on stored versions per chapter.
MAX_VERSIONS_PER_CHAPTER = 60


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


class NovelService:
    def __init__(self, projects: ProjectService) -> None:
        self.projects = projects

    def database_for(self, project_id: str) -> Database:
        return self.projects.database_for(self.projects.get(project_id))

    # ------------------------------------------------------------------
    # Volumes
    # ------------------------------------------------------------------
    def list_volumes(self, project_id: str) -> list[Volume]:
        database = self.database_for(project_id)
        with database.session() as session:
            statement = select(Volume).order_by(Volume.sort_order, Volume.created_at)
            return list(session.scalars(statement))

    def create_volume(self, project_id: str, payload: VolumeCreate) -> Volume:
        database = self.database_for(project_id)
        with database.session() as session:
            next_order = int(session.scalar(select(func.max(Volume.sort_order))) or 0) + 1
            volume = Volume(
                id=new_id("vol"),
                project_id=project_id,
                title=payload.title.strip(),
                summary=payload.summary,
                sort_order=next_order,
            )
            session.add(volume)
            session.flush()
            logger.info("volume_created", project_id=project_id, volume_id=volume.id)
            return volume

    def update_volume(self, project_id: str, volume_id: str, payload: VolumeUpdate) -> Volume:
        database = self.database_for(project_id)
        with database.session() as session:
            volume = session.get(Volume, volume_id)
            if volume is None or volume.project_id != project_id:
                raise NotFound(f"Volume {volume_id} not found")

            if payload.row_version is not None and payload.row_version != volume.row_version:
                raise Conflict("Volume changed elsewhere; reload and retry.")

            for field in ("title", "summary", "sort_order"):
                value = getattr(payload, field)
                if value is not None:
                    setattr(volume, field, value)
            volume.row_version += 1
            volume.updated_at = _now()
            session.flush()
            return volume

    def delete_volume(self, project_id: str, volume_id: str) -> None:
        database = self.database_for(project_id)
        with database.session() as session:
            volume = session.get(Volume, volume_id)
            if volume is None or volume.project_id != project_id:
                raise NotFound(f"Volume {volume_id} not found")
            # Chapters must survive: detach them rather than cascade.
            session.execute(
                Chapter.__table__.update()
                .where(Chapter.volume_id == volume_id)
                .values(volume_id=None, updated_at=_now())
            )
            session.delete(volume)
            logger.info("volume_deleted", project_id=project_id, volume_id=volume_id)

    # ------------------------------------------------------------------
    # Chapters
    # ------------------------------------------------------------------
    def list_chapters(
        self,
        project_id: str,
        *,
        volume_id: str | None = None,
        include_deleted: bool = False,
    ) -> list[ChapterListItem]:
        database = self.database_for(project_id)
        with database.session() as session:
            statement = select(Chapter)
            if not include_deleted:
                statement = statement.where(Chapter.is_deleted.is_(False))
            if volume_id is not None:
                statement = statement.where(Chapter.volume_id == volume_id)
            statement = statement.order_by(Chapter.sort_order, Chapter.created_at)
            rows = list(session.scalars(statement))
            return [
                ChapterListItem(
                    id=row.id,
                    project_id=row.project_id,
                    volume_id=row.volume_id,
                    title=row.title,
                    sort_order=row.sort_order,
                    word_count=row.word_count,
                    status=row.status,
                    summary=row.summary,
                    is_deleted=row.is_deleted,
                    deleted_at=_as_utc(row.deleted_at) if row.deleted_at else None,
                    updated_at=_as_utc(row.updated_at),
                )
                for row in rows
            ]

    def get_chapter(self, project_id: str, chapter_id: str) -> ChapterOut:
        database = self.database_for(project_id)
        with database.session() as session:
            chapter = self._require_chapter(session, project_id, chapter_id)
            return self._to_chapter_out(chapter)

    def create_chapter(self, project_id: str, payload: ChapterCreate) -> ChapterOut:
        database = self.database_for(project_id)
        with database.session() as session:
            if payload.volume_id is not None:
                self._require_volume(session, project_id, payload.volume_id)
            next_order = int(session.scalar(select(func.max(Chapter.sort_order))) or 0) + 1
            chapter = Chapter(
                id=new_id("chap"),
                project_id=project_id,
                volume_id=payload.volume_id,
                title=payload.title.strip(),
                content=payload.content,
                word_count=count_words(payload.content),
                status=payload.status,
                sort_order=next_order,
                updated_at=_now(),
            )
            session.add(chapter)
            session.flush()
            if payload.content:
                self._write_version(session, chapter, source="user", note="创建章节")
            logger.info("chapter_created", project_id=project_id, chapter_id=chapter.id)
            return self._to_chapter_out(chapter)

    def update_chapter(
        self, project_id: str, chapter_id: str, payload: ChapterUpdate
    ) -> ChapterOut:
        database = self.database_for(project_id)
        with database.session() as session:
            chapter = self._require_chapter(session, project_id, chapter_id)

            if payload.row_version is not None and payload.row_version != chapter.row_version:
                raise Conflict(
                    "Chapter changed elsewhere; reload before saving.",
                    details={"expected": payload.row_version, "actual": chapter.row_version},
                )

            content_changed = False
            provided = payload.model_fields_set

            if "title" in provided and payload.title is not None:
                chapter.title = payload.title
            if "status" in provided and payload.status is not None:
                chapter.status = payload.status
            if "sort_order" in provided and payload.sort_order is not None:
                chapter.sort_order = payload.sort_order
            if "volume_id" in provided:
                # An explicit null detaches the chapter from its volume, so the
                # check must run on presence, not on truthiness.
                if payload.volume_id is not None:
                    self._require_volume(session, project_id, payload.volume_id)
                chapter.volume_id = payload.volume_id

            if payload.content is not None and payload.content != chapter.content:
                chapter.content = payload.content
                chapter.word_count = count_words(payload.content)
                # Content changed: the memory index is now stale.
                chapter.indexed_hash = None
                content_changed = True

            if content_changed:
                self._maybe_snapshot(session, chapter, force=payload.snapshot)
            elif payload.snapshot:
                self._write_version(session, chapter, source="user", note="手动快照")

            chapter.row_version += 1
            chapter.updated_at = _now()
            session.flush()
            return self._to_chapter_out(chapter)

    def delete_chapter(self, project_id: str, chapter_id: str) -> None:
        database = self.database_for(project_id)
        with database.session() as session:
            chapter = self._require_chapter(session, project_id, chapter_id)
            chapter.is_deleted = True
            chapter.deleted_at = _now()
            chapter.row_version += 1
            logger.info("chapter_deleted", project_id=project_id, chapter_id=chapter_id)

    def reorder_chapters(self, project_id: str, chapter_ids: list[str]) -> list[ChapterListItem]:
        database = self.database_for(project_id)
        with database.session() as session:
            rows = list(
                session.scalars(
                    select(Chapter)
                    .where(
                        Chapter.project_id == project_id,
                        Chapter.is_deleted.is_(False),
                    )
                    .order_by(Chapter.sort_order, Chapter.created_at)
                )
            )
            by_id = {row.id: row for row in rows}

            unknown = [cid for cid in chapter_ids if cid not in by_id]
            if unknown:
                raise ValidationFailed(
                    "Unknown chapter ids in reorder payload",
                    details={"unknown": unknown},
                )
            if len(set(chapter_ids)) != len(chapter_ids):
                raise ValidationFailed("Duplicate chapter ids in reorder payload")

            # Chapters the caller did not mention keep their relative order and
            # follow the listed ones, so sort_order stays a dense 0..n-1 range.
            ordered = list(chapter_ids)
            ordered.extend(row.id for row in rows if row.id not in set(chapter_ids))

            for position, chapter_id in enumerate(ordered):
                chapter = by_id[chapter_id]
                chapter.sort_order = position
                chapter.updated_at = _now()
        return self.list_chapters(project_id)

    # ------------------------------------------------------------------
    # Versions
    # ------------------------------------------------------------------
    def list_versions(self, project_id: str, chapter_id: str) -> list[ChapterVersionOut]:
        database = self.database_for(project_id)
        with database.session() as session:
            self._require_chapter(session, project_id, chapter_id)
            rows = session.scalars(
                select(ChapterVersion)
                .where(ChapterVersion.chapter_id == chapter_id)
                .order_by(ChapterVersion.version_no.desc())
            )
            return [self._to_version_out(row) for row in rows]

    def snapshot_chapter(
        self, project_id: str, chapter_id: str, note: str = ""
    ) -> list[ChapterVersionOut]:
        database = self.database_for(project_id)
        with database.session() as session:
            chapter = self._require_chapter(session, project_id, chapter_id)
            self._write_version(session, chapter, source="user", note=note or "手动快照")
            session.flush()
        return self.list_versions(project_id, chapter_id)

    def restore_version(self, project_id: str, chapter_id: str, version_id: str) -> ChapterOut:
        database = self.database_for(project_id)
        with database.session() as session:
            chapter = self._require_chapter(session, project_id, chapter_id)
            version = session.get(ChapterVersion, version_id)
            if version is None or version.chapter_id != chapter_id:
                raise NotFound(f"Version {version_id} not found for this chapter")

            # Keep the current text recoverable before overwriting it.
            self._write_version(
                session, chapter, source="restore", note=f"恢复前快照（来自 v{version.version_no}）"
            )
            chapter.title = version.title or chapter.title
            chapter.content = version.content
            chapter.word_count = count_words(version.content)
            chapter.indexed_hash = None
            chapter.row_version += 1
            chapter.updated_at = _now()
            session.flush()
            logger.info(
                "chapter_restored",
                project_id=project_id,
                chapter_id=chapter_id,
                version_no=version.version_no,
            )
            return self._to_chapter_out(chapter)

    def accept_ai(
        self, project_id: str, chapter_id: str, payload: ChapterAcceptAi
    ) -> ChapterAcceptAiResult:
        """Adopt AI text as the chapter body without losing the blood-line.

        Order matters and is the whole point of this method:

        1. snapshot the *current* text as ``source="user"`` (protect the scene),
        2. overwrite the chapter (only then is the old text gone),
        3. record the new text as ``source="ai"`` carrying ``task_id``.

        Autosave and restore keep their own policies; this is the only path that
        writes ``chapter_versions.source = 'ai'``.
        """
        database = self.database_for(project_id)
        with database.session() as session:
            chapter = self._require_chapter(session, project_id, chapter_id)

            # 1. The pre-accept manuscript stays recoverable.
            self._write_version(session, chapter, source="user", note="采纳 AI 前的原文")

            # 2. Adopt the accepted text.
            chapter.content = payload.content
            chapter.word_count = count_words(payload.content)
            chapter.indexed_hash = None
            if payload.title is not None:
                chapter.title = payload.title
            chapter.row_version += 1
            chapter.updated_at = _now()
            session.flush()

            # 3. Provenance of the accepted text.
            version = self._write_version(
                session,
                chapter,
                source="ai",
                task_id=payload.task_id,
                note=payload.note or "AI 采纳",
            )
            logger.info(
                "chapter_ai_accepted",
                project_id=project_id,
                chapter_id=chapter_id,
                task_id=payload.task_id,
                version_no=version.version_no,
            )
            return ChapterAcceptAiResult(
                chapter=self._to_chapter_out(chapter),
                version=self._to_version_out(version),
            )

    # ------------------------------------------------------------------
    # Stats / helpers
    # ------------------------------------------------------------------
    def stats(self, project_id: str) -> dict[str, int]:
        return collect_stats(self.database_for(project_id))

    def _require_chapter(self, session: Session, project_id: str, chapter_id: str) -> Chapter:
        chapter = session.get(Chapter, chapter_id)
        if chapter is None or chapter.is_deleted or chapter.project_id != project_id:
            raise NotFound(f"Chapter {chapter_id} not found")
        return chapter

    def _require_volume(self, session: Session, project_id: str, volume_id: str) -> Volume:
        """Reject a volume that does not exist in *this* project (422, not 500)."""
        volume = session.get(Volume, volume_id)
        if volume is None or volume.project_id != project_id:
            raise ValidationFailed(
                "volume_id does not belong to this project",
                details={"volume_id": volume_id, "project_id": project_id},
            )
        return volume

    def _to_chapter_out(self, chapter: Chapter) -> ChapterOut:
        return ChapterOut(
            id=chapter.id,
            project_id=chapter.project_id,
            volume_id=chapter.volume_id,
            title=chapter.title,
            sort_order=chapter.sort_order,
            word_count=chapter.word_count,
            status=chapter.status,
            summary=chapter.summary,
            updated_at=_as_utc(chapter.updated_at),
            content=chapter.content,
            row_version=chapter.row_version,
            created_at=_as_utc(chapter.created_at),
        )

    def _to_version_out(self, version: ChapterVersion) -> ChapterVersionOut:
        return ChapterVersionOut(
            id=version.id,
            chapter_id=version.chapter_id,
            version_no=version.version_no,
            title=version.title,
            word_count=version.word_count,
            source=version.source,
            task_id=version.task_id,
            note=version.note,
            created_at=_as_utc(version.created_at),
        )

    def _write_version(
        self,
        session: Session,
        chapter: Chapter,
        *,
        source: str,
        task_id: str | None = None,
        note: str = "",
    ) -> ChapterVersion:
        newest_no = int(
            session.scalar(
                select(func.max(ChapterVersion.version_no)).where(
                    ChapterVersion.chapter_id == chapter.id
                )
            )
            or 0
        )
        version = ChapterVersion(
            id=new_id("ver"),
            project_id=chapter.project_id,
            chapter_id=chapter.id,
            version_no=newest_no + 1,
            title=chapter.title,
            content=chapter.content,
            word_count=chapter.word_count,
            source=source,
            task_id=task_id,
            note=note,
            created_at=_now(),
        )
        session.add(version)
        session.flush()
        self._prune_versions(session, chapter.id)
        return version

    def _maybe_snapshot(
        self, session: Session, chapter: Chapter, *, force: bool
    ) -> ChapterVersion | None:
        if not chapter.content:
            return None
        newest = session.scalar(
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id == chapter.id)
            .order_by(ChapterVersion.version_no.desc())
            .limit(1)
        )
        if newest is not None:
            if newest.content == chapter.content:
                return None
            if not force:
                age = (_now() - _as_utc(newest.created_at)).total_seconds()
                if age < SNAPSHOT_INTERVAL_SECONDS:
                    return None
        return self._write_version(session, chapter, source="user", note="自动保存")

    def _prune_versions(self, session: Session, chapter_id: str) -> None:
        rows = list(
            session.scalars(
                select(ChapterVersion)
                .where(ChapterVersion.chapter_id == chapter_id)
                .order_by(ChapterVersion.version_no.desc())
                .offset(MAX_VERSIONS_PER_CHAPTER)
            )
        )
        if not rows:
            return
        session.execute(
            delete(ChapterVersion).where(ChapterVersion.id.in_([row.id for row in rows]))
        )
        logger.info("versions_pruned", chapter_id=chapter_id, removed=len(rows))

    # ------------------------------------------------------------------
    # Bulk helpers used by import
    # ------------------------------------------------------------------
    def append_chapters(self, project_id: str, chapters: list[dict[str, Any]]) -> list[ChapterOut]:
        """Insert an ordered list of chapters (used by TXT/DOCX import)."""
        database = self.database_for(project_id)
        created: list[Chapter] = []
        with database.session() as session:
            base = int(session.scalar(select(func.max(Chapter.sort_order))) or 0)
            for offset, item in enumerate(chapters, start=1):
                content = str(item.get("content", ""))
                chapter = Chapter(
                    id=new_id("chap"),
                    project_id=project_id,
                    title=str(item.get("title") or f"第 {base + offset} 章"),
                    content=content,
                    word_count=count_words(content),
                    status="draft",
                    sort_order=base + offset,
                    updated_at=_now(),
                )
                session.add(chapter)
                created.append(chapter)
            session.flush()
        return [self.get_chapter(project_id, chapter.id) for chapter in created]


def volumes_to_out(rows: list[Volume]) -> list[VolumeOut]:
    return [VolumeOut.model_validate(row) for row in rows]
