"""Provider-neutral request/response types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(slots=True)
class ChatMessage:
    """One turn in a chat completion."""

    role: Role
    content: str


@dataclass(slots=True)
class LLMUsage:
    """Token accounting. Values are estimates when a provider omits them."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(slots=True)
class LLMRequest:
    """A single completion request."""

    model: str
    messages: list[ChatMessage]
    temperature: float = 0.8
    top_p: float = 1.0
    max_tokens: int = 4096
    stop: list[str] | None = None
    #: Ask the provider for strict JSON. Only sent when the model advertises it.
    json_mode: bool = False


@dataclass(slots=True)
class LLMResponse:
    """A completed, non-streamed response."""

    text: str
    model: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    finish_reason: str | None = None


@dataclass(slots=True)
class StreamChunk:
    """One streamed increment.

    ``text`` is the delta to append; ``usage`` and ``finish_reason`` appear on
    the final chunk only.
    """

    text: str = ""
    usage: LLMUsage | None = None
    finish_reason: str | None = None
