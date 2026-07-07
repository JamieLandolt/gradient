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

EMBEDDING_DIMENSIONS = 384
MOCK_EMBEDDING_MODEL = "mock-hashed-bow-384"

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _token_bucket_and_sign(token: str) -> tuple[int, float]:
    digest = hashlib.sha256(token.encode()).digest()
    bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    return bucket, sign


def embed_text(text: str) -> list[float]:
    """Embed text into a deterministic, L2-normalised 384-dim vector."""
    vector = [0.0] * EMBEDDING_DIMENSIONS
    tokens = _TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return vector
    for token in tokens:
        bucket, sign = _token_bucket_and_sign(token)
        vector[bucket] += sign
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        return vector
    return [component / norm for component in vector]
