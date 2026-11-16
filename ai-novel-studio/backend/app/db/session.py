"""SQLite engine/session management.

Concurrency model (see ``docs/architecture.md``):

* **WAL** journalling so readers never block the writer and vice versa.
* **One process owns the writes.** The FastAPI backend is the only writer; the
  Rust shell talks to it over HTTP and never opens ``novel.db``.
* ``busy_timeout`` turns rare cross-process contention into a short wait
  instead of an immediate ``database is locked`` error.
* Backups use SQLite's online backup API, never a file copy, so a backup taken
  while chapters are being written is always consistent.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger

logger = get_logger(__name__)

#: Pragmas applied to every new SQLite connection.
SQLITE_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
    "PRAGMA temp_store=MEMORY",
)


def sqlite_path_from_url(url: str) -> Path | None:
    """Extract the filesystem path from a ``sqlite+pysqlite:///`` URL."""
    if not url.startswith("sqlite"):
        return None
    parsed = urlparse(url)
    if parsed.path in ("", "/:memory:", "/"):
        return None
    raw = parsed.path.lstrip("/")
    if url.startswith("sqlite+pysqlite:///"):
        return Path(raw)
    return Path(raw)


def _configure_connection(dbapi_connection: sqlite3.Connection, _record: object) -> None:
    """Apply pragmas and load optional extensions on connect."""
    cursor = dbapi_connection.cursor()
    try:
        for pragma in SQLITE_PRAGMAS:
            try:
                cursor.execute(pragma)
            except sqlite3.DatabaseError as exc:  # pragma: no cover - defensive
                logger.warning("sqlite_pragma_failed", pragma=pragma, error=str(exc))
    finally:
        cursor.close()
    _load_sqlite_vec(dbapi_connection)


def _load_sqlite_vec(dbapi_connection: sqlite3.Connection) -> None:
    """Load the ``sqlite-vec`` extension when the package is available.

    The vector index degrades to FTS5-only retrieval when the extension is
    missing, so a failed load must never abort start-up.
    """
    try:
        import sqlite_vec
    except ImportError:
        return
    try:
        dbapi_connection.enable_load_extension(True)
        sqlite_vec.load(dbapi_connection)
        dbapi_connection.enable_load_extension(False)
    except (AttributeError, sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
        logger.warning("sqlite_vec_load_failed", error=str(exc))


class Database:
    """Thin, explicit wrapper around a SQLAlchemy engine and session factory."""

    def __init__(self, url: str, *, echo: bool = False, label: str = "db") -> None:
        self.label = label
        self.url = url
        self.path = sqlite_path_from_url(url)
        if self.path is not None and ":memory:" not in url:
            self.path.parent.mkdir(parents=True, exist_ok=True)

        self.engine: Engine = create_engine(
            url,
            echo=echo,
            future=True,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False, "timeout": 5},
        )
        event.listen(self.engine, "connect", _configure_connection)
        self._session_factory: sessionmaker[Session] = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )

    # -- sessions ---------------------------------------------------------
    @contextmanager
    def session(self) -> Iterator[Session]:
        """Transactional session: commit on success, roll back on error."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def new_session(self) -> Session:
        """Create a bare session; the caller owns commit/rollback/close."""
        return self._session_factory()

    # -- lifecycle --------------------------------------------------------
    def create_all(self) -> None:
        """Create missing tables (development / first run only)."""
        from app.db.base import Base

        Base.metadata.create_all(self.engine)

    def migrate(self, table: str, *, backup_root: Path | None = None) -> list[int]:
        """Apply pending schema migrations to this database.

        When *backup_root* is given, a consistent snapshot is written to
        ``<backup_root>/backups/`` before the first statement runs.
        """
        from app.db import migrations

        def make_backup() -> Path:
            if self.path is None:
                raise RuntimeError(f"Database {self.label!r} is not file backed")
            target = migrations.backup_path_for(backup_root, table)
            self.backup_to(target)
            return target

        with self.engine.begin() as connection:
            return migrations.run(
                connection,
                table=table,
                backup=make_backup if backup_root is not None else None,
            )

    def dispose(self) -> None:
        self.engine.dispose()

    # -- maintenance ------------------------------------------------------
    def backup_to(self, target: Path) -> Path:
        """Write a consistent copy of the database to *target*."""
        if self.path is None:
            raise RuntimeError(f"Database {self.label!r} is not file backed")
        target.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(self.path, timeout=10)
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        return target

    def vacuum(self) -> None:
        if self.path is None:
            return
        with self.engine.begin() as connection:
            connection.exec_driver_sql("VACUUM")

    def checkpoint(self) -> None:
        """Fold the WAL back into the main database file.

        Required before copying a project directory: a ``.db`` file copied
        without its ``-wal`` companion would silently lose recent chapters.
        """
        if self.path is None:
            return
        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")

    def integrity_check(self) -> list[str]:
        if self.path is None:
            return []
        with self.engine.connect() as connection:
            rows = connection.exec_driver_sql("PRAGMA integrity_check").fetchall()
        return [str(row[0]) for row in rows]
