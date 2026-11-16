"""``POST /api/ai/outline/{chapter_id}`` fills the (previously dead) ``outlines`` table.

``outlines`` had the columns but no writer: the only reference in the codebase
was a ``count(*)`` in ``collect_stats``. This pins the structured path — JSON in,
one ``level="chapter"`` row keyed by ``parent_id=chapter_id`` out, upserted (not
duplicated) on regeneration, and degraded to the raw reply when the model
ignores the JSON instruction.

A tiny mock ``/chat/completions`` server plays the provider so prompt rendering,
the adapter, loose JSON parsing and the upsert all run without an API key.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient

CHAPTER_TITLE = "第一章 铜铃"
CHAPTER_TEXT = (
    "雨夜，沈砚推开旧书店的门，柜台后的老人递来一只生锈的铜铃。"
    "铜铃一响，墙上的老钟停了。"
)

OUTLINE_PAYLOAD = {
    "title": "铜铃响起的那一夜",
    "goal": "沈砚拿到铜铃并意识到它有异样。",
    "conflict": "老人不肯说明铜铃的来历。",
    "characters": ["沈砚", "老人"],
    "key_events": ["铜铃交接", "老钟停摆"],
    "twists": "铜铃其实是从沈砚父亲那里流出的。",
    "foreshadows": ["停摆的老钟"],
    "ending": "沈砚带着铜铃离开书店，雨还没停。",
    "target_word_count": 2000,
}


class MockProvider:
    """Holds the canned reply and records every request the adapter sends."""

    def __init__(self) -> None:
        self.reply = ""
        #: When non-empty, the n-th request gets ``replies[n]`` (last one repeats);
        #: lets a test script "first attempt" and "repair attempt" separately.
        self.replies: list[str] = []
        self.requests: list[dict[str, Any]] = []
        self.url = ""

    def next_reply(self) -> str:
        if not self.replies:
            return self.reply
        return self.replies[min(len(self.requests) - 1, len(self.replies) - 1)]


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
                    {"message": {"content": provider.next_reply()}, "finish_reason": "stop"}
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


def _seed(client: TestClient, auth: dict[str, str], base_url: str) -> tuple[str, str, dict]:
    model = client.post(
        "/api/model-configs",
        json={
            "name": "大纲 Mock",
            "provider": "openai_compatible",
            "base_url": base_url,
            "model_name": "mock-model",
            "temperature": 0.5,
            "context_window": 8192,
            "max_tokens": 512,
        },
        headers=auth,
    )
    assert model.status_code == 201, model.text
    model_id = model.json()["id"]
    default = client.post(f"/api/model-configs/{model_id}/default", headers=auth)
    assert default.status_code == 200, default.text

    project = client.post(
        "/api/projects", json={"name": "大纲测试", "novel_type": "悬疑"}, headers=auth
    ).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": CHAPTER_TITLE, "content": CHAPTER_TEXT},
        headers=auth,
    )
    assert chapter.status_code == 201, chapter.text
    return project["id"], chapter.json()["id"], chapter.json()


def _outline_rows(client: TestClient, project_id: str) -> list[Any]:
    from sqlalchemy import select

    from app.models.novel import Outline
    from app.services.novel_service import NovelService

    service = NovelService(client.app.state.runtime.project_service)  # type: ignore[attr-defined]
    database = service.database_for(project_id)
    with database.session() as session:
        return list(session.scalars(select(Outline)))


def test_first_call_writes_chapter_level_outline(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.reply = json.dumps(OUTLINE_PAYLOAD, ensure_ascii=False)
    project_id, chapter_id, chapter = _seed(client, auth, provider.url)

    response = client.post(
        f"/api/ai/outline/{chapter_id}",
        json={"project_id": project_id},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["degraded"] is False
    assert body["cached"] is False
    assert body["title"] == OUTLINE_PAYLOAD["title"]
    assert body["key_events"] == OUTLINE_PAYLOAD["key_events"]
    assert body["target_word_count"] == OUTLINE_PAYLOAD["target_word_count"]

    rows = _outline_rows(client, project_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.level == "chapter"
    assert row.parent_id == chapter_id
    assert row.project_id == project_id
    assert row.sort_order == chapter["sort_order"]
    assert row.title == OUTLINE_PAYLOAD["title"]
    assert row.goal == OUTLINE_PAYLOAD["goal"]
    assert row.conflict == OUTLINE_PAYLOAD["conflict"]
    assert row.characters == OUTLINE_PAYLOAD["characters"]
    assert row.foreshadows == OUTLINE_PAYLOAD["foreshadows"]
    assert row.ending == OUTLINE_PAYLOAD["ending"]
    assert row.target_word_count == OUTLINE_PAYLOAD["target_word_count"]
    assert row.row_version == 1


def test_second_call_reuses_row_without_another_model_call(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.reply = json.dumps(OUTLINE_PAYLOAD, ensure_ascii=False)
    project_id, chapter_id, _ = _seed(client, auth, provider.url)

    first = client.post(
        f"/api/ai/outline/{chapter_id}", json={"project_id": project_id}, headers=auth
    )
    assert first.status_code == 200, first.text
    calls_after_first = len(provider.requests)

    second = client.post(
        f"/api/ai/outline/{chapter_id}", json={"project_id": project_id}, headers=auth
    )
    assert second.status_code == 200, second.text
    assert second.json()["cached"] is True
    assert second.json()["outline_id"] == first.json()["outline_id"]
    assert len(provider.requests) == calls_after_first, "缓存命中不得再调用模型"
    assert len(_outline_rows(client, project_id)) == 1, "不得新增第二行"


def test_force_regenerates_the_same_row(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.reply = json.dumps(OUTLINE_PAYLOAD, ensure_ascii=False)
    project_id, chapter_id, _ = _seed(client, auth, provider.url)

    first = client.post(
        f"/api/ai/outline/{chapter_id}", json={"project_id": project_id}, headers=auth
    )
    assert first.status_code == 200, first.text

    provider.reply = json.dumps(
        {**OUTLINE_PAYLOAD, "title": "第二版大纲"}, ensure_ascii=False
    )
    second = client.post(
        f"/api/ai/outline/{chapter_id}",
        json={"project_id": project_id, "force": True},
        headers=auth,
    )
    assert second.status_code == 200, second.text
    assert second.json()["cached"] is False
    assert second.json()["outline_id"] == first.json()["outline_id"]
    assert second.json()["title"] == "第二版大纲"

    rows = _outline_rows(client, project_id)
    assert len(rows) == 1
    assert rows[0].title == "第二版大纲"
    assert rows[0].row_version == 2, "更新必须自增 row_version"


def test_non_json_reply_degrades_and_keeps_raw_text(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    prose = "这一章写雨夜书店的相遇，主角拿到铜铃，老钟停摆，气氛压抑。"
    provider.reply = prose
    project_id, chapter_id, _ = _seed(client, auth, provider.url)

    response = client.post(
        f"/api/ai/outline/{chapter_id}", json={"project_id": project_id}, headers=auth
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["degraded"] is True
    assert body["content"] == prose
    assert body["title"] == CHAPTER_TITLE
    assert body["goal"] == ""
    assert body["key_events"] == []

    rows = _outline_rows(client, project_id)
    assert len(rows) == 1
    assert rows[0].content == prose
    assert rows[0].title == CHAPTER_TITLE
    assert rows[0].level == "chapter"
    assert rows[0].parent_id == chapter_id


def test_truncated_reply_with_blank_repair_still_degrades_with_content(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    """Truncated JSON + an empty repair turn: degraded, but ``content`` is the reply.

    This is the shape a real run produced (``smoke_ai.py`` step 4 failed with
    ``degraded=True`` and ``content=""``): the reply the author paid for must
    survive even though neither turn was valid JSON.
    """
    truncated = '{"title": "铜铃响起的那一夜", "goal": "沈砚拿到铜铃并意识到它'
    provider.replies = [truncated, ""]
    project_id, chapter_id, _ = _seed(client, auth, provider.url)

    response = client.post(
        f"/api/ai/outline/{chapter_id}",
        json={"project_id": project_id},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["degraded"] is True
    assert body["content"] == truncated, "降级时 content 不能为空"
    assert body["title"] == CHAPTER_TITLE

    rows = _outline_rows(client, project_id)
    assert len(rows) == 1
    assert rows[0].content == truncated


def test_unknown_chapter_returns_404(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.reply = json.dumps(OUTLINE_PAYLOAD, ensure_ascii=False)
    project_id, _, _ = _seed(client, auth, provider.url)

    response = client.post(
        "/api/ai/outline/chap_does_not_exist",
        json={"project_id": project_id},
        headers=auth,
    )
    assert response.status_code == 404, response.text
    assert provider.requests == []
