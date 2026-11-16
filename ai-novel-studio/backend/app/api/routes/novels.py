"""Volume and chapter endpoints (plan §13.2), all scoped to one project."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import Response

from app.api.deps import NovelServiceDep
from app.schemas.novel import (
    ChapterAcceptAi,
    ChapterAcceptAiResult,
    ChapterCreate,
    ChapterListItem,
    ChapterOut,
    ChapterReorder,
    ChapterUpdate,
    ChapterVersionOut,
    VolumeCreate,
    VolumeOut,
    VolumeUpdate,
)
from app.services.novel_service import volumes_to_out

router = APIRouter(prefix="/projects/{project_id}", tags=["novels"])


# ---------------------------------------------------------------------------
# Volumes
# ---------------------------------------------------------------------------


@router.get("/volumes", response_model=list[VolumeOut], summary="List volumes")
async def list_volumes(project_id: str, service: NovelServiceDep) -> list[VolumeOut]:
    return volumes_to_out(service.list_volumes(project_id))


@router.post(
    "/volumes",
    response_model=VolumeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a volume",
)
async def create_volume(
    project_id: str, payload: VolumeCreate, service: NovelServiceDep
) -> VolumeOut:
    return VolumeOut.model_validate(service.create_volume(project_id, payload))


@router.patch("/volumes/{volume_id}", response_model=VolumeOut, summary="Update a volume")
async def update_volume(
    project_id: str, volume_id: str, payload: VolumeUpdate, service: NovelServiceDep
) -> VolumeOut:
    return VolumeOut.model_validate(service.update_volume(project_id, volume_id, payload))


@router.delete(
    "/volumes/{volume_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a volume (its chapters are kept)",
)
async def delete_volume(project_id: str, volume_id: str, service: NovelServiceDep) -> Response:
    service.delete_volume(project_id, volume_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------


@router.get(
    "/chapters",
    response_model=list[ChapterListItem],
    summary="List chapters (metadata only)",
)
async def list_chapters(
    project_id: str,
    service: NovelServiceDep,
    volume_id: Annotated[str | None, Query()] = None,
    include_deleted: bool = False,
) -> list[ChapterListItem]:
    return service.list_chapters(project_id, volume_id=volume_id, include_deleted=include_deleted)


@router.post(
    "/chapters",
    response_model=ChapterOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a chapter",
)
async def create_chapter(
    project_id: str, payload: ChapterCreate, service: NovelServiceDep
) -> ChapterOut:
    return service.create_chapter(project_id, payload)


@router.post("/chapters/reorder", response_model=list[ChapterListItem], summary="Reorder chapters")
async def reorder_chapters(
    project_id: str, payload: ChapterReorder, service: NovelServiceDep
) -> list[ChapterListItem]:
    return service.reorder_chapters(project_id, payload.chapter_ids)


@router.get(
    "/chapters/{chapter_id}",
    response_model=ChapterOut,
    summary="Read a chapter with its manuscript",
)
async def get_chapter(project_id: str, chapter_id: str, service: NovelServiceDep) -> ChapterOut:
    return service.get_chapter(project_id, chapter_id)


@router.put(
    "/chapters/{chapter_id}",
    response_model=ChapterOut,
    summary="Save a chapter (autosave or manual)",
)
async def update_chapter(
    project_id: str, chapter_id: str, payload: ChapterUpdate, service: NovelServiceDep
) -> ChapterOut:
    return service.update_chapter(project_id, chapter_id, payload)


@router.delete(
    "/chapters/{chapter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chapter (soft delete)",
)
async def delete_chapter(project_id: str, chapter_id: str, service: NovelServiceDep) -> Response:
    service.delete_chapter(project_id, chapter_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


@router.get(
    "/chapters/{chapter_id}/versions",
    response_model=list[ChapterVersionOut],
    summary="List chapter versions, newest first",
)
async def list_versions(
    project_id: str, chapter_id: str, service: NovelServiceDep
) -> list[ChapterVersionOut]:
    return service.list_versions(project_id, chapter_id)


@router.post(
    "/chapters/{chapter_id}/accept-ai",
    response_model=ChapterAcceptAiResult,
    summary="Adopt AI text, keeping the pre-accept text as history",
)
async def accept_ai(
    project_id: str, chapter_id: str, payload: ChapterAcceptAi, service: NovelServiceDep
) -> ChapterAcceptAiResult:
    return service.accept_ai(project_id, chapter_id, payload)


@router.post(
    "/chapters/{chapter_id}/versions",
    response_model=list[ChapterVersionOut],
    status_code=status.HTTP_201_CREATED,
    summary="Snapshot the current chapter text",
)
async def snapshot_version(
    project_id: str, chapter_id: str, service: NovelServiceDep
) -> list[ChapterVersionOut]:
    return service.snapshot_chapter(project_id, chapter_id)


@router.post(
    "/chapters/{chapter_id}/versions/{version_id}/restore",
    response_model=ChapterOut,
    summary="Restore a version (the current text is snapshotted first)",
)
async def restore_version(
    project_id: str, chapter_id: str, version_id: str, service: NovelServiceDep
) -> ChapterOut:
    return service.restore_version(project_id, chapter_id, version_id)
