"""Degree-planner orchestration: programs + history → planning engine (FR-3.6.x).

The planning engine stays pure: preference inputs (topic interests) are matched
to course text HERE, and only the resulting course-code set is handed to the
scheduler, so the deterministic engine never touches catalogue-shaped fields.
"""

import re
from typing import Any

from app.core.errors import NotFoundError, ValidationFailedError
from app.domain.planning.dual_degree import merge_required_courses
from app.domain.planning.models import (
    PlanPreferences,
    PlanResult,
    ProgramRequirements,
    Semester,
)
from app.domain.planning.prereq_ast import evaluate_prereq
from app.domain.planning.scheduler import build_plan
from app.repositories.artifacts import ArtifactRepository
from app.repositories.catalogue import CatalogueRepository
from app.repositories.students import StudentRepository

_WORD = re.compile(r"[a-z]{3,}")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _parse_label(label: str) -> tuple[int, str]:
    """'2026 S1' → (2026, 'S1'); tolerant of unexpected formats."""
    parts = label.split()
    if len(parts) == 2 and parts[0].isdigit():
        return int(parts[0]), parts[1]
    return 0, label


def _prev_semester(semester: Semester) -> Semester:
    """Inverse of Semester.next(): step one study period backwards."""
    if semester.period == "S2":
        return Semester(semester.year, "S1")
    return Semester(semester.year - 1, "S2")


def _rebuild_semesters(
    grouped: dict[int, list[dict[str, Any]]], label_by_index: dict[int, str]
) -> list[dict[str, Any]]:
    """Rebuild the contiguous semester list (incl. empty gaps) from stored entries."""
    if not grouped:
        return []
    min_index = min(grouped)
    max_index = max(grouped)
    year, period = _parse_label(label_by_index[min_index])
    if not year:
        # Label was not the expected 'YYYY Sx' form — present the stored ones as-is.
        return [
            {
                "year": 0,
                "semester": label_by_index[index],
                "label": label_by_index[index],
                "entries": sorted(grouped[index], key=lambda e: e["course_code"] or ""),
            }
            for index in sorted(grouped)
        ]
    current = Semester(year, period)
    for _ in range(min_index):  # walk back to reconstruct index 0
        current = _prev_semester(current)
    semesters = []
    for index in range(max_index + 1):
        semesters.append(
            {
                "year": current.year,
                "semester": current.period,
                "label": current.label,
                "entries": sorted(grouped.get(index, []), key=lambda e: e["course_code"] or ""),
            }
        )
        current = current.next()
    return semesters


