"""Pydantic schemas for the project API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectCreate(BaseModel):
    """Payload for ``POST /api/projects`` (plan §4.1)."""

    name: str = Field(min_length=1, max_length=200)
    novel_type: str = Field(default="web", max_length=64)
    synopsis: str = Field(default="", max_length=20000)
    target_word_count: int = Field(default=0, ge=0, le=1_000_000_000)
    target_chapter_count: int = Field(default=0, ge=0, le=100_000)
    writing_style: str = Field(default="", max_length=4000)
    target_reader: str = Field(default="", max_length=200)
    language: str = Field(default="zh-CN", max_length=16)
    author: str = Field(default="", max_length=200)
    default_model_config_id: str | None = None
    embedding_model_config_id: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class ProjectUpdate(BaseModel):
    """Payload for ``PUT /api/projects/{id}``; every field is optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    novel_type: str | None = Field(default=None, max_length=64)
    synopsis: str | None = Field(default=None, max_length=20000)
    target_word_count: int | None = Field(default=None, ge=0, le=1_000_000_000)
    target_chapter_count: int | None = Field(default=None, ge=0, le=100_000)
    writing_style: str | None = Field(default=None, max_length=4000)
    target_reader: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=16)
    author: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=32)
    default_model_config_id: str | None = None
    embedding_model_config_id: str | None = None
    settings: dict[str, Any] | None = None
    #: optimistic concurrency guard; when set, the update fails if the row moved
    row_version: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def _name_not_null(cls, value: str | None) -> str | None:
        """An explicit ``null`` is a client bug, not a request to erase the title."""
        if value is None:
            raise ValueError("name must not be null")
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class ProjectStats(BaseModel):
    volumes: int = 0
    chapters: int = 0
    words: int = 0
    characters: int = 0
    outlines: int = 0
    events: int = 0
    foreshadows: int = 0
    chunks: int = 0
    versions: int = 0


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    novel_type: str
    synopsis: str
    target_word_count: int
    target_chapter_count: int
    writing_style: str
    target_reader: str
    language: str
    author: str
    status: str
    path: str
    schema_version: int
    default_model_config_id: str | None = None
    embedding_model_config_id: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    row_version: int
    created_at: datetime
    updated_at: datetime

    stats: ProjectStats = Field(default_factory=ProjectStats)


class ProjectSummary(BaseModel):
    """Compact projection used by lists."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    novel_type: str
    status: str
    language: str
    target_word_count: int
    target_chapter_count: int
    updated_at: datetime
    created_at: datetime
