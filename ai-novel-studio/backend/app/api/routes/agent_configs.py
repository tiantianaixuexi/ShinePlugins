"""Per-agent model binding endpoints (plan §7.2, gap 1.5).

``PUT`` is an upsert keyed by ``agent_type``: the settings page never has to
know whether a binding already exists, and a repeated save edits the same row
instead of accumulating duplicates.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AgentConfigServiceDep
from app.schemas.agent_config import AgentConfigOut, AgentConfigUpsert

router = APIRouter(prefix="/agent-configs", tags=["agent-configs"])


@router.get("", response_model=list[AgentConfigOut], summary="List per-agent bindings")
async def list_agent_configs(service: AgentConfigServiceDep) -> list[AgentConfigOut]:
    return [AgentConfigOut.model_validate(row) for row in service.list()]


@router.put(
    "/{agent_type}",
    response_model=AgentConfigOut,
    summary="Create or update the binding for one agent type",
)
async def upsert_agent_config(
    agent_type: str, payload: AgentConfigUpsert, service: AgentConfigServiceDep
) -> AgentConfigOut:
    row = service.upsert(agent_type, **payload.model_dump(exclude_unset=True))
    return AgentConfigOut.model_validate(row)