class PlannerService:
    def __init__(
        self,
        catalogue: CatalogueRepository,
        students: StudentRepository,
        artifacts: ArtifactRepository,
    ):
        self._catalogue = catalogue
        self._students = students
        self._artifacts = artifacts

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
        codes = sorted(merged.required | merged.elective)
        # Batch the catalogue reads (was get_course + get_prereq_tree + raw-text per code).
        by_code = {course["code"]: course for course in self._catalogue.list_courses()}
        relevant = [by_code[code] for code in codes if code in by_code]
        course_ids = [course["id"] for course in relevant]
        trees = self._catalogue.get_prereq_trees(course_ids)
        raw_by_id = self._catalogue.get_prereq_raw_texts(course_ids)
        statuses = []
        for course in relevant:
            code = course["code"]
            evaluation = evaluate_prereq(trees.get(course["id"]), completed)
            statuses.append(
                {
                    "course_code": code,
                    "course_title": course["title"],
                    "requirement_kind": "required" if code in merged.required else "elective",
                    "is_completed": code in completed,
                    "prereq_status": evaluation.status.value,
                    "outstanding": list(evaluation.outstanding),
                    "requires_manual_check": evaluation.requires_manual_check,
                    "raw_prerequisite": raw_by_id.get(course["id"]),
                }
            )
        return statuses

    # ── Sequence generation (FR-3.6.2, FR-3.6.5, FR-3.6.6) ─────────────────
    def _interest_codes(self, codes: list[str], interests: list[str]) -> frozenset[str]:
        interest_words = _tokens(" ".join(interests))
        if not interest_words:
            return frozenset()
        text_by_code = {
            course["code"]: f"{course['title']} {course.get('description', '')}"
            for course in self._catalogue.list_courses()
        }
        return frozenset(
            code
            for code in codes
            if interest_words & _tokens(text_by_code.get(code, code))
        )

    def _run(
        self,
        user_id: str,
        start_year: int,
        start_semester: str,
        max_units_per_semester: float,
        prioritise_available: bool,
        interests: list[str],
    ) -> PlanResult:
        merged = merge_required_courses(self._program_requirements(user_id))
        completed = self._students.completed_course_codes(user_id)
        to_plan = sorted(merged.required - completed)
        plannable = self._catalogue.get_plannable_courses(to_plan)
        preferences = PlanPreferences(
            prioritise_available=prioritise_available,
            interest_codes=self._interest_codes(to_plan, interests),
        )
        return build_plan(
            plannable,
            completed=completed,
            start=Semester(start_year, start_semester),
            max_units_per_semester=max_units_per_semester,
            preferences=preferences,
        )

    @staticmethod
    def _shape(plan: PlanResult) -> dict[str, Any]:
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

    def sequence(
        self,
        user_id: str,
        start_year: int,
        start_semester: str,
        max_units_per_semester: float,
        prioritise_available: bool = False,
        interests: list[str] | None = None,
    ) -> dict[str, Any]:
        """A valid ordered study plan for the required courses (FR-3.6.2, FR-3.6.5)."""
        plan = self._run(
            user_id,
            start_year,
            start_semester,
            max_units_per_semester,
            prioritise_available,
            interests or [],
        )
        return self._shape(plan)

    # ── Saved, nameable degree plans (FR-3.6.2) ───────────────────────────
    def save_plan(
        self,
        user_id: str,
        name: str,
        start_year: int,
        start_semester: str,
        max_units_per_semester: float,
        prioritise_available: bool = False,
        interests: list[str] | None = None,
    ) -> dict[str, Any]:
        plan = self._run(
            user_id,
            start_year,
            start_semester,
            max_units_per_semester,
            prioritise_available,
            interests or [],
        )
        code_to_id = {course["code"]: course["id"] for course in self._catalogue.list_courses()}
        entries = []
        for index, semester in enumerate(plan.semesters):
            for entry in semester.entries:
                course_id = code_to_id.get(entry.course_code)
                if course_id is None:
                    continue
                entries.append(
                    {
                        "semester_index": index,
                        "semester_label": semester.semester.label,
                        "course_id": course_id,
                        "explanation": entry.explanation,
                    }
                )
        diagnostics = [
            {"severity": d.severity, "message": d.message} for d in plan.diagnostics
        ]
        record = self._artifacts.save_degree_plan(
            user_id, name, plan.feasible, entries, diagnostics
        )
        return self.get_plan(user_id, record["id"])

    def list_plans(self, user_id: str) -> list[dict[str, Any]]:
        return self._artifacts.list_degree_plans(user_id)

    def get_plan(self, user_id: str, plan_id: int) -> dict[str, Any]:
        row = self._artifacts.get_degree_plan(user_id, plan_id)
        if row is None:
            raise NotFoundError("Degree plan not found")
        return self._shape_saved(row)

    def delete_plan(self, user_id: str, plan_id: int) -> None:
        if not self._artifacts.delete_degree_plan(user_id, plan_id):
            raise NotFoundError("Degree plan not found")

    @staticmethod
    def _shape_saved(row: dict[str, Any]) -> dict[str, Any]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        label_by_index: dict[int, str] = {}
        for entry in row.get("degree_plan_entries") or []:
            index = entry["semester_index"]
            label_by_index[index] = entry["semester_label"]
            course = entry.get("courses") or {}
            grouped.setdefault(index, []).append(
                {
                    "course_code": course.get("code"),
                    "units": course.get("units"),
                    "explanation": entry.get("explanation", ""),
                }
            )
        return {
            "id": row["id"],
            "name": row["name"],
            "feasible": row["feasible"],
            "generated_at": row.get("generated_at"),
            # Reconstruct the FULL contiguous semester list — the scheduler keeps
            # empty 'gap' semesters between placements, but only course rows are
            # persisted, so empty semesters must be rebuilt to match the live plan.
            "semesters": _rebuild_semesters(grouped, label_by_index),
            "diagnostics": [
                {"severity": d["severity"], "message": d["message"]}
                for d in row.get("degree_plan_diagnostics") or []
            ],
        }
