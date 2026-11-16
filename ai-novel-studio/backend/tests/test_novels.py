"""Volume, chapter and version behaviour."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.utils.text import count_words


def test_count_words_counts_cjk_and_latin() -> None:
    assert count_words("天地玄黄") == 4
    assert count_words("hello world") == 2
    assert count_words("天地玄黄宇宙洪荒\n\n日月盈昃") == 12
    assert count_words("") == 0


def test_volume_crud(client: TestClient, auth: dict[str, str], project: dict) -> None:
    pid = project["id"]

    created = client.post(
        f"/api/projects/{pid}/volumes", json={"title": "第一卷 开端"}, headers=auth
    )
    assert created.status_code == 201, created.text
    volume = created.json()
    assert volume["sort_order"] == 1

    listed = client.get(f"/api/projects/{pid}/volumes", headers=auth).json()
    assert [item["id"] for item in listed] == [volume["id"]]

    updated = client.patch(
        f"/api/projects/{pid}/volumes/{volume['id']}",
        json={"title": "第一卷 缘起", "row_version": 1},
        headers=auth,
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "第一卷 缘起"

    # Deleting a volume must not delete its chapters.
    chapter = client.post(
        f"/api/projects/{pid}/chapters",
        json={"title": "第一章", "volume_id": volume["id"]},
        headers=auth,
    ).json()

    assert (
        client.delete(f"/api/projects/{pid}/volumes/{volume['id']}", headers=auth).status_code
        == 204
    )
    remaining = client.get(f"/api/projects/{pid}/chapters", headers=auth).json()
    assert [item["id"] for item in remaining] == [chapter["id"]]
    assert remaining[0]["volume_id"] is None


def test_chapter_lifecycle_and_word_count(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]

    chapter = client.post(
        f"/api/projects/{pid}/chapters",
        json={"title": "第一章 启程", "content": "少年踏上了旅途。"},
        headers=auth,
    ).json()
    assert chapter["word_count"] == count_words("少年踏上了旅途。")

    saved = client.put(
        f"/api/projects/{pid}/chapters/{chapter['id']}",
        json={"content": "少年踏上了旅途。\n\n他没有回头。", "row_version": chapter["row_version"]},
        headers=auth,
    )
    assert saved.status_code == 200
    assert saved.json()["word_count"] == count_words("少年踏上了旅途。\n\n他没有回头。")

    fetched = client.get(f"/api/projects/{pid}/chapters/{chapter['id']}", headers=auth).json()
    assert fetched["content"].startswith("少年踏上了旅途。")

    assert (
        client.delete(f"/api/projects/{pid}/chapters/{chapter['id']}", headers=auth).status_code
        == 204
    )
    # Soft deleted: hidden from the list, still refused on direct read.
    assert client.get(f"/api/projects/{pid}/chapters", headers=auth).json() == []
    assert (
        client.get(f"/api/projects/{pid}/chapters/{chapter['id']}", headers=auth).status_code == 404
    )


def test_stale_row_version_is_rejected(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]
    chapter = client.post(
        f"/api/projects/{pid}/chapters", json={"title": "第一章"}, headers=auth
    ).json()

    client.put(
        f"/api/projects/{pid}/chapters/{chapter['id']}",
        json={"content": "第一版"},
        headers=auth,
    )
    conflict = client.put(
        f"/api/projects/{pid}/chapters/{chapter['id']}",
        json={"content": "并发写入", "row_version": 1},
        headers=auth,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"]["expected"] == 1


def test_versions_snapshot_and_restore(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]
    chapter = client.post(
        f"/api/projects/{pid}/chapters",
        json={"title": "第一章", "content": "原始正文"},
        headers=auth,
    ).json()
    cid = chapter["id"]

    # Creation already stored a baseline version.
    versions = client.get(f"/api/projects/{pid}/chapters/{cid}/versions", headers=auth).json()
    assert len(versions) == 1
    baseline = versions[0]

    forced = client.post(f"/api/projects/{pid}/chapters/{cid}/versions", headers=auth)
    assert forced.status_code == 201
    versions = forced.json()
    assert len(versions) == 2
    assert versions[0]["version_no"] == baseline["version_no"] + 1

    # Autosave without the snapshot flag stays within the snapshot window.
    client.put(
        f"/api/projects/{pid}/chapters/{cid}",
        json={"content": "改写后的正文"},
        headers=auth,
    )
    assert len(client.get(f"/api/projects/{pid}/chapters/{cid}/versions", headers=auth).json()) == 2

    restored = client.post(
        f"/api/projects/{pid}/chapters/{cid}/versions/{baseline['id']}/restore", headers=auth
    )
    assert restored.status_code == 200
    assert restored.json()["content"] == "原始正文"

    # Restoring keeps the previous text recoverable as a new version.
    versions = client.get(f"/api/projects/{pid}/chapters/{cid}/versions", headers=auth).json()
    assert len(versions) >= 3


def test_reorder_chapters(client: TestClient, auth: dict[str, str], project: dict) -> None:
    pid = project["id"]
    ids = []
    for index in range(3):
        chapter = client.post(
            f"/api/projects/{pid}/chapters",
            json={"title": f"第 {index + 1} 章"},
            headers=auth,
        ).json()
        ids.append(chapter["id"])

    reversed_order = list(reversed(ids))
    response = client.post(
        f"/api/projects/{pid}/chapters/reorder",
        json={"chapter_ids": reversed_order},
        headers=auth,
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == reversed_order

    bad = client.post(
        f"/api/projects/{pid}/chapters/reorder",
        json={"chapter_ids": ["chap_missing0000"]},
        headers=auth,
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "validation_failed"


def test_stats_reflect_written_content(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]
    text = "天地玄黄，宇宙洪荒。" * 10
    client.post(
        f"/api/projects/{pid}/chapters",
        json={"title": "第一章", "content": text},
        headers=auth,
    )

    stats = client.get(f"/api/projects/{pid}/stats", headers=auth).json()
    assert stats["chapters"] == 1
    assert stats["words"] == count_words(text)


def test_unknown_volume_is_a_422_not_a_500(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]
    response = client.post(
        f"/api/projects/{pid}/chapters",
        json={"title": "孤章", "volume_id": "vol_does_not_exist"},
        headers=auth,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_volume_from_another_project_is_rejected(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    other = client.post("/api/projects", json={"name": "另一本书"}, headers=auth).json()
    foreign_volume = client.post(
        f"/api/projects/{other['id']}/volumes", json={"title": "别人的卷"}, headers=auth
    ).json()

    response = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "孤章", "volume_id": foreign_volume["id"]},
        headers=auth,
    )
    assert response.status_code == 422


def test_chapter_can_be_detached_from_its_volume(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]
    volume = client.post(
        f"/api/projects/{pid}/volumes", json={"title": "第一卷"}, headers=auth
    ).json()
    chapter = client.post(
        f"/api/projects/{pid}/chapters",
        json={"title": "第一章", "volume_id": volume["id"]},
        headers=auth,
    ).json()
    assert chapter["volume_id"] == volume["id"]

    detached = client.put(
        f"/api/projects/{pid}/chapters/{chapter['id']}",
        json={"volume_id": None},
        headers=auth,
    )
    assert detached.status_code == 200
    assert detached.json()["volume_id"] is None


def test_reorder_produces_a_dense_sequence(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]
    ids = [
        client.post(
            f"/api/projects/{pid}/chapters", json={"title": f"第 {n} 章"}, headers=auth
        ).json()["id"]
        for n in range(4)
    ]

    # Reorder only two of them; the rest must follow without colliding.
    response = client.post(
        f"/api/projects/{pid}/chapters/reorder",
        json={"chapter_ids": [ids[2], ids[0]]},
        headers=auth,
    )
    assert response.status_code == 200
    order = [item["sort_order"] for item in response.json()]
    assert order == [0, 1, 2, 3]
    assert [item["id"] for item in response.json()][:2] == [ids[2], ids[0]]


def test_deleted_chapters_are_visible_with_a_flag(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    pid = project["id"]
    chapter = client.post(
        f"/api/projects/{pid}/chapters", json={"title": "待删除"}, headers=auth
    ).json()
    client.delete(f"/api/projects/{pid}/chapters/{chapter['id']}", headers=auth)

    rows = client.get(f"/api/projects/{pid}/chapters?include_deleted=true", headers=auth).json()
    assert len(rows) == 1
    assert rows[0]["is_deleted"] is True
    assert rows[0]["deleted_at"]
