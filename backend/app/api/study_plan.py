"""Weekly, multi-course study-plan endpoints (FR-3.8.x, authed)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_weekly_study_plan_service
from app.core.auth import AuthUser, get_current_user
from app.core.envelope import success_payload
from app.schemas.api import (
    AssessmentTargetsRequest,
    StudyAvailabilityRequest,
    WeeklyStudyPlanGenerateRequest,
)
from app.services.study_plan import WeeklyStudyPlanService

router = APIRouter(tags=["study-plan"])


@router.get("/study-availability")
def get_study_availability(
    user: AuthUser = Depends(get_current_user),
    service: WeeklyStudyPlanService = Depends(get_weekly_study_plan_service),
) -> dict:
    return success_payload(service.get_availability(user.id))


@router.put("/study-availability")
def set_study_availability(
    request: StudyAvailabilityRequest,
    user: AuthUser = Depends(get_current_user),
    service: WeeklyStudyPlanService = Depends(get_weekly_study_plan_service),
) -> dict:
    slots = [slot.model_dump() for slot in request.slots]
    return success_payload(service.set_availability(user.id, slots))


@router.get("/study-plans/remaining-assessments")
def get_remaining_assessments(
    user: AuthUser = Depends(get_current_user),
    service: WeeklyStudyPlanService = Depends(get_weekly_study_plan_service),
) -> dict:
    """Every not-yet-graded assessment across all in-progress courses, with
    any existing target attached — the UI uses this to render target inputs."""
    return success_payload(service.remaining_assessments(user.id))


@router.put("/study-plans/targets")
def set_assessment_targets(
    request: AssessmentTargetsRequest,
    user: AuthUser = Depends(get_current_user),
    service: WeeklyStudyPlanService = Depends(get_weekly_study_plan_service),
) -> dict:
    service.set_targets(user.id, [target.model_dump() for target in request.targets])
    return success_payload({"saved": True})


@router.post("/study-plans/generate")
def generate_weekly_study_plan(
    request: WeeklyStudyPlanGenerateRequest,
    user: AuthUser = Depends(get_current_user),
    service: WeeklyStudyPlanService = Depends(get_weekly_study_plan_service),
) -> dict:
    return success_payload(service.generate(user.id, request.week_start.isoformat()))


@router.get("/study-plans")
def list_weekly_study_plans(
    user: AuthUser = Depends(get_current_user),
    service: WeeklyStudyPlanService = Depends(get_weekly_study_plan_service),
) -> dict:
    return success_payload(service.list_plans(user.id))


@router.get("/study-plans/{plan_id}")
def get_weekly_study_plan(
    plan_id: int,
    user: AuthUser = Depends(get_current_user),
    service: WeeklyStudyPlanService = Depends(get_weekly_study_plan_service),
) -> dict:
    return success_payload(service.get_plan(user.id, plan_id))


@router.delete("/study-plans/{plan_id}")
def delete_weekly_study_plan(
    plan_id: int,
    user: AuthUser = Depends(get_current_user),
    service: WeeklyStudyPlanService = Depends(get_weekly_study_plan_service),
) -> dict:
    service.delete_plan(user.id, plan_id)
    return success_payload({"deleted": True})
