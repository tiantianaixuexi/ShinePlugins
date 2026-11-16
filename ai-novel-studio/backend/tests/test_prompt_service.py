"""Prompt template tests: seeding, resolution, rendering and author overrides.

``prompt_templates`` used to be write-once (seeded at start-up, version pinned
to 1) with no endpoint to change it, so ``builtin.py``'s promise that "the
authoring UI can override any of them" was unreachable. These tests pin the
seeding contract, the DB-wins resolution order, the missing-variable reporting
and the new ``PATCH /api/ai/prompts/{key}`` version bump.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi.testclient import TestClient

from app.ai.prompts.builtin import PROMPTS, PROMPTS_BY_KEY
from app.ai.prompts.service import PromptService, render


def _prompts(client: TestClient) -> PromptService:
    # ``TestClient.app`` is typed as the generic ASGI app union, so reach the
    # runtime through the concrete ASGI type the factory actually returned.
    asgi = cast(Any, client.app)
    return cast(PromptService, asgi.state.runtime.prompts)


def test_builtins_are_seeded_once(client: TestClient) -> None:
    service = _prompts(client)

    rows = service.list()
    assert {row.key for row in rows} == set(PROMPTS_BY_KEY)
    assert len(rows) == len(PROMPTS)
    assert all(row.version == 1 for row in rows)
    # Seeding is idempotent: a second start must not add duplicates.
    assert service.ensure_builtins() == 0


def test_render_reports_missing_variables(client: TestClient) -> None:
    text, missing = render("甲{{a}}乙{{b}}", {"a": "1"})
    assert text == "甲1乙"
    assert missing == ["b"]

    service = _prompts(client)
    messages, key, missing_vars = service.render_for("write", {})
    assert key == "write.chapter"
    assert missing_vars  # declared placeholders that no caller supplied
    assert messages[0]["role"] == "system"
    assert "{{" not in messages[1]["content"]


def test_resolve_prefers_database_over_builtin(client: TestClient, auth: dict[str, str]) -> None:
    service = _prompts(client)
    builtin = PROMPTS_BY_KEY["edit.polish"]

    response = client.patch(
        "/api/ai/prompts/edit.polish",
        json={"content": "### system\n改过的系统\n### user\n改过的用户"},
        headers=auth,
    )
    assert response.status_code == 200, response.text

    spec = service.resolve("edit.polish")
    assert spec.system == "改过的系统"
    assert spec.user == "改过的用户"
    assert spec.system != builtin.system
    assert spec.operation == builtin.operation


def test_patch_bumps_version_and_keeps_history(
    client: TestClient, auth: dict[str, str]
) -> None:
    before = client.get("/api/ai/prompts", headers=auth)
    assert before.status_code == 200, before.text
    original: dict[str, Any] = next(
        item for item in before.json() if item["key"] == "write.chapter"
    )
    assert original["version"] == 1

    response = client.patch(
        "/api/ai/prompts/write.chapter",
        json={
            "content": "### system\n新版系统\n### user\n{{outline}}",
            "name": "新版写作",
            "variables": ["outline"],
        },
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["key"] == "write.chapter"
    assert body["version"] == 2
    assert body["name"] == "新版写作"
    assert body["variables"] == ["outline"]
    assert body["is_active"] is True

    after = [
        item
        for item in client.get("/api/ai/prompts", headers=auth).json()
        if item["key"] == "write.chapter"
    ]
    assert [item["version"] for item in after] == [1, 2]
    assert max(item["version"] for item in after) == 2


def test_patch_unknown_key_is_404(client: TestClient, auth: dict[str, str]) -> None:
    response = client.patch(
        "/api/ai/prompts/not.a.real.prompt",
        json={"content": "随便写点"},
        headers=auth,
    )
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert "not.a.real.prompt" in error["message"]


def test_patch_rejects_empty_content(client: TestClient, auth: dict[str, str]) -> None:
    response = client.patch(
        "/api/ai/prompts/write.chapter", json={"content": ""}, headers=auth
    )
    assert response.status_code == 422
