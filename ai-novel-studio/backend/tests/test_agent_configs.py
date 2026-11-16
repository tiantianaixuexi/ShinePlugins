"""Per-agent model bindings: ``agent_configs`` finally has readers.

The table existed but nothing read it, so "让润色走便宜的小模型" was impossible.
These tests pin the two halves of the contract:

* the settings surface (``GET/PUT /api/agent-configs``), and
* model selection precedence: request id > per-agent binding > default model.

A tiny mock ``/chat/completions`` server records the ``model`` field of every
request, which is how the precedence is observed end to end — no API key needed.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient

DEFAULT_MODEL_NAME = "default-cheap-model"
AGENT_MODEL_NAME = "agent-special-model"


class MockProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.url = ""

    @property
    def last_model(self) -> str:
        assert self.requests, "the provider was never called"
        return str(self.requests[-1].get("model"))


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # stdlib naming
        provider: MockProvider = self.server.provider  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        provider.requests.append(json.loads(raw or b"{}"))

        body = json.dumps(
            {
                "model": "mock",
                "choices": [{"message": {"content": "改写后的句子。"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
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


def _model(
    client: TestClient, auth: dict[str, str], base_url: str, name: str, model_name: str
) -> str:
    response = client.post(
        "/api/model-configs",
        json={
            "name": name,
            "provider": "openai_compatible",
            "base_url": base_url,
            "model_name": model_name,
            "max_tokens": 256,
            "max_output_tokens": 256,
        },
        headers=auth,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _bindings(client: TestClient, auth: dict[str, str]) -> list[dict]:
    response = client.get("/api/agent-configs", headers=auth)
    assert response.status_code == 200, response.text
    return response.json()


def _polish(client: TestClient, auth: dict[str, str], pid: str, **extra: Any):
    return client.post(
        "/api/ai/polish",
        json={
            "project_id": pid,
            "content": "原文一句话。",
            "selection": "原文一句话。",
            **extra,
        },
        headers=auth,
    )


def test_put_then_get_lists_the_binding(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    model_id = _model(client, auth, provider.url, "便宜模型", DEFAULT_MODEL_NAME)

    response = client.put(
        "/api/agent-configs/polish",
        json={"display_name": "润色员", "model_config_id": model_id, "temperature": 0.4},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agent_type"] == "polish"
    assert body["display_name"] == "润色员"
    assert body["model_config_id"] == model_id
    assert body["temperature"] == 0.4

    listed = {row["agent_type"]: row for row in _bindings(client, auth)}
    assert listed["polish"]["model_config_id"] == model_id


def test_second_put_updates_in_place(
    client: TestClient, auth: dict[str, str], provider: MockProvider
) -> None:
    """``agent_type`` is the natural key: no duplicate rows, version bumps."""
    first_model = _model(client, auth, provider.url, "模型甲", DEFAULT_MODEL_NAME)
    second_model = _model(client, auth, provider.url, "模型乙", AGENT_MODEL_NAME)

    created = client.put(
        "/api/agent-configs/rewrite",
        json={"display_name": "改写员", "model_config_id": first_model},
        headers=auth,
    ).json()
    updated = client.put(
        "/api/agent-configs/rewrite",
        json={"model_config_id": second_model},
        headers=auth,
    ).json()

    rows = [row for row in _bindings(client, auth) if row["agent_type"] == "rewrite"]
    assert len(rows) == 1, "PUT must not add a second row for the same agent type"
    assert updated["model_config_id"] == second_model
    assert updated["display_name"] == "改写员", "an omitted field keeps its value"
    assert updated["row_version"] == created["row_version"] + 1


def test_unbound_operation_uses_the_default_model(
    client: TestClient, auth: dict[str, str], provider: MockProvider, project: dict
) -> None:
    default_id = _model(client, auth, provider.url, "默认模型", DEFAULT_MODEL_NAME)
    assert client.post(
        f"/api/model-configs/{default_id}/default", headers=auth
    ).status_code == 200

    response = _polish(client, auth, project["id"])
    assert response.status_code == 200, response.text
    assert provider.last_model == DEFAULT_MODEL_NAME


def test_agent_binding_selects_the_model(
    client: TestClient, auth: dict[str, str], provider: MockProvider, project: dict
) -> None:
    default_id = _model(client, auth, provider.url, "默认模型", DEFAULT_MODEL_NAME)
    agent_id = _model(client, auth, provider.url, "专用模型", AGENT_MODEL_NAME)
    client.post(f"/api/model-configs/{default_id}/default", headers=auth)
    client.put(
        "/api/agent-configs/polish",
        json={"display_name": "润色员", "model_config_id": agent_id},
        headers=auth,
    )

    response = _polish(client, auth, project["id"])
    assert response.status_code == 200, response.text
    assert provider.last_model == AGENT_MODEL_NAME


def test_explicit_model_config_id_overrides_the_binding(
    client: TestClient, auth: dict[str, str], provider: MockProvider, project: dict
) -> None:
    default_id = _model(client, auth, provider.url, "默认模型", DEFAULT_MODEL_NAME)
    agent_id = _model(client, auth, provider.url, "专用模型", AGENT_MODEL_NAME)
    client.post(f"/api/model-configs/{default_id}/default", headers=auth)
    client.put(
        "/api/agent-configs/polish",
        json={"display_name": "润色员", "model_config_id": agent_id},
        headers=auth,
    )

    response = _polish(client, auth, project["id"], model_config_id=default_id)
    assert response.status_code == 200, response.text
    assert provider.last_model == DEFAULT_MODEL_NAME
