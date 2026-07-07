"""Provider interfaces for all language-model-assisted features (SRS §2.4).

Deterministic logic never lives behind these interfaces — they cover only
extraction, embeddings, and advisory generation. v1 ships mock implementations;
real providers (ollama / anthropic) plug in behind the same contracts.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.planning.models import PrereqNode


@dataclass(frozen=True)
class ExtractedAssessment:
    name: str
    weight: float
    max_mark: float
    due_date: str | None
    hurdle_min_percent: float | None
    hurdle_description: str | None


@dataclass(frozen=True)
class ExtractedProfile:
    course_code: str
    course_title: str
    units: float
    description: str
    version_label: str
    assessments: tuple[ExtractedAssessment, ...]
    grade_cutoffs: dict[int, float] | None
    prerequisite_raw: str | None
    prerequisite_tree: PrereqNode | None
    warnings: tuple[str, ...] = field(default_factory=tuple)


class ExtractionProvider(Protocol):
    def extract(self, text: str) -> ExtractedProfile: ...


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    def embed(self, text: str) -> list[float]: ...


class RecommendationProvider(Protocol):
    def recommend(
        self,
        candidates: list[dict[str, Any]],
        interests: list[str],
        completed_codes: frozenset[str],
        limit: int,
    ) -> list[dict[str, Any]]: ...


class StudyPlanProvider(Protocol):
    def generate(
        self,
        course_code: str,
        items: list[dict[str, Any]],
        target_grade: int,
        required_average_percent: float | None,
        start_date: str,
    ) -> list[dict[str, Any]]: ...


class AssistantProvider(Protocol):
    def answer(self, question: str, facts: dict[str, Any]) -> str: ...
