"""Schemas for the AI writing endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.ai.prompts.builtin import OPERATIONS


class AIRequest(BaseModel):
    """One writing operation against one project."""

    project_id: str
    chapter_id: str | None = None

    #: The working text. For whole-chapter operations this may be empty when
    #: ``chapter_id`` is given (the chapter body is loaded from the database).
    content: str = Field(default="", max_length=2_000_000)
    #: The selected passage for expand/rewrite/polish.
    selection: str = Field(default="", max_length=200_000)
    #: Free-form instruction from the author ("节奏再快一点").
    instruction: str = Field(default="", max_length=8000)
    #: Optional outline override for write/outline.
    outline: str = Field(default="", max_length=200_000)

    target_words: int = Field(default=0, ge=0, le=100_000)
    model_config_id: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    @field_validator("chapter_id", "model_config_id")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class AIResult(BaseModel):
    task_id: str
    operation: str
    text: str
    model: str
    prompt_key: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


class SummaryRequest(BaseModel):
    """Ask for one chapter to be distilled into L1 memory."""

    project_id: str
    #: Re-summarise even when a non-empty summary already exists.
    force: bool = False


class SummaryResult(BaseModel):
    chapter_id: str
    summary: str = ""
    #: True when an existing summary was returned without calling the model.
    cached: bool = False
    #: Set when nothing was generated (``"empty"`` = chapter body is blank).
    skipped: str | None = None


class OutlineRequest(BaseModel):
    """Ask for one chapter outline to be generated **and persisted**."""

    project_id: str
    #: Regenerate even when a usable outline row already exists.
    force: bool = False
    #: Extra guidance for this outline ("这一章节奏放慢").
    instruction: str = Field(default="", max_length=8000)


class OutlineResult(BaseModel):
    """One ``outlines`` row as returned by ``POST /api/ai/outline/{chapter_id}``."""

    chapter_id: str
    outline_id: str
    level: str = "chapter"
    parent_id: str | None = None
    title: str = ""
    goal: str = ""
    conflict: str = ""
    characters: list[str] = Field(default_factory=list)
    key_events: list[str] = Field(default_factory=list)
    twists: str = ""
    foreshadows: list[str] = Field(default_factory=list)
    ending: str = ""
    target_word_count: int = 0
    #: Raw model reply, kept so a degraded outline still has something to show.
    content: str = ""
    #: True when the reply was not JSON and only ``content`` could be filled.
    degraded: bool = False
    #: True when an existing row was returned without calling the model.
    cached: bool = False
    row_version: int = 1


class PromptSummary(BaseModel):
    key: str
    name: str
    version: int
    description: str = ""
    variables: list[str] = Field(default_factory=list)
    is_active: bool = True


class PromptUpdate(BaseModel):
    """Body for ``PATCH /api/ai/prompts/{key}``.

    ``content`` uses the stored ``### system`` / ``### user`` form so the split
    in :meth:`PromptService._split` keeps working; a plain body is accepted too
    and treated as the user prompt.
    """

    content: str = Field(min_length=1, max_length=200_000)
    #: Display name override; omitted keeps the previous row's name.
    name: str | None = Field(default=None, max_length=200)
    #: Declared placeholders; omitted keeps the previous row's list.
    variables: list[str] | None = Field(default=None, max_length=64)


class AITaskSummary(BaseModel):
    id: str
    project_id: str | None
    kind: str
    status: str
    model_config_id: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    error: str | None = None
    created_at: str


def available_operations() -> list[str]:
    return sorted(OPERATIONS)
