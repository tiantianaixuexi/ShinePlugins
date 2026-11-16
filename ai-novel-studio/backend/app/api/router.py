"""API router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import ai, health, model_configs, novels, projects, system

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(projects.router)
api_router.include_router(novels.router)
api_router.include_router(model_configs.router)
api_router.include_router(ai.router)
api_router.include_router(system.router)
