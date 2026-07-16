"""Grade-tracking orchestration: DB rows → calculation engine → API shapes.

FR-3.2.x and FR-3.3.x. All arithmetic happens in app.domain.calculation.
"""

from typing import Any

from app.core.errors import NotFoundError, ValidationFailedError
from app.domain.calculation.gpa import compute_gpa
from app.domain.calculation.models import (
    AssessmentItem,
    GpaEntry,
    InvalidAssessmentStructureError,
    RequiredMarksResult,
)
from app.domain.calculation.required_marks import compute_required_marks
from app.domain.calculation.standing import compute_standing
from app.repositories.catalogue import CatalogueRepository
from app.repositories.students import StudentRepository


class TrackingService:
    def __init__(self, catalogue: CatalogueRepository, students: StudentRepository):
        self._catalogue = catalogue
        self._students = students

    # ── Enrolment lifecycle (FR-3.2.1, FR-3.4.3) ──────────────────────────
    def enrol(self, user_id: str, request: dict[str, Any]) -> dict[str, Any]:
        course = self._catalogue.get_course(request["course_code"])
        if course is None:
            raise NotFoundError(f"Course {request['course_code']} not found")
        offering = self._catalogue.find_offering(
            course["id"], request["year"], request["semester"]
        )
        if offering is None:
            if not request.get("is_transfer"):
                raise ValidationFailedError(
                    f"{course['code']} is not offered in {request['year']} "
                    f"{request['semester']}"
                )
            # Historical/transfer records may predate the catalogue (FR-3.4.3).
            offering = self._catalogue.create_offering(
                course["id"], request["year"], request["semester"]
            )
        created = self._students.create_enrolment(
            user_id,
            {
                "course_offering_id": offering["id"],
                "status": request.get("status", "in_progress"),
                "is_transfer": request.get("is_transfer", False),
                "final_grade": request.get("final_grade"),
                "final_percent": request.get("final_percent"),
            },
        )
        return self._require_enrolment(user_id, created["id"])

    def update_enrolment(
        self, user_id: str, enrolment_id: int, values: dict[str, Any]
    ) -> dict[str, Any]:
        clean = {k: v for k, v in values.items() if v is not None}
        if not clean:
            raise ValidationFailedError("Nothing to update")
        updated = self._students.update_enrolment(user_id, enrolment_id, clean)
        if updated is None:
            raise NotFoundError("Enrolment not found")
        return self._require_enrolment(user_id, enrolment_id)

    def remove_enrolment(self, user_id: str, enrolment_id: int) -> None:
        if not self._students.delete_enrolment(user_id, enrolment_id):
            raise NotFoundError("Enrolment not found")

    # ── Assessment assembly ───────────────────────────────────────────────
    def assessment_rows(self, user_id: str, enrolment: dict[str, Any]) -> list[dict[str, Any]]:
        """Profile assessments (verified ECP) or the student's custom items, with scores."""
        course = enrolment["course_offerings"]["courses"]
        profile = self._catalogue.get_verified_profile(course["id"])
        return self._rows_for_profile(user_id, enrolment, profile)

    def _profile_context(
        self, user_id: str, enrolment: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[int, float] | None]:
        """Assessment rows and grade cut-offs from a SINGLE profile read.

        assessment_rows() and grade_cutoffs() each fetch the verified profile
        independently; callers needing both would otherwise pay for the same
        3-query profile read twice on every request.
        """
        course = enrolment["course_offerings"]["courses"]
        profile = self._catalogue.get_verified_profile(course["id"])
        rows = self._rows_for_profile(user_id, enrolment, profile)
        return rows, (profile["grade_cutoffs"] if profile else None)

    def _rows_for_profile(
        self, user_id: str, enrolment: dict[str, Any], profile: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        grades = self._students.list_grades(user_id, enrolment["id"])
        score_by_assessment = {
            g["assessment_id"]: g["score"] for g in grades if g["assessment_id"] is not None
        }
        score_by_custom = {
            g["custom_assessment_id"]: g["score"]
            for g in grades
            if g["custom_assessment_id"] is not None
        }

        rows: list[dict[str, Any]] = []
        if profile and profile["assessments"]:
            for item in profile["assessments"]:
                rows.append(
                    {**item, "source": "profile", "score": score_by_assessment.get(item["id"])}
                )
        else:
            for item in self._students.list_custom_assessments(user_id, enrolment["id"]):
                rows.append(
                    {**item, "source": "custom", "score": score_by_custom.get(item["id"])}
                )
        return rows

    def grade_cutoffs(self, enrolment: dict[str, Any]) -> dict[int, float] | None:
        course = enrolment["course_offerings"]["courses"]
        profile = self._catalogue.get_verified_profile(course["id"])
        return profile["grade_cutoffs"] if profile else None

    @staticmethod
    def to_engine_items(rows: list[dict[str, Any]]) -> tuple[AssessmentItem, ...]:
        return tuple(
            AssessmentItem(
                name=row["name"],
                weight=float(row["weight"]),
                max_mark=float(row["max_mark"]),
                score=None if row.get("score") is None else float(row["score"]),
                hurdle_min_percent=(
                    None
                    if row.get("hurdle_min_percent") is None
                    else float(row["hurdle_min_percent"])
                ),
                hurdle_description=row.get("hurdle_description"),
            )
            for row in rows
        )

    # ── Calculations ──────────────────────────────────────────────────────
    def standing(self, user_id: str, enrolment_id: int) -> dict[str, Any]:
        enrolment = self._require_enrolment(user_id, enrolment_id)
        rows, cutoffs = self._profile_context(user_id, enrolment)
        if not rows:
            raise ValidationFailedError(
                "This course has no assessment items yet — add them first"
            )
        try:
            standing = compute_standing(self.to_engine_items(rows), cutoffs)
        except InvalidAssessmentStructureError as exc:
            raise ValidationFailedError(str(exc)) from exc
        return {
            "enrolment_id": enrolment_id,
            "secured_percent": standing.secured_percent,
            "remaining_weight": standing.remaining_weight,
            "best_case_percent": standing.best_case_percent,
            "worst_case_percent": standing.worst_case_percent,
            "projected_percent": standing.projected_percent,
            "projected_grade": standing.projected_grade,
            # Without these the UI shows a projected grade the weighted total
            # doesn't explain, and no reason for it.
            "hurdle_blocked": standing.hurdle_blocked,
            "hurdle_warnings": list(standing.hurdle_warnings),
            "items": rows,
        }

    def required_marks(
        self,
        user_id: str,
        enrolment_id: int,
        target_grade: int,
        what_if_scores: dict[str, float],
    ) -> RequiredMarksResult:
        enrolment = self._require_enrolment(user_id, enrolment_id)
        rows, cutoffs = self._profile_context(user_id, enrolment)
        if not rows:
            raise ValidationFailedError(
                "This course has no assessment items yet — add them first"
            )
        try:
            return compute_required_marks(
                self.to_engine_items(rows),
                target_grade=target_grade,
                grade_cutoffs=cutoffs,
                what_if_scores=what_if_scores or None,
            )
        except InvalidAssessmentStructureError as exc:
            raise ValidationFailedError(str(exc)) from exc

    def gpa(self, user_id: str) -> dict[str, Any]:
        enrolments = self._students.list_enrolments(user_id)
        completed = [
            e for e in enrolments if e["status"] == "completed" and e["final_grade"] is not None
        ]
        entries = [
            GpaEntry(
                grade=e["final_grade"],
                units=float(e["course_offerings"]["courses"]["units"]),
            )
            for e in completed
        ]
        try:
            value = compute_gpa(entries)
        except InvalidAssessmentStructureError as exc:
            raise ValidationFailedError(str(exc)) from exc
        return {
            "gpa": value,
            "completed_courses": len(entries),
            "total_units": sum(entry.units for entry in entries),
        }

    def history(self, user_id: str) -> list[dict[str, Any]]:
        """Completed + in-progress record (FR-3.4.1)."""
        result = []
        for e in self._students.list_enrolments(user_id):
            offering = e["course_offerings"]
            course = offering["courses"]
            result.append(
                {
                    "enrolment_id": e["id"],
                    "course_code": course["code"],
                    "course_title": course["title"],
                    "units": course["units"],
                    "year": offering["year"],
                    "semester": offering["semester"],
                    "status": e["status"],
                    "final_grade": e["final_grade"],
                    "final_percent": e["final_percent"],
                    "is_transfer": e["is_transfer"],
                }
            )
        return result

    def _require_enrolment(self, user_id: str, enrolment_id: int) -> dict[str, Any]:
        enrolment = self._students.get_enrolment(user_id, enrolment_id)
        if enrolment is None:
            raise NotFoundError("Enrolment not found")
        return enrolment
