import math

from app.providers.mock.embeddings import DEFAULT_EMBEDDING_DIMENSIONS, embed_text


def test_embedding_has_fixed_dimensions_and_unit_norm():
    vector = embed_text("machine learning and neural networks")

    assert len(vector) == DEFAULT_EMBEDDING_DIMENSIONS
    norm = math.sqrt(sum(component**2 for component in vector))
    assert math.isclose(norm, 1.0, rel_tol=1e-9)


def test_embedding_is_deterministic():
    text = "relational database systems and SQL"

    assert embed_text(text) == embed_text(text)


def test_similar_texts_are_closer_than_unrelated_texts():
    def cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    ml_course = embed_text("machine learning neural networks deep learning models")
    ai_course = embed_text("artificial intelligence machine learning agents")
    biology_course = embed_text("cell structure genetics inheritance evolution")

    assert cosine(ml_course, ai_course) > cosine(ml_course, biology_course)


def test_empty_text_returns_zero_vector():
    vector = embed_text("")

    assert len(vector) == DEFAULT_EMBEDDING_DIMENSIONS
    assert all(component == 0.0 for component in vector)


def test_the_mock_honours_the_configured_dimension():
    """The DB column is vector(EMBEDDING_DIM). The mock used to hardcode 384 and
    ignore the setting, so the documented mock setup (EMBEDDING_DIM=1024 since
    migration 0010) wrote vectors Postgres rejected on every insert."""
    from app.config import Settings
    from app.providers.factory import get_providers

    settings = Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_ANON_KEY="k",
        SUPABASE_SERVICE_ROLE_KEY="k",
        AI_PROVIDER="mock",
        EMBEDDING_DIM=1024,
    )
    providers = get_providers(settings)

    assert len(providers.embeddings.embed("algorithms")) == 1024
    assert "1024" in providers.embeddings.model_name


def test_a_narrower_configured_dimension_is_also_honoured():
    from app.providers.mock.embeddings import MockEmbeddingProvider

    assert len(MockEmbeddingProvider(384).embed("algorithms")) == 384
