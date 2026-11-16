"""Shared pytest fixtures.

Every test runs against a throwaway data directory so a broken run can never
touch the developer's real studio library.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-token"


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    directory = tmp_path / "studio-data"
    directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("NOVEL_STUDIO_DATA_DIR", str(directory))
    monkeypatch.setenv("NOVEL_STUDIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("NOVEL_STUDIO_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("NOVEL_STUDIO_LOG_JSON", "0")

    from app.core.config import reset_settings_cache

    reset_settings_cache()
    try:
        yield directory
    finally:
        reset_settings_cache()


@pytest.fixture()
def settings(data_dir: Path):
    from app.core.config import get_settings

    return get_settings()


@pytest.fixture()
def client(settings) -> Iterator[TestClient]:
    from app.main import create_app

    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def other_auth() -> dict[str, str]:
    return {"Authorization": "Bearer wrong-token"}


@pytest.fixture()
def project(client: TestClient, auth: dict[str, str]) -> dict:
    """A ready-to-use project with its own on-disk database."""
    response = client.post(
        "/api/projects",
        json={
            "name": "测试小说",
            "novel_type": "玄幻",
            "synopsis": "用于测试的项目",
            "target_word_count": 100_000,
            "target_chapter_count": 100,
        },
        headers=auth,
    )
    assert response.status_code == 201, response.text
    return response.json()
