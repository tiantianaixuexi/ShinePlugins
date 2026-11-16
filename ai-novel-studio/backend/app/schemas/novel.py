"""Pydantic schemas for volumes, chapters and chapter versions."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

CHAPTER_STATUSES = ("draft", "writing", "review", "done", "archived")
VOLUME_STATUSES = ("draft", "writing", "done", "archived")


class VolumeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=20000)


class VolumeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=20000)
    sort_order: int | None = Field(default=None, ge=0)
    row_version: int | None = Field(default=None, ge=1)


class VolumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    summary: str
    sort_order: int
    word_count: int
    status: str
    created_at: datetime
    updated_at: datetime


class ChapterCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    volume_id: str | None = None
    content: str = Field(default="", max_length=5_000_000)
    status: str = Field(default="draft")

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str) -> str:
        if value not in CHAPTER_STATUSES:
            raise ValueError(f"Unknown status {value!r}")
        return value


class ChapterUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    volume_id: str | None = None
    content: str | None = Field(default=None, max_length=5_000_000)
    status: str | None = None
    sort_order: int | None = Field(default=None, ge=0)
    #: Force a history snapshot even if the last one is recent.
    snapshot: bool = False
    row_version: int | None = Field(default=None, ge=1)

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str | None) -> str | None:
        if value is not None and value not in CHAPTER_STATUSES:
            raise ValueError(f"Unknown status {value!r}")
        return value


class ChapterListItem(BaseModel):
    """Chapter metadata without the manuscript body (lists must stay cheap)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    volume_id: str | None
    title: str
    sort_order: int
    word_count: int
    status: str
    summary: str
    #: Present so a recycle bin / "recently deleted" view can tell rows apart.
    is_deleted: bool = False
    deleted_at: datetime | None = None
    updated_at: datetime


class ChapterOut(ChapterListItem):
    content: str
    row_version: int
    created_at: datetime


class ChapterVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chapter_id: str
    version_no: int
    title: str
    word_count: int
    source: str
    #: Set only for ``source="ai"`` versions produced by an AI task.
    task_id: str | None = None
    note: str
    created_at: datetime


class ChapterAcceptAi(BaseModel):
    """Body of ``POST /chapters/{id}/accept-ai``.

    The client sends the **full** post-accept manuscript (it already merged the
    AI text into the draft), so the server never has to guess how a fragment
    was applied.
    """

    content: str = Field(min_length=1, max_length=5_000_000)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    #: Which AI task produced the text; ``None`` when the caller cannot tell.
    task_id: str | None = Field(default=None, max_length=40)
    note: str = Field(default="", max_length=2000)


class ChapterAcceptAiResult(BaseModel):
    """The chapter after the accept plus the ``source="ai"`` version created."""

    chapter: ChapterOut
    version: ChapterVersionOut


class ChapterReorder(BaseModel):
    """New ordering for a project's chapters (ids in the desired order)."""

    chapter_ids: list[str] = Field(min_length=0, max_length=10000)


class VolumeWithChapters(BaseModel):
    volume: VolumeOut
    chapters: list[ChapterListItem] = Field(default_factory=list)
