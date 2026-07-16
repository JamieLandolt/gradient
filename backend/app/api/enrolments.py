"""Enrolment, assessment, grade, standing, and required-marks endpoints (authed)."""

from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.api.deps import get_student_repo, get_tracking_service
from app.core.auth import AuthUser, get_current_user
from app.core.envelope import success_payload
from app.core.errors import NotFoundError, ValidationFailedError
from app.repositories.students import StudentRepository
from app.schemas.api import (
    CustomAssessmentRequest,
    EnrolmentCreateRequest,
    EnrolmentUpdateRequest,
    GradeUpsertRequest,
    RequiredMarksRequest,
)
from app.services.tracking import TrackingService

router = APIRouter(tags=["enrolments"])


@router.get("/enrolments")
async def list_enrolments(
    user: AuthUser = Depends(get_current_user),
    tracking: TrackingService = Depends(get_tracking_service),
) -> dict:
    return success_payload(tracking.history(user.id))


@router.post("/enrolments", status_code=201)
async def create_enrolment(
    request: EnrolmentCreateRequest,
    user: AuthUser = Depends(get_current_user),
    tracking: TrackingService = Depends(get_tracking_service),
) -> dict:
    enrolment = tracking.enrol(user.id, request.model_dump())
    return success_payload(enrolment)


@router.patch("/enrolments/{enrolment_id}")
async def update_enrolment(
    enrolment_id: int,
    request: EnrolmentUpdateRequest,
    user: AuthUser = Depends(get_current_user),
    tracking: TrackingService = Depends(get_tracking_service),
) -> dict:
    return success_payload(
        tracking.update_enrolment(user.id, enrolment_id, request.model_dump())
    )


@router.delete("/enrolments/{enrolment_id}")
async def delete_enrolment(
    enrolment_id: int,
    user: AuthUser = Depends(get_current_user),
    tracking: TrackingService = Depends(get_tracking_service),
) -> dict:
    tracking.remove_enrolment(user.id, enrolment_id)
    return success_payload({"deleted": True})


# ── Standing & required marks ────────────────────────────────────────────────
@router.get("/enrolments/{enrolment_id}/standing")
async def get_standing(
    enrolment_id: int,
    user: AuthUser = Depends(get_current_user),
    tracking: TrackingService = Depends(get_tracking_service),
) -> dict:
    return success_payload(tracking.standing(user.id, enrolment_id))


@router.post("/enrolments/{enrolment_id}/required-marks")
async def required_marks(
    enrolment_id: int,
    request: RequiredMarksRequest,
    user: AuthUser = Depends(get_current_user),
    tracking: TrackingService = Depends(get_tracking_service),
) -> dict:
    result = tracking.required_marks(
        user.id, enrolment_id, request.target_grade, request.what_if_scores
    )
    payload = asdict(result)
    payload["status"] = result.status.value
    return success_payload(payload)


# ── Custom assessments (FR-3.2.2) ────────────────────────────────────────────
@router.post("/enrolments/{enrolment_id}/assessments", status_code=201)
async def add_custom_assessment(
    enrolment_id: int,
    request: CustomAssessmentRequest,
    user: AuthUser = Depends(get_current_user),
    students: StudentRepository = Depends(get_student_repo),
) -> dict:
    if students.get_enrolment(user.id, enrolment_id) is None:
        raise NotFoundError("Enrolment not found")
    values = request.model_dump()
    if values.get("due_date") is not None:
        values["due_date"] = values["due_date"].isoformat()
    return success_payload(
        students.create_custom_assessment(user.id, enrolment_id, values)
    )


@router.patch("/assessments/custom/{assessment_id}")
async def update_custom_assessment(
    assessment_id: int,
    request: CustomAssessmentRequest,
    user: AuthUser = Depends(get_current_user),
    students: StudentRepository = Depends(get_student_repo),
) -> dict:
    values = request.model_dump()
    if values.get("due_date") is not None:
        values["due_date"] = values["due_date"].isoformat()
    updated = students.update_custom_assessment(user.id, assessment_id, values)
    if updated is None:
        raise NotFoundError("Assessment item not found")
    return success_payload(updated)


@router.delete("/assessments/custom/{assessment_id}")
async def delete_custom_assessment(
    assessment_id: int,
    user: AuthUser = Depends(get_current_user),
    students: StudentRepository = Depends(get_student_repo),
) -> dict:
    if not students.delete_custom_assessment(user.id, assessment_id):
        raise NotFoundError("Assessment item not found")
    return success_payload({"deleted": True})


# ── Grades (FR-3.2.3) ────────────────────────────────────────────────────────
@router.put("/enrolments/{enrolment_id}/grades")
async def upsert_grade(
    enrolment_id: int,
    request: GradeUpsertRequest,
    user: AuthUser = Depends(get_current_user),
    students: StudentRepository = Depends(get_student_repo),
) -> dict:
    if not request.target_is_valid():
        raise ValidationFailedError(
            "Provide exactly one of assessment_id or custom_assessment_id"
        )
    if students.get_enrolment(user.id, enrolment_id) is None:
        raise NotFoundError("Enrolment not found")
    # Bound the score against the item it belongs to BEFORE storing it. The
    # calculation engine validates this on read, so a score above max_mark used
    # to persist happily and then 422 every subsequent load of the course —
    # leaving the page unrenderable and the bad mark unfixable through the UI.
    max_mark = (
        students.get_assessment_max_mark(request.assessment_id)
        if request.assessment_id is not None
        else students.get_custom_assessment_max_mark(user.id, request.custom_assessment_id)
    )
    if max_mark is None:
        raise NotFoundError("Assessment item not found")
    if not 0 <= request.score <= max_mark:
        raise ValidationFailedError(
            f"Score must be between 0 and {max_mark:g} for this item"
        )
    grade = students.upsert_grade(
        user.id,
        enrolment_id,
        score=request.score,
        assessment_id=request.assessment_id,
        custom_assessment_id=request.custom_assessment_id,
    )
    return success_payload(grade)


@router.delete("/grades/{grade_id}")
async def delete_grade(
    grade_id: int,
    user: AuthUser = Depends(get_current_user),
    students: StudentRepository = Depends(get_student_repo),
) -> dict:
    if not students.delete_grade(user.id, grade_id):
        raise NotFoundError("Grade not found")
    return success_payload({"deleted": True})
