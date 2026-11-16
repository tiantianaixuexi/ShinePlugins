"""Adapter for any OpenAI-compatible ``/chat/completions`` endpoint.

Covers OpenAI, DeepSeek, Moonshot, SiliconFlow, Ollama, LM Studio, vLLM and most
gateways. Behaviour that matters in production:

* **Retries** with exponential backoff for 408/429/5xx and network errors;
* **No retry** for 400/401/403/404/422, which will never succeed on retry;
* **SSE streaming** with correct handling of ``[DONE]`` and usage-only frames;
* **Explicit errors** that carry the provider's own message so the UI can show
  "余额不足" rather than "调用失败";
* **Usage accounting** from the provider when present, otherwise estimated.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.ai.llm.base import BaseAdapter, estimate_tokens
from app.ai.llm.errors import (
    LLMAdapterError,
    ProviderAuth,
    ProviderBadRequest,
    ProviderConnection,
    ProviderInvalidResponse,
    ProviderRateLimit,
    ProviderServer,
    ProviderTimeout,
)
from app.ai.llm.types import LLMRequest, LLMResponse, LLMUsage, StreamChunk

#: Statuses where retrying can plausibly succeed.
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})
BACKOFF_BASE_SECONDS = 0.6
CONNECT_TIMEOUT_SECONDS = 10.0


def _prompt_text(request: LLMRequest) -> str:
    return "\n".join(message.content for message in request.messages)


class OpenAICompatibleAdapter(BaseAdapter):
    """Talk to one OpenAI-compatible model.

    *transport* exists so tests can inject ``httpx.MockTransport`` instead of
    reaching the network; production always passes ``None``.
    """

    def __init__(
        self,
        config,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(config, api_key)
        self._transport = transport

    def _client(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        if self._transport is not None:
            return httpx.AsyncClient(timeout=timeout, transport=self._transport)
        return httpx.AsyncClient(timeout=timeout)

    # -- endpoints --------------------------------------------------------
    def _url(self) -> str:
        base = (self.config.base_url or "").strip().rstrip("/")
        if not base:
            raise ProviderBadRequest(
                "这个模型配置没有填写 Base URL，无法调用。",
                provider=self.provider,
            )
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _headers(self, *, stream: bool) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, request: LLMRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": self._request_messages(request),
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        if request.stop:
            payload["stop"] = request.stop
        if request.json_mode and self.config.supports_json_mode:
            payload["response_format"] = {"type": "json_object"}
        # Some gateways reject unknown fields, so this is opt-in per model.
        if stream and self.config.capabilities.get("stream_usage"):
            payload["stream_options"] = {"include_usage": True}
        return payload

    # -- error mapping ----------------------------------------------------
    @staticmethod
    def _error_message(response: httpx.Response, body: bytes | None = None) -> str:
        raw = body if body is not None else response.content
        if raw:
            try:
                parsed = json.loads(raw.decode("utf-8", errors="replace"))
            except (ValueError, AttributeError):
                parsed = None
            if isinstance(parsed, dict):
                error = parsed.get("error")
                if isinstance(error, dict):
                    message = error.get("message") or error.get("code")
                    if message:
                        return str(message)
                if isinstance(error, str) and error:
                    return error
                message = parsed.get("message")
                if message:
                    return str(message)
            text = raw.decode("utf-8", errors="replace").strip()
            if text:
                return text[:500]
        return f"HTTP {response.status_code}"

    def _raise_for_status(self, response: httpx.Response, body: bytes | None = None) -> None:
        status = response.status_code
        message = self._error_message(response, body)
        common = {"provider": self.provider, "status": status}

        if status in (401, 403):
            raise ProviderAuth("API Key 无效或没有访问权限。请在设置中检查密钥。", **common)
        if status == 429:
            raise ProviderRateLimit("请求过于频繁或额度不足，请稍后重试。", **common)
        if status in (400, 404, 422):
            raise ProviderBadRequest(f"请求被拒绝：{message}", **common)
        if status in RETRYABLE_STATUS:
            raise ProviderServer(f"服务暂时不可用：{message}", **common)
        raise ProviderBadRequest(f"调用失败：{message}", **common)

    # -- non-streaming ----------------------------------------------------
    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload = self._payload(request, stream=False)
        attempts = max(1, self.config.retry_count + 1)
        last: LLMAdapterError | None = None

        for attempt in range(attempts):
            try:
                return await self._complete_once(payload, request)
            except LLMAdapterError as exc:
                last = exc
                if not exc.retryable or attempt == attempts - 1:
                    raise
                await asyncio.sleep(BACKOFF_BASE_SECONDS * (2**attempt))

        raise last or ProviderConnection("调用失败。", provider=self.provider)  # pragma: no cover

    async def _complete_once(self, payload: dict[str, Any], request: LLMRequest) -> LLMResponse:
        timeout = httpx.Timeout(self.config.timeout_s, connect=CONNECT_TIMEOUT_SECONDS)
        async with self._client(timeout) as client:
            try:
                response = await client.post(
                    self._url(), json=payload, headers=self._headers(stream=False)
                )
            except httpx.TimeoutException as exc:
                raise ProviderTimeout(
                    f"模型在 {self.config.timeout_s:.0f} 秒内没有响应。", provider=self.provider
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderConnection(
                    f"无法连接模型服务：{exc}", provider=self.provider
                ) from exc

        if response.status_code >= 400:
            self._raise_for_status(response)

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderInvalidResponse("模型返回的不是 JSON。", provider=self.provider) from exc

        return self._parse_completion(data, request)

    def _parse_completion(self, data: dict[str, Any], request: LLMRequest) -> LLMResponse:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderInvalidResponse("响应里没有 choices 字段。", provider=self.provider)

        choice = choices[0] or {}
        message = choice.get("message") or {}
        text = message.get("content") or ""
        if isinstance(text, list):  # some gateways return content parts
            text = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in text
            )

        usage = self._parse_usage(data.get("usage"))
        if usage.input_tokens == 0:
            usage.input_tokens = estimate_tokens(_prompt_text(request))
        if usage.output_tokens == 0:
            usage.output_tokens = estimate_tokens(text)

        return LLMResponse(
            text=text,
            model=str(data.get("model") or request.model),
            usage=usage,
            finish_reason=choice.get("finish_reason"),
        )

    # -- streaming --------------------------------------------------------
    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        payload = self._payload(request, stream=True)
        attempts = max(1, self.config.retry_count + 1)
        emitted = False

        for attempt in range(attempts):
            try:
                async for chunk in self._stream_once(payload, request):
                    emitted = True
                    yield chunk
                return
            except LLMAdapterError as exc:
                # Once bytes reached the user we must not silently restart and
                # duplicate half a chapter.
                if emitted or not exc.retryable or attempt == attempts - 1:
                    raise
                await asyncio.sleep(BACKOFF_BASE_SECONDS * (2**attempt))

    async def _stream_once(
        self, payload: dict[str, Any], request: LLMRequest
    ) -> AsyncIterator[StreamChunk]:
        timeout = httpx.Timeout(self.config.timeout_s, connect=CONNECT_TIMEOUT_SECONDS)
        usage = LLMUsage()
        finish_reason: str | None = None
        produced: list[str] = []

        async with self._client(timeout) as client:
            try:
                async with client.stream(
                    "POST", self._url(), json=payload, headers=self._headers(stream=True)
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        self._raise_for_status(response, body)

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if not data or data == "[DONE]":
                            if data == "[DONE]":
                                break
                            continue
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        if isinstance(event.get("usage"), dict):
                            usage = self._parse_usage(event["usage"])

                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        choice = choices[0] or {}
                        delta = choice.get("delta") or {}
                        # Reasoning models (e.g. MiniMax M3.1, DeepSeek-R1) stream
                        # their chain of thought first under a separate key. It must
                        # never be appended to the answer text.
                        thought = delta.get("reasoning_content")
                        if not isinstance(thought, str) or not thought:
                            thought = delta.get("reasoning")
                        if isinstance(thought, str) and thought:
                            yield StreamChunk(thinking=thought)
                        piece = delta.get("content")
                        if piece:
                            produced.append(piece)
                            yield StreamChunk(text=piece)
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
            except httpx.TimeoutException as exc:
                raise ProviderTimeout(
                    f"流式输出中断（{self.config.timeout_s:.0f} 秒无数据）。",
                    provider=self.provider,
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderConnection(f"流式连接失败：{exc}", provider=self.provider) from exc

        if usage.input_tokens == 0:
            usage.input_tokens = estimate_tokens(_prompt_text(request))
        if usage.output_tokens == 0:
            usage.output_tokens = estimate_tokens("".join(produced))
        yield StreamChunk(usage=usage, finish_reason=finish_reason)

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _parse_usage(raw: Any) -> LLMUsage:
        if not isinstance(raw, dict):
            return LLMUsage()
        return LLMUsage(
            input_tokens=int(raw.get("prompt_tokens") or raw.get("input_tokens") or 0),
            output_tokens=int(raw.get("completion_tokens") or raw.get("output_tokens") or 0),
        )
