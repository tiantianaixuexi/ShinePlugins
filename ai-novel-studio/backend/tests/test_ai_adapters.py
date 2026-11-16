"""Model adapter behaviour against a scripted OpenAI-compatible transport.

A real provider call is exercised by `scripts/smoke_ai.py`; these tests pin the
protocol handling that must not regress: retries, error mapping, SSE parsing and
usage accounting. No network and no global patching: the adapter takes an
``httpx`` transport directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.ai.llm.base import estimate_tokens
from app.ai.llm.errors import (
    ProviderAuth,
    ProviderBadRequest,
    ProviderRateLimit,
    ProviderServer,
)
from app.ai.llm.openai_compatible import OpenAICompatibleAdapter
from app.ai.llm.types import ChatMessage, LLMRequest, LLMUsage
from app.models.studio import ModelConfig

BASE_URL = "https://example.test/v1"

Handler = Callable[[httpx.Request], httpx.Response]


def make_config(**overrides: Any) -> ModelConfig:
    values: dict[str, Any] = {
        "id": "mdl_test",
        "name": "测试模型",
        "provider": "openai_compatible",
        "base_url": BASE_URL,
        "model_name": "test-model",
        "api_key_ref": None,
        "temperature": 0.7,
        "top_p": 1.0,
        "max_tokens": 1024,
        "timeout_s": 5.0,
        "retry_count": 2,
        "context_window": 8192,
        "max_output_tokens": 1024,
        "supports_streaming": True,
        "supports_json_mode": False,
        "supports_vision": False,
        "supports_tools": False,
        "input_price_per_1m": 1.0,
        "output_price_per_1m": 2.0,
        "capabilities": {},
        "notes": "",
        "is_active": True,
        "is_default": False,
        "fallback_ids": [],
        "row_version": 1,
    }
    values.update(overrides)
    return ModelConfig(**values)


def make_request(text: str = "你好") -> LLMRequest:
    return LLMRequest(
        model="test-model",
        messages=[
            ChatMessage(role="system", content="你是助手"),
            ChatMessage(role="user", content=text),
        ],
    )


def completion(
    content: str = "你好，世界", *, usage: dict[str, int] | None = None
) -> httpx.Response:
    payload: dict[str, Any] = {
        "model": "test-model",
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
    }
    if usage is not None:
        payload["usage"] = usage
    return httpx.Response(200, json=payload)


def sse(*frames: str) -> httpx.Response:
    body = ("\n\n".join(frames) + "\n\n").encode("utf-8")
    return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})


def make_adapter(handler: Handler, **overrides: Any) -> OpenAICompatibleAdapter:
    """Build an adapter wired to a mock transport."""
    return OpenAICompatibleAdapter(
        make_config(**overrides),
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )


# ---------------------------------------------------------------------------
# Non-streaming
# ---------------------------------------------------------------------------


async def test_complete_parses_content_and_usage() -> None:
    adapter = make_adapter(
        lambda request: completion(usage={"prompt_tokens": 11, "completion_tokens": 7})
    )

    response = await adapter.complete(make_request())

    assert response.text == "你好，世界"
    assert response.usage == LLMUsage(input_tokens=11, output_tokens=7)
    assert response.finish_reason == "stop"
    assert response.model == "test-model"


async def test_usage_is_estimated_when_provider_omits_it() -> None:
    adapter = make_adapter(lambda request: completion("天地玄黄"))

    response = await adapter.complete(make_request())

    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens == 4


async def test_retry_then_success() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="overloaded")
        return completion("ok")

    adapter = make_adapter(handler, retry_count=2)
    response = await adapter.complete(make_request())

    assert response.text == "ok"
    assert calls["n"] == 3


async def test_retries_are_bounded() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    adapter = make_adapter(handler, retry_count=2)

    with pytest.raises(ProviderServer):
        await adapter.complete(make_request())

    assert calls["n"] == 3  # initial attempt + 2 retries


async def test_auth_error_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    adapter = make_adapter(handler, retry_count=3)

    with pytest.raises(ProviderAuth) as excinfo:
        await adapter.complete(make_request())

    assert calls["n"] == 1
    assert excinfo.value.status == 401
    # The wire message is replaced by actionable copy, not leaked to the UI.
    assert "API Key" in str(excinfo.value)


async def test_rate_limit_is_retried_and_named() -> None:
    adapter = make_adapter(
        lambda request: httpx.Response(429, json={"error": {"message": "slow down"}}),
        retry_count=1,
    )

    with pytest.raises(ProviderRateLimit):
        await adapter.complete(make_request())


async def test_bad_request_carries_provider_message() -> None:
    adapter = make_adapter(
        lambda request: httpx.Response(
            400, json={"error": {"message": "unsupported model", "type": "invalid_request"}}
        )
    )

    with pytest.raises(ProviderBadRequest) as excinfo:
        await adapter.complete(make_request())

    assert "unsupported model" in str(excinfo.value)


async def test_missing_base_url_is_reported_clearly() -> None:
    adapter = OpenAICompatibleAdapter(
        make_config(base_url=""),
        api_key=None,
        transport=httpx.MockTransport(lambda request: completion()),
    )

    with pytest.raises(ProviderBadRequest) as excinfo:
        await adapter.complete(make_request())

    assert "Base URL" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


async def test_stream_collects_deltas_and_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return sse(
            'data: {"choices":[{"delta":{"content":"你"}}]}',
            'data: {"choices":[{"delta":{"content":"好"}}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":2}}',
            "data: [DONE]",
        )

    adapter = make_adapter(handler)

    deltas: list[str] = []
    usage: LLMUsage | None = None
    async for chunk in adapter.stream(make_request()):
        if chunk.text:
            deltas.append(chunk.text)
        if chunk.usage is not None:
            usage = chunk.usage

    assert "".join(deltas) == "你好"
    assert usage == LLMUsage(input_tokens=5, output_tokens=2)


async def test_stream_ignores_malformed_frames() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return sse(
            "data: not-json",
            'data: {"choices":[{"delta":{"content":"好"}}]}',
            "data: [DONE]",
        )

    adapter = make_adapter(handler)

    chunks = [chunk.text async for chunk in adapter.stream(make_request()) if chunk.text]
    assert "".join(chunks) == "好"


async def test_stream_error_before_first_token_is_retryable() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="overloaded")
        return sse('data: {"choices":[{"delta":{"content":"好"}}]}', "data: [DONE]")

    adapter = make_adapter(handler, retry_count=1)

    chunks = [chunk.text async for chunk in adapter.stream(make_request()) if chunk.text]

    assert "".join(chunks) == "好"
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Payload / helpers
# ---------------------------------------------------------------------------


def test_payload_uses_json_mode_only_when_supported() -> None:
    request = LLMRequest(
        model="m", messages=[ChatMessage(role="user", content="x")], json_mode=True
    )

    enabled = OpenAICompatibleAdapter(
        make_config(supports_json_mode=True),
        "sk",
        transport=httpx.MockTransport(lambda request: completion()),
    )
    assert enabled._payload(request, stream=False)["response_format"] == {"type": "json_object"}

    disabled = OpenAICompatibleAdapter(
        make_config(supports_json_mode=False),
        "sk",
        transport=httpx.MockTransport(lambda request: completion()),
    )
    assert "response_format" not in disabled._payload(request, stream=False)


def test_estimate_tokens_handles_mixed_text() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("天地玄黄") == 4
    assert estimate_tokens("hello world") == 2
