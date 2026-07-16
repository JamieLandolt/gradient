"""ECP ingestion (students submit) and curator review endpoints (FR-3.5.x)."""

import logging

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from app.api.deps import get_current_curator, get_ingestion_service
from app.core.auth import AuthUser, get_current_user
from app.core.envelope import success_payload
from app.core.errors import ValidationFailedError
from app.core.rate_limit import RateLimit, rate_limit
from app.ingestion.pdf import extract_upload_text
from app.schemas.api import IngestionSubmitRequest, IngestionUrlRequest
from app.services.ingestion import IngestionService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ingestion"])

# Each submission runs an LLM extraction (and, for from-url, a scrape of
# UQ's site). Cap per caller so one account can't queue work in a loop.
_SUBMIT_LIMIT = RateLimit(requests=10, window_s=60)

# A paste large enough to be a real ECP but bounded so a huge upload can't tie up
# the extraction worker (mirrors IngestionSubmitRequest.payload's max_length).
MAX_UPLOAD_CHARS = 100_000
# Cap the raw bytes we buffer so a giant upload can't exhaust memory before the
# character cap is even reachable. ECP PDFs are well under this.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post(
    "/ingestion/jobs", status_code=201,
    dependencies=[Depends(rate_limit(_SUBMIT_LIMIT))],
)
def submit_job(
    request: IngestionSubmitRequest,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> dict:
    """Queue a paste for extraction. Returns ``queued`` at once; the client
    polls ``GET /ingestion/jobs/{id}`` for the terminal status (NFR-5.1.5)."""
    job = ingestion.create_job(
        user.id,
        source_type=request.source_type,
        payload=request.payload,
        source_ref=request.source_ref,
    )
    background_tasks.add_task(
        ingestion.run_extraction,
        job["id"], request.payload, request.source_type, request.source_ref,
    )
    return success_payload(job)


@router.post(
    "/ingestion/uploads", status_code=201,
    dependencies=[Depends(rate_limit(_SUBMIT_LIMIT))],
)
async def upload_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_ref: str = Form(""),
    user: AuthUser = Depends(get_current_user),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> dict:
    """Accept an ECP PDF (or .txt), extract its text locally, then queue the
    same background extraction pipeline as a paste (FR-3.5.3, review item 13)."""
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise ValidationFailedError("The uploaded file is too large (max 10 MB).")
    # Bounded read: never buffer more than the cap even if the declared size lied.
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationFailedError("The uploaded file is too large (max 10 MB).")

    # PDF parsing is CPU-bound; keep it off the event loop so one large or
    # hostile file can't stall the pollers this feature depends on.
    try:
        text = await anyio.to_thread.run_sync(
            extract_upload_text, data, file.filename or "", file.content_type or ""
        )
    except ValueError as exc:
        # Log the parser detail server-side; return a generic message so pypdf
        # internals don't leak to the client.
        logger.warning("ECP upload parse failed: %s", exc)
        raise ValidationFailedError(
            "The file could not be read. Upload a valid PDF or .txt course profile."
        ) from exc
    if not text.strip():
        raise ValidationFailedError("The uploaded file contained no readable text.")
    if len(text) > MAX_UPLOAD_CHARS:
        raise ValidationFailedError("The uploaded file is too large to process.")

    ref = source_ref or (file.filename or "")
    job = ingestion.create_job(user.id, source_type="upload", payload=text, source_ref=ref)
    background_tasks.add_task(ingestion.run_extraction, job["id"], text, "upload", ref)
    return success_payload(job)


@router.post(
    "/ingestion/from-url", status_code=201,
    dependencies=[Depends(rate_limit(_SUBMIT_LIMIT))],
)
def submit_url_job(
    request: IngestionUrlRequest,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> dict:
    """Queue a course code for ECP web-scraping (FR-3.5.1). Returns ``queued``
    at once; the scrape + extraction run in the background, same as a paste."""
    job = ingestion.create_url_job(user.id, request.course_code)
    background_tasks.add_task(ingestion.run_url_extraction, job["id"], request.course_code)
    return success_payload(job)


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
