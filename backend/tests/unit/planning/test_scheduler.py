"""Semester scheduling: prerequisites, unit caps, offering patterns (FR-3.6.2, FR-3.6.5)."""

import pytest

from app.domain.planning.models import (
    PlannableCourse,
    PlanPreferences,
    PrereqNode,
    Semester,
)
from app.domain.planning.scheduler import build_plan

S1 = "S1"
S2 = "S2"


def course(code: str, offerings: tuple[str, ...] = (S1, S2), prereq: PrereqNode | None = None,
           units: float = 2) -> PlannableCourse:
    return PlannableCourse(code=code, units=units, offerings=frozenset(offerings), prereq=prereq)


def scheduled_codes(plan) -> list[str]:
    return [entry.course_code for semester in plan.semesters for entry in semester.entries]


def semester_of(plan, code: str) -> int:
    for index, semester in enumerate(plan.semesters):
        if any(entry.course_code == code for entry in semester.entries):
            return index
    raise AssertionError(f"{code} not scheduled")


class TestPrerequisiteOrdering:
    def test_prerequisite_comes_before_dependent(self):
        courses = [
            course("CSSE2002", prereq=PrereqNode.course("CSSE1001")),
            course("CSSE1001"),
        ]
        plan = build_plan(courses, completed=frozenset(), start=Semester(2026, S1))

        assert plan.feasible is True
        assert semester_of(plan, "CSSE1001") < semester_of(plan, "CSSE2002")

    def test_chain_of_three_takes_three_semesters(self):
        courses = [
            course("C", prereq=PrereqNode.course("B")),
            course("B", prereq=PrereqNode.course("A")),
            course("A"),
        ]
        plan = build_plan(courses, completed=frozenset(), start=Semester(2026, S1))

        assert semester_of(plan, "A") < semester_of(plan, "B") < semester_of(plan, "C")

    def test_completed_prerequisites_unlock_immediately(self):
        courses = [course("CSSE2002", prereq=PrereqNode.course("CSSE1001"))]
        plan = build_plan(
            courses, completed=frozenset({"CSSE1001"}), start=Semester(2026, S1)
        )

        assert semester_of(plan, "CSSE2002") == 0

    def test_or_prerequisite_satisfied_by_either_branch(self):
        prereq = PrereqNode.any_of(PrereqNode.course("MATH1051"), PrereqNode.course("MATH1071"))
        courses = [course("MATH1052", prereq=prereq)]
        plan = build_plan(
            courses, completed=frozenset({"MATH1071"}), start=Semester(2026, S1)
        )

        assert plan.feasible is True
        assert semester_of(plan, "MATH1052") == 0


class TestUnitCapAndOfferings:
    def test_unit_cap_limits_courses_per_semester(self):
        courses = [course(f"C{i}") for i in range(6)]
        plan = build_plan(
            courses, completed=frozenset(), start=Semester(2026, S1), max_units_per_semester=4
        )

        assert plan.feasible is True
        for semester in plan.semesters:
            assert sum(entry.units for entry in semester.entries) <= 4

    def test_course_waits_for_its_offered_semester(self):
        courses = [course("S2ONLY", offerings=(S2,))]
        plan = build_plan(courses, completed=frozenset(), start=Semester(2026, S1))

        placed = plan.semesters[semester_of(plan, "S2ONLY")]
        assert placed.semester.period == S2

    def test_all_courses_are_scheduled_exactly_once(self):
        courses = [course(f"C{i}") for i in range(5)]
        plan = build_plan(courses, completed=frozenset(), start=Semester(2026, S1))

        codes = scheduled_codes(plan)
        assert sorted(codes) == sorted(f"C{i}" for i in range(5))


class TestTargetCoursesPerSemester:
    """FR-3.6.6: full-time/part-time study load (a course-count target, not just a unit cap)."""

    def test_fills_up_to_the_target_when_enough_are_eligible(self):
        courses = [course(f"C{i}") for i in range(8)]
        plan = build_plan(
            courses, completed=frozenset(), start=Semester(2026, S1),
            max_units_per_semester=100, target_courses_per_semester=4,
        )

        assert len(plan.semesters[0].entries) == 4
        assert not any(d.severity == "info" for d in plan.diagnostics)

    def test_shortfall_diagnostic_when_fewer_are_eligible_than_the_target(self):
        courses = [course("A"), course("B")]
        plan = build_plan(
            courses, completed=frozenset(), start=Semester(2026, S1),
            max_units_per_semester=100, target_courses_per_semester=4,
        )

        assert len(plan.semesters[0].entries) == 2
        info_messages = [d.message for d in plan.diagnostics if d.severity == "info"]
        assert len(info_messages) == 1
        assert "Only 2" in info_messages[0]
        assert "2026 S1" in info_messages[0]

    def test_no_shortfall_diagnostic_without_a_target(self):
        courses = [course("A"), course("B")]
        plan = build_plan(courses, completed=frozenset(), start=Semester(2026, S1))

        assert not any(d.severity == "info" for d in plan.diagnostics)


class TestInfeasibility:
    def test_cycle_is_reported_not_returned(self):
        courses = [
            course("A", prereq=PrereqNode.course("B")),
            course("B", prereq=PrereqNode.course("A")),
        ]
        plan = build_plan(courses, completed=frozenset(), start=Semester(2026, S1))

        assert plan.feasible is False
        assert any("cycle" in d.message.lower() for d in plan.diagnostics)

    def test_never_offered_course_is_reported(self):
        courses = [course("GHOST", offerings=())]
        plan = build_plan(courses, completed=frozenset(), start=Semester(2026, S1))

        assert plan.feasible is False
        assert any("GHOST" in d.message for d in plan.diagnostics)

    def test_missing_prerequisite_course_is_reported(self):
        # Prereq references a course not in the plan and not completed
        courses = [course("DEP", prereq=PrereqNode.course("ABSENT"))]
        plan = build_plan(courses, completed=frozenset(), start=Semester(2026, S1))

        assert plan.feasible is False
        assert any("ABSENT" in d.message for d in plan.diagnostics)


