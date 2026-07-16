"""Sliding-window rate limiting for expensive endpoints.

Scope, stated plainly: this is an in-process limiter. It exists because the AI
endpoints cost real money per call — `GET /search/courses` needs no auth and
embeds its query via a billed API, so an anonymous loop could run up the bill
unbounded. One process holding one dict closes that hole with no new
infrastructure, which is the right trade for a single-worker deployment.

It is NOT a general defence: run more than one worker and each gets its own
allowance, and a distributed attacker rotating IPs is unaffected. A real
deployment wants a shared store (Redis) and a limiter at the edge.
"""

import time
from collections import deque
from dataclasses import dataclass

from fastapi import Request

from app.core.auth import decode_token_subject
from app.core.errors import RateLimitedError

# Entries idle for longer than this are dropped on the next sweep, so the dict
# tracks only recent callers rather than growing for the process's lifetime.
_IDLE_EVICTION_S = 300.0


@dataclass(frozen=True)
class RateLimit:
    """`requests` calls allowed per `window_s`, per caller."""

    requests: int
    window_s: float


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._last_sweep = 0.0

    def check(self, key: str, limit: RateLimit, now: float) -> None:
        """Record a hit for `key`, or raise RateLimitedError if it's over."""
        self._sweep(now)
        window = self._hits.setdefault(key, deque())
        cutoff = now - limit.window_s
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= limit.requests:
            retry_in = max(1, int(window[0] + limit.window_s - now))
            raise RateLimitedError(
                f"Too many requests — please wait {retry_in}s and try again."
            )
        window.append(now)

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < _IDLE_EVICTION_S:
            return
        self._last_sweep = now
        cutoff = now - _IDLE_EVICTION_S
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()
        self._last_sweep = 0.0


_limiter = SlidingWindowLimiter()


def get_limiter() -> SlidingWindowLimiter:
    return _limiter


def caller_key(request: Request) -> str:
    """Identify the caller: the authenticated subject where there is one, else
    the peer address. The token is only read for identity here — never trusted
    for authorisation, and an unverified/absent one just falls back to the IP.
    """
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        subject = decode_token_subject(header[7:])
        if subject:
            return f"user:{subject}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


def rate_limit(limit: RateLimit):
    """FastAPI dependency enforcing `limit` per caller on one route."""

    def dependency(request: Request) -> None:
        get_limiter().check(caller_key(request), limit, time.monotonic())

    return dependency
