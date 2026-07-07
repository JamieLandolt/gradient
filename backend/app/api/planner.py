"""Degree-planner endpoints (authed): prerequisite status and study sequence."""

from fastapi import APIRouter, Depends

from app.api.deps import get_planner_service, get_student_repo
from app.core.auth import AuthUser, get_current_user
from app.core.envelope import success_payload
from app.repositories.students import StudentRepository
from app.schemas.api import ProgramSelectionRequest, SequenceRequest
from app.services.planner import PlannerService

router = APIRouter(tags=["planner"])


@router.get("/planner/programs")
async def get_my_programs(
    user: AuthUser = Depends(get_current_user),
    students: StudentRepository = Depends(get_student_repo),
) -> dict:
    return success_payload(students.get_user_programs(user.id))


@router.put("/planner/programs")
async def set_my_programs(
    request: ProgramSelectionRequest,
    user: AuthUser = Depends(get_current_user),
    students: StudentRepository = Depends(get_student_repo),
) -> dict:
    students.set_user_programs(user.id, request.program_ids)
    return success_payload(students.get_user_programs(user.id))


@router.get("/planner/prereq-status")
async def prereq_status(
    user: AuthUser = Depends(get_current_user),
    planner: PlannerService = Depends(get_planner_service),
) -> dict:
    return success_payload(planner.prereq_status(user.id))


@router.post("/planner/sequence")
async def sequence(
    request: SequenceRequest,
    user: AuthUser = Depends(get_current_user),
    planner: PlannerService = Depends(get_planner_service),
) -> dict:
    return success_payload(
        planner.sequence(
            user.id,
            start_year=request.start_year,
            start_semester=request.start_semester,
            max_units_per_semester=request.max_units_per_semester,
        )
    )
