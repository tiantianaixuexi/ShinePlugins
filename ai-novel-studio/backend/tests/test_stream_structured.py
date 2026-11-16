"""Streaming twins of the structured endpoints: ``/ai/summary/{id}/stream`` and
``/ai/outline/{id}/stream``.

Outline generation takes ~103 s against a real provider, during which the
non-streaming endpoint shows nothing at all. These tests pin the fix: a tiny
mock ``/chat/completions`` server plays the provider and the whole path —
request validation, SSE framing, JSON parsing of a streamed reply, the single
repair attempt when the model answers in prose, persistence and task accounting
— is exercised without an API key.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient

#: A well-behaved outline reply.
OUTLINE_JSON = (
    '{"title": "第一章 雨夜", "goal": "等第三声梆子", "conflict": "信从哪来", '
    '"characters": ["林清"], "key_events": ["收到匿名信"], "twists": "梆子停了", '
    '"foreshadows": ["旧仓"], "ending": "推门而出", "target_word_count": 2000}'
)
#: A well-behaved summary reply.
SUMMARY_JSON = (
    '{"summary": "雨夜客栈，一封匿名信。", "plot_progress": "入局", '
    '"characters": ["林清"], "events": ["收到信"], "locations": ["客栈"], '
    '"keywords": ["梆子"], "foreshadows": ["旧仓"]}'
)
#: First attempt of the repair test: prose, no JSON at all.
PROSE_PIECES = ("好的，", "我这就写。")


class MockProvider:
    """Canned replies plus every request body the adapter sent."""

    def __init__(self) -> None:
        self.stream_pieces: tuple[str, ...] = (SUMMARY_JSON,)
        #: Chain-of-thought the provider streams *before* the answer (T-36).
        self.thought_pieces: tuple[str, ...] = ()
        self.plain_reply: str = SUMMARY_JSON
        self.requests: list[dict[str, Any]] = []
        self.url = ""


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # stdlib naming
        provider: MockProvider = self.server.provider  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        body = json.loads(raw or b"{}")
        provider.requests.append(body)

        if body.get("stream"):
            self._stream(provider.thought_pieces, provider.stream_pieces)
        else:
            self._json(provider.plain_reply)

    def _json(self, text: str) -> None:
        payload = json.dumps(
            {
                "model": "mock-model",
                "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 9},
            },
            ensure_ascii=False,
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()

    def _stream(self, thoughts: tuple[str, ...], pieces: tuple[str, ...]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for thought in thoughts:
            frame = {"choices": [{"delta": {"reasoning_content": thought}}]}
            self.wfile.write(f"data: {json.dumps(frame, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        for piece in pieces:
            frame = {"choices": [{"delta": {"content": piece}}]}
            self.wfile.write(f"data: {json.dumps(frame, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        tail = {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5},
        }
        self.wfile.write(f"data: {json.dumps(tail)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

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


def _collect_sse(response) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    name: str | None = None
    for raw_line in response.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line:
            continue
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            events.append((name or "message", json.loads(line.split(":", 1)[1])))
            name = None
    return events


def _seed(client: TestClient, auth: dict[str, str], base_url: str) -> tuple[str, str, str]:
    model = client.post(
        "/api/model-configs",
        json={
            "name": "结构化 Mock",
            "provider": "openai_compatible",
            "base_url": base_url,
            "model_name": "mock-model",
            "temperature": 0.5,
            "context_window": 8192,
            "max_tokens": 512,
            "supports_streaming": True,
        },
        headers=auth,
    )
    assert model.status_code == 201, model.text
    model_id = model.json()["id"]
    # Both endpoints resolve the default model (their request bodies carry no id).
    default = client.post(f"/api/model-configs/{model_id}/default", headers=auth)
    assert default.status_code == 200, default.text

    project = client.post(
        "/api/projects", json={"name": "结构化流式", "novel_type": "悬疑"}, headers=auth
    ).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "第一章 雨夜", "content": "雨下了整夜。林清推开客栈的木窗。"},
        headers=auth,
    ).json()
    return model_id, project["id"], chapter["id"]


def test_summary_stream_yields_deltas_and_persists(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.stream_pieces = (SUMMARY_JSON,)
    _model_id, project_id, chapter_id = _seed(client, auth, provider.url)

    with client.stream(
        "POST",
        f"/api/ai/summary/{chapter_id}/stream",
        headers=auth,
        json={"project_id": project_id, "force": True},
    ) as response:
        assert response.status_code == 200, response.text
        events = _collect_sse(response)

    deltas = [data["text"] for name, data in events if name == "delta"]
    assert deltas, f"missing delta frames: {events}"

    done = [data for name, data in events if name == "done"]
    assert done, f"missing done frame: {events}"
    assert done[0]["summary"] == "雨夜客栈，一封匿名信。"
    assert done[0]["usage"] == {"input_tokens": 11, "output_tokens": 5}

    # The row landed in the project database: the non-streaming twin now hits cache.
    cached = client.post(
        f"/api/ai/summary/{chapter_id}", headers=auth, json={"project_id": project_id}
    )
    assert cached.status_code == 200, cached.text
    assert cached.json()["cached"] is True
    assert cached.json()["summary"] == "雨夜客栈，一封匿名信。"

    tasks = client.get("/api/ai/tasks", headers=auth).json()
    assert any(task["kind"] == "ai.summary" and task["status"] == "success" for task in tasks)
    assert provider.requests and provider.requests[0]["stream"] is True


def test_outline_stream_persists_chapter_row(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    provider.stream_pieces = (OUTLINE_JSON,)
    _model_id, project_id, chapter_id = _seed(client, auth, provider.url)

    with client.stream(
        "POST",
        f"/api/ai/outline/{chapter_id}/stream",
        headers=auth,
        json={"project_id": project_id, "force": True, "instruction": "节奏放慢"},
    ) as response:
        assert response.status_code == 200, response.text
        events = _collect_sse(response)

    done = [data for name, data in events if name == "done"]
    assert done, f"missing done frame: {events}"
    payload = done[0]
    assert payload["parent_id"] == chapter_id
    assert payload["level"] == "chapter"
    assert payload["degraded"] is False
    assert payload["title"] == "第一章 雨夜"
    assert payload["key_events"] == ["收到匿名信"]
    assert payload["usage"] == {"input_tokens": 11, "output_tokens": 5}

    again = client.post(
        f"/api/ai/outline/{chapter_id}", headers=auth, json={"project_id": project_id}
    )
    assert again.status_code == 200, again.text
    assert again.json()["cached"] is True
    assert again.json()["outline_id"] == payload["outline_id"]

    tasks = client.get("/api/ai/tasks", headers=auth).json()
    assert any(
        task["kind"] == "ai.outline.structured" and task["status"] == "success" for task in tasks
    )


def test_outline_stream_repairs_a_non_json_reply(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    """Prose first, JSON after the repair: still parseable, both segments streamed."""
    provider.stream_pieces = PROSE_PIECES
    provider.plain_reply = OUTLINE_JSON
    _model_id, project_id, chapter_id = _seed(client, auth, provider.url)

    with client.stream(
        "POST",
        f"/api/ai/outline/{chapter_id}/stream",
        headers=auth,
        json={"project_id": project_id, "force": True},
    ) as response:
        assert response.status_code == 200, response.text
        events = _collect_sse(response)

    deltas = [data["text"] for name, data in events if name == "delta"]
    # Two segments: the streamed prose, then the repaired JSON as one frame.
    assert len(deltas) == len(PROSE_PIECES) + 1, deltas
    assert "".join(deltas[: len(PROSE_PIECES)]) == "".join(PROSE_PIECES)
    assert deltas[-1] == OUTLINE_JSON

    # A ``reset`` frame sits between the two segments: a client that keeps
    # concatenating deltas must throw the prose away and keep the repair only.
    names = [name for name, _data in events]
    assert "reset" in names, f"missing reset frame: {names}"
    reset_at = names.index("reset")
    assert reset_at < len(names) - 1
    assert names[reset_at + 1] == "delta"
    assert [data["text"] for name, data in events[reset_at:] if name == "delta"] == [OUTLINE_JSON]
    assert events[reset_at][1] == {}

    done = [data for name, data in events if name == "done"]
    assert done, f"missing done frame: {events}"
    assert done[0]["degraded"] is False
    assert done[0]["goal"] == "等第三声梆子"
    # Both attempts are billed: 11+7 in, 5+9 out.
    assert done[0]["usage"] == {"input_tokens": 18, "output_tokens": 14}

    # One streaming call, then one non-streaming repair.
    assert [call.get("stream") for call in provider.requests] == [True, False]


def test_thinking_frames_do_not_pollute_the_json_reply(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    """T-36: a reasoning model's chain-of-thought arrives as its own event.

    The answer body must still parse into the same structured payload, and the
    thought text must never appear inside the ``delta`` frames a client
    concatenates as the article.
    """
    provider.thought_pieces = ("先想", "标题要一致")
    provider.stream_pieces = (OUTLINE_JSON,)
    _model_id, project_id, chapter_id = _seed(client, auth, provider.url)

    with client.stream(
        "POST",
        f"/api/ai/outline/{chapter_id}/stream",
        headers=auth,
        json={"project_id": project_id, "force": True},
    ) as response:
        assert response.status_code == 200, response.text
        events = _collect_sse(response)

    names = [name for name, _data in events]
    assert "thinking" in names, names
    # Reasoning always precedes the answer: that is the whole point of T-36.
    assert names.index("thinking") < names.index("delta")

    assert "".join(data["text"] for name, data in events if name == "thinking") == "先想标题要一致"
    deltas = "".join(data["text"] for name, data in events if name == "delta")
    assert deltas == OUTLINE_JSON
    assert "先想" not in deltas

    done = [data for name, data in events if name == "done"]
    assert done, f"missing done frame: {events}"
    assert done[0]["degraded"] is False
    assert done[0]["title"] == "第一章 雨夜"
    assert done[0]["goal"] == "等第三声梆子"
    # Usage stays the provider's answer-only accounting.
    assert done[0]["usage"] == {"input_tokens": 11, "output_tokens": 5}


def test_summary_stream_reports_failure_as_error_frame(
    client: TestClient, auth: dict[str, str]
) -> None:
    """An unreachable provider becomes an ``error`` frame, not a 500."""
    model = client.post(
        "/api/model-configs",
        json={
            "name": "不可达",
            "provider": "openai_compatible",
            "base_url": "http://127.0.0.1:1/v1",
            "model_name": "nope",
            "retry_count": 0,
            "timeout_s": 2.0,
        },
        headers=auth,
    ).json()
    default = client.post(f"/api/model-configs/{model['id']}/default", headers=auth)
    assert default.status_code == 200, default.text

    project = client.post("/api/projects", json={"name": "失败"}, headers=auth).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "第一章", "content": "雨夜。"},
        headers=auth,
    ).json()

    with client.stream(
        "POST",
        f"/api/ai/summary/{chapter['id']}/stream",
        headers=auth,
        json={"project_id": project["id"], "force": True},
    ) as response:
        assert response.status_code == 200
        events = _collect_sse(response)

    errors = [data for name, data in events if name == "error"]
    assert errors, f"expected an error frame: {events}"
    assert not [data for name, data in events if name == "done"]

    tasks = client.get("/api/ai/tasks", headers=auth).json()
    assert any(task["status"] == "failed" for task in tasks)
