"""Supabase JWT verification (NFR-5.3.1).

Tokens are verified locally — no per-request round-trip to Supabase:
- Asymmetric projects (current default): keys fetched from the project's JWKS
  endpoint and cached by PyJWKClient (ES256/RS256).
- Legacy projects: HS256 with SUPABASE_JWT_SECRET when configured.
"""

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Request

from app.config import Settings
from app.core.errors import UnauthorizedError

SUPPORTED_ASYMMETRIC_ALGORITHMS = ["ES256", "RS256"]
EXPECTED_AUDIENCE = "authenticated"


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str | None


@lru_cache(maxsize=4)
def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(
        f"{supabase_url}/auth/v1/.well-known/jwks.json", cache_keys=True
    )


def decode_token(token: str, settings: Settings) -> dict:
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg", "")
    try:
        if algorithm in SUPPORTED_ASYMMETRIC_ALGORITHMS:
            signing_key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=SUPPORTED_ASYMMETRIC_ALGORITHMS,
                audience=EXPECTED_AUDIENCE,
            )
        if algorithm == "HS256" and settings.supabase_jwt_secret:
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=EXPECTED_AUDIENCE,
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
