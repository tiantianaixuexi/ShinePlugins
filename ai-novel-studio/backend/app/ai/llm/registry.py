"""Build adapters from model configurations and run the fallback chain."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from app.ai.llm.base import BaseAdapter
from app.ai.llm.errors import AllProvidersFailed, LLMAdapterError
from app.ai.llm.openai_compatible import OpenAICompatibleAdapter
from app.ai.llm.types import LLMRequest, LLMResponse, StreamChunk
from app.core.errors import NotFound, ValidationFailed
from app.core.keystore import secret_label_for_model
from app.core.logging import get_logger

if TYPE_CHECKING:  # avoid a runtime import cycle with the service layer
    from app.models.studio import ModelConfig
    from app.services.model_config_service import ModelConfigService

logger = get_logger(__name__)

#: Providers with a different wire format, which we cannot serve with the
#: OpenAI-compatible adapter. Everything else — including any provider string a
#: user typed for a self-hosted gateway — is treated as OpenAI-compatible.
_NATIVE_ONLY = {
    "anthropic": "Anthropic 原生接口尚未适配，请填写 OpenAI 兼容网关的 URL。",
    "gemini": "Gemini 原生接口尚未适配，请填写 OpenAI 兼容网关的 URL。",
}


def build_adapter(config: ModelConfig, api_key: str | None) -> BaseAdapter:
    """Instantiate the adapter for one model row.

    The adapter is chosen by capability, not by vendor name: any endpoint that
    speaks ``/chat/completions`` works, which is what makes "fill in your own
    URL" possible.
    """
    if config.provider in _NATIVE_ONLY:
        raise ValidationFailed(_NATIVE_ONLY[config.provider])
    return OpenAICompatibleAdapter(config, api_key)


class ChatClient:
    """Resolve a model, run it, and fall back to backups when it fails."""

    def __init__(self, model_service: ModelConfigService) -> None:
        self.model_service = model_service

    # -- resolution -------------------------------------------------------
    def resolve(self, model_config_id: str | None = None) -> ModelConfig:
        if model_config_id:
            model = self.model_service.get(model_config_id)
        else:
            model = self.model_service.default_model()
            if model is None:
                raise ValidationFailed(
                    "还没有可用模型。请先在「系统设置 → 模型配置」中添加一个模型。"
                )
        if not model.is_active:
            raise ValidationFailed(f"模型「{model.name}」已停用，请启用后重试。")
        return model

    def _adapter(self, model: ModelConfig) -> BaseAdapter:
        api_key = self.model_service.secrets.get(secret_label_for_model(model.id))
        if not api_key and model.provider not in {"ollama", "custom"}:
            logger.warning("model_without_api_key", model_id=model.id, name=model.name)
        return build_adapter(model, api_key)

    def _chain(self, model_config_id: str | None) -> list[BaseAdapter]:
        primary = self.resolve(model_config_id)
        chain = [self._adapter(primary)]
        for fallback_id in primary.fallback_ids or []:
            try:
                model = self.model_service.get(fallback_id)
                if not model.is_active:
                    logger.warning(
                        "fallback_model_inactive",
                        model_id=primary.id,
                        fallback=fallback_id,
                    )
                    continue
                chain.append(self._adapter(model))
            except (NotFound, ValidationFailed) as exc:
                logger.warning(
                    "fallback_model_unavailable",
                    model_id=primary.id,
                    fallback=fallback_id,
                    error=str(exc),
                )
        return chain

    # -- calls ------------------------------------------------------------
    async def complete(
        self, request: LLMRequest, *, model_config_id: str | None = None
    ) -> LLMResponse:
        attempts: list[str] = []
        for adapter in self._chain(model_config_id):
            try:
                return await adapter.complete(request)
            except LLMAdapterError as exc:
                attempts.append(str(exc))
                logger.warning(
                    "model_call_failed",
                    provider=adapter.provider,
                    model=adapter.model_name,
                    error=str(exc),
                    retryable=exc.retryable,
                )
                if not exc.retryable:
                    raise
        raise AllProvidersFailed("所有可用模型都调用失败。", attempts=attempts)

    async def stream(
        self, request: LLMRequest, *, model_config_id: str | None = None
    ) -> AsyncIterator[StreamChunk]:
        attempts: list[str] = []
        for adapter in self._chain(model_config_id):
            emitted = False
            try:
                async for chunk in adapter.stream(request):
                    emitted = True
                    yield chunk
                return
            except LLMAdapterError as exc:
                attempts.append(str(exc))
                logger.warning(
                    "model_stream_failed",
                    provider=adapter.provider,
                    model=adapter.model_name,
                    error=str(exc),
                    emitted=emitted,
                )
                # Restarting after bytes reached the client would duplicate text.
                if emitted or not exc.retryable:
                    raise
        raise AllProvidersFailed("所有可用模型都调用失败。", attempts=attempts)
