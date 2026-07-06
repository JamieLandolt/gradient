"""Current standing per course: secured marks, best/worst case, projection (FR-3.2.4)."""

from collections.abc import Mapping

from app.domain.calculation.grading import grade_for_percent
from app.domain.calculation.models import AssessmentItem, CourseStanding, validate_items


def compute_standing(
    items: list[AssessmentItem] | tuple[AssessmentItem, ...],
    grade_cutoffs: Mapping[int, float] | None = None,
) -> CourseStanding:
    validate_items(items)

    secured = sum(item.secured_weight_percent for item in items)
    remaining_weight = sum(item.weight for item in items if not item.is_completed)
    completed_weight = sum(item.weight for item in items if item.is_completed)

    projected_percent: float | None = None
    projected_grade: int | None = None
    if completed_weight > 0:
        current_average = secured / completed_weight  # fraction of marks kept so far
        projected_percent = secured + current_average * remaining_weight
        projected_grade = grade_for_percent(projected_percent, grade_cutoffs)

    return CourseStanding(
        secured_percent=secured,
        remaining_weight=remaining_weight,
        best_case_percent=secured + remaining_weight,
        worst_case_percent=secured,
        projected_percent=projected_percent,
        projected_grade=projected_grade,
    )
