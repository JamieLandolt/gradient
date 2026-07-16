"""Student-owned data access.

CRITICAL: the backend uses the service-role key, which bypasses RLS. Every
method here filters by user_id from the verified JWT (FR-3.1.3).
"""

from typing import Any

from supabase import Client

ENROLMENT_SELECT = (
    "id, status, final_grade, final_percent, is_transfer, profile_version_id, "
    "course_offerings(id, year, semester, courses(id, code, title, units))"
)


class StudentRepository:
    def __init__(self, db: Client):
        self._db = db

    # ── Enrolments ────────────────────────────────────────────────────────
    def list_enrolments(self, user_id: str) -> list[dict[str, Any]]:
        return (
            self._db.table("enrolments")
            .select(ENROLMENT_SELECT)
            .eq("user_id", user_id)
            .order("id")
            .execute()
            .data
        )

    def get_enrolment(self, user_id: str, enrolment_id: int) -> dict[str, Any] | None:
        rows = (
            self._db.table("enrolments")
            .select(ENROLMENT_SELECT)
            .eq("user_id", user_id)
            .eq("id", enrolment_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def create_enrolment(self, user_id: str, values: dict[str, Any]) -> dict[str, Any]:
        row = {**values, "user_id": user_id}
        return self._db.table("enrolments").insert(row).execute().data[0]

    def update_enrolment(
        self, user_id: str, enrolment_id: int, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        rows = (
            self._db.table("enrolments")
            .update(values)
            .eq("user_id", user_id)
            .eq("id", enrolment_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def delete_enrolment(self, user_id: str, enrolment_id: int) -> bool:
        rows = (
            self._db.table("enrolments")
            .delete()
            .eq("user_id", user_id)
            .eq("id", enrolment_id)
            .execute()
            .data
        )
        return bool(rows)

    def completed_course_codes(self, user_id: str) -> frozenset[str]:
        rows = (
            self._db.table("enrolments")
            .select("status, course_offerings(courses(code))")
            .eq("user_id", user_id)
            .eq("status", "completed")
            .execute()
            .data
        )
        return frozenset(
            row["course_offerings"]["courses"]["code"]
            for row in rows
            if row.get("course_offerings")
        )

    # ── Custom assessments (FR-3.2.2) ─────────────────────────────────────
    def list_custom_assessments(self, user_id: str, enrolment_id: int) -> list[dict[str, Any]]:
        return (
            self._db.table("custom_assessments")
            .select(
                "id, name, weight, max_mark, due_date, hurdle_min_percent, "
                "hurdle_description, sort_order"
            )
            .eq("user_id", user_id)
            .eq("enrolment_id", enrolment_id)
            .order("sort_order")
            .execute()
            .data
        )

    def create_custom_assessment(
        self, user_id: str, enrolment_id: int, values: dict[str, Any]
    ) -> dict[str, Any]:
        row = {**values, "user_id": user_id, "enrolment_id": enrolment_id}
        return self._db.table("custom_assessments").insert(row).execute().data[0]

    def update_custom_assessment(
        self, user_id: str, assessment_id: int, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        rows = (
            self._db.table("custom_assessments")
            .update(values)
            .eq("user_id", user_id)
            .eq("id", assessment_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def delete_custom_assessment(self, user_id: str, assessment_id: int) -> bool:
        rows = (
            self._db.table("custom_assessments")
            .delete()
            .eq("user_id", user_id)
            .eq("id", assessment_id)
            .execute()
            .data
        )
        return bool(rows)

    # ── Grades (FR-3.2.3) ─────────────────────────────────────────────────
    def list_grades(self, user_id: str, enrolment_id: int) -> list[dict[str, Any]]:
        return (
            self._db.table("grades")
            .select("id, assessment_id, custom_assessment_id, score")
            .eq("user_id", user_id)
            .eq("enrolment_id", enrolment_id)
            .execute()
            .data
        )

    def upsert_grade(
        self,
        user_id: str,
        enrolment_id: int,
        score: float,
        assessment_id: int | None = None,
        custom_assessment_id: int | None = None,
    ) -> dict[str, Any]:
        conflict = "enrolment_id,assessment_id" if assessment_id else (
            "enrolment_id,custom_assessment_id"
        )
        row = {
            "user_id": user_id,
            "enrolment_id": enrolment_id,
            "assessment_id": assessment_id,
            "custom_assessment_id": custom_assessment_id,
            "score": score,
        }
        return (
            self._db.table("grades").upsert(row, on_conflict=conflict).execute().data[0]
        )

    def delete_grade(self, user_id: str, grade_id: int) -> bool:
        rows = (
            self._db.table("grades")
            .delete()
            .eq("user_id", user_id)
            .eq("id", grade_id)
            .execute()
            .data
        )
        return bool(rows)

    # ── Assessment targets (FR-3.8.x): a target mark per item, distinct from
    # `grades` (an already-received mark) — can exist before the item is due.
    def list_assessment_targets(
        self, user_id: str, enrolment_ids: list[int]
    ) -> list[dict[str, Any]]:
        if not enrolment_ids:
            return []
        return (
            self._db.table("assessment_targets")
            .select("id, enrolment_id, assessment_id, custom_assessment_id, target_percent")
            .eq("user_id", user_id)
            .in_("enrolment_id", enrolment_ids)
            .execute()
            .data
        )

    def upsert_assessment_target(
        self,
        user_id: str,
        enrolment_id: int,
        target_percent: float,
        assessment_id: int | None = None,
        custom_assessment_id: int | None = None,
    ) -> dict[str, Any]:
        conflict = "enrolment_id,assessment_id" if assessment_id else (
            "enrolment_id,custom_assessment_id"
        )
        row = {
            "user_id": user_id,
            "enrolment_id": enrolment_id,
            "assessment_id": assessment_id,
            "custom_assessment_id": custom_assessment_id,
            "target_percent": target_percent,
        }
        return (
            self._db.table("assessment_targets")
            .upsert(row, on_conflict=conflict)
            .execute()
            .data[0]
        )

    # ── Weekly study availability (FR-3.8.x): a reusable weekly time-block
    # template (blocked vs study hours), edited as a whole.
    def list_study_availability(self, user_id: str) -> list[dict[str, Any]]:
        return (
            self._db.table("study_availability")
            .select("day_of_week, start_hour, slot_type")
            .eq("user_id", user_id)
            .execute()
            .data
        )

    def replace_study_availability(
        self, user_id: str, slots: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        self._db.table("study_availability").delete().eq("user_id", user_id).execute()
        if not slots:
            return []
        rows = [{**slot, "user_id": user_id} for slot in slots]
        return self._db.table("study_availability").insert(rows).execute().data

    # ── Programs (FR-3.6.3) ───────────────────────────────────────────────
    def get_user_programs(self, user_id: str) -> list[dict[str, Any]]:
        return (
            self._db.table("user_programs")
            .select("position, programs(id, code, title, total_units)")
            .eq("user_id", user_id)
            .order("position")
            .execute()
            .data
        )

    def set_user_programs(self, user_id: str, program_ids: list[int]) -> None:
        self._db.table("user_programs").delete().eq("user_id", user_id).execute()
        if program_ids:
            rows = [
                {"user_id": user_id, "program_id": program_id, "position": index + 1}
                for index, program_id in enumerate(program_ids[:2])
            ]
            self._db.table("user_programs").insert(rows).execute()

    # ── Profile / account (FR-3.1.4) ──────────────────────────────────────
    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        rows = (
            self._db.table("profiles")
            .select("id, display_name, role, created_at")
            .eq("id", user_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def update_profile(self, user_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        rows = (
            self._db.table("profiles")
            .update(values)
            .eq("id", user_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def delete_account(self, user_id: str) -> None:
        """Delete the auth user; profile and all owned rows cascade (FR-3.1.4)."""
        self._db.auth.admin.delete_user(user_id)
