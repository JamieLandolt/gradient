"""Advisory endpoints: recommendations, study plans, semantic search, assistant."""

import logging
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps import get_advisory_service
from app.core.auth import AuthUser, get_current_user
from app.core.envelope import success_payload
from app.providers.openai_compatible import AIProviderError
from app.schemas.api import AssistantAskRequest, RecommendRequest
from app.services.advisory import AdvisoryService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["advisory"])

_STREAM_ERROR_NOTICE = "\n\n[The assistant is unavailable right now — please try again.]"


# ── Recommendations (FR-3.7.x) ───────────────────────────────────────────────
@router.post("/recommendations/generate")
def generate_recommendations(
    request: RecommendRequest,
    user: AuthUser = Depends(get_current_user),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    return success_payload(advisory.recommend(user.id, request.interests, request.limit))


@router.get("/recommendations/latest")
def latest_recommendation(
    user: AuthUser = Depends(get_current_user),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    return success_payload(advisory.latest_recommendation(user.id))


@router.get("/recommendations")
def list_recommendations(
    user: AuthUser = Depends(get_current_user),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    return success_payload(advisory.list_recommendations(user.id))


@router.delete("/recommendations/{recommendation_id}")
def delete_recommendation(
    recommendation_id: int,
    user: AuthUser = Depends(get_current_user),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    advisory.delete_recommendation(user.id, recommendation_id)
    return success_payload({"deleted": True})


# ── Search (FR-3.9.2: no auth needed) ────────────────────────────────────────
@router.get("/search/courses")
def search_courses(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=10, ge=1, le=50),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    """Semantic search over public course descriptions."""
    return success_payload(advisory.search(q, limit))


# ── Assistant (FR-3.9.3) ─────────────────────────────────────────────────────
@router.post("/assistant/ask")
def ask_assistant(
    request: AssistantAskRequest,
    user: AuthUser = Depends(get_current_user),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    return success_payload(advisory.ask(user.id, request.question, request.enrolment_id))


@router.post("/assistant/ask/stream")
def ask_assistant_stream(
    request: AssistantAskRequest,
    user: AuthUser = Depends(get_current_user),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> StreamingResponse:
    """Stream the grounded answer token-by-token as plain UTF-8 text.

    Validation/fact-assembly run before the response starts (so bad input yields
    a normal error), and a provider failure mid-stream degrades to a short notice
    rather than a broken connection.
    """
    tokens = advisory.ask_stream(user.id, request.question, request.enrolment_id)

    def body() -> Iterator[bytes]:
        try:
            for token in tokens:
                yield token.encode("utf-8")
        except AIProviderError as exc:
            logger.warning("assistant stream failed for user %s: %s", user.id, exc)
            yield _STREAM_ERROR_NOTICE.encode("utf-8")

    return StreamingResponse(body(), media_type="text/plain; charset=utf-8")
