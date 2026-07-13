"""Env-driven provider selection (AI_PROVIDER)."""

import threading
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
from app.providers.openai_compatible import (
    OpenAICompatibleAssistantProvider,
    OpenAICompatibleClient,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleExtractionProvider,
    OpenAICompatibleRecommendationProvider,
    OpenAICompatibleStudyPlanProvider,
)


@dataclass(frozen=True)
class ProviderBundle:
    extraction: ExtractionProvider
    embeddings: EmbeddingProvider
    recommendations: RecommendationProvider
    study_plans: StudyPlanProvider
    assistant: AssistantProvider
    name: str


# The hosted bundle owns a shared httpx client — build it once per process, not
# per request. Settings are constant for the process (app.state.settings).
_openai_bundle: ProviderBundle | None = None
_openai_lock = threading.Lock()


def _get_openai_compatible_bundle(settings: Settings) -> ProviderBundle:
    global _openai_bundle
    if _openai_bundle is None:
        with _openai_lock:
            if _openai_bundle is None:
                client = OpenAICompatibleClient(settings)
                _openai_bundle = ProviderBundle(
                    extraction=OpenAICompatibleExtractionProvider(client),
                    embeddings=OpenAICompatibleEmbeddingProvider(
                        client, settings.ai_embedding_model
                    ),
                    recommendations=OpenAICompatibleRecommendationProvider(client),
                    study_plans=OpenAICompatibleStudyPlanProvider(client),
                    assistant=OpenAICompatibleAssistantProvider(client),
                    name="openai_compatible",
                )
    return _openai_bundle


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
    if settings.ai_provider == "openai_compatible":
        return _get_openai_compatible_bundle(settings)
    raise NotImplementedError(
        f"AI provider '{settings.ai_provider}' is not implemented yet — "
        "use AI_PROVIDER=mock or openai_compatible"
    )
