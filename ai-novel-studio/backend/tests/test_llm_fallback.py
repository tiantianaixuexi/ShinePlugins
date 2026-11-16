"""Fallback-chain behaviour of :class:`~app.ai.llm.registry.ChatClient`.

``test_ai_adapters.py`` pins one adapter in isolation; this file pins what the
chain does when the primary model fails and a backup has to answer. Everything is
scripted through ``httpx.MockTransport`` — no network and no database: the model
service is a stub, only the transports are injected.

The assertions describe what the code does *today* (including "a non-retryable
4xx does not fall back"), which is the behaviour we want to keep stable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest

from app.ai.llm.errors import (
    AllProvidersFailed,
    ProviderAuth,
    ProviderConnection,
    ProviderServer,
)
from app.ai.llm.openai_compatible import OpenAICompatibleAdapter
from app.ai.llm.registry import ChatClient
from app.ai.llm.types import ChatMessage, LLMRequest, LLMUsage
from app.core.errors import NotFound
from app.models.studio import ModelConfig

BASE_URL = "https://example.test/v1"

Handler = Callable[[httpx.Request], httpx.Response]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_model(model_id: str, model_name: str, **overrides: Any) -> ModelConfig:
    values: dict[str, Any] = {
        "id": model_id,
        "name": model_name,
        "provider": "openai_compatible",
        "base_url": BASE_URL,
        "model_name": model_name,
        "api_key_ref": None,
        "temperature": 0.7,
        "top_p": 1.0,
        "max_tokens": 1024,
        "timeout_s": 5.0,
        "retry_count": 0,
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


def make_request() -> LLMRequest:
    return LLMRequest(
        model="test-model",
        messages=[
            ChatMessage(role="system", content="你是助手"),
            ChatMessage(role="user", content="写一段开头"),
        ],
    )


def completion(
    model: str, content: str, *, usage: dict[str, int] | None = None
) -> httpx.Response:
    """A success whose ``model`` field echoes the endpoint that answered."""
    payload: dict[str, Any] = {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
    }
    if usage is not None:
        payload["usage"] = usage
    return httpx.Response(200, json=payload)


def sse(*frames: str) -> httpx.Response:
    body = ("\n\n".join(frames) + "\n\n").encode()
    return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})


class DiesMidStream(httpx.AsyncByteStream):
    """One SSE delta, then a dropped connection."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield 'data: {"choices":[{"delta":{"content":"你"}}]}\n\n'.encode()
        raise httpx.ReadError("connection reset by peer")


class StubSecrets:
    def get(self, label: str) -> str | None:
        return "sk-test"


class StubModelService:
    """Only the surface ``ChatClient`` touches: ``get`` / ``default_model``."""

    def __init__(self, models: list[ModelConfig]) -> None:
        self._models = {model.id: model for model in models}
        self.secrets = StubSecrets()

    def get(self, model_id: str) -> ModelConfig:
        try:
            return self._models[model_id]
        except KeyError:
            raise NotFound(f"Model configuration {model_id} not found") from None

    def default_model(self) -> ModelConfig | None:
        return next((model for model in self._models.values() if model.is_default), None)


class ScriptedChatClient(ChatClient):
    """The real chain/fallback logic, with a scripted transport per model."""

    def __init__(self, models: list[ModelConfig], handlers: dict[str, Handler]) -> None:
        super().__init__(StubModelService(models))
        self._handlers = handlers

    def _adapter(self, model: ModelConfig) -> OpenAICompatibleAdapter:
        return OpenAICompatibleAdapter(
            model,
            api_key="sk-test",
            transport=httpx.MockTransport(self._handlers[model.id]),
        )


def build_client(*scripts: tuple[ModelConfig, Handler]) -> ScriptedChatClient:
    """The first script is the primary; the rest are reachable as fallbacks."""
    return ScriptedChatClient(
        [model for model, _ in scripts], {model.id: handler for model, handler in scripts}
    )


# ---------------------------------------------------------------------------
# Non-streaming
# ---------------------------------------------------------------------------


