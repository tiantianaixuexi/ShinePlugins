"""Structured output: loose JSON parsing, one repair retry, provider-safe json_mode.

The summary writer used to parse replies inline. This pins the shared behaviour
moved to :mod:`app.ai.structured`: models answer with bare JSON only by luck, so
parsing must survive ``` fences and prose, a bad reply gets exactly one repair
attempt, and a model that does not advertise ``supports_json_mode`` must never be
sent ``response_format`` (some gateways reject the field outright).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.ai.llm.openai_compatible import OpenAICompatibleAdapter
from app.ai.llm.types import ChatMessage, LLMRequest, LLMResponse, LLMUsage
from app.ai.structured import REPAIR_INSTRUCTION, complete_json, parse_json_object
from app.models.studio import ModelConfig


def make_request() -> LLMRequest:
    return LLMRequest(
        model="test-model",
        messages=[
            ChatMessage(role="system", content="你是摘要助手"),
            ChatMessage(role="user", content="总结这一章"),
        ],
    )


class FakeClient:
    """Scripted stand-in for :class:`~app.ai.llm.registry.ChatClient`."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.requests: list[LLMRequest] = []

    async def complete(
        self, request: LLMRequest, *, model_config_id: str | None = None
    ) -> LLMResponse:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.replies) - 1)
        return LLMResponse(
            text=self.replies[index],
            model=request.model,
            usage=LLMUsage(input_tokens=10, output_tokens=5),
        )


def make_config(**overrides: Any) -> ModelConfig:
    values: dict[str, Any] = {
        "id": "mdl_test",
        "name": "测试模型",
        "provider": "openai_compatible",
        "base_url": "https://example.test/v1",
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


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


async def test_bare_json_reply_is_parsed_without_a_retry() -> None:
    client = FakeClient('{"summary": "雨夜书店", "characters": ["沈砚"]}')

    reply = await complete_json(client, make_request())
    data, text = reply

    assert data == {"summary": "雨夜书店", "characters": ["沈砚"]}
    assert text == '{"summary": "雨夜书店", "characters": ["沈砚"]}'
    assert reply.ok is True
    assert reply.attempts == 1
    assert len(client.requests) == 1
    assert client.requests[0].json_mode is True


async def test_fenced_json_reply_is_parsed() -> None:
    client = FakeClient('```json\n{"summary": "雨夜书店"}\n```')

    reply = await complete_json(client, make_request())

    assert reply.data == {"summary": "雨夜书店"}
    assert reply.attempts == 1


async def test_json_wrapped_in_prose_is_parsed() -> None:
    client = FakeClient('好的，结果如下：\n{"summary": "雨夜书店", "keywords": "铜铃"}\n以上。')

    reply = await complete_json(client, make_request())

    assert reply.data == {"summary": "雨夜书店", "keywords": "铜铃"}
    assert reply.attempts == 1


async def test_non_json_reply_fails_after_one_repair_attempt() -> None:
    client = FakeClient("这一章写雨夜书店的相遇。", "还是散文，没有 JSON。")

    reply = await complete_json(client, make_request())
    data, text = reply

    assert data is None, "非 JSON 必须降级为 None，而不是抛错"
    assert text == "还是散文，没有 JSON。", "降级时回传最后一次原文"
    assert reply.attempts == 2, "第一次 + 一次修复重试"
    assert len(client.requests) == 2
    # The repair turn must carry the offending reply and the instruction.
    repaired = client.requests[1].messages
    assert repaired[-2].role == "assistant"
    assert repaired[-2].content == "这一章写雨夜书店的相遇。"
    assert repaired[-1] == ChatMessage(role="user", content=REPAIR_INSTRUCTION)


async def test_truncated_reply_survives_a_blank_repair_turn() -> None:
    """A repair turn that answers ``""`` must not swallow the first attempt.

    Real models truncate at ``max_tokens`` and then answer the repair prompt
    with nothing at all; the caller stores ``text`` as the degraded ``content``,
    so returning the blank repair reply would lose the whole paid reply.
    """
    truncated = '{"title": "铜铃响起的那一夜", "goal": "沈砚拿到铜铃并意识到它'
    client = FakeClient(truncated, "")

    reply = await complete_json(client, make_request())
    data, text = reply

    assert data is None, "截断的 JSON 解析不出来"
    assert text == truncated, "修复轮空串时必须回退到首轮原文"
    assert reply.attempts == 2
    assert len(client.requests) == 2


async def test_parsing_repair_reply_wins_over_a_longer_first_attempt() -> None:
    """When the repair parses, ``text`` is the repair's reply — not the longer junk."""
    junk = "好的，我先把大纲写成散文说明一下：" + "雨夜书店的相遇、" * 3
    client = FakeClient(junk, '{"goal": "拿到铜铃"}')

    reply = await complete_json(client, make_request())
    data, text = reply

    assert data == {"goal": "拿到铜铃"}
    assert text == '{"goal": "拿到铜铃"}', "解析成功的那一轮原文优先"
    assert len(junk) > len(text), "首轮原文更长，但解析成功的一轮胜出"


def test_parse_json_object_rejects_arrays_and_garbage() -> None:
    assert parse_json_object('["a", "b"]') is None
    assert parse_json_object("完全没有 JSON") is None
    assert parse_json_object("   ") is None


# ---------------------------------------------------------------------------
# json_mode wire format
# ---------------------------------------------------------------------------


def test_model_without_json_capability_gets_no_response_format() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(
            200,
            json={"model": "test-model", "choices": [{"message": {"content": "{}"}}]},
        )

    adapter = OpenAICompatibleAdapter(
        make_config(supports_json_mode=False),
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    request = make_request()
    request.json_mode = True

    payload = adapter._payload(request, stream=False)
    assert "response_format" not in payload, "模型不自称支持 JSON 模式时不能发这个字段"

    supporting = OpenAICompatibleAdapter(
        make_config(supports_json_mode=True),
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    assert supporting._payload(request, stream=False)["response_format"] == {
        "type": "json_object"
    }
