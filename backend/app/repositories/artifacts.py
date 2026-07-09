"""Persistence for AI/plan artefacts (FR-3.6.2, FR-3.7.x, FR-3.8.x).

Recommendations, study plans, and saved degree plans are student-owned. As with
the other student repositories, the backend uses the service-role key (which
bypasses RLS), so EVERY method filters by the authenticated user's id. Parent
rows are inserted first, then their children keyed by the returned parent id —
the same pattern as IngestionRepository.create_draft_version.
"""

from typing import Any

from supabase import Client

_RECOMMENDATION_ITEM_SELECT = (
    "course_id, rank, reason, prereq_status, courses(code, title)"
)
_STUDY_SESSION_SELECT = (
    "assessment_id, custom_assessment_id, session_date, duration_minutes, focus, sort_order"
)
_ENROLMENT_COURSE_SELECT = "enrolments(course_offerings(courses(code, title)))"
_DEGREE_ENTRY_SELECT = "semester_index, semester_label, explanation, courses(code, units)"


class ArtifactRepository:
    def __init__(self, db: Client):
        self._db = db

    # ── Recommendations (FR-3.7.x) ────────────────────────────────────────
    def save_recommendation(
        self, user_id: str, provider: str, items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Persist a generated recommendation set and its ranked items."""
        record = (
            self._db.table("recommendations")
            .insert({"user_id": user_id, "provider": provider})
            .execute()
            .data[0]
        )
        item_rows = [
            {
                "recommendation_id": record["id"],
                "course_id": item["course_id"],
                "rank": item["rank"],
                "reason": item["reason"],
                "prereq_status": item["prereq_status"],
            }
            for item in items
        ]
        if item_rows:
            self._db.table("recommendation_items").insert(item_rows).execute()
        return record

    def latest_recommendation(self, user_id: str) -> dict[str, Any] | None:
        rows = (
            self._db.table("recommendations")
            .select(
                f"id, provider, generated_at, recommendation_items({_RECOMMENDATION_ITEM_SELECT})"
            )
            .eq("user_id", user_id)
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def list_recommendations(self, user_id: str) -> list[dict[str, Any]]:
        return (
            self._db.table("recommendations")
            .select("id, provider, generated_at, recommendation_items(course_id)")
            .eq("user_id", user_id)
            .order("generated_at", desc=True)
            .execute()
            .data
        )

    def delete_recommendation(self, user_id: str, recommendation_id: int) -> bool:
        rows = (
            self._db.table("recommendations")
            .delete()
            .eq("user_id", user_id)
            .eq("id", recommendation_id)
            .execute()
            .data
        )
        return bool(rows)

    # ── Study plans (FR-3.8.x) ────────────────────────────────────────────
    def save_study_plan(
        self,
        user_id: str,
        enrolment_id: int | None,
        target_grade: int,
        provider: str,
        sessions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        record = (
            self._db.table("study_plans")
            .insert(
                {
                    "user_id": user_id,
                    "enrolment_id": enrolment_id,
                    "target_grade": target_grade,
                    "provider": provider,
                }
            )
            .execute()
            .data[0]
        )
        session_rows = [
            {
                "study_plan_id": record["id"],
                # Sessions reference free-text assessment names, not ids; store the
                # figure-carrying `focus` text and leave the FKs null (allowed by
                # the num_nonnulls(...) <= 1 check).
                "session_date": session["session_date"],
                "duration_minutes": session["duration_minutes"],
                "focus": session["focus"],
                "sort_order": session.get("sort_order", order),
            }
            for order, session in enumerate(sessions)
        ]
        if session_rows:
            self._db.table("study_sessions").insert(session_rows).execute()
        return record

    def list_study_plans(self, user_id: str) -> list[dict[str, Any]]:
        return (
            self._db.table("study_plans")
            .select(
                "id, enrolment_id, target_grade, provider, generated_at, "
                + _ENROLMENT_COURSE_SELECT
            )
            .eq("user_id", user_id)
            .order("generated_at", desc=True)
            .execute()
            .data
        )

    def get_study_plan(self, user_id: str, plan_id: int) -> dict[str, Any] | None:
        rows = (
            self._db.table("study_plans")
            .select(
                f"id, enrolment_id, target_grade, provider, generated_at, "
                f"{_ENROLMENT_COURSE_SELECT}, study_sessions({_STUDY_SESSION_SELECT})"
            )
            .eq("user_id", user_id)
            .eq("id", plan_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def delete_study_plan(self, user_id: str, plan_id: int) -> bool:
        rows = (
            self._db.table("study_plans")
            .delete()
            .eq("user_id", user_id)
            .eq("id", plan_id)
            .execute()
            .data
        )
        return bool(rows)

    # ── Degree plans (FR-3.6.2) ───────────────────────────────────────────
    def save_degree_plan(
        self,
        user_id: str,
        name: str,
        feasible: bool,
        entries: list[dict[str, Any]],
        diagnostics: list[dict[str, Any]],
    ) -> dict[str, Any]:
        record = (
            self._db.table("degree_plans")
            .insert({"user_id": user_id, "name": name, "feasible": feasible})
            .execute()
            .data[0]
        )
        entry_rows = [
            {
                "degree_plan_id": record["id"],
                "semester_index": entry["semester_index"],
                "semester_label": entry["semester_label"],
                "course_id": entry["course_id"],
                "explanation": entry.get("explanation", ""),
            }
            for entry in entries
        ]
        if entry_rows:
            self._db.table("degree_plan_entries").insert(entry_rows).execute()
        diagnostic_rows = [
            {
                "degree_plan_id": record["id"],
                "severity": diagnostic["severity"],
                "message": diagnostic["message"],
            }
            for diagnostic in diagnostics
        ]
        if diagnostic_rows:
            self._db.table("degree_plan_diagnostics").insert(diagnostic_rows).execute()
        return record

    def list_degree_plans(self, user_id: str) -> list[dict[str, Any]]:
        return (
            self._db.table("degree_plans")
            .select("id, name, feasible, generated_at")
            .eq("user_id", user_id)
            .order("generated_at", desc=True)
            .execute()
            .data
        )

    def get_degree_plan(self, user_id: str, plan_id: int) -> dict[str, Any] | None:
        rows = (
            self._db.table("degree_plans")
            .select(
                f"id, name, feasible, generated_at, "
                f"degree_plan_entries({_DEGREE_ENTRY_SELECT}), "
                f"degree_plan_diagnostics(severity, message)"
            )
            .eq("user_id", user_id)
            .eq("id", plan_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def delete_degree_plan(self, user_id: str, plan_id: int) -> bool:
        rows = (
            self._db.table("degree_plans")
            .delete()
            .eq("user_id", user_id)
            .eq("id", plan_id)
            .execute()
            .data
        )
        return bool(rows)
