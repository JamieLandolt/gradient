"""Env-driven provider selection (AI_PROVIDER). Only 'mock' is implemented in v1."""

from dataclasses import dataclass

from app.config import Settings
from app.providers.interfaces import (
    AssistantProvider,
    EmbeddingProvider,
    ExtractionProvider,
    RecommendationProvider,
    StudyPlanProvider,
)
from app.providers.mock.assistant import MockAssistantProvider
from app.providers.mock.embeddings import MockEmbeddingProvider
from app.providers.mock.extraction import MockExtractionProvider
from app.providers.mock.recommendations import MockRecommendationProvider
from app.providers.mock.study_plans import MockStudyPlanProvider


@dataclass(frozen=True)
class ProviderBundle:
    extraction: ExtractionProvider
    embeddings: EmbeddingProvider
    recommendations: RecommendationProvider
    study_plans: StudyPlanProvider
    assistant: AssistantProvider
    name: str


def get_providers(settings: Settings) -> ProviderBundle:
    if settings.ai_provider == "mock":
        return ProviderBundle(
            extraction=MockExtractionProvider(),
            embeddings=MockEmbeddingProvider(),
            recommendations=MockRecommendationProvider(),
            study_plans=MockStudyPlanProvider(),
            assistant=MockAssistantProvider(),
            name="mock",
        )
    raise NotImplementedError(
        f"AI provider '{settings.ai_provider}' is not implemented yet — use AI_PROVIDER=mock"
    )
