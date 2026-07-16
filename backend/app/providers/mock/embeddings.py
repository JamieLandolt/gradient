"""Deterministic mock text embeddings.

Hashed-token bag-of-words vectors: each token is hashed into one of
EMBEDDING_DIMENSIONS signed buckets and the result is L2-normalised.
Texts sharing vocabulary get meaningfully high cosine similarity, which is
enough for the semantic-search feature to behave sensibly without a real
embedding model. A real provider can replace this behind the same interface.
"""

import hashlib
import math
import re

# The default matches the vector(N) column the migrations create. The mock used
# to hardcode 384 and ignore EMBEDDING_DIM entirely, so the documented setup in
# .env.example (AI_PROVIDER=mock + EMBEDDING_DIM=1024, the column width since
# migration 0010) wrote vectors Postgres rejected — and the failure was swallowed
# as a warning, leaving every ingested course silently unsearchable.
DEFAULT_EMBEDDING_DIMENSIONS = 1024

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _token_bucket_and_sign(token: str, dimensions: int) -> tuple[int, float]:
    digest = hashlib.sha256(token.encode()).digest()
    bucket = int.from_bytes(digest[:4], "big") % dimensions
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    return bucket, sign


def mock_embedding_model(dimensions: int) -> str:
    return f"mock-hashed-bow-{dimensions}"


class MockEmbeddingProvider:
    """Provider-interface wrapper around embed_text."""

    def __init__(self, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS):
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return mock_embedding_model(self._dimensions)

    def embed(self, text: str) -> list[float]:
        return embed_text(text, self._dimensions)


def embed_text(text: str, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS) -> list[float]:
    """Embed text into a deterministic, L2-normalised `dimensions`-wide vector."""
    vector = [0.0] * dimensions
    tokens = _TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return vector
    for token in tokens:
        bucket, sign = _token_bucket_and_sign(token, dimensions)
        vector[bucket] += sign
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        return vector
    return [component / norm for component in vector]
