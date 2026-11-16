"""Liveness and build information."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from app.api.deps import RuntimeDep

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe with build information")
async def health(runtime: RuntimeDep) -> dict[str, Any]:
    """Always cheap; the desktop shell polls this before loading the UI."""
    return {
        "status": "ok" if runtime.is_started else "starting",
        "app": runtime.settings.app_name,
        "version": runtime.settings.app_version,
        "schema_version": runtime.schema_version(),
        "environment": runtime.settings.environment,
        "time": datetime.now(UTC).isoformat(),
    }


@router.get("/system/info", summary="Static information about this installation")
async def system_info(runtime: RuntimeDep) -> dict[str, Any]:
    settings = runtime.settings
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "schema_version": runtime.schema_version(),
        "environment": settings.environment,
        "data_dir": str(settings.data_dir),
        "projects_dir": str(settings.projects_root),
        "projects": runtime.project_service.count(),
        "auth_required": settings.is_auth_enabled,
    }
