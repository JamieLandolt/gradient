"""Supabase JWT verification (NFR-5.3.1).

Tokens are verified locally — no per-request round-trip to Supabase:
- Asymmetric projects (current default): keys fetched from the project's JWKS
  endpoint and cached by PyJWKClient (ES256/RS256).
- Legacy projects: HS256 with SUPABASE_JWT_SECRET when configured.
"""

import ssl
import time
from dataclasses import dataclass
from functools import lru_cache

import certifi
import jwt
from fastapi import Request

from app.config import Settings
from app.core.errors import UnauthorizedError

SUPPORTED_ASYMMETRIC_ALGORITHMS = ["ES256", "RS256"]
EXPECTED_AUDIENCE = "authenticated"
JWKS_RETRY_DELAY_SECONDS = 0.5
# Tolerate small clock differences between this host and the auth server
# (a 2s skew was observed rejecting freshly issued tokens as "not yet valid").
CLOCK_SKEW_LEEWAY_SECONDS = 10


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str | None


@lru_cache(maxsize=4)
def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    # Explicit CA bundle: framework Python builds often lack system certs,
    # which would make every JWKS fetch (and so every login) fail.
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    return jwt.PyJWKClient(
        f"{supabase_url}/auth/v1/.well-known/jwks.json",
        cache_keys=True,
        ssl_context=ssl_context,
    )


def _signing_key_with_retry(supabase_url: str, token: str):
    """Fetch the token's signing key, retrying once on transient network failure.

    The JWKS fetch happens only on a cold cache; a network blip there must not
    401 an otherwise-valid session.
    """
    client = _jwks_client(supabase_url)
    try:
        return client.get_signing_key_from_jwt(token)
    except jwt.exceptions.PyJWKClientConnectionError:
        time.sleep(JWKS_RETRY_DELAY_SECONDS)
        return client.get_signing_key_from_jwt(token)


def decode_token(token: str, settings: Settings) -> dict:
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg", "")
    try:
        if algorithm in SUPPORTED_ASYMMETRIC_ALGORITHMS:
            signing_key = _signing_key_with_retry(settings.supabase_url, token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=SUPPORTED_ASYMMETRIC_ALGORITHMS,
                audience=EXPECTED_AUDIENCE,
                leeway=CLOCK_SKEW_LEEWAY_SECONDS,
            )
        if algorithm == "HS256" and settings.supabase_jwt_secret:
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=EXPECTED_AUDIENCE,
                leeway=CLOCK_SKEW_LEEWAY_SECONDS,
            )
        raise UnauthorizedError("Unsupported token signing algorithm")
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired session") from exc


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("Missing bearer token")
    return token.strip()


def get_current_user(request: Request) -> AuthUser:
    """FastAPI dependency: the authenticated user from the Supabase JWT."""
    settings: Settings = request.app.state.settings
    claims = decode_token(_bearer_token(request), settings)
    user_id = claims.get("sub")
    if not user_id:
        raise UnauthorizedError("Token has no subject")
    return AuthUser(id=user_id, email=claims.get("email"))
