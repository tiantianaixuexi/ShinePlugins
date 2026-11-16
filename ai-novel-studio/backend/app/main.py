"""FastAPI application factory.

The desktop shell starts this module as a sidecar (``python -m app``), so the
process must be startable with no arguments and must bind to an ephemeral port
supplied through ``NOVEL_STUDIO_PORT``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.security import extract_bearer, is_token_valid
from app.runtime import Runtime

logger = get_logger(__name__)


class TokenMiddleware:
    """Reject unauthenticated ``/api`` calls before they reach a handler.

    Pure ASGI (not ``BaseHTTPMiddleware``) so streaming and background tasks
    keep working and so 404s are protected too.
    """

    #: Paths under ``/api`` that stay reachable without the shared secret.
    OPEN_PATHS = frozenset({"/api/docs", "/api/openapi.json", "/api/redoc"})

    def __init__(self, app: ASGIApp, token: str | None) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.token:
            await self.app(scope, receive, send)
            return

        # CORS preflights carry no credentials by design. Let CORSMiddleware
        # answer them; the real request still has to present the token.
        if scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if not path.startswith("/api"):
            await self.app(scope, receive, send)
            return

        # The schema and the interactive docs are not sensitive: they describe
        # the API surface of a service bound to 127.0.0.1, and requiring a
        # one-shot token makes them unusable from a browser.
        if path in self.OPEN_PATHS:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        provided = extract_bearer(headers.get("authorization")) or headers.get("x-studio-token")
        if not is_token_valid(provided, self.token):
            response = JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "auth_required",
                        "message": "Missing or invalid access token.",
                        "details": None,
                    }
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class ErrorEnvelopeMiddleware:
    """Guarantee the ``{"error": {...}}`` envelope for unhandled exceptions.

    ``ServerErrorMiddleware`` sits outside user middleware and, depending on the
    server, can surface a bare 500 with an empty body. Wrapping the app here
    keeps the documented contract ("every failure is JSON") true even when an
    unexpected exception escapes a handler.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Any) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            logger.exception("unhandled_exception", path=scope.get("path"))
            if response_started:
                # Headers are already on the wire; the client gets a truncated
                # body, which is the only honest option at this point.
                raise
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "Unexpected server error.",
                        "details": {"type": type(exc).__name__},
                    }
                },
            )
            await response(scope, receive, send)


def _frontend_dist() -> Path | None:
    """Locate the built frontend, when it exists next to the backend."""
    candidate = Path(__file__).resolve().parents[2] / "desktop" / "dist"
    return candidate if candidate.is_dir() else None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(
        level=settings.log_level,
        json_output=settings.log_json,
        log_dir=settings.logs_dir,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = Runtime(settings)
        app.state.runtime = runtime
        runtime.start()
        try:
            yield
        finally:
            runtime.stop()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="AI Novel Studio local service",
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TokenMiddleware, token=settings.auth_token)
    # Added last so it wraps everything else (last added == outermost).
    app.add_middleware(ErrorEnvelopeMiddleware)

    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, Any]:
        """Unauthenticated liveness marker used by process supervisors."""
        return {"status": "ok"}

    dist = _frontend_dist()
    if dist is not None:
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

    logger.info(
        "app_created",
        environment=settings.environment,
        auth="on" if settings.is_auth_enabled else "off",
    )
    return app


app = create_app()