async def test_primary_server_error_falls_back_to_backup() -> None:
    primary_calls = {"n": 0}
    backup_calls = {"n": 0}

    def primary_handler(request: httpx.Request) -> httpx.Response:
        primary_calls["n"] += 1
        return httpx.Response(503, text="overloaded")

    def backup_handler(request: httpx.Request) -> httpx.Response:
        backup_calls["n"] += 1
        return completion(
            "backup-model",
            "备模型写的开头",
            usage={"prompt_tokens": 9, "completion_tokens": 6},
        )

    client = build_client(
        (
            make_model(
                "mdl_primary",
                "primary-model",
                is_default=True,
                retry_count=1,
                fallback_ids=["mdl_backup"],
            ),
            primary_handler,
        ),
        (make_model("mdl_backup", "backup-model"), backup_handler),
    )

    response = await client.complete(make_request())

    assert response.text == "备模型写的开头"
    # The caller records the model that actually answered, and its usage.
    assert response.model == "backup-model"
    assert response.usage == LLMUsage(input_tokens=9, output_tokens=6)
    assert response.finish_reason == "stop"
    assert primary_calls["n"] == 2  # initial attempt + retry_count=1
    assert backup_calls["n"] == 1


async def test_every_provider_failing_raises_all_providers_failed() -> None:
    def primary_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom-primary")

    def backup_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="boom-backup")

    client = build_client(
        (
            make_model(
                "mdl_primary",
                "primary-model",
                is_default=True,
                fallback_ids=["mdl_backup"],
            ),
            primary_handler,
        ),
        (make_model("mdl_backup", "backup-model"), backup_handler),
    )

    with pytest.raises(AllProvidersFailed) as excinfo:
        await client.complete(make_request())

    # One entry per model tried, each carrying that provider's own message.
    assert len(excinfo.value.attempts) == 2
    assert "boom-primary" in excinfo.value.attempts[0]
    assert "boom-backup" in excinfo.value.attempts[1]
    assert excinfo.value.retryable is True


async def test_non_retryable_auth_error_does_not_fall_back() -> None:
    """Current behaviour: a 401 fails fast instead of burning the backup quota."""
    primary_calls = {"n": 0}
    backup_calls = {"n": 0}

    def primary_handler(request: httpx.Request) -> httpx.Response:
        primary_calls["n"] += 1
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    def backup_handler(request: httpx.Request) -> httpx.Response:
        backup_calls["n"] += 1
        return completion("backup-model", "不该被调用")

    client = build_client(
        (
            make_model(
                "mdl_primary",
                "primary-model",
                is_default=True,
                retry_count=3,
                fallback_ids=["mdl_backup"],
            ),
            primary_handler,
        ),
        (make_model("mdl_backup", "backup-model"), backup_handler),
    )

    with pytest.raises(ProviderAuth):
        await client.complete(make_request())

    assert primary_calls["n"] == 1  # neither retried nor replaced
    assert backup_calls["n"] == 0


async def test_primary_recovered_by_adapter_retry_never_reaches_backup() -> None:
    """Retrying the primary is cheaper than switching models."""
    primary_calls = {"n": 0}
    backup_calls = {"n": 0}

    def primary_handler(request: httpx.Request) -> httpx.Response:
        primary_calls["n"] += 1
        if primary_calls["n"] == 1:
            return httpx.Response(500, text="瞬断")
        return completion("primary-model", "重试后成功")

    def backup_handler(request: httpx.Request) -> httpx.Response:
        backup_calls["n"] += 1
        return completion("backup-model", "不该被调用")

    client = build_client(
        (
            make_model(
                "mdl_primary",
                "primary-model",
                is_default=True,
                retry_count=1,
                fallback_ids=["mdl_backup"],
            ),
            primary_handler,
        ),
        (make_model("mdl_backup", "backup-model"), backup_handler),
    )

    response = await client.complete(make_request())

    assert response.text == "重试后成功"
    assert response.model == "primary-model"
    assert backup_calls["n"] == 0


