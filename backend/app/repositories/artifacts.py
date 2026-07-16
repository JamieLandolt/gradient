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
_WEEKLY_BLOCK_SELECT = (
    "day_of_week, start_hour, enrolment_id, assessment_id, custom_assessment_id, "
    "focus, sort_order, enrolments(course_offerings(courses(code, title)))"
)
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

    # ── Weekly study plans (FR-3.8.x) ──────────────────────────────────────
    def save_weekly_study_plan(
        self, user_id: str, week_start: str, blocks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Regenerating the same week replaces it outright (delete + fresh
        insert, not upsert) so `generated_at` always reflects this run."""
        existing = (
            self._db.table("weekly_study_plans")
            .select("id")
            .eq("user_id", user_id)
            .eq("week_start", week_start)
            .execute()
            .data
        )
        if existing:
            self._db.table("weekly_study_plans").delete().eq("id", existing[0]["id"]).execute()
        record = (
            self._db.table("weekly_study_plans")
            .insert({"user_id": user_id, "week_start": week_start})
            .execute()
            .data[0]
        )
        block_rows = [
            {
                "weekly_study_plan_id": record["id"],
                "day_of_week": block["day_of_week"],
                "start_hour": block["start_hour"],
                "enrolment_id": block.get("enrolment_id"),
                "assessment_id": block.get("assessment_id"),
                "custom_assessment_id": block.get("custom_assessment_id"),
                "focus": block["focus"],
                "sort_order": order,
            }
            for order, block in enumerate(blocks)
        ]
        if block_rows:
            self._db.table("weekly_study_blocks").insert(block_rows).execute()
        return record

    def list_weekly_study_plans(self, user_id: str) -> list[dict[str, Any]]:
        return (
            self._db.table("weekly_study_plans")
            .select("id, week_start, generated_at")
            .eq("user_id", user_id)
            .order("week_start", desc=True)
            .execute()
            .data
        )

    def get_weekly_study_plan(self, user_id: str, plan_id: int) -> dict[str, Any] | None:
        rows = (
            self._db.table("weekly_study_plans")
            .select(
                f"id, week_start, generated_at, weekly_study_blocks({_WEEKLY_BLOCK_SELECT})"
            )
            .eq("user_id", user_id)
            .eq("id", plan_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def delete_weekly_study_plan(self, user_id: str, plan_id: int) -> bool:
        rows = (
            self._db.table("weekly_study_plans")
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
