"""Deterministic semester scheduler (FR-3.6.2, FR-3.6.5, FR-3.6.6).

Greedy topological placement: each semester, take the eligible courses
(prerequisites met by previously completed/placed courses, offered in the
period) up to the unit cap, prioritising courses that unlock the most others.
Correctness (prerequisite order, caps, offerings) is guaranteed here — never
by a language model (FR-3.6.7).
"""

from app.domain.planning.graph import find_cycle_members, unlock_counts
from app.domain.planning.models import (
    DEFAULT_MAX_SEMESTERS,
    DEFAULT_MAX_UNITS_PER_SEMESTER,
    PLANNING_PERIODS,
    PlanDiagnostic,
    PlanEntry,
    PlannableCourse,
    PlanPreferences,
    PlanResult,
    PlanSemester,
    PrereqStatus,
    Semester,
)
from app.domain.planning.prereq_ast import collect_course_codes, evaluate_prereq


def _is_eligible(course: PlannableCourse, done: frozenset[str]) -> tuple[bool, bool]:
    """(eligible, needs_manual_check) against the done set."""
    evaluation = evaluate_prereq(course.prereq, done)
    if evaluation.status is PrereqStatus.MET:
        return True, evaluation.requires_manual_check
    # An expression blocked ONLY by unparseable note fragments (no outstanding
    # courses) is let through with a manual-check warning rather than blocking
    # the plan forever — it is never silently treated as satisfied.
    if evaluation.requires_manual_check and not evaluation.outstanding:
        return True, True
    return False, False


def _sort_key(
    course: PlannableCourse,
    priorities: dict[str, int],
    preferences: PlanPreferences,
    done_codes: frozenset[str] = frozenset(),
) -> tuple[int, int, str]:
    """Deterministic tie-break order among the courses eligible this semester.

    With no preferences this reduces to the historical "unlock-heavy first"
    ordering. Interest matches always sort first; when 'prioritise available' is
    set, remaining courses are ordered by fewest remaining (unmet) prerequisites
    instead of by unlock count.
    """
    interest_rank = 0 if course.code in preferences.interest_codes else 1
    if preferences.prioritise_available:
        secondary = len(collect_course_codes(course.prereq) - done_codes)
    else:
        secondary = -priorities.get(course.code, 0)
    return (interest_rank, secondary, course.code)


def _explanation(
    course: PlannableCourse, needs_manual_check: bool, preferences: PlanPreferences
) -> str:
    prereq_codes = sorted(collect_course_codes(course.prereq))
    if prereq_codes:
        base = (
            f"Prerequisites ({', '.join(prereq_codes)}) satisfied by this point; "
            f"placed in the next semester it is offered."
        )
    else:
        base = "No prerequisites; placed in the first offered semester with capacity."
    if course.code in preferences.interest_codes:
        base += " Prioritised because it matches your stated interests."
    elif preferences.prioritise_available and not prereq_codes:
        base += " Brought forward because you can take it now."
    if needs_manual_check:
        base += " Contains a requirement that must be checked manually."
    return base


def _diagnose_unscheduled(
    course: PlannableCourse,
    cycle_members: frozenset[str],
    known_codes: frozenset[str],
    done: frozenset[str],
) -> PlanDiagnostic:
    if course.code in cycle_members:
        return PlanDiagnostic(
            severity="error",
            message=f"{course.code} is part of an unsatisfiable prerequisite cycle.",
        )
    if not (course.offerings & set(PLANNING_PERIODS)):
        return PlanDiagnostic(
            severity="error",
            message=f"{course.code} is never offered in a plannable study period.",
        )
    evaluation = evaluate_prereq(course.prereq, done)
    missing = [code for code in evaluation.outstanding if code not in known_codes]
    if missing:
        return PlanDiagnostic(
            severity="error",
            message=(
                f"{course.code} requires {', '.join(sorted(missing))}, "
                f"which is neither completed nor part of this plan."
            ),
        )
    return PlanDiagnostic(
        severity="error",
        message=f"{course.code} could not be placed within the planning horizon.",
    )


def build_plan(
    courses: list[PlannableCourse],
    completed: frozenset[str],
    start: Semester,
    max_units_per_semester: float = DEFAULT_MAX_UNITS_PER_SEMESTER,
    max_semesters: int = DEFAULT_MAX_SEMESTERS,
    preferences: PlanPreferences | None = None,
) -> PlanResult:
    preferences = preferences or PlanPreferences()
    to_schedule = [course for course in courses if course.code not in completed]
    cycle_members = find_cycle_members(to_schedule)
    priorities = unlock_counts(to_schedule)

    diagnostics: list[PlanDiagnostic] = []
    if cycle_members:
        diagnostics.append(
            PlanDiagnostic(
                severity="error",
                message=(
                    "Prerequisite cycle detected involving: "
                    f"{', '.join(sorted(cycle_members))}."
                ),
            )
        )

    semesters: list[PlanSemester] = []
    remaining = {course.code: course for course in to_schedule if course.code not in cycle_members}
    done = set(completed)
    current = start

    for _ in range(max_semesters):
        if not remaining:
            break
        done_before = frozenset(done)
        eligible: list[tuple[PlannableCourse, bool]] = []
        for course in remaining.values():
            if current.period not in course.offerings:
                continue
            is_eligible, needs_check = _is_eligible(course, done_before)
            if is_eligible:
                eligible.append((course, needs_check))

        eligible.sort(key=lambda pair: _sort_key(pair[0], priorities, preferences, done_before))

        entries: list[PlanEntry] = []
        used_units = 0.0
        for course, needs_check in eligible:
            if used_units + course.units > max_units_per_semester:
                continue
            entries.append(
                PlanEntry(
                    course_code=course.code,
                    units=course.units,
                    explanation=_explanation(course, needs_check, preferences),
                )
            )
            used_units += course.units
            if needs_check:
                diagnostics.append(
                    PlanDiagnostic(
                        severity="warning",
                        message=(
                            f"{course.code} has a prerequisite that could not be parsed; "
                            f"check the course profile manually."
                        ),
                    )
                )

        semesters.append(PlanSemester(semester=current, entries=tuple(entries)))
        for entry in entries:
            done.add(entry.course_code)
            del remaining[entry.course_code]
        current = current.next()

    # Trim trailing empty semesters but keep gaps before the last placement.
    while semesters and not semesters[-1].entries:
        semesters.pop()
    if not semesters:
        semesters.append(PlanSemester(semester=start, entries=()))

    known_codes = frozenset(course.code for course in courses) | completed
    unplaced = list(remaining.values()) + [
        course for course in to_schedule if course.code in cycle_members
    ]
    for course in remaining.values():
        diagnostics.append(
            _diagnose_unscheduled(course, cycle_members, known_codes, frozenset(done))
        )

    return PlanResult(
        feasible=not unplaced,
        semesters=tuple(semesters),
        diagnostics=tuple(diagnostics),
    )
