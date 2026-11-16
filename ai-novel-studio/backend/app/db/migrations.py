"""Schema migration runner for both databases.

Two databases evolve independently:

* ``studio.db`` — the registry, migrated when the backend starts;
* ``<project>/database/novel.db`` — migrated when that project is opened.

Design rules (the manuscript is the user's asset, so migrations must be safe):

1. **Never downgrade.** A file written by a newer build is refused loudly rather
   than partially read.
2. **Back up before changing.** Every migration run snapshots the database first.
3. **One transaction.** A failed migration rolls back and leaves the old version
   stamped, so the next start retries from the same point.
4. **Stamp per step.** The version advances only after a migration succeeds.

Adding a schema change is a two-line job::

    @migration(2)
    def add_outline_index(connection: Connection) -> None:
        connection.execute(text("CREATE INDEX ..."))
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Connection, text

from app.core.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "MIGRATIONS",
    "SCHEMA_VERSION_KEY",
    "backup_path_for",
    "latest_version",
    "plan",
    "read_version",
    "run",
]

SCHEMA_VERSION_KEY = "schema_version"

#: ``(version, description, callable)`` in ascending order.
Migration = tuple[int, str, Callable[[Connection], None]]


def _baseline(connection: Connection) -> None:
    """v1 baseline.

    Tables are created by ``Base.metadata.create_all`` on first run, which keeps
    development friction low; this step exists so the version has a real
    migration to point at and later changes always follow the same path.
    """


def _add_chapter_version_task_id(connection: Connection) -> None:
    """v2: remember which AI task produced a stored version.

    Blood-line for accepted AI text: without it an accepted AI draft is
    indistinguishable from something the author typed. The column is nullable
    and additive — existing rows keep their meaning (``task_id`` NULL), so no
    data is rewritten and nothing is lost on a downgrade to reading it.
    """
    columns = {
        str(row[1]) for row in connection.execute(text("PRAGMA table_info(chapter_versions)"))
    }
    if "task_id" not in columns:
        connection.execute(text("ALTER TABLE chapter_versions ADD COLUMN task_id VARCHAR(40)"))
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_chapter_versions_task_id "
            "ON chapter_versions (task_id)"
        )
    )


MIGRATIONS: list[Migration] = [
    (1, "baseline schema (created from the SQLAlchemy models)", _baseline),
    (2, "chapter_versions.task_id (AI blood-line)", _add_chapter_version_task_id),
]


def latest_version() -> int:
    """Highest schema version this build understands."""
    return max((version for version, _, _ in MIGRATIONS), default=0)


def read_version(connection: Connection, table: str) -> int:
    """Return the stored schema version, or ``0`` when absent."""
    try:
        row = connection.execute(
            text(f"SELECT value FROM {table} WHERE key = :key"),
            {"key": SCHEMA_VERSION_KEY},
        ).first()
    except Exception:
        return 0
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        logger.warning("schema_version_unreadable", table=table, value=row[0])
        return 0


def _stamp(connection: Connection, table: str, version: int) -> None:
    updated = connection.execute(
        text(f"UPDATE {table} SET value = :value WHERE key = :key"),
        {"value": str(version), "key": SCHEMA_VERSION_KEY},
    )
    if updated.rowcount == 0:
        connection.execute(
            text(f"INSERT INTO {table} (key, value) VALUES (:key, :value)"),
            {"key": SCHEMA_VERSION_KEY, "value": str(version)},
        )


def plan(connection: Connection, table: str, target: int) -> list[int]:
    """Versions that would be applied, in order."""
    current = read_version(connection, table)
    return sorted(version for version, _, _ in MIGRATIONS if current < version <= target)


def run(
    connection: Connection,
    *,
    table: str,
    target: int | None = None,
    backup: Callable[[], Path] | None = None,
) -> list[int]:
    """Apply pending migrations inside the caller's transaction.

    *backup* is invoked once, before the first statement, when there is anything
    to do. Returns the versions that were applied.
    """
    target = latest_version() if target is None else target
    current = read_version(connection, table)

    if current > target:
        raise RuntimeError(
            f"{table} is at schema version {current}, but this build only "
            f"understands {target}. Refusing to open to avoid data loss; "
            "upgrade the application."
        )

    pending = sorted(
        (item for item in MIGRATIONS if current < item[0] <= target),
        key=lambda item: item[0],
    )
    if not pending:
        if current == 0:
            _stamp(connection, table, target)
        return []

    if backup is not None:
        path = backup()
        logger.info("migration_backup_written", table=table, path=str(path))

    applied: list[int] = []
    for version, description, function in pending:
        logger.info("migration_starting", table=table, version=version, name=description)
        function(connection)
        _stamp(connection, table, version)
        applied.append(version)
        logger.info("migration_applied", table=table, version=version)

    return applied


def backup_path_for(base_dir: Path, label: str) -> Path:
    """Return ``<base_dir>/backups/<label>-<timestamp>.db`` and create its folder.

    Callers are responsible for filling the file; use SQLite's online backup
    API rather than copying the file, so a backup taken mid-write is consistent.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = base_dir / "backups" / f"{label}-{stamp}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target