def test_chain_drops_fallbacks_it_cannot_build() -> None:
    """Deleted, unsupported, or inactive backups must never reach the chain.

    An inactive backup is dropped entirely, so complete()/stream() cannot call
    it; the NotFound and native-provider paths below stay covered as warnings.
    """
    primary = make_model(
        "mdl_primary",
        "primary-model",
        is_default=True,
        fallback_ids=["mdl_native", "mdl_ghost", "mdl_inactive", "mdl_backup"],
    )
    native = make_model("mdl_native", "claude", provider="anthropic")
    inactive = make_model("mdl_inactive", "inactive-model", is_active=False)
    backup = make_model("mdl_backup", "backup-model")

    chain = ChatClient(StubModelService([primary, native, inactive, backup]))._chain(None)

    # The inactive and native rows are gone; the ghost row raises NotFound.
    # Only the active backup remains reachable after the primary.
    assert [adapter.model_name for adapter in chain] == ["primary-model", "backup-model"]


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


async def test_stream_failure_before_first_token_falls_back() -> None:
    primary_calls = {"n": 0}
    backup_calls = {"n": 0}

    def primary_handler(request: httpx.Request) -> httpx.Response:
        primary_calls["n"] += 1
        return httpx.Response(503, text="overloaded")

    def backup_handler(request: httpx.Request) -> httpx.Response:
        backup_calls["n"] += 1
        return sse(
            'data: {"choices":[{"delta":{"content":"备"}}]}',
            'data: {"choices":[{"delta":{"content":"用"}}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        )

    client = build_client(
        (
            make_model(
                "mdl_primary",
                "primary-model",
                is_default=True,
                fallback_ids=["mdl_backup"],
            ),
            primary_handler,
        ),
        (make_model("mdl_backup", "backup-model"), backup_handler),
    )

    text: list[str] = []
    usage: LLMUsage | None = None
    async for chunk in client.stream(make_request()):
        if chunk.text:
            text.append(chunk.text)
        if chunk.usage is not None:
            usage = chunk.usage

    assert "".join(text) == "备用"
    assert usage is not None and usage.input_tokens > 0
    assert primary_calls["n"] == 1
    assert backup_calls["n"] == 1


async def test_stream_failure_after_first_delta_does_not_fall_back() -> None:
    """Restarting mid-stream would duplicate text, so the error must surface."""
    primary_calls = {"n": 0}
    backup_calls = {"n": 0}

    def primary_handler(request: httpx.Request) -> httpx.Response:
        primary_calls["n"] += 1
        return httpx.Response(
            200, stream=DiesMidStream(), headers={"content-type": "text/event-stream"}
        )

    def backup_handler(request: httpx.Request) -> httpx.Response:
        backup_calls["n"] += 1
        return sse('data: {"choices":[{"delta":{"content":"备"}}]}', "data: [DONE]")

    client = build_client(
        (
            make_model(
                "mdl_primary",
                "primary-model",
                is_default=True,
                retry_count=2,
                fallback_ids=["mdl_backup"],
            ),
            primary_handler,
        ),
        (make_model("mdl_backup", "backup-model"), backup_handler),
    )

    text: list[str] = []
    with pytest.raises(ProviderConnection) as excinfo:
        async for chunk in client.stream(make_request()):
            if chunk.text:
                text.append(chunk.text)

    # The partial delta reached the caller unchanged, then the error surfaced.
    assert "".join(text) == "你"
    assert "流式连接失败" in str(excinfo.value)
    assert primary_calls["n"] == 1  # no retry: bytes already went out
    assert backup_calls["n"] == 0


async def test_stream_walks_the_whole_chain_before_giving_up() -> None:
    def failing(model_name: str) -> Handler:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text=f"down-{model_name}")

        return handler

    client = build_client(
        (
            make_model(
                "mdl_primary",
                "primary-model",
                is_default=True,
                fallback_ids=["mdl_backup"],
            ),
            failing("primary"),
        ),
        (make_model("mdl_backup", "backup-model"), failing("backup")),
    )

    with pytest.raises(AllProvidersFailed) as excinfo:
        async for _ in client.stream(make_request()):
            pass

    assert len(excinfo.value.attempts) == 2
    assert "down-primary" in excinfo.value.attempts[0]
    assert "down-backup" in excinfo.value.attempts[1]


def test_error_retryability_matches_the_wire_status() -> None:
    """The flags the chain reads before deciding to fall back."""
    assert ProviderServer("boom").retryable is True
    assert ProviderConnection("boom").retryable is True
    assert ProviderAuth("boom").retryable is False
