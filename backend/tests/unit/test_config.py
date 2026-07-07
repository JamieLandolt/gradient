import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_load_from_explicit_values():
    settings = Settings(
        SUPABASE_URL="https://x.supabase.co",
        SUPABASE_ANON_KEY="anon",
        SUPABASE_SERVICE_ROLE_KEY="service",
        _env_file=None,
    )

    assert settings.supabase_url == "https://x.supabase.co"
    assert settings.ai_provider == "mock"


def test_missing_required_variable_raises(monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_blank_required_variable_rejected():
    with pytest.raises(ValidationError):
        Settings(
            SUPABASE_URL="   ",
            SUPABASE_ANON_KEY="anon",
            SUPABASE_SERVICE_ROLE_KEY="service",
            _env_file=None,
        )


def test_invalid_ai_provider_rejected():
    with pytest.raises(ValidationError):
        Settings(
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_ANON_KEY="anon",
            SUPABASE_SERVICE_ROLE_KEY="service",
            AI_PROVIDER="not-a-provider",
            _env_file=None,
        )


def test_cors_origin_list_parses_csv():
    settings = Settings(
        SUPABASE_URL="https://x.supabase.co",
        SUPABASE_ANON_KEY="anon",
        SUPABASE_SERVICE_ROLE_KEY="service",
        CORS_ORIGINS="http://a.test, http://b.test",
        _env_file=None,
    )

    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]
