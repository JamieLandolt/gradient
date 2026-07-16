"""Current standing per course: secured marks, best/worst case, projection (FR-3.2.4)."""

from collections.abc import Mapping

from app.domain.calculation.constants import MAX_GRADE_WITH_FAILED_HURDLE
from app.domain.calculation.grading import grade_for_percent
from app.domain.calculation.hurdles import failed_hurdles
from app.domain.calculation.models import AssessmentItem, CourseStanding, validate_items


def compute_standing(
    items: list[AssessmentItem] | tuple[AssessmentItem, ...],
    grade_cutoffs: Mapping[int, float] | None = None,
) -> CourseStanding:
    validate_items(items)

    secured = sum(item.secured_weight_percent for item in items)
    remaining_weight = sum(item.weight for item in items if not item.is_completed)
    completed_weight = sum(item.weight for item in items if item.is_completed)

    hurdle_warnings = failed_hurdles(tuple(items))

    projected_percent: float | None = None
    projected_grade: int | None = None
    if completed_weight > 0:
        current_average = secured / completed_weight  # fraction of marks kept so far
        projected_percent = secured + current_average * remaining_weight
        projected_grade = grade_for_percent(projected_percent, grade_cutoffs)
        if hurdle_warnings:
            # The student has already missed a mandatory hurdle, so the weighted
            # total no longer determines the result — it cannot be a pass. Showing
            # the raw grade here told a failing student they were on track.
            projected_grade = min(projected_grade, MAX_GRADE_WITH_FAILED_HURDLE)

    return CourseStanding(
        secured_percent=secured,
        remaining_weight=remaining_weight,
        best_case_percent=secured + remaining_weight,
        worst_case_percent=secured,
        projected_percent=projected_percent,
        projected_grade=projected_grade,
        hurdle_blocked=bool(hurdle_warnings),
        hurdle_warnings=hurdle_warnings,
    )
