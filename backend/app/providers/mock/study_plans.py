"""Deterministic mock study-plan generation (FR-3.8.x).

Spreads study sessions across the days before each remaining assessment's due
date. Session counts scale with item weight; all cited figures (weights, due
dates, required marks) come from the deterministic engine via the service.
"""

from datetime import date, timedelta
from typing import Any

MIN_SESSIONS_PER_ITEM = 2
WEIGHT_PER_EXTRA_SESSION = 15.0
BASE_SESSION_MINUTES = 60
HIGH_STAKES_SESSION_MINUTES = 90
HIGH_STAKES_WEIGHT = 40.0
DEFAULT_LEAD_DAYS = 14


class MockStudyPlanProvider:
    def generate(
        self,
        course_code: str,
        items: list[dict[str, Any]],
        target_grade: int,
        required_average_percent: float | None,
        start_date: str,
    ) -> list[dict[str, Any]]:
        start = date.fromisoformat(start_date)
        sessions: list[dict[str, Any]] = []

        remaining = [item for item in items if item.get("score") is None]
        for item in remaining:
            due = (
                date.fromisoformat(item["due_date"])
                if item.get("due_date")
                else start + timedelta(days=DEFAULT_LEAD_DAYS)
            )
            if due <= start:
                continue
            weight = float(item["weight"])
            session_count = MIN_SESSIONS_PER_ITEM + int(weight // WEIGHT_PER_EXTRA_SESSION)
            window_days = max((due - start).days, 1)
            step = max(window_days // (session_count + 1), 1)
            duration = (
                HIGH_STAKES_SESSION_MINUTES
                if weight >= HIGH_STAKES_WEIGHT
                else BASE_SESSION_MINUTES
            )
            target_note = (
                f"aiming for an average of {required_average_percent:.0f}% "
                f"to reach a grade {target_grade}"
                if required_average_percent is not None
                else f"working toward a grade {target_grade}"
            )
            for index in range(session_count):
                session_date = min(start + timedelta(days=step * (index + 1)), due)
                sessions.append(
                    {
                        "session_date": session_date.isoformat(),
                        "duration_minutes": duration,
                        "focus": (
                            f"{course_code} — {item['name']} "
                            f"(session {index + 1} of {session_count}, "
                            f"worth {weight:g}%, {target_note})"
                        ),
                        "assessment_name": item["name"],
                    }
                )

        sessions.sort(key=lambda s: (s["session_date"], s["assessment_name"]))
        for order, session in enumerate(sessions):
            session["sort_order"] = order
        return sessions
