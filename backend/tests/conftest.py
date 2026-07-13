"""Shared test fixtures: settings with dummy values and a TestClient app."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


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
    return TestClient(create_app(settings), raise_server_exceptions=True)
