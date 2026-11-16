"""Model configuration endpoints (plan §7.1 model profiles)."""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import Response

from app.api.deps import ModelConfigServiceDep
from app.schemas.model_config import ModelConfigCreate, ModelConfigOut, ModelConfigUpdate
from app.services.model_config_service import to_out

router = APIRouter(prefix="/model-configs", tags=["model-configs"])


@router.post(
    "",
    response_model=ModelConfigOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a model configuration",
)
async def create_model(payload: ModelConfigCreate, service: ModelConfigServiceDep) -> dict:
    model = service.create(payload)
    return to_out(model, service)


@router.get("", response_model=list[ModelConfigOut], summary="List model configurations")
async def list_models(service: ModelConfigServiceDep) -> list[dict]:
    return [to_out(model, service) for model in service.list()]


@router.get("/{model_id}", response_model=ModelConfigOut, summary="Get one model configuration")
async def get_model(model_id: str, service: ModelConfigServiceDep) -> dict:
    return to_out(service.get(model_id), service)


@router.put("/{model_id}", response_model=ModelConfigOut, summary="Update a model configuration")
async def update_model(
    model_id: str, payload: ModelConfigUpdate, service: ModelConfigServiceDep
) -> dict:
    model = service.update(model_id, payload)
    return to_out(model, service)


@router.delete(
    "/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a model configuration",
)
async def delete_model(model_id: str, service: ModelConfigServiceDep) -> Response:
    service.delete(model_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{model_id}/default",
    response_model=ModelConfigOut,
    summary="Mark this model as the default for new work",
)
async def set_default(model_id: str, service: ModelConfigServiceDep) -> dict:
    model = service.set_default(model_id)
    return to_out(model, service)
