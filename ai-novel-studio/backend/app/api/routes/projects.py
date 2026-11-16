"""Project endpoints (plan §13.1)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from app.api.deps import ProjectServiceDep
from app.core.errors import ValidationFailed
from app.schemas.project import (
    ProjectCreate,
    ProjectOut,
    ProjectStats,
    ProjectSummary,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _to_out(project: Any, stats: dict[str, int] | None = None) -> ProjectOut:
    payload = ProjectOut.model_validate(project)
    if stats is not None:
        payload.stats = ProjectStats(**stats)
    return payload


@router.post(
    "", response_model=ProjectOut, status_code=status.HTTP_201_CREATED, summary="Create a project"
)
async def create_project(payload: ProjectCreate, service: ProjectServiceDep) -> ProjectOut:
    project = service.create(payload)
    return _to_out(project, service.stats_for(project))


@router.get("", response_model=list[ProjectSummary], summary="List projects")
async def list_projects(
    service: ProjectServiceDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_deleted: bool = False,
) -> list[ProjectSummary]:
    projects = service.list(limit=limit, offset=offset, include_deleted=include_deleted)
    return [ProjectSummary.model_validate(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectOut, summary="Get one project")
async def get_project(project_id: str, service: ProjectServiceDep) -> ProjectOut:
    project = service.get(project_id)
    return _to_out(project, service.stats_for(project))


@router.put("/{project_id}", response_model=ProjectOut, summary="Update a project")
async def update_project(
    project_id: str, payload: ProjectUpdate, service: ProjectServiceDep
) -> ProjectOut:
    project = service.update(project_id, payload)
    return _to_out(project, service.stats_for(project))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a project")
async def delete_project(
    project_id: str,
    service: ProjectServiceDep,
    hard: bool = False,
) -> Response:
    service.delete(project_id, hard=hard)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{project_id}/duplicate",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Copy a project directory",
)
async def duplicate_project(
    project_id: str,
    payload: dict[str, Any],
    service: ProjectServiceDep,
) -> ProjectOut:
    new_name = str(payload.get("name") or "").strip()
    if not new_name:
        raise ValidationFailed("A name for the copy is required.")
    project = service.duplicate(project_id, new_name)
    return _to_out(project, service.stats_for(project))


@router.get("/{project_id}/stats", response_model=ProjectStats, summary="Counters for one project")
async def project_stats(project_id: str, service: ProjectServiceDep) -> ProjectStats:
    project = service.get(project_id)
    return ProjectStats(**service.stats_for(project))
