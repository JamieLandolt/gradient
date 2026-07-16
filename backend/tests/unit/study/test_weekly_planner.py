"""Deterministic weekly study-block allocation (FR-3.8.x)."""

from datetime import date

from app.domain.study.weekly_planner import (
    RemainingAssessment,
    WeeklySlot,
    build_weekly_plan,
)

WEEK_START = date(2026, 8, 3)  # a Monday


def item(
    enrolment_id=1, course_code="COMP3506", name="Assignment 1", weight=30.0,
    due_date=None, target_percent=None,
) -> RemainingAssessment:
    return RemainingAssessment(
        enrolment_id=enrolment_id, course_code=course_code, name=name, weight=weight,
        due_date=due_date, target_percent=target_percent,
    )


def slots(n: int) -> list[WeeklySlot]:
    return [WeeklySlot(day_of_week=d, start_hour=h) for d in range(7) for h in range(24)][:n]


def test_no_items_or_no_slots_returns_empty_without_error():
    assert build_weekly_plan([], slots(10), WEEK_START).blocks == ()
    assert build_weekly_plan([item()], [], WEEK_START).blocks == ()


def test_allocates_more_hours_to_higher_weight_items():
    items = [item(name="Big", weight=60.0), item(name="Small", weight=20.0)]
    result = build_weekly_plan(items, slots(8), WEEK_START)

    big_hours = sum(1 for b in result.blocks if "Big" in b.focus)
    small_hours = sum(1 for b in result.blocks if "Small" in b.focus)
    assert big_hours > small_hours
    assert big_hours + small_hours == 8  # every available slot used


def test_due_sooner_gets_more_hours_than_identical_item_due_later():
    soon = item(name="Soon", weight=30.0, due_date=WEEK_START.isoformat())
    later = item(
        name="Later", weight=30.0,
        due_date=(WEEK_START.replace(month=WEEK_START.month + 2)).isoformat(),
    )
    result = build_weekly_plan([soon, later], slots(10), WEEK_START)

    soon_hours = sum(1 for b in result.blocks if "Soon" in b.focus)
    later_hours = sum(1 for b in result.blocks if "Later" in b.focus)
    assert soon_hours > later_hours


def test_missing_target_defaults_and_is_shown_in_focus_text():
    result = build_weekly_plan([item(target_percent=None)], slots(4), WEEK_START)
    assert result.blocks
    assert "aiming for 65%" in result.blocks[0].focus


def test_explicit_target_is_reflected_in_focus_text():
    result = build_weekly_plan([item(target_percent=90.0)], slots(4), WEEK_START)
    assert "aiming for 90%" in result.blocks[0].focus


def test_never_allocates_more_hours_than_available_slots():
    items = [item(name=f"A{i}", weight=float(10 + i)) for i in range(5)]
    result = build_weekly_plan(items, slots(6), WEEK_START)
    assert len(result.blocks) == 6


def test_shortfall_diagnostic_when_an_item_gets_zero_hours():
    # One huge item dominates a tiny slot pool; a low-weight item can round to 0.
    items = [item(name="Dominant", weight=95.0), item(name="Tiny", weight=1.0)]
    result = build_weekly_plan(items, slots(2), WEEK_START)

    tiny_diagnostics = [d for d in result.diagnostics if "Tiny" in d.message]
    assert tiny_diagnostics
    assert not any("Tiny" in b.focus for b in result.blocks)


def test_blocks_fill_slots_in_day_and_hour_order():
    out_of_order = [WeeklySlot(3, 10), WeeklySlot(0, 9), WeeklySlot(0, 8)]
    result = build_weekly_plan([item(weight=100.0)], out_of_order, WEEK_START)

    placed = [(b.slot.day_of_week, b.slot.start_hour) for b in result.blocks]
    assert placed == sorted(placed)


