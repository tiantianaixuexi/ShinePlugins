"""Health and authentication behaviour."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_is_ok(client: TestClient, auth: dict[str, str]) -> None:
    response = client.get("/api/health", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "AI Novel Studio"
    assert body["schema_version"] >= 1


def test_health_requires_token(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "auth_required"


def test_wrong_token_is_rejected(client: TestClient, other_auth: dict[str, str]) -> None:
    response = client.get("/api/health", headers=other_auth)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


def test_cors_preflight_is_not_blocked_by_auth(client: TestClient) -> None:
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://127.0.0.1:1420",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_healthz_is_public(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200


def test_system_info(client: TestClient, auth: dict[str, str]) -> None:
    body = client.get("/api/system/info", headers=auth).json()
    assert body["app"] == "AI Novel Studio"
    assert body["projects"] == 0
    assert body["auth_required"] is True
    assert body["data_dir"]


def test_studio_stats_starts_empty(client: TestClient, auth: dict[str, str]) -> None:
    body = client.get("/api/system/stats", headers=auth).json()
    assert body["totals"]["projects"] == 0
    assert body["projects"] == []
