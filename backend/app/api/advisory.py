"""Advisory endpoints: recommendations, study plans, semantic search, assistant."""

import logging
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps import get_advisory_service
from app.core.auth import AuthUser, get_current_user
from app.core.envelope import success_payload
from app.core.rate_limit import RateLimit, rate_limit
from app.providers.openai_compatible import AIProviderError
from app.schemas.api import AssistantAskRequest, RecommendRequest
from app.services.advisory import AdvisoryService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["advisory"])

_STREAM_ERROR_NOTICE = "\n\n[The assistant is unavailable right now — please try again.]"

# Every route below spends money with the hosted AI provider on each call, so
# each one is capped per caller. Search is the loosest because it is the only
# unauthenticated one (FR-3.9.2) and is meant to feel interactive; generate/ask
# are tighter because a single call is a full chat completion. The numbers are
# well above any human demo pace and well below what a script could spend.
_SEARCH_LIMIT = RateLimit(requests=30, window_s=60)
_GENERATE_LIMIT = RateLimit(requests=10, window_s=60)
_ASSISTANT_LIMIT = RateLimit(requests=15, window_s=60)


# ── Recommendations (FR-3.7.x) ───────────────────────────────────────────────
@router.post(
    "/recommendations/generate",
    dependencies=[Depends(rate_limit(_GENERATE_LIMIT))],
)
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
@router.get("/search/courses", dependencies=[Depends(rate_limit(_SEARCH_LIMIT))])
def search_courses(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=10, ge=1, le=50),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    """Semantic search over public course descriptions."""
    return success_payload(advisory.search(q, limit))


# ── Assistant (FR-3.9.3) ─────────────────────────────────────────────────────
@router.post("/assistant/ask", dependencies=[Depends(rate_limit(_ASSISTANT_LIMIT))])
def ask_assistant(
    request: AssistantAskRequest,
    user: AuthUser = Depends(get_current_user),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    return success_payload(advisory.ask(user.id, request.question, request.enrolment_id))


@router.post(
    "/assistant/ask/stream",
    dependencies=[Depends(rate_limit(_ASSISTANT_LIMIT))],
)
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
