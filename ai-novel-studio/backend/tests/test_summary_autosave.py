"""Auto-refresh of L1 memory: the summary cache is keyed by chapter content.

T-32: a saved chapter never refreshed its ``chapter_summaries`` row, so「前情提要」
went stale the moment the author edited anything. Regenerating on every autosave
was out of the question (it would bill a model call per typing pause), so the
trigger moved to "leaving the chapter" — which is only safe if asking twice for
an unchanged chapter is free.

That is what ``chapter_summaries.source_hash`` buys:

* same body → ``cached=True`` and **no** model request;
* edited body → exactly one regeneration, and the fingerprint moves with it;
* ``force=True`` → regenerate regardless, so the panel's 「生成摘要」 button keeps
  its explicit "do it again" meaning.

The mock provider below is the same trick as ``test_chapter_summary.py``: a local
``/chat/completions`` server, so the whole path runs without an API key.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient

CHAPTER_TEXT = "雨夜，沈砚推开旧书店的门，柜台后的老人递来一只生锈的铜铃。"
EDITED_TEXT = CHAPTER_TEXT + "铜铃一响，墙上的老钟停了。"

SUMMARY_PAYLOAD = {
    "summary": "雨夜沈砚进入旧书店，老人交给他一只生锈的铜铃。",
    "characters": ["沈砚", "老人"],
    "events": ["铜铃交接"],
    "locations": ["旧书店"],
    "keywords": ["铜铃", "雨夜"],
    "foreshadows": ["停摆的老钟"],
    "plot_progress": "主角得到关键道具。",
}


class MockProvider:
    """Holds the canned reply and counts how often the model was asked."""

    def __init__(self) -> None:
        self.reply = ""
        self.requests: list[dict[str, Any]] = []
        self.url = ""


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # stdlib naming
        provider: MockProvider = self.server.provider  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        provider.requests.append(json.loads(raw or b"{}"))

        body = json.dumps(
            {
                "model": "mock-model",
                "choices": [
                    {"message": {"content": provider.reply}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 40, "completion_tokens": 20},
            },
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture()
def provider() -> Iterator[MockProvider]:
    state = MockProvider()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.provider = state  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        state.url = f"http://{host}:{port}/v1"
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _seed(
    client: TestClient, auth: dict[str, str], base_url: str, *, content: str = CHAPTER_TEXT
) -> tuple[str, str]:
    """One project with one chapter, backed by the mock provider."""
    model = client.post(
        "/api/model-configs",
        json={
            "name": "摘要缓存 Mock",
            "provider": "openai_compatible",
            "base_url": base_url,
            "model_name": "mock-model",
            "temperature": 0.3,
            "context_window": 8192,
            "max_tokens": 512,
        },
        headers=auth,
    )
    assert model.status_code == 201, model.text
    default = client.post(f"/api/model-configs/{model.json()['id']}/default", headers=auth)
    assert default.status_code == 200, default.text

    project = client.post(
        "/api/projects", json={"name": "摘要缓存测试", "novel_type": "悬疑"}, headers=auth
    ).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "第一章 铜铃", "content": content},
        headers=auth,
    )
    assert chapter.status_code == 201, chapter.text
    return project["id"], chapter.json()["id"]


def _summarize(
    client: TestClient, auth: dict[str, str], project_id: str, chapter_id: str, *, force: bool = False
) -> dict[str, Any]:
    response = client.post(
        f"/api/ai/summary/{chapter_id}",
        json={"project_id": project_id, "force": force},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _rows(client: TestClient, project_id: str) -> list[Any]:
    from sqlalchemy import select

    from app.models.novel import ChapterSummary
    from app.services.novel_service import NovelService

    service = NovelService(client.app.state.runtime.project_service)  # type: ignore[attr-defined]
    database = service.database_for(project_id)
    with database.session() as session:
        return list(session.scalars(select(ChapterSummary)))


def test_first_call_records_the_source_hash(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    from app.services.ai_service import content_fingerprint

    provider.reply = json.dumps(SUMMARY_PAYLOAD, ensure_ascii=False)
    project_id, chapter_id = _seed(client, auth, provider.url)

    body = _summarize(client, auth, project_id, chapter_id)
    assert body["cached"] is False
    assert body["summary"] == SUMMARY_PAYLOAD["summary"]

    rows = _rows(client, project_id)
    assert len(rows) == 1
    # The fingerprint is what makes the next call free (or not).
    assert rows[0].source_hash == content_fingerprint(CHAPTER_TEXT)


def test_unchanged_chapter_is_a_free_cache_hit(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.reply = json.dumps(SUMMARY_PAYLOAD, ensure_ascii=False)
    project_id, chapter_id = _seed(client, auth, provider.url)

    _summarize(client, auth, project_id, chapter_id)
    calls_after_first = len(provider.requests)

    # Exactly what an editor does when the author flips between two chapters.
    again = _summarize(client, auth, project_id, chapter_id)
    assert again["cached"] is True
    assert again["summary"] == SUMMARY_PAYLOAD["summary"]
    assert len(provider.requests) == calls_after_first, "unchanged body must not bill a call"
    assert len(_rows(client, project_id)) == 1


def test_edited_chapter_regenerates_and_moves_the_hash(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.reply = json.dumps(SUMMARY_PAYLOAD, ensure_ascii=False)
    project_id, chapter_id = _seed(client, auth, provider.url)
    first = _summarize(client, auth, project_id, chapter_id)
    hash_before = _rows(client, project_id)[0].source_hash

    updated = client.put(
        f"/api/projects/{project_id}/chapters/{chapter_id}",
        json={"content": EDITED_TEXT},
        headers=auth,
    )
    assert updated.status_code == 200, updated.text

    provider.reply = json.dumps(
        {**SUMMARY_PAYLOAD, "summary": "雨夜沈砚进入旧书店，铜铃一响老钟停摆。"},
        ensure_ascii=False,
    )
    second = _summarize(client, auth, project_id, chapter_id)
    assert second["cached"] is False, "a stale summary must not be served as fresh"
    assert second["summary"] != first["summary"]

    rows = _rows(client, project_id)
    assert len(rows) == 1, "the row is upserted by chapter_id, never duplicated"
    from app.services.ai_service import content_fingerprint

    assert rows[0].source_hash == content_fingerprint(EDITED_TEXT)
    assert rows[0].source_hash != hash_before


def test_force_regenerates_even_when_the_hash_matches(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.reply = json.dumps(SUMMARY_PAYLOAD, ensure_ascii=False)
    project_id, chapter_id = _seed(client, auth, provider.url)
    _summarize(client, auth, project_id, chapter_id)
    calls_before = len(provider.requests)

    forced = _summarize(client, auth, project_id, chapter_id, force=True)
    assert forced["cached"] is False
    assert len(provider.requests) == calls_before + 1, "force must bypass the cache"
    assert len(_rows(client, project_id)) == 1
