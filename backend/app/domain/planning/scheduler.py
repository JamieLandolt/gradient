"""Deterministic semester scheduler (FR-3.6.2, FR-3.6.5, FR-3.6.6).

Greedy topological placement: each semester, take the eligible courses
(prerequisites met by previously completed/placed courses, offered in the
period) up to the unit cap, prioritising courses that unlock the most others.
Correctness (prerequisite order, caps, offerings) is guaranteed here — never
by a language model (FR-3.6.7).
"""

from app.domain.planning.graph import cycle_participants, find_cycle_members, unlock_counts
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
    Semester,
)
from app.domain.planning.prereq_ast import collect_course_codes, eligibility, evaluate_prereq


def _is_eligible(course: PlannableCourse, done: frozenset[str]) -> tuple[bool, bool]:
    """(eligible, needs_manual_check) against the done set."""
    return eligibility(course.prereq, done)


def _sort_key(
    course: PlannableCourse,
    priorities: dict[str, int],
    preferences: PlanPreferences,
) -> tuple[int, int, str]:
    """Deterministic tie-break order among the courses eligible this semester.

    With no preferences this reduces to the historical "unlock-heavy first"
    ordering. Interest matches always sort first; when 'prioritise available' is
    set, remaining courses are ordered by fewest prerequisites (take what you can
    now) instead of by unlock count.
    """
    interest_rank = 0 if course.code in preferences.interest_codes else 1
    if preferences.prioritise_available:
        secondary = len(collect_course_codes(course.prereq))
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
    participants: frozenset[str],
    unresolvable: frozenset[str],
    known_codes: frozenset[str],
    done: frozenset[str],
    max_units_per_semester: float,
) -> PlanDiagnostic:
    if course.code in participants:
        return PlanDiagnostic(
            severity="error",
            message=f"{course.code} is part of an unsatisfiable prerequisite cycle.",
        )
    if course.code in unresolvable:
        # Downstream of a cycle, not in one. Naming the courses it's waiting on
        # points the student at the thing they can actually act on.
        blockers = sorted(collect_course_codes(course.prereq) & unresolvable)
        blocked_by = f" (it depends on {', '.join(blockers)})" if blockers else ""
        return PlanDiagnostic(
            severity="error",
            message=(
                f"{course.code} cannot be scheduled because it is blocked by an "
                f"unsatisfiable prerequisite cycle{blocked_by}."
            ),
        )
    if not (course.offerings & set(PLANNING_PERIODS)):
        return PlanDiagnostic(
            severity="error",
            message=f"{course.code} is never offered in a plannable study period.",
        )
    if course.units > max_units_per_semester:
        return PlanDiagnostic(
            severity="error",
            message=(
                f"{course.code} is {course.units:g} units, which exceeds the "
                f"{max_units_per_semester:g}-unit limit for a single semester."
            ),
        )
    evaluation = evaluate_prereq(course.prereq, done)
    # `outstanding` can carry a None for a malformed course node; joining it
    # raises TypeError and 500s the whole plan request.
    missing = [
        code for code in evaluation.outstanding if code and code not in known_codes
    ]
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
    target_courses_per_semester: int | None = None,
) -> PlanResult:
    preferences = preferences or PlanPreferences()
    to_schedule = [course for course in courses if course.code not in completed]
    # `unresolvable` is the cycle PLUS everything downstream of it — all of it
    # unschedulable — but only `participants` are actually in the loop, and only
    # they should be blamed for one.
    unresolvable = find_cycle_members(to_schedule, completed)
    participants = cycle_participants(to_schedule, unresolvable)
    priorities = unlock_counts(to_schedule)

    diagnostics: list[PlanDiagnostic] = []
    if participants:
        diagnostics.append(
            PlanDiagnostic(
                severity="error",
                message=(
                    "Prerequisite cycle detected involving: "
                    f"{', '.join(sorted(participants))}."
                ),
            )
        )

    semesters: list[PlanSemester] = []
    remaining = {course.code: course for course in to_schedule if course.code not in unresolvable}
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

        eligible.sort(key=lambda pair: _sort_key(pair[0], priorities, preferences))

        entries: list[PlanEntry] = []
        used_units = 0.0
        target_reached = False
        capped_by_units = False
        for course, needs_check in eligible:
            if (
                target_courses_per_semester is not None
                and len(entries) >= target_courses_per_semester
            ):
                target_reached = True
                break
            if used_units + course.units > max_units_per_semester:
                # The unit cap, not a shortage of eligible courses, is what
                # stopped this one going in — the shortfall message below must
                # not then claim nothing else was eligible.
                capped_by_units = True
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

        # A target was set (full-time/part-time) but this semester fell short of
        # it. Say WHY, truthfully: too few eligible courses, or the unit cap.
        if (
            target_courses_per_semester is not None
            and not target_reached
            and entries
            and len(entries) < target_courses_per_semester
        ):
            if capped_by_units:
                message = (
                    f"Only {len(entries)} course"
                    f"{'s' if len(entries) != 1 else ''} fit within your "
                    f"{max_units_per_semester:g}-unit limit in {current.label}."
                )
            else:
                message = (
                    f"Only {len(entries)} course"
                    f"{'s were' if len(entries) != 1 else ' was'} eligible in "
                    f"{current.label} — you've taken everything else you're "
                    f"currently eligible for."
                )
            diagnostics.append(PlanDiagnostic(severity="info", message=message))

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
    # Every course that didn't make the plan gets its own explanation, including
    # the ones excluded up front for the cycle — they were previously dropped
    # with only the one summary line, which made this branch dead code.
    unplaced = list(remaining.values()) + [
        course for course in to_schedule if course.code in unresolvable
    ]
    for course in unplaced:
        diagnostics.append(
            _diagnose_unscheduled(
                course,
                participants,
                unresolvable,
                known_codes,
                frozenset(done),
                max_units_per_semester,
            )
        )

    return PlanResult(
        feasible=not unplaced,
        semesters=tuple(semesters),
        diagnostics=tuple(diagnostics),
    )
