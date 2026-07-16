"""Shared test fixtures: settings with dummy values and a TestClient app."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.rate_limit import get_limiter
from app.main import create_app
from app.services import advisory


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The limiter is process-global (see core/rate_limit.py), so without this a
    test suite hammering an endpoint would start 429-ing later tests."""
    get_limiter().reset()
    yield
    get_limiter().reset()


@pytest.fixture(autouse=True)
def _reset_recommend_cache():
    """The recommend() cache is module-level (shared across requests within a
    process, see advisory.py), so it must not leak between tests — otherwise a
    cache hit here can return a stale result from a different test's isolated
    fake database, keyed only by (user_id, interests, completed, limit)."""
    advisory._recommend_cache.clear()
    yield
    advisory._recommend_cache.clear()


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        SUPABASE_URL="https://test-project.supabase.co",
        SUPABASE_ANON_KEY="test-anon-key",
        SUPABASE_SERVICE_ROLE_KEY="test-service-role-key",
        AI_PROVIDER="mock",
        CORS_ORIGINS="http://localhost:5173",
    )


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings), raise_server_exceptions=False)
