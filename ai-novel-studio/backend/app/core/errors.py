"""Application error hierarchy and FastAPI exception handlers.

Every API failure is reported as::

    {"error": {"code": "...", "message": "...", "details": {...}}}

so the desktop client can branch on a stable machine-readable code instead of
parsing human text.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class StudioError(Exception):
    """Base class for every error the application raises on purpose."""

    code: str = "internal_error"
    status: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ValidationFailed(StudioError):
    code = "validation_failed"
    # 422 is spelled numerically: Starlette renamed the constant in 0.4x and the
    # old name now emits a DeprecationWarning.
    status = 422


class AuthRequired(StudioError):
    code = "auth_required"
    status = status.HTTP_401_UNAUTHORIZED


class NotFound(StudioError):
    code = "not_found"
    status = status.HTTP_404_NOT_FOUND


class Conflict(StudioError):
    code = "conflict"
    status = status.HTTP_409_CONFLICT


class ProjectLocked(StudioError):
    """The project is already open in another editor / writer process."""

    code = "project_locked"
    status = status.HTTP_423_LOCKED


class ProviderError(StudioError):
    """An upstream model provider failed or returned an unusable answer."""

    code = "provider_error"
    status = status.HTTP_502_BAD_GATEWAY


class TaskFailed(StudioError):
    code = "task_failed"
    status = status.HTTP_500_INTERNAL_SERVER_ERROR


def _payload(exc: StudioError) -> dict[str, Any]:
    return exc.to_payload()


def register_error_handlers(app: FastAPI) -> None:
    """Attach the handlers to a FastAPI application."""

    @app.exception_handler(StudioError)
    async def _studio_error(_: Any, exc: StudioError) -> JSONResponse:  # type: ignore[misc]
        return JSONResponse(status_code=exc.status, content=_payload(exc))

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Any, exc: RequestValidationError) -> JSONResponse:  # type: ignore[misc]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_failed",
                    "message": "Request payload is invalid.",
                    "details": {"errors": _jsonable(exc.errors())},
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Any, exc: StarletteHTTPException) -> JSONResponse:  # type: ignore[misc]
        code = {
            401: "auth_required",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            423: "project_locked",
        }.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": str(exc.detail),
                    "details": None,
                }
            },
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Any, exc: Exception) -> JSONResponse:  # type: ignore[misc]
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Unexpected server error.",
                    "details": {"type": type(exc).__name__},
                }
            },
        )


def _jsonable(value: Any) -> Any:
    """Best-effort conversion of pydantic error payloads to JSON-safe data."""
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
