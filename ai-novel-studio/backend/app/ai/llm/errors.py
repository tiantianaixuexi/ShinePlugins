"""Adapter-level failures.

Each carries ``retryable`` so the retry/fallback logic can decide without
parsing provider-specific messages.
"""

from __future__ import annotations


class LLMAdapterError(Exception):
    """Base class for every failure raised by an adapter."""

    code = "provider_error"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        status: int | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status = status
        if retryable is not None:
            self.retryable = retryable

    def __str__(self) -> str:  # pragma: no cover - trivial
        prefix = f"[{self.provider}] " if self.provider else ""
        return f"{prefix}{self.message}"


class ProviderTimeout(LLMAdapterError):
    code = "provider_timeout"
    retryable = True


class ProviderConnection(LLMAdapterError):
    code = "provider_unavailable"
    retryable = True


class ProviderRateLimit(LLMAdapterError):
    code = "provider_rate_limited"
    retryable = True


class ProviderServer(LLMAdapterError):
    code = "provider_server_error"
    retryable = True


class ProviderAuth(LLMAdapterError):
    code = "provider_auth_failed"
    retryable = False


class ProviderBadRequest(LLMAdapterError):
    code = "provider_bad_request"
    retryable = False


class ProviderInvalidResponse(LLMAdapterError):
    code = "provider_invalid_response"
    retryable = False


class AllProvidersFailed(LLMAdapterError):
    """Every model in the fallback chain failed."""

    code = "all_providers_failed"
    retryable = True

    def __init__(self, message: str, *, attempts: list[str]) -> None:
        super().__init__(message)
        self.attempts = attempts
