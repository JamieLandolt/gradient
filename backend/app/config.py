"""Application settings, loaded from the environment and validated at startup.

Two modes:
- APP_MODE=demo (default): no external services; the API serves the sample
  catalogue from seed JSON with an in-memory single-user store. Zero setup.
- APP_MODE=supabase: full multi-user mode; the Supabase variables become
  mandatory and startup fails fast with a clear message if any is missing
  (NFR-5.3.5).
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: Literal["demo", "supabase"] = Field(default="demo", alias="APP_MODE")

    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    # Only needed for legacy HS256 projects; new projects verify via JWKS.
    supabase_jwt_secret: str = Field(default="", alias="SUPABASE_JWT_SECRET")

    ai_provider: Literal["mock", "ollama", "anthropic"] = Field(
        default="mock", alias="AI_PROVIDER"
    )
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    @model_validator(mode="after")
    def require_supabase_config_in_supabase_mode(self) -> "Settings":
        if self.app_mode != "supabase":
            return self
        missing = [
            name
            for name, value in (
                ("SUPABASE_URL", self.supabase_url),
                ("SUPABASE_ANON_KEY", self.supabase_anon_key),
                ("SUPABASE_SERVICE_ROLE_KEY", self.supabase_service_role_key),
            )
            if not value.strip()
        ]
        if missing:
            raise ValueError(
                f"APP_MODE=supabase requires {', '.join(missing)} — see .env.example"
            )
        return self

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
