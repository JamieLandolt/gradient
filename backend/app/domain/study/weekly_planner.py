"""Deterministic weekly study-block planner (FR-3.8.x).

Given a student's remaining (ungraded) assessment items across every
in-progress course — each with a weight, due date, and personal target mark —
and their own weekly 'study' time slots, allocates study time to items and
places it onto those slots for one specific week.

No AI provider is involved: every figure here is arithmetic over facts the
student already gave the app (weights, due dates, their own targets and their
own time-block template) — the same grounding principle as the degree
scheduler in app.domain.planning.scheduler.
"""

from dataclasses import dataclass
from datetime import date

DEFAULT_TARGET_PERCENT = 65.0
# Urgency ramps from 4x (due this week) down to 1x (due 3+ weeks out).
_LOOKAHEAD_WEEKS_FOR_FULL_URGENCY = 3.0
_MAX_URGENCY = 4.0


@dataclass(frozen=True)
class WeeklySlot:
    day_of_week: int  # 0=Monday..6=Sunday
    start_hour: int  # 0-23


@dataclass(frozen=True)
class RemainingAssessment:
    enrolment_id: int
    course_code: str
    name: str
    weight: float
    assessment_id: int | None = None
    custom_assessment_id: int | None = None
    due_date: str | None = None  # ISO date, or None if not specified
    target_percent: float | None = None


@dataclass(frozen=True)
class StudyBlock:
    slot: WeeklySlot
    enrolment_id: int
    focus: str
    assessment_id: int | None = None
    custom_assessment_id: int | None = None


@dataclass(frozen=True)
class WeeklyPlanDiagnostic:
    severity: str  # 'info' | 'warning'
    message: str


@dataclass(frozen=True)
class WeeklyPlanResult:
    blocks: tuple[StudyBlock, ...]
    diagnostics: tuple[WeeklyPlanDiagnostic, ...]


def _urgency_multiplier(due_date: str | None, week_start: date) -> float:
    if not due_date:
        return 1.0
    due = date.fromisoformat(due_date)
    weeks_until_due = max(0, (due - week_start).days) / 7
    if weeks_until_due >= _LOOKAHEAD_WEEKS_FOR_FULL_URGENCY:
        return 1.0
    return _MAX_URGENCY - (
        (_MAX_URGENCY - 1.0) * weeks_until_due / _LOOKAHEAD_WEEKS_FOR_FULL_URGENCY
    )


def _priority(item: RemainingAssessment, week_start: date) -> float:
    target = item.target_percent if item.target_percent is not None else DEFAULT_TARGET_PERCENT
    effort = item.weight * (target / 100)
    return effort * _urgency_multiplier(item.due_date, week_start)


def _focus_text(item: RemainingAssessment) -> str:
    target = item.target_percent if item.target_percent is not None else DEFAULT_TARGET_PERCENT
    due_part = f" · due {item.due_date}" if item.due_date else ""
    return (
        f"{item.course_code} — {item.name} "
        f"({item.weight:.0f}% · aiming for {target:.0f}%{due_part})"
    )


def _allocate_hours(priorities: list[float], total_slots: int) -> list[int]:
    """Largest-remainder apportionment: whole hours proportional to priority,
    summing to exactly `total_slots` (never over-allocates)."""
    total_priority = sum(priorities)
    if total_priority <= 0 or total_slots <= 0:
        return [0] * len(priorities)
    raw = [p / total_priority * total_slots for p in priorities]
    base = [int(r) for r in raw]
    remaining = total_slots - sum(base)
    by_remainder = sorted(range(len(raw)), key=lambda i: raw[i] - base[i], reverse=True)
    for i in by_remainder[:remaining]:
        base[i] += 1
    return base


def build_weekly_plan(
    items: list[RemainingAssessment],
    study_slots: list[WeeklySlot],
    week_start: date,
) -> WeeklyPlanResult:
    """Allocate this week's `study_slots` across `items` by priority (weight ×
    target mark × due-date urgency), then place each item's allotted hours
    onto the earliest available slots in (day, hour) order.
    """
    if not items or not study_slots:
        return WeeklyPlanResult(blocks=(), diagnostics=())

    scored = sorted(
        ((_priority(item, week_start), item) for item in items),
        key=lambda pair: pair[0],
        reverse=True,
    )
    allocations = _allocate_hours([priority for priority, _ in scored], len(study_slots))
    available = sorted(study_slots, key=lambda s: (s.day_of_week, s.start_hour))

    blocks: list[StudyBlock] = []
    diagnostics: list[WeeklyPlanDiagnostic] = []
    cursor = 0
    for (_priority_value, item), hours in zip(scored, allocations, strict=True):
        if hours == 0:
            diagnostics.append(
                WeeklyPlanDiagnostic(
                    severity="info",
                    message=(
                        f"No study time could be allocated to {item.name} "
                        f"({item.course_code}) this week — add more study slots to cover it."
                    ),
                )
            )
            continue
        focus = _focus_text(item)
        placed = 0
        while placed < hours and cursor < len(available):
            blocks.append(
                StudyBlock(
                    slot=available[cursor],
                    enrolment_id=item.enrolment_id,
                    assessment_id=item.assessment_id,
                    custom_assessment_id=item.custom_assessment_id,
                    focus=focus,
                )
            )
            cursor += 1
            placed += 1
        if placed < hours:
            diagnostics.append(
                WeeklyPlanDiagnostic(
                    severity="info",
                    message=(
                        f"Only {placed} of {hours} planned hours for {item.name} "
                        f"({item.course_code}) fit this week's study slots."
                    ),
                )
            )

    return WeeklyPlanResult(blocks=tuple(blocks), diagnostics=tuple(diagnostics))
