"""Degree-planner endpoints (authed): prerequisite status and study sequence."""

from fastapi import APIRouter, Depends

from app.api.deps import get_planner_service, get_student_repo
from app.core.auth import AuthUser, get_current_user
from app.core.envelope import success_payload
from app.repositories.students import StudentRepository
from app.schemas.api import (
    DegreePlanSaveRequest,
    ProgramSelectionRequest,
    SequenceRequest,
)
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
            study_load=request.study_load,
            prioritise_available=request.prioritise_available,
            interests=request.interests,
        )
    )


@router.get("/planner/plans")
async def list_plans(
    user: AuthUser = Depends(get_current_user),
    planner: PlannerService = Depends(get_planner_service),
) -> dict:
    return success_payload(planner.list_plans(user.id))


@router.post("/planner/plans", status_code=201)
async def save_plan(
    request: DegreePlanSaveRequest,
    user: AuthUser = Depends(get_current_user),
    planner: PlannerService = Depends(get_planner_service),
) -> dict:
    return success_payload(
        planner.save_plan(
            user.id,
            name=request.name,
            start_year=request.start_year,
            start_semester=request.start_semester,
            study_load=request.study_load,
            prioritise_available=request.prioritise_available,
            interests=request.interests,
        )
    )


@router.get("/planner/plans/{plan_id}")
async def get_plan(
    plan_id: int,
    user: AuthUser = Depends(get_current_user),
    planner: PlannerService = Depends(get_planner_service),
) -> dict:
    return success_payload(planner.get_plan(user.id, plan_id))


@router.delete("/planner/plans/{plan_id}")
async def delete_plan(
    plan_id: int,
    user: AuthUser = Depends(get_current_user),
    planner: PlannerService = Depends(get_planner_service),
) -> dict:
    planner.delete_plan(user.id, plan_id)
    return success_payload({"deleted": True})
