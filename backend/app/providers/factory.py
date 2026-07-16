"""Env-driven provider selection (AI_PROVIDER). Only 'mock' is implemented in v1."""

from dataclasses import dataclass

from app.config import Settings
from app.providers.interfaces import (
    AssistantProvider,
    EmbeddingProvider,
    ExtractionProvider,
    RecommendationProvider,
)
from app.providers.mock.assistant import MockAssistantProvider
from app.providers.mock.embeddings import MockEmbeddingProvider
from app.providers.mock.extraction import MockExtractionProvider
from app.providers.mock.recommendations import MockRecommendationProvider
from app.providers.openai_compatible import (
    OpenAICompatibleAssistantProvider,
    OpenAICompatibleClient,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleExtractionProvider,
    OpenAICompatibleRecommendationProvider,
)


@dataclass(frozen=True)
class ProviderBundle:
    extraction: ExtractionProvider
    embeddings: EmbeddingProvider
    recommendations: RecommendationProvider
    # Weekly study plans (FR-3.8.x) are fully deterministic (no AI provider) —
    # see app.domain.study.weekly_planner.
    assistant: AssistantProvider
    name: str


# The hosted bundle owns a shared httpx client — build it once per process, not
# per request. Settings are constant for the process (app.state.settings).
_openai_bundle: ProviderBundle | None = None


def _get_openai_compatible_bundle(settings: Settings) -> ProviderBundle:
    global _openai_bundle
    if _openai_bundle is None:
        client = OpenAICompatibleClient(settings)
        _openai_bundle = ProviderBundle(
            extraction=OpenAICompatibleExtractionProvider(client),
            embeddings=OpenAICompatibleEmbeddingProvider(client, settings.ai_embedding_model),
            recommendations=OpenAICompatibleRecommendationProvider(client),
            assistant=OpenAICompatibleAssistantProvider(client),
            name="openai_compatible",
        )
    return _openai_bundle


def get_providers(settings: Settings) -> ProviderBundle:
    if settings.ai_provider == "mock":
        return ProviderBundle(
            extraction=MockExtractionProvider(),
            # Honour the configured width: the DB column is vector(EMBEDDING_DIM)
            # and a mismatch is rejected on every write.
            embeddings=MockEmbeddingProvider(settings.embedding_dim),
            recommendations=MockRecommendationProvider(),
            assistant=MockAssistantProvider(),
            name="mock",
        )
    if settings.ai_provider == "openai_compatible":
        return _get_openai_compatible_bundle(settings)
    raise NotImplementedError(
        f"AI provider '{settings.ai_provider}' is not implemented yet — "
        "use AI_PROVIDER=mock or openai_compatible"
    )
