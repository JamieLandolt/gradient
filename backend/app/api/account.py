"""Account endpoints: profile, GPA, history, and account deletion (FR-3.1.4)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_student_repo, get_tracking_service
from app.core.auth import AuthUser, get_current_user
from app.core.envelope import success_payload
from app.core.errors import NotFoundError
from app.repositories.students import StudentRepository
from app.schemas.api import ProfileUpdateRequest
from app.services.tracking import TrackingService

router = APIRouter(tags=["account"])


@router.get("/me")
async def get_me(
    user: AuthUser = Depends(get_current_user),
    students: StudentRepository = Depends(get_student_repo),
) -> dict:
    profile = students.get_profile(user.id)
    if profile is None:
        raise NotFoundError("Profile not found")
    profile["email"] = user.email
    profile["programs"] = students.get_user_programs(user.id)
    return success_payload(profile)


@router.patch("/me")
async def update_me(
    request: ProfileUpdateRequest,
    user: AuthUser = Depends(get_current_user),
    students: StudentRepository = Depends(get_student_repo),
) -> dict:
    updated = students.update_profile(user.id, {"display_name": request.display_name})
    if updated is None:
        raise NotFoundError("Profile not found")
    return success_payload(updated)


@router.delete("/me")
async def delete_me(
    user: AuthUser = Depends(get_current_user),
    students: StudentRepository = Depends(get_student_repo),
) -> dict:
    students.delete_account(user.id)
    return success_payload({"deleted": True})


@router.get("/me/gpa")
async def get_gpa(
    user: AuthUser = Depends(get_current_user),
    tracking: TrackingService = Depends(get_tracking_service),
) -> dict:
    return success_payload(tracking.gpa(user.id))


@router.get("/me/history")
async def get_history(
    user: AuthUser = Depends(get_current_user),
    tracking: TrackingService = Depends(get_tracking_service),
) -> dict:
    return success_payload(tracking.history(user.id))
