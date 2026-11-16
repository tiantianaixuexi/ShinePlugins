"""Context channels: 「前情提要」 looks only back, 「伏笔」 only forward.

T-33: ``_recent_summaries`` used to take the last N summaries of the *whole*
project, so writing chapter 50 pulled in the summaries of chapters 51 and 52 —
plot the author had not written yet leaked into the prompt as if it had
happened. The fix splits the two directions into two channels:

* ``context`` (前情提要) — ``chapter_summaries`` of chapters with a smaller
  ``sort_order`` than the target chapter, and nothing else;
* ``foreshadows`` (伏笔与后续规划) — the target chapter and up to three chapters
  after it, read from their ``outlines`` rows (falling back to
  ``chapter_summaries``), so the information is **kept** but labelled as a
  direction constraint rather than as fact.

The last two tests pin the prompt-upgrade contract: a database seeded by the
previous build gains a new ``prompt_templates`` version, while a row the author
edited is never overwritten.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.prompts.builtin import (
    BUILTIN_VERSION,
    LEGACY_USER_TEXTS,
    PROMPTS_BY_KEY,
)
from app.ai.prompts.service import BUILTIN_VERSION_KEY, PromptService, render
from app.models.novel import ChapterSummary, Outline
from app.models.studio import AppMeta, ModelConfig, PromptTemplate
from app.schemas.ai import AIRequest


def _ai(client: TestClient) -> Any:
    return cast(Any, client.app.state.runtime).ai


def _prompts(client: TestClient) -> PromptService:
    return cast(PromptService, cast(Any, client.app.state.runtime).prompts)


def _novel_db(client: TestClient, project_id: str) -> Any:
    from app.services.novel_service import NovelService

    service = NovelService(cast(Any, client.app.state.runtime).project_service)
    return service.database_for(project_id)


def _model() -> ModelConfig:
    """A transient model row: only ``context_window`` matters to the builder."""
    return ModelConfig(name="上下文测试", model_name="mock-model", context_window=8192)


def _chapters(
    client: TestClient, auth: dict[str, str], project_id: str, titles: list[str]
) -> list[str]:
    ids: list[str] = []
    for title in titles:
        response = client.post(
            f"/api/projects/{project_id}/chapters", json={"title": title}, headers=auth
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    return ids


def _add_summary(
    client: TestClient,
    project_id: str,
    chapter_id: str,
    summary: str,
    *,
    foreshadows: list[str] | None = None,
    plot_progress: str = "",
) -> None:
    database = _novel_db(client, project_id)
    with database.session() as session:
        session.add(
            ChapterSummary(
                project_id=project_id,
                chapter_id=chapter_id,
                summary=summary,
                foreshadows=foreshadows or [],
                plot_progress=plot_progress,
            )
        )


def _add_outline(
    client: TestClient,
    project_id: str,
    chapter_id: str,
    *,
    title: str,
    goal: str = "",
    foreshadows: list[str] | None = None,
    sort_order: int = 0,
) -> None:
    database = _novel_db(client, project_id)
    with database.session() as session:
        session.add(
            Outline(
                project_id=project_id,
                level="chapter",
                parent_id=chapter_id,
                title=title,
                goal=goal,
                foreshadows=foreshadows or [],
                sort_order=sort_order,
            )
        )


def _variables(client: TestClient, project_id: str, chapter_id: str | None) -> dict[str, str]:
    return _ai(client)._build_variables(
        "write",
        AIRequest(project_id=project_id, chapter_id=chapter_id),
        _model(),
    )


def test_context_only_includes_chapters_before_the_target(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    project_id = project["id"]
    ids = _chapters(
        client, auth, project_id, ["第一章", "第二章", "第三章", "第四章", "第五章"]
    )
    for number, chapter_id in enumerate(ids, start=1):
        _add_summary(client, project_id, chapter_id, f"摘要-第{number}章")

    context = _variables(client, project_id, ids[3])["context"]

    assert "摘要-第1章" in context
    assert "摘要-第3章" in context
    # The target chapter's own summary is not "前情", and later chapters are spoilers.
    assert "摘要-第4章" not in context
    assert "摘要-第5章" not in context


def test_future_outline_feeds_the_foreshadow_channel(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    project_id = project["id"]
    ids = _chapters(client, auth, project_id, ["第一章", "第二章", "第三章"])
    _add_summary(client, project_id, ids[0], "摘要-第一章", foreshadows=["雨夜出现的铜铃"])
    _add_outline(
        client,
        project_id,
        ids[2],
        title="第三章 玉佩",
        goal="沈砚查明玉佩的来历",
        foreshadows=["玉佩上缺失的第三道刻痕"],
    )

    variables = _variables(client, project_id, ids[1])

    # Forward information is kept, not dropped …
    assert "玉佩上缺失的第三道刻痕" in variables["foreshadows"]
    assert "第三章 玉佩" in variables["foreshadows"]
    assert "沈砚查明玉佩的来历" in variables["foreshadows"]
    # … but it never reaches 前情提要, which is the spoiler channel.
    assert "玉佩上缺失的第三道刻痕" not in variables["context"]

    user_text, missing = render(PROMPTS_BY_KEY["write.chapter"].user, variables)
    assert missing == []
    assert "尚未发生" in user_text
    assert "玉佩上缺失的第三道刻痕" in user_text


def test_summary_foreshadows_are_used_when_a_chapter_has_no_outline(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    project_id = project["id"]
    ids = _chapters(client, auth, project_id, ["第一章", "第二章"])
    _add_summary(
        client,
        project_id,
        ids[1],
        "摘要-第二章",
        foreshadows=["老人不肯提起的旧名字"],
        plot_progress="主角开始怀疑老人身份",
    )

    variables = _variables(client, project_id, ids[0])

    assert "老人不肯提起的旧名字" in variables["foreshadows"]
    assert "主角开始怀疑老人身份" in variables["foreshadows"]
    assert "老人不肯提起的旧名字" not in variables["context"]


def test_no_outline_and_no_summary_yields_placeholder(
    client: TestClient, auth: dict[str, str], project: dict
) -> None:
    project_id = project["id"]
    ids = _chapters(client, auth, project_id, ["第一章"])

    assert _variables(client, project_id, ids[0])["foreshadows"] == "（无）"
    # No chapter in flight must not raise either.
    unscoped = _ai(client)._build_variables(
        "write", AIRequest(project_id=project_id), _model()
    )
    assert unscoped["foreshadows"] == "（无）"
    assert unscoped["context"] == ""


def test_old_database_gains_a_new_prompt_version(
    client: TestClient, auth: dict[str, str]
) -> None:
    """A v1 row (previous built-in, no marker) is upgraded instead of ignored."""
    service = _prompts(client)

    with service.db.session() as session:
        for key, legacy_users in LEGACY_USER_TEXTS.items():
            spec = PROMPTS_BY_KEY[key]
            legacy_user = legacy_users[0]
            assert "{{foreshadows}}" not in legacy_user
            row = session.scalars(
                select(PromptTemplate).where(PromptTemplate.key == key)
            ).one()
            row.content = f"### system\n{spec.system}\n### user\n{legacy_user}"
            row.variables = [name for name in spec.variables if name != "foreshadows"]
        marker = session.get(AppMeta, BUILTIN_VERSION_KEY)
        if marker is not None:
            session.delete(marker)

    assert service.ensure_builtins() == len(LEGACY_USER_TEXTS)

    items = [
        item
        for item in client.get("/api/ai/prompts", headers=auth).json()
        if item["key"] == "write.chapter"
    ]
    assert [item["version"] for item in items] == [1, BUILTIN_VERSION]
    newest = max(items, key=lambda item: item["version"])
    assert newest["version"] == 2
    assert "foreshadows" in newest["variables"]

    resolved = service.resolve("write.chapter")
    assert "{{foreshadows}}" in resolved.user
    assert "尚未发生" in resolved.user


def test_author_edit_is_never_overwritten_by_an_upgrade(
    client: TestClient, auth: dict[str, str]
) -> None:
    service = _prompts(client)
    response = client.patch(
        "/api/ai/prompts/write.chapter",
        json={"content": "### system\n我的系统\n### user\n{{outline}}"},
        headers=auth,
    )
    assert response.status_code == 200, response.text

    # Clear the marker so the next start believes an upgrade is pending.
    with service.db.session() as session:
        marker = session.get(AppMeta, BUILTIN_VERSION_KEY)
        if marker is not None:
            session.delete(marker)

    assert service.ensure_builtins() == 0
    assert service.resolve("write.chapter").user == "{{outline}}"
