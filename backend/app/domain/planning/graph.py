"""Prerequisite dependency graph over a set of plannable courses (FR-3.6.1).

Edges point prerequisite → dependent. Cycle detection uses Kahn's algorithm:
whatever cannot be topologically ordered is part of (or downstream of) a cycle.
"""

from collections import deque

from app.domain.planning.models import PlannableCourse
from app.domain.planning.prereq_ast import collect_course_codes


def prerequisite_codes_within(
    course: PlannableCourse, plan_codes: frozenset[str]
) -> frozenset[str]:
    """Prerequisite codes of a course restricted to courses inside the plan."""
    return collect_course_codes(course.prereq) & plan_codes


def find_cycle_members(courses: list[PlannableCourse]) -> frozenset[str]:
    """Course codes that can never be ordered because of a prerequisite cycle.

    Uses Kahn's algorithm (BFS with in-degree tracking) for O(V+E) complexity.
    """
    plan_codes = frozenset(course.code for course in courses)
    dependencies = {
        course.code: set(prerequisite_codes_within(course, plan_codes)) for course in courses
    }

    in_degree: dict[str, int] = {code: 0 for code in plan_codes}
    dependents: dict[str, list[str]] = {code: [] for code in plan_codes}
    for code, deps in dependencies.items():
        in_degree[code] = len(deps)
        for dep in deps:
            dependents[dep].append(code)

    queue: deque[str] = deque(code for code, deg in in_degree.items() if deg == 0)
    resolved: set[str] = set()
    while queue:
        current = queue.popleft()
        resolved.add(current)
        for dependent in dependents[current]:
            if dependent not in resolved:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

    return plan_codes - resolved


def unlock_counts(courses: list[PlannableCourse]) -> dict[str, int]:
    """How many other plan courses each course unlocks (used to prioritise)."""
    plan_codes = frozenset(course.code for course in courses)
    counts = dict.fromkeys(plan_codes, 0)
    for course in courses:
        for code in prerequisite_codes_within(course, plan_codes):
            counts[code] += 1
    return counts
