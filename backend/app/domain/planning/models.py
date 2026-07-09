"""Immutable value objects for the planning engine (FR-3.6.x)."""

from dataclasses import dataclass, field
from enum import Enum

S1 = "S1"
S2 = "S2"
SUMMER = "SUMMER"
# The scheduler plans across the two main study periods; SUMMER offerings are
# accepted as input but not used as planning slots in v1.
PLANNING_PERIODS = (S1, S2)

DEFAULT_MAX_UNITS_PER_SEMESTER = 8.0
DEFAULT_MAX_SEMESTERS = 20


class PrereqStatus(Enum):
    MET = "met"
    PARTIALLY_MET = "partially_met"
    NOT_MET = "not_met"


@dataclass(frozen=True)
class PrereqNode:
    """One node of a prerequisite boolean expression tree."""

    node_type: str  # 'and' | 'or' | 'course' | 'note'
    code: str | None = None
    text: str | None = None
    children: tuple["PrereqNode", ...] = field(default_factory=tuple)

    @classmethod
    def course(cls, code: str) -> "PrereqNode":
        return cls(node_type="course", code=code)

    @classmethod
    def note(cls, text: str) -> "PrereqNode":
        return cls(node_type="note", text=text)

    @classmethod
    def all_of(cls, *children: "PrereqNode") -> "PrereqNode":
        return cls(node_type="and", children=tuple(children))

    @classmethod
    def any_of(cls, *children: "PrereqNode") -> "PrereqNode":
        return cls(node_type="or", children=tuple(children))


@dataclass(frozen=True)
class PrereqEvaluation:
    status: PrereqStatus
    outstanding: tuple[str, ...]
    requires_manual_check: bool = False


@dataclass(frozen=True)
class Semester:
    year: int
    period: str  # 'S1' | 'S2'

    @property
    def label(self) -> str:
        return f"{self.year} {self.period}"

    def next(self) -> "Semester":
        if self.period == S1:
            return Semester(self.year, S2)
        return Semester(self.year + 1, S1)


@dataclass(frozen=True)
class PlannableCourse:
    code: str
    units: float
    offerings: frozenset[str]
    prereq: PrereqNode | None = None


@dataclass(frozen=True)
class PlanEntry:
    course_code: str
    units: float
    explanation: str


@dataclass(frozen=True)
class PlanSemester:
    semester: Semester
    entries: tuple[PlanEntry, ...]


@dataclass(frozen=True)
class PlanDiagnostic:
    severity: str  # 'info' | 'warning' | 'error'
    message: str


@dataclass(frozen=True)
class PlanResult:
    feasible: bool
    semesters: tuple[PlanSemester, ...]
    diagnostics: tuple[PlanDiagnostic, ...]


@dataclass(frozen=True)
class PlanPreferences:
    """Optional, deterministic scheduling preferences (FR-3.6.6).

    Neither field ever relaxes prerequisite correctness or unit caps — they only
    change the tie-break order among courses that are already eligible in a
    semester, so every produced plan still re-validates.
    """

    prioritise_available: bool = False
    # Course codes the student is interested in (matched to text upstream in the
    # service, so the pure engine never touches catalogue-shaped fields).
    interest_codes: frozenset[str] = frozenset()

    @property
    def is_active(self) -> bool:
        return self.prioritise_available or bool(self.interest_codes)


@dataclass(frozen=True)
class ProgramRequirements:
    program_code: str
    required: frozenset[str]
    elective: frozenset[str]


@dataclass(frozen=True)
class MergedRequirements:
    required: frozenset[str]
    elective: frozenset[str]
