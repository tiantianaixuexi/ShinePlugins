"""Aggregate statistics across every registered project."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import ProjectServiceDep

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/stats", summary="Aggregate studio statistics")
async def studio_stats(service: ProjectServiceDep) -> dict[str, Any]:
    projects = service.list(limit=500)
    totals = {
        "projects": len(projects),
        "words": 0,
        "chapters": 0,
        "characters": 0,
        "chunks": 0,
    }
    by_project: list[dict[str, Any]] = []
    for project in projects:
        stats = service.stats_for(project)
        totals["words"] += stats.get("words", 0)
        totals["chapters"] += stats.get("chapters", 0)
        totals["characters"] += stats.get("characters", 0)
        totals["chunks"] += stats.get("chunks", 0)
        by_project.append(
            {
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "updated_at": project.updated_at.isoformat(),
                "words": stats.get("words", 0),
                "chapters": stats.get("chapters", 0),
            }
        )
    return {"totals": totals, "projects": by_project}
