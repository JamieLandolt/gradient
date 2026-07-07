"""ECP ingestion (students submit) and curator review endpoints (FR-3.5.x)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_curator, get_ingestion_service
from app.core.auth import AuthUser, get_current_user
from app.core.envelope import success_payload
from app.schemas.api import IngestionSubmitRequest
from app.services.ingestion import IngestionService

router = APIRouter(tags=["ingestion"])


@router.post("/ingestion/jobs", status_code=201)
async def submit_job(
    request: IngestionSubmitRequest,
    user: AuthUser = Depends(get_current_user),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> dict:
    return success_payload(
        ingestion.submit(
            user.id,
            source_type=request.source_type,
            payload=request.payload,
            source_ref=request.source_ref,
        )
    )


@router.get("/ingestion/jobs/{job_id}")
async def get_job(
    job_id: int,
    user: AuthUser = Depends(get_current_user),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> dict:
    return success_payload(ingestion.get_job(user.id, job_id))


# ── Curator review (FR-3.5.3) ────────────────────────────────────────────────
@router.get("/curator/profile-versions")
async def list_draft_versions(
    curator: AuthUser = Depends(get_current_curator),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> dict:
    return success_payload(ingestion.list_drafts())


@router.post("/curator/profile-versions/{version_id}/verify")
async def verify_version(
    version_id: int,
    curator: AuthUser = Depends(get_current_curator),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> dict:
    return success_payload(ingestion.verify(version_id, curator.id))


@router.post("/curator/profile-versions/{version_id}/reject")
async def reject_version(
    version_id: int,
    curator: AuthUser = Depends(get_current_curator),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> dict:
    return success_payload(ingestion.reject(version_id, curator.id))
