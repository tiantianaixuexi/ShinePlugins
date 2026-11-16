"""End-to-end streaming test: FastAPI + adapter + a real SSE socket.

A tiny mock ``/chat/completions`` server plays the provider, so this exercises
the whole path the desktop client uses — request validation, prompt rendering,
the httpx streaming client, SSE parsing and the adapter's usage accounting —
without needing an API key.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

PIECES = ("第一段。", "第二段。", "第三段。")


class _MockProvider(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        for piece in PIECES:
            frame = {"choices": [{"delta": {"content": piece}}]}
            self.wfile.write(f"data: {json.dumps(frame, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.02)

        tail = {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3},
        }
        self.wfile.write(f"data: {json.dumps(tail)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *args: object) -> None:  # silence the test output
        return


@pytest.fixture()
def mock_provider() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockProvider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}/v1"
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
            "name": "Mock 提供方",
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

    project = client.post(
        "/api/projects", json={"name": "流式测试", "novel_type": "悬疑"}, headers=auth
    ).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "第一章", "content": "雨夜。"},
        headers=auth,
    ).json()
    return model.json()["id"], project["id"], chapter["id"]


def test_stream_flows_deltas_and_usage(
    client: TestClient, auth: dict[str, str], mock_provider: str
) -> None:
    model_id, project_id, chapter_id = _seed(client, auth, mock_provider)

    with client.stream(
        "POST",
        "/api/ai/polish/stream",
        headers=auth,
        json={
            "project_id": project_id,
            "chapter_id": chapter_id,
            "selection": "雨夜。",
            "instruction": "更凝练",
            "model_config_id": model_id,
        },
    ) as response:
        assert response.status_code == 200, response.text
        events = _collect_sse(response)

    deltas = [data.get("text", "") for name, data in events if name == "delta"]
    assert "".join(deltas) == "".join(PIECES)

    done = [data for name, data in events if name == "done"]
    assert done, f"missing done frame: {events}"
    assert done[0]["output_tokens"] == 3
    assert done[0]["input_tokens"] > 0
    assert done[0]["model"] == "mock-model"

    # The generation must be accounted for in the task ledger.
    tasks = client.get("/api/ai/tasks", headers=auth).json()
    assert any(task["kind"] == "ai.polish" and task["status"] == "success" for task in tasks)


def test_stream_reports_provider_failure(client: TestClient, auth: dict[str, str]) -> None:
    """A provider that refuses the connection surfaces as an error frame, not a 500."""
    # Port 1 is closed; the adapter retries and then reports a provider error.
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
    )
    model_id = model.json()["id"]

    project = client.post("/api/projects", json={"name": "失败测试"}, headers=auth).json()

    with client.stream(
        "POST",
        "/api/ai/polish/stream",
        headers=auth,
        json={
            "project_id": project["id"],
            "selection": "文本",
            "model_config_id": model_id,
        },
    ) as response:
        assert response.status_code == 200
        events = _collect_sse(response)

    errors = [data for name, data in events if name == "error"]
    assert errors, f"expected an error frame: {events}"
    assert errors[0]["code"] in {"all_providers_failed", "provider_unavailable"} or errors[0][
        "code"
    ].startswith("provider")

    tasks = client.get("/api/ai/tasks", headers=auth).json()
    failed = [task for task in tasks if task["status"] == "failed"]
    assert failed, "the failed task must still be recorded"
