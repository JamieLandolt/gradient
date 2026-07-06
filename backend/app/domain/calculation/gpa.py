"""GPA / WGPA on the 1–7 scale, weighted by unit value (FR-3.2.5)."""

from app.domain.calculation.models import (
    GpaEntry,
    InvalidAssessmentStructureError,
    validate_grade,
)


def compute_gpa(entries: list[GpaEntry] | tuple[GpaEntry, ...]) -> float | None:
    """Unit-weighted grade point average; None when there is nothing to average."""
    if not entries:
        return None

    for entry in entries:
        validate_grade(entry.grade)
        if entry.units <= 0:
            raise InvalidAssessmentStructureError(
                f"Course units must be positive, got {entry.units:g}"
            )

    total_units = sum(entry.units for entry in entries)
    weighted_points = sum(entry.grade * entry.units for entry in entries)
    return weighted_points / total_units
