"""Model adapter layer.

The rest of the backend talks to :class:`~app.ai.llm.base.BaseAdapter`, never to
a vendor SDK, so adding a provider means adding one module here.
"""

from app.ai.llm.base import BaseAdapter
from app.ai.llm.openai_compatible import OpenAICompatibleAdapter
from app.ai.llm.registry import ChatClient, build_adapter
from app.ai.llm.types import (
    ChatMessage,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    StreamChunk,
)

__all__ = [
    "BaseAdapter",
    "ChatClient",
    "ChatMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMUsage",
    "OpenAICompatibleAdapter",
    "StreamChunk",
    "build_adapter",
]
