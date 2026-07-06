"""Immutable value objects for the calculation engine.

All inputs and outputs are frozen dataclasses: the engine never mutates its
arguments and always returns new objects (FR-3.3.6 is pure arithmetic).
"""

from dataclasses import dataclass, field
from enum import Enum

from app.domain.calculation.constants import (
    MAX_GRADE,
    MIN_GRADE,
    WEIGHT_SUM_TOLERANCE,
)


class InvalidAssessmentStructureError(ValueError):
    """Raised when assessment inputs are structurally invalid (bad weights, scores…)."""


class TargetStatus(Enum):
    REACHABLE = "reachable"
    ALREADY_SECURED = "already_secured"
    NOT_REACHABLE = "not_reachable"
    LOCKED = "locked"


@dataclass(frozen=True)
class AssessmentItem:
    """One assessment item; score is None until the student records a mark."""

    name: str
    weight: float
    max_mark: float = 100.0
    score: float | None = None
    hurdle_min_percent: float | None = None
    hurdle_description: str | None = None

    @property
    def is_completed(self) -> bool:
        return self.score is not None

    @property
    def score_percent(self) -> float | None:
        if self.score is None:
            return None
        return (self.score / self.max_mark) * 100.0

    @property
    def secured_weight_percent(self) -> float:
        """Contribution to the final percentage from this item's recorded mark."""
        if self.score is None:
            return 0.0
        return (self.score / self.max_mark) * self.weight


@dataclass(frozen=True)
class CourseStanding:
    secured_percent: float
    remaining_weight: float
    best_case_percent: float
    worst_case_percent: float
    projected_percent: float | None
    projected_grade: int | None


@dataclass(frozen=True)
class PerItemRequirement:
    name: str
    weight: float
    required_percent: float
    hurdle_min_percent: float | None


@dataclass(frozen=True)
class RequiredMarksResult:
    target_grade: int
    target_percent: float
    status: TargetStatus
    required_average_percent: float | None
    per_item: tuple[PerItemRequirement, ...] = field(default_factory=tuple)
    hurdle_blocked: bool = False
    hurdle_warnings: tuple[str, ...] = field(default_factory=tuple)
    final_percent: float | None = None
    final_grade: int | None = None


@dataclass(frozen=True)
class GpaEntry:
    grade: int
    units: float


def validate_items(items: list[AssessmentItem] | tuple[AssessmentItem, ...]) -> None:
    """Fail fast on structurally invalid assessment inputs."""
    if not items:
        raise InvalidAssessmentStructureError("A course needs at least one assessment item")

    total_weight = sum(item.weight for item in items)
    if abs(total_weight - 100.0) > WEIGHT_SUM_TOLERANCE:
        raise InvalidAssessmentStructureError(
            f"Assessment weights must sum to 100, got {total_weight:g}"
        )

    for item in items:
        if item.weight < 0:
            raise InvalidAssessmentStructureError(f"'{item.name}' has a negative weight")
        if item.max_mark <= 0:
            raise InvalidAssessmentStructureError(f"'{item.name}' must have a positive max mark")
        if item.score is not None and not (0 <= item.score <= item.max_mark):
            raise InvalidAssessmentStructureError(
                f"'{item.name}' score {item.score:g} is outside 0–{item.max_mark:g}"
            )


def validate_grade(grade: int, label: str = "grade") -> None:
    if not (MIN_GRADE <= grade <= MAX_GRADE):
        raise InvalidAssessmentStructureError(
            f"{label} must be between {MIN_GRADE} and {MAX_GRADE}, got {grade}"
        )
