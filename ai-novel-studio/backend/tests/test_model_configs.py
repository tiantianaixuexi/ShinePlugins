"""Model configuration endpoints and secret handling."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

PAYLOAD = {
    "name": "本地模型",
    "provider": "openai_compatible",
    "base_url": "http://127.0.0.1:11434/v1",
    "model_name": "qwen2.5:14b",
    "temperature": 0.7,
    "context_window": 32768,
    "input_price_per_1m": 0.0,
    "output_price_per_1m": 0.0,
}

SECRET = "sk-test-1234567890"


def test_template_exists_on_first_boot(client: TestClient, auth: dict[str, str]) -> None:
    """A fresh install should offer an editable model instead of an empty page."""
    models = client.get("/api/model-configs", headers=auth).json()
    assert len(models) >= 1
    assert models[0]["provider"] == "openai_compatible"


def test_create_does_not_leak_the_key(client: TestClient, auth: dict[str, str]) -> None:
    response = client.post("/api/model-configs", json={**PAYLOAD, "api_key": SECRET}, headers=auth)
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["has_api_key"] is True
    assert SECRET not in response.text
    assert "api_key" not in body


def test_key_is_stored_encrypted(client: TestClient, auth: dict[str, str], data_dir: Path) -> None:
    created = client.post(
        "/api/model-configs", json={**PAYLOAD, "api_key": SECRET}, headers=auth
    ).json()

    secrets_file = data_dir / "secrets.json"
    assert secrets_file.exists()
    raw = secrets_file.read_text(encoding="utf-8")
    assert SECRET not in raw

    from app.core.keystore import SecretStore, secret_label_for_model

    store = SecretStore(data_dir)
    assert store.get(secret_label_for_model(created["id"])) == SECRET


def test_update_replaces_and_clears_key(client: TestClient, auth: dict[str, str]) -> None:
    created = client.post(
        "/api/model-configs", json={**PAYLOAD, "api_key": SECRET}, headers=auth
    ).json()
    mid = created["id"]

    rotated = client.put(
        f"/api/model-configs/{mid}",
        json={"api_key": "sk-rotated-9876543210", "row_version": created["row_version"]},
        headers=auth,
    )
    assert rotated.status_code == 200
    assert rotated.json()["has_api_key"] is True

    cleared = client.put(
        f"/api/model-configs/{mid}",
        json={"api_key": "", "row_version": rotated.json()["row_version"]},
        headers=auth,
    )
    assert cleared.status_code == 200
    assert cleared.json()["has_api_key"] is False


def test_custom_provider_strings_are_accepted(client: TestClient, auth: dict[str, str]) -> None:
    """The provider is a label, not a dispatch key: any endpoint may be configured."""
    response = client.post(
        "/api/model-configs",
        json={**PAYLOAD, "provider": "my-private-gateway"},
        headers=auth,
    )
    assert response.status_code == 201, response.text
    assert response.json()["provider"] == "my-private-gateway"


def test_blank_provider_falls_back_to_openai_compatible(
    client: TestClient, auth: dict[str, str]
) -> None:
    response = client.post("/api/model-configs", json={**PAYLOAD, "provider": "   "}, headers=auth)
    assert response.status_code == 201
    assert response.json()["provider"] == "openai_compatible"


def test_delete_removes_row_and_secret(
    client: TestClient, auth: dict[str, str], data_dir: Path
) -> None:
    created = client.post(
        "/api/model-configs", json={**PAYLOAD, "api_key": SECRET}, headers=auth
    ).json()

    assert client.delete(f"/api/model-configs/{created['id']}", headers=auth).status_code == 204

    from app.core.keystore import secret_label_for_model

    secrets_file = data_dir / "secrets.json"
    if secrets_file.exists():
        assert secret_label_for_model(created["id"]) not in secrets_file.read_text(encoding="utf-8")


def test_set_default(client: TestClient, auth: dict[str, str]) -> None:
    created = client.post(
        "/api/model-configs", json={**PAYLOAD, "name": "备用"}, headers=auth
    ).json()

    promoted = client.post(f"/api/model-configs/{created['id']}/default", headers=auth)
    assert promoted.status_code == 200
    assert promoted.json()["is_default"] is True

    others = client.get("/api/model-configs", headers=auth).json()
    assert [item["id"] for item in others if item["is_default"]] == [created["id"]]


def test_stale_row_version_is_rejected(client: TestClient, auth: dict[str, str]) -> None:
    created = client.post("/api/model-configs", json={**PAYLOAD}, headers=auth).json()
    response = client.put(
        f"/api/model-configs/{created['id']}",
        json={"temperature": 0.1, "row_version": 99},
        headers=auth,
    )
    assert response.status_code == 409


def test_explicit_null_resets_not_null_columns(client: TestClient, auth: dict[str, str]) -> None:
    """`null` means "clear this field", never a 500 from a NOT NULL column."""
    created = client.post(
        "/api/model-configs", json={**PAYLOAD, "notes": "临时备注"}, headers=auth
    ).json()

    response = client.put(
        f"/api/model-configs/{created['id']}",
        json={"base_url": None, "notes": None, "row_version": created["row_version"]},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["base_url"] == ""
    assert body["notes"] == ""


def test_absent_field_is_left_unchanged(client: TestClient, auth: dict[str, str]) -> None:
    created = client.post(
        "/api/model-configs", json={**PAYLOAD, "notes": "保留我"}, headers=auth
    ).json()

    response = client.put(
        f"/api/model-configs/{created['id']}",
        json={"temperature": 0.2},
        headers=auth,
    )
    assert response.status_code == 200
    assert response.json()["notes"] == "保留我"
    assert response.json()["temperature"] == 0.2
