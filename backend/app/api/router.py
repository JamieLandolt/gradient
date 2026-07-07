"""Aggregates all /api/v1 routers. Feature routers are added phase by phase."""

from fastapi import APIRouter

from app.api import health

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
