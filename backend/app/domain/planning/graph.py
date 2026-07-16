"""Prerequisite dependency graph over a set of plannable courses (FR-3.6.1).

Edges point prerequisite → dependent. Cycle detection grows a resolved set to a
fixed point: whatever can never be reached is part of (or downstream of) a cycle.
"""

from app.domain.planning.models import PlannableCourse
from app.domain.planning.prereq_ast import collect_course_codes, eligibility


def prerequisite_codes_within(
    course: PlannableCourse, plan_codes: frozenset[str]
) -> frozenset[str]:
    """Prerequisite codes of a course restricted to courses inside the plan."""
    return collect_course_codes(course.prereq) & plan_codes


def find_cycle_members(
    courses: list[PlannableCourse], completed: frozenset[str] = frozenset()
) -> frozenset[str]:
    """Course codes that can never be ordered because of a prerequisite cycle.

    Resolvability is decided by evaluating each course's actual prerequisite
    expression, NOT by flattening it to a set of codes: a flattened set turns
    every OR into an AND, so `A or B` would demand both and a plan that is
    perfectly orderable gets reported as cyclic — dropping the course and its
    whole downstream cone. UQ prerequisites are OR-heavy ("X or Y or
    equivalent"), so that mis-reading is the common case, not a corner one.

    Codes referenced but outside the plan and not completed are assumed
    available here: a missing prerequisite is not a cycle, and the scheduler
    diagnoses it far more precisely than "cycle detected" would.
    """
    plan_codes = frozenset(course.code for course in courses)
    external: frozenset[str] = frozenset()
    for course in courses:
        external |= collect_course_codes(course.prereq) - plan_codes
    assumed = completed | external

    resolved: set[str] = set()
    changed = True
    while changed:
        changed = False
        for course in courses:
            if course.code in resolved:
                continue
            can_take, _ = eligibility(course.prereq, frozenset(assumed | resolved))
            if can_take:
                resolved.add(course.code)
                changed = True

    return plan_codes - resolved


def cycle_participants(
    courses: list[PlannableCourse], unresolvable: frozenset[str]
) -> frozenset[str]:
    """Of the unresolvable courses, the ones actually ON a prerequisite cycle.

    `find_cycle_members` returns the cycle AND everything downstream of it, which
    is what the scheduler must skip — but blaming all of them for "being part of
    a cycle" tells a student to fix a loop in courses that have none. A real
    participant is one with a dependency path back to itself.
    """
    edges = {
        course.code: collect_course_codes(course.prereq) & unresolvable
        for course in courses
        if course.code in unresolvable
    }
    participants: set[str] = set()
    for start in edges:
        seen: set[str] = set()
        stack = list(edges[start])
        while stack:
            node = stack.pop()
            if node == start:
                participants.add(start)
                break
            if node in seen:
                continue
            seen.add(node)
            stack.extend(edges.get(node, frozenset()))
    return frozenset(participants)


def unlock_counts(courses: list[PlannableCourse]) -> dict[str, int]:
    """How many other plan courses each course unlocks (used to prioritise)."""
    plan_codes = frozenset(course.code for course in courses)
    counts = dict.fromkeys(plan_codes, 0)
    for course in courses:
        for code in prerequisite_codes_within(course, plan_codes):
            counts[code] += 1
    return counts
