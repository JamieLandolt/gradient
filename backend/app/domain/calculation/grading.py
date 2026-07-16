"""Mapping a final percentage to a 1–7 grade via cut-offs."""

from collections.abc import Mapping

from app.domain.calculation.constants import DEFAULT_GRADE_CUTOFFS, MIN_GRADE

# Weighted totals reach here as sum((score / max_mark) * weight), which for
# ordinary marks lands a few ulps off the exact value: 40/40/72/41 against
# weights 10/20/30/40 accumulates to 49.99999999999999, not 50.0. Compared raw
# against a cut-off that drops a whole grade — an exact-50 student is told they
# failed. Quantise both sides first, at a precision far finer than any real mark
# but far coarser than the accumulated error.
_CUTOFF_PRECISION = 9


def resolve_cutoffs(grade_cutoffs: Mapping[int, float] | None) -> Mapping[int, float]:
    """ECP-supplied cut-offs layered over the UQ defaults.

    An extracted ECP normally states only the bands at or above a pass, so
    honouring it verbatim would leave a failing mark with no band to land in.
    Stated values win; the defaults fill the gaps, guaranteeing every grade
    1–7 has a cut-off. Returns a new mapping — the caller's is never mutated.
    """
    if not grade_cutoffs:
        return DEFAULT_GRADE_CUTOFFS
    return {**DEFAULT_GRADE_CUTOFFS, **grade_cutoffs}


def grade_for_percent(percent: float, grade_cutoffs: Mapping[int, float] | None = None) -> int:
    """Highest grade whose minimum percentage the given percent meets."""
    cutoffs = resolve_cutoffs(grade_cutoffs)
    value = round(percent, _CUTOFF_PRECISION)
    for grade in sorted(cutoffs, reverse=True):
        if value >= round(cutoffs[grade], _CUTOFF_PRECISION):
            return grade
    return MIN_GRADE