class TestExplanations:
    def test_entries_explain_their_placement(self):
        courses = [
            course("CSSE2002", prereq=PrereqNode.course("CSSE1001")),
            course("CSSE1001"),
        ]
        plan = build_plan(courses, completed=frozenset(), start=Semester(2026, S1))

        dependent = next(
            entry for semester in plan.semesters for entry in semester.entries
            if entry.course_code == "CSSE2002"
        )
        assert "CSSE1001" in dependent.explanation


class TestPlanValidity:
    def test_every_plan_revalidates(self):
        # Property-style check over a denser catalogue
        prereqs = {
            "B1": PrereqNode.course("A1"),
            "B2": PrereqNode.course("A2"),
            "C1": PrereqNode.all_of(PrereqNode.course("B1"), PrereqNode.course("B2")),
            "C2": PrereqNode.any_of(PrereqNode.course("B1"), PrereqNode.course("A3")),
        }
        courses = [
            course("A1", offerings=(S1,)),
            course("A2"),
            course("A3", offerings=(S2,)),
            course("B1", prereq=prereqs["B1"]),
            course("B2", prereq=prereqs["B2"], offerings=(S2,)),
            course("C1", prereq=prereqs["C1"]),
            course("C2", prereq=prereqs["C2"], offerings=(S1,)),
        ]
        plan = build_plan(
            courses, completed=frozenset(), start=Semester(2026, S1), max_units_per_semester=4
        )

        assert plan.feasible is True
        seen: set[str] = set()
        for semester in plan.semesters:
            semester_units = sum(entry.units for entry in semester.entries)
            assert semester_units <= 4
            for entry in semester.entries:
                course_obj = next(c for c in courses if c.code == entry.course_code)
                assert semester.semester.period in course_obj.offerings
                if course_obj.prereq is not None:
                    from app.domain.planning.models import PrereqStatus
                    from app.domain.planning.prereq_ast import evaluate_prereq

                    evaluation = evaluate_prereq(course_obj.prereq, frozenset(seen))
                    assert evaluation.status is PrereqStatus.MET
            seen.update(entry.course_code for entry in semester.entries)


class TestPreferences:
    """FR-3.6.6: deterministic, correctness-preserving scheduling preferences."""

    def test_interest_courses_are_front_loaded(self):
        # Two independent courses; only one fits per semester (units 2, cap 2).
        courses = [course("AAAA"), course("BBBB")]
        default = build_plan(
            courses, completed=frozenset(), start=Semester(2026, S1),
            max_units_per_semester=2,
        )
        assert semester_of(default, "AAAA") == 0  # alphabetical when nothing distinguishes

        prefs = PlanPreferences(interest_codes=frozenset({"BBBB"}))
        prioritised = build_plan(
            courses, completed=frozenset(), start=Semester(2026, S1),
            max_units_per_semester=2, preferences=prefs,
        )
        assert semester_of(prioritised, "BBBB") == 0  # interest wins the slot

    def test_prioritise_available_prefers_fewer_prerequisites(self):
        # MIDAAA unlocks TARGET (unlock-heavy) but has a prerequisite; LEAFZZ has none.
        courses = [
            course("MIDAAA", prereq=PrereqNode.course("DONE")),
            course("LEAFZZ"),
            course("TARGET", prereq=PrereqNode.course("MIDAAA")),
        ]
        completed = frozenset({"DONE"})
        default = build_plan(
            courses, completed=completed, start=Semester(2026, S1),
            max_units_per_semester=2,
        )
        assert semester_of(default, "MIDAAA") == 0  # unlock-heavy first by default

        prefs = PlanPreferences(prioritise_available=True)
        prioritised = build_plan(
            courses, completed=completed, start=Semester(2026, S1),
            max_units_per_semester=2, preferences=prefs,
        )
        assert semester_of(prioritised, "LEAFZZ") == 0  # fewest prereqs brought forward

    def test_explanations_reflect_active_preferences(self):
        courses = [course("AAAA"), course("BBBB")]
        prefs = PlanPreferences(
            prioritise_available=True, interest_codes=frozenset({"BBBB"})
        )
        plan = build_plan(
            courses, completed=frozenset(), start=Semester(2026, S1), preferences=prefs
        )
        explanations = {
            e.course_code: e.explanation for s in plan.semesters for e in s.entries
        }
        assert "interests" in explanations["BBBB"].lower()
        assert "take it now" in explanations["AAAA"].lower()

    def test_preferences_never_break_prerequisite_order(self):
        courses = [
            course("CSSE2002", prereq=PrereqNode.course("CSSE1001")),
            course("CSSE1001"),
        ]
        prefs = PlanPreferences(
            prioritise_available=True, interest_codes=frozenset({"CSSE2002"})
        )
        plan = build_plan(
            courses, completed=frozenset(), start=Semester(2026, S1), preferences=prefs
        )
        # Even though the dependent course is the "interest", correctness holds.
        assert semester_of(plan, "CSSE1001") < semester_of(plan, "CSSE2002")


def test_start_semester_alternates_periods():
    plan = build_plan(
        [course("X", offerings=(S1,)), course("Y", offerings=(S2,))],
        completed=frozenset(),
        start=Semester(2026, S2),
    )

    assert plan.semesters[0].semester == Semester(2026, S2)
    with pytest.raises(AssertionError):
        # sanity: helper raises for unscheduled courses
        semester_of(plan, "NOPE")
