import pytest
from pydantic import ValidationError

from app.config import Settings


def test_demo_mode_needs_no_supabase_config():
    settings = Settings(_env_file=None)

    assert settings.app_mode == "demo"
    assert settings.ai_provider == "mock"


def test_supabase_mode_with_full_config_loads():
    settings = Settings(
        APP_MODE="supabase",
        SUPABASE_URL="https://x.supabase.co",
        SUPABASE_ANON_KEY="anon",
        SUPABASE_SERVICE_ROLE_KEY="service",
        _env_file=None,
    )

    assert settings.supabase_url == "https://x.supabase.co"


def test_supabase_mode_missing_keys_fails_fast(monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ValidationError, match="SUPABASE_URL"):
        Settings(APP_MODE="supabase", _env_file=None)


def test_supabase_mode_blank_key_rejected():
    with pytest.raises(ValidationError, match="SUPABASE_URL"):
        Settings(
            APP_MODE="supabase",
            SUPABASE_URL="   ",
            SUPABASE_ANON_KEY="anon",
            SUPABASE_SERVICE_ROLE_KEY="service",
            _env_file=None,
        )


def test_invalid_ai_provider_rejected():
    with pytest.raises(ValidationError):
        Settings(AI_PROVIDER="not-a-provider", _env_file=None)


def test_invalid_app_mode_rejected():
    with pytest.raises(ValidationError):
        Settings(APP_MODE="banana", _env_file=None)


def test_cors_origin_list_parses_csv():
    settings = Settings(CORS_ORIGINS="http://a.test, http://b.test", _env_file=None)

    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]
