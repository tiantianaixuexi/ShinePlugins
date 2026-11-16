"""Pydantic schemas for the per-agent model bindings (plan §7.2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentConfigUpsert(BaseModel):
    """Body for ``PUT /api/agent-configs/{agent_type}``.

    Every field is optional so one endpoint serves both "create" and "edit a
    single setting". Fields that are **omitted** keep their previous value;
    fields explicitly set to ``null`` (``model_config_id`` / ``temperature`` /
    ``max_tokens``) clear the override, which is how the UI unbinds a model.
    """

    display_name: str | None = Field(default=None, max_length=120)
    model_config_id: str | None = Field(default=None, max_length=40)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=4_000_000)
    system_prompt: str | None = Field(default=None, max_length=200_000)

    @field_validator("display_name", "model_config_id", "system_prompt")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class AgentConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_type: str
    display_name: str
    model_config_id: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str = ""
    row_version: int
