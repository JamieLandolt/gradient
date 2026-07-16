"""Weekly, multi-course study planning (FR-3.8.x) — fully deterministic.

For every in-progress course, pulls the assessments the student hasn't been
graded on yet, matches each to the student's own target mark (if set), and
places study blocks onto the student's own weekly 'study' time slots. No AI
provider is involved — see app.domain.study.weekly_planner for the allocation
engine and app.services.advisory for the (separate) AI-assisted features.
"""

from datetime import date
from typing import Any

from app.core.errors import NotFoundError, ValidationFailedError
from app.domain.study.weekly_planner import RemainingAssessment, WeeklySlot, build_weekly_plan
from app.repositories.artifacts import ArtifactRepository
from app.repositories.students import StudentRepository
from app.services.tracking import TrackingService

_DISCLAIMER = (
    "Weekly study plans are advisory; assessment details come from your course "
    "profile and your own targets and recorded marks."
)


class WeeklyStudyPlanService:
    def __init__(
        self,
        students: StudentRepository,
        tracking: TrackingService,
        artifacts: ArtifactRepository,
    ):
        self._students = students
        self._tracking = tracking
        self._artifacts = artifacts

    # ── Weekly availability template ───────────────────────────────────────
    def get_availability(self, user_id: str) -> list[dict[str, Any]]:
        return self._students.list_study_availability(user_id)

    def set_availability(
        self, user_id: str, slots: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        seen: set[tuple[int, int]] = set()
        for slot in slots:
            key = (slot["day_of_week"], slot["start_hour"])
            if key in seen:
                raise ValidationFailedError(
                    f"Duplicate slot for day {slot['day_of_week']} hour {slot['start_hour']}"
                )
            seen.add(key)
        return self._students.replace_study_availability(user_id, slots)

    # ── Remaining assessments + targets ─────────────────────────────────────
    def remaining_assessments(self, user_id: str) -> list[dict[str, Any]]:
        """Every not-yet-graded assessment item across all in-progress courses,
        with the student's existing target (if any) attached."""
        enrolments = [
            e for e in self._students.list_enrolments(user_id) if e["status"] == "in_progress"
        ]
        targets = self._students.list_assessment_targets(
            user_id, [e["id"] for e in enrolments]
        )
        target_by_key = {
            (t["enrolment_id"], t["assessment_id"], t["custom_assessment_id"]): t["target_percent"]
            for t in targets
        }
        items = []
        for enrolment in enrolments:
            course_code = enrolment["course_offerings"]["courses"]["code"]
            for row in self._tracking.assessment_rows(user_id, enrolment):
                if row.get("score") is not None:
                    continue  # already graded — nothing left to study for
                assessment_id = row["id"] if row["source"] == "profile" else None
                custom_assessment_id = row["id"] if row["source"] == "custom" else None
                items.append(
                    {
                        "enrolment_id": enrolment["id"],
                        "course_code": course_code,
                        "assessment_id": assessment_id,
                        "custom_assessment_id": custom_assessment_id,
                        "name": row["name"],
                        "weight": float(row["weight"]),
                        "due_date": row.get("due_date"),
                        "target_percent": target_by_key.get(
                            (enrolment["id"], assessment_id, custom_assessment_id)
                        ),
                    }
                )
        return items

    def set_targets(self, user_id: str, targets: list[dict[str, Any]]) -> None:
        """Validate and authorise every target before writing any of them.

        `enrolment_id` arrives from the request body, so each one must be proven
        to belong to the caller: the upsert's conflict key is
        (enrolment_id, assessment_id) with no user_id in it, and the
        service-role client bypasses RLS — an unowned id would overwrite another
        student's target row and reassign it. Mirrors the guard on the sibling
        grades route (api/enrolments.py). Checking up front also stops a bad
        target midway through the list from leaving the earlier ones committed.
        """
        for target in targets:
            has_assessment = target.get("assessment_id") is not None
            has_custom = target.get("custom_assessment_id") is not None
            if has_assessment == has_custom:
                raise ValidationFailedError(
                    "Provide exactly one of assessment_id or custom_assessment_id"
                )
        for enrolment_id in dict.fromkeys(target["enrolment_id"] for target in targets):
            if self._students.get_enrolment(user_id, enrolment_id) is None:
                raise NotFoundError(f"Enrolment {enrolment_id} not found")
        for target in targets:
            self._students.upsert_assessment_target(
                user_id,
                enrolment_id=target["enrolment_id"],
                target_percent=target["target_percent"],
                assessment_id=target.get("assessment_id"),
                custom_assessment_id=target.get("custom_assessment_id"),
            )

    # ── Generation ───────────────────────────────────────────────────────────
    def generate(self, user_id: str, week_start: str) -> dict[str, Any]:
        # One pass only: remaining_assessments costs ~3 queries per in-progress
        # course, and generate() used to call it and then have the caller call it
        # again for the same data.
        items = self.remaining_assessments(user_id)
        if not items:
            raise ValidationFailedError(
                "No remaining assessments to plan — add courses/assessments first"
            )
        availability = self._students.list_study_availability(user_id)
        study_slots = [
            WeeklySlot(day_of_week=a["day_of_week"], start_hour=a["start_hour"])
            for a in availability
            if a["slot_type"] == "study"
        ]
        if not study_slots:
            raise ValidationFailedError(
                "No study slots set — mark some hours as 'study' on your weekly "
                "template first"
            )
        engine_items = [
            RemainingAssessment(
                enrolment_id=i["enrolment_id"],
                course_code=i["course_code"],
                name=i["name"],
                weight=i["weight"],
                assessment_id=i["assessment_id"],
                custom_assessment_id=i["custom_assessment_id"],
                due_date=i["due_date"],
                target_percent=i["target_percent"],
            )
            for i in items
        ]
        result = build_weekly_plan(engine_items, study_slots, date.fromisoformat(week_start))
        record = self._artifacts.save_weekly_study_plan(
            user_id,
            week_start,
            [
                {
                    "day_of_week": b.slot.day_of_week,
                    "start_hour": b.slot.start_hour,
                    "enrolment_id": b.enrolment_id,
                    "assessment_id": b.assessment_id,
                    "custom_assessment_id": b.custom_assessment_id,
                    "focus": b.focus,
                }
                for b in result.blocks
            ],
        )
        course_code_by_enrolment = {i["enrolment_id"]: i["course_code"] for i in items}
        return {
            "id": record["id"],
            "week_start": record["week_start"],
            "generated_at": record.get("generated_at"),
            "blocks": [
                {
                    "day_of_week": b.slot.day_of_week,
                    "start_hour": b.slot.start_hour,
                    "focus": b.focus,
                    "course_code": course_code_by_enrolment.get(b.enrolment_id),
                }
                for b in result.blocks
            ],
            "diagnostics": [
                {"severity": d.severity, "message": d.message} for d in result.diagnostics
            ],
            "disclaimer": _DISCLAIMER,
        }

    # ── Saved plans ──────────────────────────────────────────────────────────
    def list_plans(self, user_id: str) -> list[dict[str, Any]]:
        return self._artifacts.list_weekly_study_plans(user_id)

    def get_plan(self, user_id: str, plan_id: int) -> dict[str, Any]:
        row = self._artifacts.get_weekly_study_plan(user_id, plan_id)
        if row is None:
            raise NotFoundError("Weekly study plan not found")
        blocks = sorted(
            row.get("weekly_study_blocks") or [],
            key=lambda b: (b["day_of_week"], b["start_hour"]),
        )
        return {
            "id": row["id"],
            "week_start": row["week_start"],
            "generated_at": row.get("generated_at"),
            "blocks": [
                {
                    "day_of_week": b["day_of_week"],
                    "start_hour": b["start_hour"],
                    "focus": b["focus"],
                    "course_code": _block_course_code(b),
                }
                for b in blocks
            ],
            "diagnostics": [],  # not persisted; only surfaced at generation time
            "disclaimer": _DISCLAIMER,
        }

    def delete_plan(self, user_id: str, plan_id: int) -> None:
        if not self._artifacts.delete_weekly_study_plan(user_id, plan_id):
            raise NotFoundError("Weekly study plan not found")


def _block_course_code(row: dict[str, Any]) -> str | None:
    enrolment = row.get("enrolments") or {}
    offering = enrolment.get("course_offerings") or {}
    course = offering.get("courses") or {}
    return course.get("code")
