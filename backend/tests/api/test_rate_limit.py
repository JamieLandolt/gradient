"""Rate limiting on the endpoints that cost money per call."""

import time

import pytest

from app.core.auth import AuthUser
from app.core.errors import RateLimitedError
from app.core.rate_limit import RateLimit, SlidingWindowLimiter, get_limiter
from tests.api.fakes import build_client

ALICE = AuthUser(id="user-alice", email="alice@uq.test")


class TestSlidingWindow:
    def test_allows_up_to_the_limit_then_rejects(self):
        limiter = SlidingWindowLimiter()
        limit = RateLimit(requests=3, window_s=60)

        for i in range(3):
            limiter.check("caller", limit, now=100.0 + i)
        with pytest.raises(RateLimitedError):
            limiter.check("caller", limit, now=103.0)

    def test_the_window_slides_so_the_allowance_comes_back(self):
        limiter = SlidingWindowLimiter()
        limit = RateLimit(requests=2, window_s=60)
        limiter.check("caller", limit, now=100.0)
        limiter.check("caller", limit, now=101.0)

        with pytest.raises(RateLimitedError):
            limiter.check("caller", limit, now=102.0)
        limiter.check("caller", limit, now=161.5)  # first hit has aged out

    def test_callers_have_independent_allowances(self):
        limiter = SlidingWindowLimiter()
        limit = RateLimit(requests=1, window_s=60)
        limiter.check("alice", limit, now=100.0)

        limiter.check("bob", limit, now=100.0)  # must not raise

    def test_idle_callers_are_evicted_so_the_map_does_not_grow_forever(self):
        limiter = SlidingWindowLimiter()
        limit = RateLimit(requests=5, window_s=1)
        for i in range(50):
            limiter.check(f"caller-{i}", limit, now=100.0)

        limiter.check("recent", limit, now=100_000.0)

        assert len(limiter._hits) == 1

    def test_the_message_tells_the_caller_when_to_retry(self):
        limiter = SlidingWindowLimiter()
        limit = RateLimit(requests=1, window_s=60)
        limiter.check("caller", limit, now=100.0)

        with pytest.raises(RateLimitedError, match=r"wait \d+s"):
            limiter.check("caller", limit, now=110.0)


class TestSearchIsProtected:
    def test_unauthenticated_search_is_capped_and_returns_429(self):
        """/search/courses needs no auth (FR-3.9.2) but embeds the query via a
        billed API, so an anonymous loop must not be able to spend without limit."""
        get_limiter().reset()
        client, _, _ = build_client(user=ALICE)

        codes = [
            client.get(f"/api/v1/search/courses?q=databases{i}").status_code
            for i in range(35)
        ]

        assert codes[0] == 200
        assert 429 in codes
        assert codes.count(200) == 30  # _SEARCH_LIMIT

    def test_a_rejected_call_uses_the_standard_error_envelope(self):
        get_limiter().reset()
        client, _, _ = build_client(user=ALICE)
        for _ in range(30):
            client.get("/api/v1/search/courses?q=x")

        response = client.get("/api/v1/search/courses?q=x")
        body = response.json()

        assert response.status_code == 429
        assert body["success"] is False
        assert "Too many requests" in body["error"]
        assert body["data"] is None


def test_the_dependency_uses_a_real_clock():
    """Guards against the limiter being wired up with a frozen `now`, which
    would make every window infinite and silently disable it."""
    get_limiter().reset()
    client, _, _ = build_client(user=ALICE)
    started = time.monotonic()

    client.get("/api/v1/search/courses?q=clock")

    hits = [t for window in get_limiter()._hits.values() for t in window]
    assert hits and all(started <= t <= time.monotonic() for t in hits)
