"""Mapping a final percentage to a 1–7 grade via cut-offs."""

from collections.abc import Mapping

from app.domain.calculation.constants import DEFAULT_GRADE_CUTOFFS


def resolve_cutoffs(grade_cutoffs: Mapping[int, float] | None) -> Mapping[int, float]:
    return grade_cutoffs if grade_cutoffs else DEFAULT_GRADE_CUTOFFS


def grade_for_percent(percent: float, grade_cutoffs: Mapping[int, float] | None = None) -> int:
    """Highest grade whose minimum percentage the given percent meets."""
    cutoffs = resolve_cutoffs(grade_cutoffs)
    for grade in sorted(cutoffs, reverse=True):
        if percent >= cutoffs[grade]:
            return grade
    return min(cutoffs)
