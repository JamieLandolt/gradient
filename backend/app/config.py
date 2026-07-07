"""Application settings, loaded from the environment and validated at startup.

The app fails fast with a clear message if a required variable is missing
(NFR-5.3.5: secrets live in environment configuration, validated at startup).
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_anon_key: str = Field(alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    # Only needed for legacy HS256 projects; new projects verify via JWKS.
    supabase_jwt_secret: str = Field(default="", alias="SUPABASE_JWT_SECRET")

    ai_provider: Literal["mock", "ollama", "anthropic"] = Field(
        default="mock", alias="AI_PROVIDER"
    )
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    @field_validator("supabase_url", "supabase_anon_key", "supabase_service_role_key")
    @classmethod
    def must_not_be_blank(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Load settings once; raises a validation error listing missing variables."""
    try:
        return Settings()
    except Exception as exc:  # re-raise with a friendlier hint
        raise RuntimeError(
            "Configuration error — check backend/.env against .env.example: "
            f"{exc}"
        ) from exc
