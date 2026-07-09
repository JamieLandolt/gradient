"""Advisory endpoints: recommendations, study plans, semantic search, assistant."""

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_advisory_service
from app.core.auth import AuthUser, get_current_user
from app.core.envelope import success_payload
from app.schemas.api import AssistantAskRequest, RecommendRequest, StudyPlanGenerateRequest
from app.services.advisory import AdvisoryService

router = APIRouter(tags=["advisory"])


@router.post("/recommendations/generate")
def generate_recommendations(
    request: RecommendRequest,
    user: AuthUser = Depends(get_current_user),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    return success_payload(advisory.recommend(user.id, request.interests, request.limit))


@router.post("/study-plans/generate")
def generate_study_plan(
    request: StudyPlanGenerateRequest,
    user: AuthUser = Depends(get_current_user),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    return success_payload(
        advisory.study_plan(
            user.id,
            request.enrolment_id,
            request.target_grade,
            request.start_date.isoformat() if request.start_date else None,
        )
    )


@router.get("/search/courses")
def search_courses(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=10, ge=1, le=50),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    """Semantic search over public course descriptions (FR-3.9.2: no auth needed)."""
    return success_payload(advisory.search(q, limit))


@router.post("/assistant/ask")
def ask_assistant(
    request: AssistantAskRequest,
    user: AuthUser = Depends(get_current_user),
    advisory: AdvisoryService = Depends(get_advisory_service),
) -> dict:
    return success_payload(advisory.ask(user.id, request.question, request.enrolment_id))
