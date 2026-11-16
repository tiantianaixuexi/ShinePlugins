"""Accepting AI text keeps its blood-line.

Two promises are guarded here:

* the chapter's previous manuscript survives an accept (recoverable history);
* the accepted text is stored as ``source="ai"`` **with** the producing
  ``task_id``, so a later "why did this happen?" can be answered.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.migrations import latest_version, read_version
from app.db.project_db import create_project_database
from app.models.novel import ChapterVersion


def _chapter(client: TestClient, auth: dict[str, str], pid: str, content: str = "作者原文") -> dict:
    response = client.post(
        f"/api/projects/{pid}/chapters",
        json={"title": "第一章 启程", "content": content},
        headers=auth,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _versions(client: TestClient, auth: dict[str, str], pid: str, cid: str) -> list[dict]:
    return client.get(f"/api/projects/{pid}/chapters/{cid}/versions", headers=auth).json()


def test_accept_ai_records_source_and_task_id(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]
    chapter = _chapter(client, auth, pid)

    response = client.post(
        f"/api/projects/{pid}/chapters/{chapter['id']}/accept-ai",
        json={
            "content": "AI 续写出来的新正文",
            "title": "第一章 启程（改）",
            "task_id": "task_abc123",
            "note": "采纳续写",
        },
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chapter"]["content"] == "AI 续写出来的新正文"
    assert body["chapter"]["title"] == "第一章 启程（改）"
    assert body["version"]["source"] == "ai"
    assert body["version"]["task_id"] == "task_abc123"

    ai_versions = [v for v in _versions(client, auth, pid, chapter["id"]) if v["source"] == "ai"]
    assert len(ai_versions) == 1
    assert ai_versions[0]["task_id"] == "task_abc123"
    assert ai_versions[0]["note"] == "采纳续写"


def test_accept_ai_keeps_the_pre_accept_text(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]
    original = "作者手写的原文，不能被 AI 覆盖掉。"
    chapter = _chapter(client, auth, pid, content=original)
    cid = chapter["id"]

    client.post(
        f"/api/projects/{pid}/chapters/{cid}/accept-ai",
        json={"content": "AI 文本", "task_id": "task_keep"},
        headers=auth,
    )

    user_versions = [v for v in _versions(client, auth, pid, cid) if v["source"] == "user"]
    assert user_versions, "the pre-accept text must be snapshotted"
    # The newest user version is the accept-time snapshot of the old manuscript.
    protected = user_versions[0]
    assert protected["note"] == "采纳 AI 前的原文"

    # Restoring it proves the stored body really is the old manuscript.
    restored = client.post(
        f"/api/projects/{pid}/chapters/{cid}/versions/{protected['id']}/restore", headers=auth
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["content"] == original


def test_accept_ai_without_task_id_falls_back_to_a_note(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]
    chapter = _chapter(client, auth, pid)

    body = client.post(
        f"/api/projects/{pid}/chapters/{chapter['id']}/accept-ai",
        json={"content": "没有任务号的 AI 文本"},
        headers=auth,
    ).json()
    assert body["version"]["source"] == "ai"
    assert body["version"]["task_id"] is None
    assert body["version"]["note"] == "AI 采纳"


def test_accept_ai_rejects_empty_content_and_unknown_chapter(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]
    chapter = _chapter(client, auth, pid)

    empty = client.post(
        f"/api/projects/{pid}/chapters/{chapter['id']}/accept-ai",
        json={"content": ""},
        headers=auth,
    )
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "validation_failed"

    missing = client.post(
        f"/api/projects/{pid}/chapters/chap_missing0000/accept-ai",
        json={"content": "正文"},
        headers=auth,
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_legacy_database_gains_the_column_and_still_reads(tmp_path: Path) -> None:
    """A project written by the previous build must open and keep its history."""
    path = tmp_path / "my-novel" / "database" / "novel.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    create_project_database(path).dispose()

    # Rewind the file to the v1 shape: no task_id column, one historical row.
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX IF EXISTS ix_chapter_versions_task_id")
        connection.execute("ALTER TABLE chapter_versions DROP COLUMN task_id")
        connection.execute("UPDATE project_meta SET value = '1' WHERE key = 'schema_version'")
        connection.execute(
            "INSERT INTO chapter_versions "
            "(id, project_id, chapter_id, version_no, title, content, word_count, source, note, "
            "created_at, updated_at) VALUES "
            "('ver_legacy0001', 'proj_legacy', 'chap_legacy', 1, '第一章', '旧正文', 3, "
            "'user', '创建章节', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.commit()

    database = create_project_database(path)  # applies the v2 migration
    try:
        with database.engine.begin() as connection:
            assert read_version(connection, "project_meta") == latest_version()
        with database.session() as session:
            row = session.scalars(
                select(ChapterVersion).where(ChapterVersion.id == "ver_legacy0001")
            ).one()
            assert row.content == "旧正文"
            assert row.task_id is None
    finally:
        database.dispose()
