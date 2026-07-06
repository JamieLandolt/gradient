"""Public catalogue endpoints: courses, profiles, programs (no auth required)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_catalogue_repo
from app.core.envelope import success_payload
from app.core.errors import NotFoundError
from app.repositories.catalogue import CatalogueRepository

router = APIRouter(tags=["catalogue"])


@router.get("/courses")
async def list_courses(catalogue: CatalogueRepository = Depends(get_catalogue_repo)) -> dict:
    return success_payload(catalogue.list_courses())


@router.get("/courses/{code}")
async def get_course(
    code: str, catalogue: CatalogueRepository = Depends(get_catalogue_repo)
) -> dict:
    course = catalogue.get_course(code.upper())
    if course is None:
        raise NotFoundError(f"Course {code.upper()} not found")
    course["offering_periods"] = sorted(catalogue.get_offering_periods(course["id"]))
    course["raw_prerequisite"] = catalogue.get_prereq_raw_text(course["id"])
    return success_payload(course)


@router.get("/courses/{code}/profile")
async def get_course_profile(
    code: str, catalogue: CatalogueRepository = Depends(get_catalogue_repo)
) -> dict:
    course = catalogue.get_course(code.upper())
    if course is None:
        raise NotFoundError(f"Course {code.upper()} not found")
    profile = catalogue.get_verified_profile(course["id"])
    if profile is None:
        raise NotFoundError(
            f"No verified course profile for {code.upper()} — add your own assessment items"
        )
    return success_payload(profile)


@router.get("/programs")
async def list_programs(catalogue: CatalogueRepository = Depends(get_catalogue_repo)) -> dict:
    programs = catalogue.list_programs()
    for program in programs:
        rows = catalogue.get_program_courses(program["id"])
        program["required_courses"] = sorted(
            r["courses"]["code"] for r in rows if r["requirement_kind"] == "required"
        )
        program["elective_courses"] = sorted(
            r["courses"]["code"] for r in rows if r["requirement_kind"] == "elective"
        )
    return success_payload(programs)
