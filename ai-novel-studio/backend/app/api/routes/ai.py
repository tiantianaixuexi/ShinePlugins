"""AI writing endpoints (plan §13.3)."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from app.ai.prompts.builtin import OPERATIONS
from app.api.deps import AIServiceDep
from app.schemas.ai import (
    AIRequest,
    AIResult,
    AITaskSummary,
    OutlineRequest,
    OutlineResult,
    PromptSummary,
    PromptUpdate,
    SummaryRequest,
    SummaryResult,
)
from app.services.ai_service import AIStreamEvent

router = APIRouter(prefix="/ai", tags=["ai"])


def _sse(event: AIStreamEvent) -> dict[str, str]:
    """Frame one service event for ``EventSourceResponse``."""
    if event.type == "delta":
        return {
            "event": "delta",
            "data": json.dumps({"text": event.text}, ensure_ascii=False),
        }
    if event.type == "thinking":
        # Chain-of-thought from reasoning models: same shape as ``delta`` but a
        # distinct event name, so clients never fold it into the answer text.
        return {
            "event": "thinking",
            "data": json.dumps({"text": event.text}, ensure_ascii=False),
        }
    # ``reset`` (the JSON repair restarted the reply) carries no payload and
    # falls into this generic branch: ``event: reset`` + ``data: {}``.
    return {
        "event": event.type,
        "data": json.dumps(event.data, ensure_ascii=False),
    }


@router.get("/operations", summary="Available writing operations")
async def list_operations() -> dict[str, list[str]]:
    return {"operations": sorted(OPERATIONS)}


@router.get("/prompts", response_model=list[PromptSummary], summary="Prompt templates")
async def list_prompts(service: AIServiceDep) -> list[PromptSummary]:
    return [
        PromptSummary(
            key=row.key,
            name=row.name,
            version=row.version,
            description=row.description,
            variables=list(row.variables),
            is_active=row.is_active,
        )
        for row in service.prompts.list()
    ]


@router.patch(
    "/prompts/{key}",
    response_model=PromptSummary,
    summary="Override a prompt template (writes a new version)",
)
async def update_prompt(
    key: str, payload: PromptUpdate, service: AIServiceDep
) -> PromptSummary:
    """Save an author-edited template as version *n+1*.

    Earlier versions are kept (never updated in place) so a generation that
    recorded version *n* still resolves to the exact text it used.
    """
    try:
        row = service.prompts.upsert_override(
            key,
            payload.content,
            name=payload.name,
            variables=payload.variables,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown prompt key: {key}") from exc
    return PromptSummary(
        key=row.key,
        name=row.name,
        version=row.version,
        description=row.description,
        variables=list(row.variables),
        is_active=row.is_active,
    )


@router.post(
    "/summary/{chapter_id}",
    response_model=SummaryResult,
    summary="Summarise one chapter into L1 memory",
)
async def summarize_chapter(
    chapter_id: str, payload: SummaryRequest, service: AIServiceDep
) -> SummaryResult:
    """Explicit, paid, non-streaming summarisation.

    Registered before ``/{operation}`` so a two-segment path is never mistaken
    for the single-segment writing-operation route.
    """
    return SummaryResult(
        **await service.summarize_chapter(
            payload.project_id, chapter_id, force=payload.force
        )
    )


@router.post(
    "/outline/{chapter_id}",
    response_model=OutlineResult,
    summary="Generate a chapter outline and persist it",
)
async def generate_outline(
    chapter_id: str, payload: OutlineRequest, service: AIServiceDep
) -> OutlineResult:
    """Structured (JSON) outline written to the project's ``outlines`` table.

    Registered before ``/{operation}`` for the same reason as ``/summary``: a
    two-segment path must never be mistaken for the writing-operation route.
    """
    return OutlineResult(
        **await service.generate_outline(
            payload.project_id,
            chapter_id,
            force=payload.force,
            instruction=payload.instruction,
        )
    )


@router.post(
    "/summary/{chapter_id}/stream",
    summary="Summarise one chapter and stream the reply",
)
async def stream_summary(
    chapter_id: str, payload: SummaryRequest, service: AIServiceDep
) -> EventSourceResponse:
    """Streaming twin of ``POST /ai/summary/{chapter_id}``.

    Registered before ``/{operation}`` like its non-streaming sibling. The
    chapter (404) and the model (422) are resolved **before** the stream opens,
    so a broken configuration still arrives as a normal HTTP error.
    """
    service.preflight_summary(payload.project_id, chapter_id)

    async def events():
        async for event in service.stream_summary(
            payload.project_id, chapter_id, force=payload.force
        ):
            yield _sse(event)

    return EventSourceResponse(events())


@router.post(
    "/outline/{chapter_id}/stream",
    summary="Generate a chapter outline and stream the reply",
)
async def stream_outline(
    chapter_id: str, payload: OutlineRequest, service: AIServiceDep
) -> EventSourceResponse:
    """Streaming twin of ``POST /ai/outline/{chapter_id}``.

    Outline calls are the slowest in the product, so this is the endpoint the
    desktop client should prefer; the payload is persisted exactly as before.
    """
    service.preflight_outline(payload.project_id, chapter_id)

    async def events():
        async for event in service.stream_outline(
            payload.project_id,
            chapter_id,
            force=payload.force,
            instruction=payload.instruction,
        ):
            yield _sse(event)

    return EventSourceResponse(events())


@router.post("/{operation}", response_model=AIResult, summary="Run a writing operation")
async def run_ai(operation: str, payload: AIRequest, service: AIServiceDep) -> AIResult:
    return await service.run(operation, payload)


@router.post("/{operation}/stream", summary="Run a writing operation and stream the text")
async def stream_ai(
    operation: str, payload: AIRequest, service: AIServiceDep
) -> EventSourceResponse:
    # Validate before the response starts, so a bad operation is a normal 422
    # rather than a broken event stream.
    service.validate_operation(operation)

    async def events():
        async for event in service.stream(operation, payload):
            yield _sse(event)

    return EventSourceResponse(events())


@router.get(
    "/tasks",
    response_model=list[AITaskSummary],
    summary="Recent AI tasks with token and cost accounting",
)
async def list_tasks(
    service: AIServiceDep,
    project_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AITaskSummary]:
    return [
        AITaskSummary(
            id=task.id,
            project_id=task.project_id,
            kind=task.kind,
            status=task.status,
            model_config_id=task.model_config_id,
            input_tokens=task.input_tokens,
            output_tokens=task.output_tokens,
            cost=task.cost,
            error=task.error,
            created_at=task.created_at.isoformat() if task.created_at else "",
        )
        for task in service.list_tasks(project_id=project_id, limit=limit)
    ]
