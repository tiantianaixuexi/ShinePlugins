"""Shared secret authentication for the local HTTP API.

The backend binds to ``127.0.0.1`` only, but any process running as the same
user could still talk to it. The desktop shell therefore generates a fresh
token at start-up, injects it through ``NOVEL_STUDIO_AUTH_TOKEN`` and sends it
back as ``Authorization: Bearer <token>`` on every request.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Iterable

from fastapi import Header

from app.core.errors import AuthRequired

BEARER_PREFIX = "bearer "


def generate_token(nbytes: int = 32) -> str:
    """Return a URL-safe random token suitable for the sidecar handshake."""
    return secrets.token_urlsafe(nbytes)


def is_token_valid(provided: str | None, expected: str | None) -> bool:
    """Constant-time comparison that tolerates auth being disabled."""
    if not expected:
        return True
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


def extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    value = authorization.strip()
    if value.lower().startswith(BEARER_PREFIX):
        return value[len(BEARER_PREFIX) :].strip()
    return value


async def require_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_studio_token: str | None = Header(default=None, alias="X-Studio-Token"),
) -> None:
    """FastAPI dependency enforcing the shared secret.

    ``X-Studio-Token`` is accepted as a fallback so WebSocket clients and curl
    based smoke tests can authenticate without the ``Authorization`` header.
    """
    from app.core.config import get_settings

    expected = get_settings().auth_token
    provided = extract_bearer(authorization) or x_studio_token
    if not is_token_valid(provided, expected):
        raise AuthRequired("Missing or invalid access token.")


def constant_time_any_match(candidate: str, allowed: Iterable[str]) -> bool:
    """Return ``True`` when *candidate* matches any allowed value."""
    return any(hmac.compare_digest(candidate, value) for value in allowed)
