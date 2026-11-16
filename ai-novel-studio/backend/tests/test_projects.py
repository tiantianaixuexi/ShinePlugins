"""Project CRUD, the project directory layout and the JSON error envelope."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

PAYLOAD = {
    "name": "星海纪元",
    "novel_type": "科幻",
    "synopsis": "人类在星海中寻找新的家园。",
    "target_word_count": 1_000_000,
    "target_chapter_count": 500,
    "writing_style": "冷峻克制",
    "target_reader": "18-35 岁科幻读者",
}


def create_project(client: TestClient, auth: dict[str, str], **overrides: object) -> dict:
    payload = {**PAYLOAD, **overrides}
    response = client.post("/api/projects", json=payload, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_project_writes_directory(
    client: TestClient, auth: dict[str, str], data_dir: Path
) -> None:
    project = create_project(client, auth)

    assert project["name"] == "星海纪元"
    assert project["id"].startswith("proj_")
    assert project["schema_version"] == 1
    assert project["stats"]["chapters"] == 0

    project_dir = Path(project["path"])
    assert project_dir.exists()
    assert project_dir.resolve().is_relative_to(data_dir.resolve())
    assert (project_dir / "project.json").exists()
    assert (project_dir / "database" / "novel.db").exists()
    assert (project_dir / "novel" / "chapters").is_dir()
    assert (project_dir / "knowledge" / "characters").is_dir()


def test_create_requires_name(client: TestClient, auth: dict[str, str]) -> None:
    response = client.post("/api/projects", json={"name": "   "}, headers=auth)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_list_and_get(client: TestClient, auth: dict[str, str]) -> None:
    created = create_project(client, auth)

    listed = client.get("/api/projects", headers=auth).json()
    assert [item["id"] for item in listed] == [created["id"]]

    detail = client.get(f"/api/projects/{created['id']}", headers=auth).json()
    assert detail["name"] == created["name"]
    assert detail["stats"]["words"] == 0


def test_get_unknown_project_returns_404_envelope(client: TestClient, auth: dict[str, str]) -> None:
    response = client.get("/api/projects/proj_deadbeefcafe", headers=auth)
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"]


def test_update_bumps_row_version(client: TestClient, auth: dict[str, str]) -> None:
    created = create_project(client, auth)
    assert created["row_version"] == 1

    updated = client.put(
        f"/api/projects/{created['id']}",
        json={"name": "星海纪元·第二稿", "row_version": created["row_version"]},
        headers=auth,
    ).json()
    assert updated["name"] == "星海纪元·第二稿"
    assert updated["row_version"] == created["row_version"] + 1

    # Stale writers are rejected instead of silently overwriting.
    conflict = client.put(
        f"/api/projects/{created['id']}",
        json={"name": "并发写入", "row_version": created["row_version"]},
        headers=auth,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict"


def test_duplicate_copies_the_directory(client: TestClient, auth: dict[str, str]) -> None:
    created = create_project(client, auth)
    source = Path(created["path"])
    (source / "novel" / "chapters" / "001.md").write_text("第一章", encoding="utf-8")

    copy = client.post(
        f"/api/projects/{created['id']}/duplicate",
        json={"name": "星海纪元 副本"},
        headers=auth,
    ).json()

    assert copy["id"] != created["id"]
    assert (Path(copy["path"]) / "novel" / "chapters" / "001.md").read_text(
        encoding="utf-8"
    ) == "第一章"


def test_delete_is_soft_by_default(client: TestClient, auth: dict[str, str]) -> None:
    created = create_project(client, auth)
    project_dir = Path(created["path"])

    response = client.delete(f"/api/projects/{created['id']}", headers=auth)
    assert response.status_code == 204

    assert client.get("/api/projects", headers=auth).json() == []
    # Soft delete keeps user data on disk.
    assert project_dir.exists()

    # Including deleted rows exposes the tombstone.
    with_deleted = client.get("/api/projects?include_deleted=true", headers=auth).json()
    assert len(with_deleted) == 1
    assert with_deleted[0]["status"] == "deleted"


def test_hard_delete_removes_the_directory(client: TestClient, auth: dict[str, str]) -> None:
    created = create_project(client, auth)
    project_dir = Path(created["path"])

    response = client.delete(f"/api/projects/{created['id']}?hard=true", headers=auth)
    assert response.status_code == 204
    assert not project_dir.exists()


def test_project_stats_endpoint(client: TestClient, auth: dict[str, str]) -> None:
    created = create_project(client, auth)
    stats = client.get(f"/api/projects/{created['id']}/stats", headers=auth).json()
    assert stats["chapters"] == 0
    assert stats["words"] == 0


def test_openapi_schema_is_served(client: TestClient) -> None:
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert "/api/projects" in response.json()["paths"]
