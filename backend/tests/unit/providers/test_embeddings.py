import math

from app.providers.mock.embeddings import EMBEDDING_DIMENSIONS, embed_text


def test_embedding_has_fixed_dimensions_and_unit_norm():
    vector = embed_text("machine learning and neural networks")

    assert len(vector) == EMBEDDING_DIMENSIONS
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

    assert len(vector) == EMBEDDING_DIMENSIONS
    assert all(component == 0.0 for component in vector)
