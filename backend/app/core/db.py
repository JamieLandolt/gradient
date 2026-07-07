"""Supabase client factory (service role).

The service-role client bypasses RLS, so every repository method that touches
student data MUST filter by the authenticated user's id — see docs/architecture.md.
"""

from functools import lru_cache

from supabase import Client, create_client

from app.config import Settings


@lru_cache(maxsize=1)
def _cached_client(url: str, service_role_key: str) -> Client:
    return create_client(url, service_role_key)


def get_supabase_client(settings: Settings) -> Client:
    return _cached_client(settings.supabase_url, settings.supabase_service_role_key)
