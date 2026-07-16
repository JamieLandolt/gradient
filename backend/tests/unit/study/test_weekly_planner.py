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
