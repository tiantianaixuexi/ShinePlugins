"""L1 memory tests: ``POST /api/ai/summary/{chapter_id}`` fills ``chapter_summaries``.

Before this endpoint existed the table was read-only (``_recent_summaries``) and
「前情提要」 was永远 empty. A tiny mock ``/chat/completions`` server plays the
provider so the whole path — prompt rendering, adapter, loose JSON parsing,
upsert — is exercised without an API key.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient

CHAPTER_TEXT = (
    "雨夜，沈砚推开旧书店的门，柜台后的老人递来一只生锈的铜铃。"
    "铜铃一响，墙上的老钟停了。"
)

SUMMARY_PAYLOAD = {
    "summary": "雨夜沈砚进入旧书店，老人交给他一只生锈的铜铃，铃响之后墙上的老钟停摆。",
    "characters": ["沈砚", "老人"],
    "events": ["铜铃交接", "老钟停摆"],
    "locations": ["旧书店"],
    "keywords": ["铜铃", "雨夜"],
    "foreshadows": ["停摆的老钟"],
    "plot_progress": "主角得到关键道具并触发异象。",
}


class MockProvider:
    """Holds the canned reply and records every request the adapter sends."""

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
                "usage": {"prompt_tokens": 42, "completion_tokens": 24},
            },
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # silence the test output
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
    client: TestClient, auth: dict[str, str], base_url: str, *, content: str
) -> tuple[str, str, str]:
    model = client.post(
        "/api/model-configs",
        json={
            "name": "摘要 Mock",
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
    model_id = model.json()["id"]
    # Summarising uses the default model, so point the default at the mock.
    default = client.post(f"/api/model-configs/{model_id}/default", headers=auth)
    assert default.status_code == 200, default.text

    project = client.post(
        "/api/projects", json={"name": "摘要测试", "novel_type": "悬疑"}, headers=auth
    ).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "第一章 铜铃", "content": content},
        headers=auth,
    )
    assert chapter.status_code == 201, chapter.text
    return model_id, project["id"], chapter.json()["id"]


def _summary_rows(client: TestClient, project_id: str) -> list[Any]:
    from sqlalchemy import select

    from app.models.novel import ChapterSummary
    from app.services.novel_service import NovelService

    service = NovelService(client.app.state.runtime.project_service)  # type: ignore[attr-defined]
    database = service.database_for(project_id)
    with database.session() as session:
        return list(session.scalars(select(ChapterSummary)))


def test_first_call_writes_row_and_recent_summaries(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.reply = json.dumps(SUMMARY_PAYLOAD, ensure_ascii=False)
    model_id, project_id, chapter_id = _seed(client, auth, provider.url, content=CHAPTER_TEXT)

    response = client.post(
        f"/api/ai/summary/{chapter_id}",
        json={"project_id": project_id},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cached"] is False
    assert body["summary"] == SUMMARY_PAYLOAD["summary"]
    assert body["skipped"] is None

    rows = _summary_rows(client, project_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.chapter_id == chapter_id
    assert row.summary == SUMMARY_PAYLOAD["summary"]
    assert row.characters == SUMMARY_PAYLOAD["characters"]
    assert row.foreshadows == SUMMARY_PAYLOAD["foreshadows"]
    assert row.plot_progress == SUMMARY_PAYLOAD["plot_progress"]
    assert row.model_config_id == model_id
    assert row.prompt_version is not None

    # The whole point of the row: 「前情提要」 must stop being empty.
    summaries = client.app.state.runtime.ai._recent_summaries(  # type: ignore[attr-defined]
        project_id, chapter_id
    )
    assert summaries and SUMMARY_PAYLOAD["summary"] in summaries[0]


def test_second_call_returns_cache_without_new_row_or_model_call(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.reply = json.dumps(SUMMARY_PAYLOAD, ensure_ascii=False)
    _, project_id, chapter_id = _seed(client, auth, provider.url, content=CHAPTER_TEXT)

    first = client.post(
        f"/api/ai/summary/{chapter_id}", json={"project_id": project_id}, headers=auth
    )
    assert first.status_code == 200, first.text
    calls_after_first = len(provider.requests)

    second = client.post(
        f"/api/ai/summary/{chapter_id}", json={"project_id": project_id}, headers=auth
    )
    assert second.status_code == 200, second.text
    assert second.json()["cached"] is True
    assert second.json()["summary"] == SUMMARY_PAYLOAD["summary"]
    assert len(provider.requests) == calls_after_first, "cache hit must not call the model"
    assert len(_summary_rows(client, project_id)) == 1


def test_empty_chapter_is_skipped_and_not_written(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.reply = json.dumps(SUMMARY_PAYLOAD, ensure_ascii=False)
    _, project_id, chapter_id = _seed(client, auth, provider.url, content="   ")

    response = client.post(
        f"/api/ai/summary/{chapter_id}", json={"project_id": project_id}, headers=auth
    )
    assert response.status_code == 200, response.text
    assert response.json()["skipped"] == "empty"
    assert provider.requests == []
    assert _summary_rows(client, project_id) == []


def test_non_json_reply_degrades_to_plain_summary(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    prose = "本章写雨夜书店的相遇，主角拿到铜铃，老钟停摆，气氛压抑。"
    provider.reply = prose
    _, project_id, chapter_id = _seed(client, auth, provider.url, content=CHAPTER_TEXT)

    response = client.post(
        f"/api/ai/summary/{chapter_id}", json={"project_id": project_id}, headers=auth
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"] == prose

    rows = _summary_rows(client, project_id)
    assert len(rows) == 1
    assert rows[0].summary == prose
    assert rows[0].characters == []
    assert rows[0].events == []
    assert rows[0].plot_progress == ""
