"""Schema migration safety.

These tests guard the promise that a user's novel survives an application
upgrade: a backup is taken before anything changes, nothing is applied twice,
and a database written by a newer build is refused rather than partially read.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db import migrations
from app.db.migrations import latest_version, read_version
from app.db.project_db import create_project_database
from app.db.session import Database


def _project_db(root: Path) -> Path:
    """`<root>/my-novel/database/novel.db`, mirroring the real layout."""
    directory = root / "my-novel" / "database"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "novel.db"


def _open(path: Path) -> Database:
    return Database(f"sqlite+pysqlite:///{path.as_posix()}", label="novel.db")


def _set_version(path: Path, value: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE project_meta SET value = ? WHERE key = 'schema_version'", (value,)
        )
        connection.commit()
    finally:
        connection.close()


def _all_versions() -> list[int]:
    """Every migration this build knows about, ascending."""
    return [version for version, _, _ in migrations.MIGRATIONS]


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }


def test_fresh_database_is_stamped(tmp_path: Path) -> None:
    database = create_project_database(_project_db(tmp_path))
    try:
        with database.engine.begin() as connection:
            assert read_version(connection, "project_meta") == latest_version()
            # Nothing left to do: reopening must be a no-op.
            assert migrations.plan(connection, "project_meta", latest_version()) == []
    finally:
        database.dispose()


def test_rewind_replays_every_migration_from_zero(tmp_path: Path) -> None:
    path = _project_db(tmp_path)
    database = create_project_database(path)
    database.dispose()

    _set_version(path, "0")
    reopened = _open(path)
    try:
        with reopened.engine.begin() as connection:
            assert read_version(connection, "project_meta") == 0
            assert migrations.plan(connection, "project_meta", latest_version()) == _all_versions()

        applied = reopened.migrate("project_meta", backup_root=tmp_path / "my-novel")
        assert applied == _all_versions()

        with reopened.engine.begin() as connection:
            assert read_version(connection, "project_meta") == latest_version()
            assert migrations.plan(connection, "project_meta", latest_version()) == []
    finally:
        reopened.dispose()


def test_migration_backs_up_the_real_database(tmp_path: Path) -> None:
    path = _project_db(tmp_path)
    database = create_project_database(path)
    database.dispose()
    _set_version(path, "0")

    reopened = _open(path)
    try:
        reopened.migrate("project_meta", backup_root=tmp_path / "my-novel")
    finally:
        reopened.dispose()

    backups = list((tmp_path / "my-novel" / "backups").glob("*.db"))
    assert backups, "a migration must snapshot the database first"
    # The snapshot must be a real database, not an empty file.
    newest = max(backups, key=lambda item: item.stat().st_mtime)
    assert "chapters" in _tables(newest)


def test_backup_lands_next_to_the_project_not_inside_it(tmp_path: Path) -> None:
    path = _project_db(tmp_path)
    database = create_project_database(path)
    database.dispose()
    _set_version(path, "0")

    reopened = _open(path)
    try:
        reopened.migrate("project_meta", backup_root=tmp_path / "my-novel")
    finally:
        reopened.dispose()

    # backups live at <project>/backups, never in <project>/database/backups
    assert (tmp_path / "my-novel" / "backups").is_dir()
    assert not (tmp_path / "my-novel" / "database" / "backups").exists()


def test_future_schema_version_is_refused(tmp_path: Path) -> None:
    path = _project_db(tmp_path)
    database = create_project_database(path)
    database.dispose()

    _set_version(path, str(latest_version() + 5))

    with pytest.raises(RuntimeError) as excinfo:
        create_project_database(path)
    assert "Refusing to open" in str(excinfo.value)


def test_opening_alone_never_stamps_a_stale_file(tmp_path: Path) -> None:
    """The runner owns the version; opening must not make a stale file look current."""
    path = _project_db(tmp_path)
    database = create_project_database(path)
    database.dispose()
    _set_version(path, "0")

    opened = _open(path)
    try:
        with opened.engine.begin() as connection:
            assert read_version(connection, "project_meta") == 0
    finally:
        opened.dispose()
