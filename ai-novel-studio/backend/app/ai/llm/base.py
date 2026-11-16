"""Adapter interface and shared token estimation."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.ai.llm.types import LLMRequest, LLMResponse, StreamChunk

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]")
_LATIN_RE = re.compile(r"[A-Za-z0-9]+")


def estimate_tokens(text: str) -> int:
    """Approximate a token count without downloading a tokenizer.

    Chinese prose runs close to one token per character, while Latin text
    averages ~4 characters per token. Providers that report real usage always
    win; this is only the fallback for cost accounting, so it errs slightly low
    rather than inventing overhead.
    """
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_RE.findall(_CJK_RE.sub(" ", text)))
    return cjk + latin


class BaseAdapter(ABC):
    """One model endpoint."""

    def __init__(self, config, api_key: str | None = None) -> None:
        self.config = config
        self.api_key = api_key

    # -- identity ---------------------------------------------------------
    @property
    def model_name(self) -> str:
        return self.config.model_name

    @property
    def provider(self) -> str:
        return self.config.provider

    @property
    def label(self) -> str:
        return f"{self.config.name} ({self.config.model_name})"

    # -- contract ---------------------------------------------------------
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Run a blocking completion."""

    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        """Run a streaming completion."""

    # -- helpers ----------------------------------------------------------
    def _request_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        return [{"role": message.role, "content": message.content} for message in request.messages]
