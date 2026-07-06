"""Liveness endpoint."""

from fastapi import APIRouter

from app.core.envelope import success_payload

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return success_payload({"status": "ok"})
