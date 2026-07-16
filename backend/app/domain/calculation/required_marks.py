"""Required-marks calculation for a target grade (FR-3.3.1–FR-3.3.6).

Pure arithmetic: required average across remaining items is
    (target% − secured%) ÷ remaining_weight × 100
with boundary cases ALREADY_SECURED (≤ 0), NOT_REACHABLE (> 100), and LOCKED
(no remaining assessment). Hurdles are evaluated independently of the weighted
total. What-if scores are treated as completed marks under the hypothesis.
"""

from collections.abc import Mapping
from dataclasses import replace

from app.domain.calculation.constants import MAX_GRADE_WITH_FAILED_HURDLE, PASS_GRADE
from app.domain.calculation.grading import grade_for_percent, resolve_cutoffs
from app.domain.calculation.hurdles import failed_hurdles, pending_hurdles
from app.domain.calculation.models import (
    AssessmentItem,
    InvalidAssessmentStructureError,
    PerItemRequirement,
    RequiredMarksResult,
    TargetStatus,
    validate_grade,
    validate_items,
)


def _apply_what_if(
    items: tuple[AssessmentItem, ...], what_if_scores: Mapping[str, float] | None
) -> tuple[AssessmentItem, ...]:
    if not what_if_scores:
        return items
    names = {item.name for item in items}
    unknown = set(what_if_scores) - names
    if unknown:
        raise InvalidAssessmentStructureError(
            f"What-if scores reference unknown items: {', '.join(sorted(unknown))}"
        )
    return tuple(
        replace(item, score=what_if_scores[item.name]) if item.name in what_if_scores else item
        for item in items
    )


def _per_item_breakdown(
    remaining: tuple[AssessmentItem, ...], uniform_required: float
) -> tuple[PerItemRequirement, ...]:
    """Per-item requirement: the uniform average, raised to any hurdle minimum."""
    return tuple(
        PerItemRequirement(
            name=item.name,
            weight=item.weight,
            required_percent=max(uniform_required, item.hurdle_min_percent or 0.0),
            hurdle_min_percent=item.hurdle_min_percent,
        )
        for item in remaining
    )


def _final_grade(
    secured: float, grade_cutoffs: Mapping[int, float] | None, hurdle_blocked: bool
) -> int:
    grade = grade_for_percent(secured, grade_cutoffs)
    if hurdle_blocked:
        return min(grade, MAX_GRADE_WITH_FAILED_HURDLE)
    return grade


def compute_required_marks(
    items: list[AssessmentItem] | tuple[AssessmentItem, ...],
    target_grade: int = PASS_GRADE,
    grade_cutoffs: Mapping[int, float] | None = None,
    what_if_scores: Mapping[str, float] | None = None,
) -> RequiredMarksResult:
    validate_items(items)
    validate_grade(target_grade, "target grade")

    effective_items = _apply_what_if(tuple(items), what_if_scores)
    validate_items(effective_items)

    cutoffs = resolve_cutoffs(grade_cutoffs)
    target_percent = cutoffs[target_grade]

    secured = sum(item.secured_weight_percent for item in effective_items)
    remaining = tuple(item for item in effective_items if not item.is_completed)
    remaining_weight = sum(item.weight for item in remaining)

    hurdle_warnings = failed_hurdles(effective_items)
    hurdle_blocked = len(hurdle_warnings) > 0

    if remaining_weight == 0:
        return RequiredMarksResult(
            target_grade=target_grade,
            target_percent=target_percent,
            status=TargetStatus.LOCKED,
            required_average_percent=None,
            hurdle_blocked=hurdle_blocked,
            hurdle_warnings=hurdle_warnings,
            final_percent=secured,
            final_grade=_final_grade(secured, grade_cutoffs, hurdle_blocked),
        )

    # A hurdle already failed caps the course below a pass, so no amount of
    # remaining marks can reach a passing target — the weighted arithmetic below
    # would otherwise happily report REACHABLE (or even ALREADY_SECURED).
    if hurdle_blocked and target_grade >= PASS_GRADE:
        return RequiredMarksResult(
            target_grade=target_grade,
            target_percent=target_percent,
            status=TargetStatus.NOT_REACHABLE,
            required_average_percent=None,
            hurdle_blocked=True,
            hurdle_warnings=hurdle_warnings,
        )

    required_average = (target_percent - secured) / remaining_weight * 100.0

    if required_average <= 0:
        # Target secured on the weighted total; remaining hurdles still apply.
        return RequiredMarksResult(
            target_grade=target_grade,
            target_percent=target_percent,
            status=TargetStatus.ALREADY_SECURED,
            required_average_percent=0.0,
            per_item=_per_item_breakdown(pending_hurdles(effective_items), 0.0),
            hurdle_blocked=hurdle_blocked,
            hurdle_warnings=hurdle_warnings,
        )

    if required_average > 100:
        return RequiredMarksResult(
            target_grade=target_grade,
            target_percent=target_percent,
            status=TargetStatus.NOT_REACHABLE,
            required_average_percent=None,
            hurdle_blocked=hurdle_blocked,
            hurdle_warnings=hurdle_warnings,
        )

    return RequiredMarksResult(
        target_grade=target_grade,
        target_percent=target_percent,
        status=TargetStatus.REACHABLE,
        required_average_percent=required_average,
        per_item=_per_item_breakdown(remaining, required_average),
        hurdle_blocked=hurdle_blocked,
        hurdle_warnings=hurdle_warnings,
    )
