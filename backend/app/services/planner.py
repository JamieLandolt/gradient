"""Degree-planner orchestration: programs + history → planning engine (FR-3.6.x)."""

from typing import Any

from app.core.errors import ValidationFailedError
from app.domain.planning.dual_degree import merge_required_courses
from app.domain.planning.models import ProgramRequirements, Semester
from app.domain.planning.prereq_ast import evaluate_prereq
from app.domain.planning.scheduler import build_plan
from app.repositories.catalogue import CatalogueRepository
from app.repositories.students import StudentRepository


class PlannerService:
    def __init__(self, catalogue: CatalogueRepository, students: StudentRepository):
        self._catalogue = catalogue
        self._students = students

    def _program_requirements(self, user_id: str) -> list[ProgramRequirements]:
        user_programs = self._students.get_user_programs(user_id)
        if not user_programs:
            raise ValidationFailedError(
                "Select your program(s) first so the planner knows what to schedule"
            )
        requirements = []
        for link in user_programs:
            program = link["programs"]
            rows = self._catalogue.get_program_courses(program["id"])
            required = frozenset(
                r["courses"]["code"] for r in rows if r["requirement_kind"] == "required"
            )
            elective = frozenset(
                r["courses"]["code"] for r in rows if r["requirement_kind"] == "elective"
            )
            requirements.append(
                ProgramRequirements(
                    program_code=program["code"], required=required, elective=elective
                )
            )
        return requirements

    def prereq_status(self, user_id: str) -> list[dict[str, Any]]:
        """Prerequisite status for every course in the student's program(s) (FR-3.6.4)."""
        merged = merge_required_courses(self._program_requirements(user_id))
        completed = self._students.completed_course_codes(user_id)
        statuses = []
        for code in sorted(merged.required | merged.elective):
            course = self._catalogue.get_course(code)
            if course is None:
                continue
            evaluation = evaluate_prereq(
                self._catalogue.get_prereq_tree(course["id"]), completed
            )
            statuses.append(
                {
                    "course_code": code,
                    "course_title": course["title"],
                    "requirement_kind": "required" if code in merged.required else "elective",
                    "is_completed": code in completed,
                    "prereq_status": evaluation.status.value,
                    "outstanding": list(evaluation.outstanding),
                    "requires_manual_check": evaluation.requires_manual_check,
                    "raw_prerequisite": self._catalogue.get_prereq_raw_text(course["id"]),
                }
            )
        return statuses

    def sequence(
        self,
        user_id: str,
        start_year: int,
        start_semester: str,
        max_units_per_semester: float,
    ) -> dict[str, Any]:
        """A valid ordered study plan for the required courses (FR-3.6.2, FR-3.6.5)."""
        merged = merge_required_courses(self._program_requirements(user_id))
        completed = self._students.completed_course_codes(user_id)
        to_plan = sorted(merged.required - completed)
        plannable = self._catalogue.get_plannable_courses(to_plan)

        plan = build_plan(
            plannable,
            completed=completed,
            start=Semester(start_year, start_semester),
            max_units_per_semester=max_units_per_semester,
        )
        return {
            "feasible": plan.feasible,
            "semesters": [
                {
                    "year": s.semester.year,
                    "semester": s.semester.period,
                    "label": s.semester.label,
                    "entries": [
                        {
                            "course_code": entry.course_code,
                            "units": entry.units,
                            "explanation": entry.explanation,
                        }
                        for entry in s.entries
                    ],
                }
                for s in plan.semesters
            ],
            "diagnostics": [
                {"severity": d.severity, "message": d.message} for d in plan.diagnostics
            ],
        }
