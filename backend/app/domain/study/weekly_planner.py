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
from datetime import date, timedelta

DEFAULT_TARGET_PERCENT = 65.0
# Urgency ramps from 4x (due this week) down to 1x (due 3+ weeks out).
_LOOKAHEAD_WEEKS_FOR_FULL_URGENCY = 3.0
_MAX_URGENCY = 4.0
# An item whose due date has already passed is still plannable (it stays in the
# list until a mark is recorded, and a tutor may not have marked it yet), but it
# is not urgent — studying for it can't change anything. Clamping a past date to
# "due now" gave a quiz that closed months ago the full 4x multiplier and twice
# the study time of an upcoming final.
_OVERDUE_URGENCY = 0.5

# Sorts after any real ISO date, so undated items are placed last.
_NO_DUE_DATE_LAST = "9999-12-31"


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
    days_until_due = (due - week_start).days
    if days_until_due < 0:
        return _OVERDUE_URGENCY
    weeks_until_due = days_until_due / 7
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

    # Priority decides HOW MANY hours each item gets; the deadline decides WHICH
    # slots it gets. Handing out slots in priority order instead put a heavy
    # assignment due Sunday ahead of a quiz due Monday — and scheduled all of the
    # quiz's study time after it had already been submitted. Items with no due
    # date sort last; ties break on code/name so the plan stays deterministic.
    by_deadline = sorted(
        zip(scored, allocations, strict=True),
        key=lambda pair: (
            pair[0][1].due_date or _NO_DUE_DATE_LAST,
            pair[0][1].course_code,
            pair[0][1].name,
        ),
    )

    slot_dates = [week_start + timedelta(days=slot.day_of_week) for slot in available]
    claimed_by: list[RemainingAssessment | None] = [None] * len(available)

    diagnostics: list[WeeklyPlanDiagnostic] = []
    wanted: dict[int, int] = {}  # index into by_deadline -> hours still unplaced

    # Pass 1: each item takes the earliest free slots that fall ON OR BEFORE its
    # due date. An item can be allotted more hours than there are slots left
    # before its deadline; those hours are not silently spent studying for
    # something already submitted — they go back to the pool in pass 2.
    for index, ((_priority_value, item), hours) in enumerate(by_deadline):
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
        due = date.fromisoformat(item.due_date) if item.due_date else None
        placed = _claim_slots(claimed_by, slot_dates, item, hours, due)
        if placed < hours:
            wanted[index] = hours - placed
            if due is not None:
                diagnostics.append(
                    WeeklyPlanDiagnostic(
                        severity="info",
                        message=(
                            f"Only {placed} of {hours} planned hours for {item.name} "
                            f"({item.course_code}) fit before it is due on {item.due_date}."
                        ),
                    )
                )

    # Pass 2: an item that couldn't fit all its hours before its own deadline may
    # still have earlier free slots it can use.
    for index, hours_left in wanted.items():
        (_priority_value, item) = by_deadline[index][0]
        due = date.fromisoformat(item.due_date) if item.due_date else None
        _claim_slots(claimed_by, slot_dates, item, hours_left, due)

    # Pass 3: hours freed by a deadline (pass 1) would otherwise leave the slot
    # idle. Offer each still-free slot to the highest-priority item that can
    # genuinely use it — one whose deadline hasn't passed by then. A slot with no
    # such taker stays free: better than booking study for submitted work.
    for i, slot_date in enumerate(slot_dates):
        if claimed_by[i] is not None:
            continue
        for _priority_value, item in scored:
            due = date.fromisoformat(item.due_date) if item.due_date else None
            if due is None or slot_date <= due:
                claimed_by[i] = item
                break

    blocks = [
        StudyBlock(
            slot=available[i],
            enrolment_id=item.enrolment_id,
            assessment_id=item.assessment_id,
            custom_assessment_id=item.custom_assessment_id,
            focus=_focus_text(item),
        )
        for i, item in enumerate(claimed_by)
        if item is not None
    ]
    return WeeklyPlanResult(blocks=tuple(blocks), diagnostics=tuple(diagnostics))


def _claim_slots(
    claimed_by: list["RemainingAssessment | None"],
    slot_dates: list[date],
    item: "RemainingAssessment",
    hours: int,
    due: date | None,
) -> int:
    """Claim up to `hours` free slots for `item`, never past `due`. Returns how
    many were claimed."""
    placed = 0
    for i, slot_date in enumerate(slot_dates):
        if placed >= hours:
            break
        if claimed_by[i] is not None:
            continue
        if due is not None and slot_date > due:
            break  # slots are chronological, so nothing later can qualify either
        claimed_by[i] = item
        placed += 1
    return placed
