"""Pydantic schemas for model configuration endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROVIDERS = (
    "openai_compatible",
    "openai",
    "anthropic",
    "gemini",
    "ollama",
    "deepseek",
    "minimax",
    "azure_openai",
    "custom",
)


class ModelConfigBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(default="openai_compatible", max_length=64)
    base_url: str = Field(default="", max_length=500)
    model_name: str = Field(min_length=1, max_length=200)

    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=1, le=4_000_000)
    timeout_s: float = Field(default=120.0, gt=0.0, le=3600.0)
    retry_count: int = Field(default=2, ge=0, le=10)

    context_window: int = Field(default=32768, ge=1, le=100_000_000)
    max_output_tokens: int = Field(default=4096, ge=1, le=4_000_000)
    supports_streaming: bool = True
    supports_json_mode: bool = False
    supports_vision: bool = False
    supports_tools: bool = False

    input_price_per_1m: float = Field(default=0.0, ge=0.0)
    output_price_per_1m: float = Field(default=0.0, ge=0.0)

    capabilities: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=4000)
    is_active: bool = True
    fallback_ids: list[str] = Field(default_factory=list)

    @field_validator("provider")
    @classmethod
    def _provider_is_a_hint(cls, value: str) -> str:
        """Any provider string is accepted.

        The provider is a label for the UI, not a dispatch key: the adapter is
        chosen by the endpoint's wire format (OpenAI-compatible), so a user can
        point at any gateway, including one we have never heard of.
        """
        stripped = value.strip()
        return stripped or "openai_compatible"

    @field_validator("name", "model_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class ModelConfigCreate(ModelConfigBase):
    #: Write-only. Stored encrypted; never returned by the API.
    api_key: str | None = Field(default=None, max_length=2000)


class ModelConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    provider: str | None = Field(default=None, max_length=64)
    base_url: str | None = Field(default=None, max_length=500)
    model_name: str | None = Field(default=None, min_length=1, max_length=200)

    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=4_000_000)
    timeout_s: float | None = Field(default=None, gt=0.0, le=3600.0)
    retry_count: int | None = Field(default=None, ge=0, le=10)

    context_window: int | None = Field(default=None, ge=1, le=100_000_000)
    max_output_tokens: int | None = Field(default=None, ge=1, le=4_000_000)
    supports_streaming: bool | None = None
    supports_json_mode: bool | None = None
    supports_vision: bool | None = None
    supports_tools: bool | None = None

    input_price_per_1m: float | None = Field(default=None, ge=0.0)
    output_price_per_1m: float | None = Field(default=None, ge=0.0)

    capabilities: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=4000)
    is_active: bool | None = None
    fallback_ids: list[str] | None = None

    #: Write-only. ``""`` clears the stored key.
    api_key: str | None = Field(default=None, max_length=2000)
    row_version: int | None = Field(default=None, ge=1)


class ModelConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    provider: str
    base_url: str
    model_name: str

    temperature: float
    top_p: float
    max_tokens: int
    timeout_s: float
    retry_count: int

    context_window: int
    max_output_tokens: int
    supports_streaming: bool
    supports_json_mode: bool
    supports_vision: bool
    supports_tools: bool

    input_price_per_1m: float
    output_price_per_1m: float

    capabilities: dict[str, Any]
    notes: str
    is_active: bool
    is_default: bool
    fallback_ids: list[str]

    #: Whether a secret is stored — the secret itself never leaves the backend.
    #: Populated by the service after validation, so it needs a default here.
    has_api_key: bool = False
    row_version: int
    created_at: datetime
    updated_at: datetime
