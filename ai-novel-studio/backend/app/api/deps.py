"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.runtime import Runtime
from app.services.agent_config_service import AgentConfigService
from app.services.ai_service import AIService
from app.services.model_config_service import ModelConfigService
from app.services.novel_service import NovelService
from app.services.project_service import ProjectService


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_project_service(request: Request) -> ProjectService:
    return request.app.state.runtime.project_service


def get_model_config_service(request: Request) -> ModelConfigService:
    return request.app.state.runtime.model_configs


def get_agent_config_service(request: Request) -> AgentConfigService:
    return request.app.state.runtime.agent_configs


def get_novel_service(project_service: ProjectServiceDep) -> NovelService:
    return NovelService(project_service)


def get_ai_service(request: Request) -> AIService:
    return request.app.state.runtime.ai


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
ModelConfigServiceDep = Annotated[ModelConfigService, Depends(get_model_config_service)]
AgentConfigServiceDep = Annotated[AgentConfigService, Depends(get_agent_config_service)]
NovelServiceDep = Annotated[NovelService, Depends(get_novel_service)]
AIServiceDep = Annotated[AIService, Depends(get_ai_service)]
