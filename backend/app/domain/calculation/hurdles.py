"""Hurdle evaluation, independent of the weighted total (FR-3.3.4)."""

from app.domain.calculation.models import AssessmentItem


def failed_hurdles(items: tuple[AssessmentItem, ...]) -> tuple[str, ...]:
    """Warnings for completed items that scored under their hurdle minimum."""
    warnings = []
    for item in items:
        if item.hurdle_min_percent is None or item.score_percent is None:
            continue
        if item.score_percent < item.hurdle_min_percent:
            requirement = item.hurdle_description or (
                f"requires at least {item.hurdle_min_percent:g}%"
            )
            warnings.append(
                f"Hurdle not met on '{item.name}': scored {item.score_percent:g}%. "
                f"{requirement}"
            )
    return tuple(warnings)


def pending_hurdles(items: tuple[AssessmentItem, ...]) -> tuple[AssessmentItem, ...]:
    """Remaining items that carry a hurdle the student still has to clear."""
    return tuple(
        item for item in items if item.hurdle_min_percent is not None and not item.is_completed
    )