def test_the_item_due_soonest_studies_first():
    """Hours are apportioned by priority, but slots are handed out by deadline.
    Previously the heavier item due Sunday took every early slot and all of the
    Monday quiz's study time landed after it had been submitted.
    """
    quiz_monday = item(
        course_code="COMP3506", name="Quiz 3", weight=30.0,
        due_date=WEEK_START.isoformat(),  # Mon 2026-08-03
    )
    assignment_sunday = item(
        course_code="COMP3506", name="Assignment 2", weight=60.0,
        due_date=date(2026, 8, 9).isoformat(),  # the following Sunday
    )
    one_per_day = [WeeklySlot(day_of_week=d, start_hour=18) for d in range(7)]

    result = build_weekly_plan([assignment_sunday, quiz_monday], one_per_day, WEEK_START)

    quiz_days = [b.slot.day_of_week for b in result.blocks if "Quiz 3" in b.focus]
    assignment_days = [b.slot.day_of_week for b in result.blocks if "Assignment 2" in b.focus]

    assert quiz_days, "the quiz should get study time"
    # day_of_week 0 = Monday: the quiz starts on, not after, its due day.
    assert min(quiz_days) == 0
    # The quiz is scheduled entirely ahead of the later assignment.
    assert max(quiz_days) < min(assignment_days)
    # …and the heavier assignment still gets more hours, so priority is intact.
    assert len(assignment_days) > len(quiz_days)


def test_items_without_a_due_date_are_placed_after_dated_ones():
    dated = item(course_code="MATH1051", name="Exam", weight=50.0,
                 due_date=date(2026, 8, 5).isoformat())
    undated = item(course_code="MATH1051", name="Portfolio", weight=50.0, due_date=None)

    result = build_weekly_plan([undated, dated], slots(4), WEEK_START)

    dated_slots = [i for i, b in enumerate(result.blocks) if "Exam" in b.focus]
    undated_slots = [i for i, b in enumerate(result.blocks) if "Portfolio" in b.focus]
    assert max(dated_slots) < min(undated_slots)


def test_no_study_is_booked_after_an_items_due_date():
    """Hours are apportioned by priority, which can hand an item more hours than
    it has slots left before its deadline. Those hours must not be spent studying
    for work that is already submitted."""
    quiz = item(name="Quiz 3", weight=30.0, due_date=WEEK_START.isoformat())  # Mon
    assignment = item(name="Assignment 2", weight=60.0, due_date=date(2026, 8, 9).isoformat())
    one_per_day = [WeeklySlot(day_of_week=d, start_hour=18) for d in range(7)]

    result = build_weekly_plan([assignment, quiz], one_per_day, WEEK_START)

    quiz_days = [b.slot.day_of_week for b in result.blocks if "Quiz 3" in b.focus]
    assert quiz_days == [0]  # Monday only — its one slot on or before the deadline
    assert any("fit before it is due" in d.message for d in result.diagnostics)


def test_hours_freed_by_a_deadline_go_to_someone_who_can_use_them():
    # The quiz can only use Monday; the rest of its allotment must not idle.
    quiz = item(name="Quiz 3", weight=30.0, due_date=WEEK_START.isoformat())
    assignment = item(name="Assignment 2", weight=60.0, due_date=date(2026, 8, 9).isoformat())
    one_per_day = [WeeklySlot(day_of_week=d, start_hour=18) for d in range(7)]

    result = build_weekly_plan([assignment, quiz], one_per_day, WEEK_START)

    assert len(result.blocks) == 7  # nothing wasted
    assert len([b for b in result.blocks if "Assignment 2" in b.focus]) == 6


def test_an_item_whose_deadline_has_passed_gets_no_blocks_at_all():
    closed = item(name="Closed Quiz", weight=100.0, due_date="2026-03-09")
    one_per_day = [WeeklySlot(day_of_week=d, start_hour=18) for d in range(7)]

    result = build_weekly_plan([closed], one_per_day, WEEK_START)

    assert result.blocks == ()
    assert result.diagnostics  # and it says why


def test_an_overdue_item_does_not_outrank_an_upcoming_one():
    """max(0, days) clamped a past due date to "due now" — the full 4x urgency —
    so a quiz that closed months ago got double the time of an upcoming final."""
    closed = item(name="Week-2 Quiz", weight=10.0, due_date="2026-03-09")
    final = item(name="Final Exam", weight=50.0, due_date="2026-08-31")
    ten = [WeeklySlot(day_of_week=d, start_hour=h) for d in range(5) for h in (18, 19)]

    result = build_weekly_plan([closed, final], ten, WEEK_START)

    quiz_hours = len([b for b in result.blocks if "Week-2 Quiz" in b.focus])
    final_hours = len([b for b in result.blocks if "Final Exam" in b.focus])
    assert quiz_hours == 0
    assert final_hours >= 9
