"""Unit tests for the UQ course fetcher: pure helpers + cache/robots/throttle (no network)."""

import time
from urllib.robotparser import RobotFileParser

import httpx
import pytest

from app.ingestion import uq_fetcher
from app.ingestion.uq_fetcher import (
    MAX_TEXT_CHARS,
    RobotsDisallowedError,
    UQCourseFetcher,
    course_url,
    html_to_text,
)


def test_course_url_format():
    assert (
        course_url("COMP3506")
        == "https://programs-courses.uq.edu.au/course.html?course_code=COMP3506"
    )


def test_html_to_text_strips_scripts_styles_and_tags():
    html = (
        "<html><head><script>var x = 1;</script><style>.a{color:red}</style></head>"
        "<body><h1>Algorithms and Data Structures</h1>  <p>Prerequisite: CSSE2002</p></body></html>"
    )
    text = html_to_text(html)

    assert "Algorithms and Data Structures" in text
    assert "Prerequisite: CSSE2002" in text
    assert "var x" not in text
    assert "<h1>" not in text and "color:red" not in text


def test_html_to_text_collapses_whitespace():
    assert html_to_text("<p>a</p>\n\n   <p>b</p>") == "a b"


def test_html_to_text_truncates_to_cap():
    html = "<p>" + ("x" * (MAX_TEXT_CHARS + 500)) + "</p>"

    assert len(html_to_text(html)) == MAX_TEXT_CHARS


# ── Cache / robots / throttle (no real network; robots stubbed, HTTP mocked) ──
def _allow_robots(*_args, **_kwargs) -> RobotFileParser:
    parser = RobotFileParser()
    parser.allow_all = True
    return parser


def _deny_robots(*_args, **_kwargs) -> RobotFileParser:
    parser = RobotFileParser()
    parser.disallow_all = True
    return parser


def _make_fetcher(monkeypatch, handler, robots=_allow_robots, cache_dir=None, throttle=0.0):
    # Patch robots loading so the constructor never touches the network.
    monkeypatch.setattr(uq_fetcher, "_load_robots", robots)
    fetcher = UQCourseFetcher(throttle_s=throttle, cache_dir=cache_dir)
    fetcher._http = httpx.Client(
        transport=httpx.MockTransport(handler), base_url=uq_fetcher.CATALOGUE_BASE
    )
    return fetcher


def test_fetch_html_caches_to_disk_and_serves_from_cache(tmp_path, monkeypatch):
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(200, text="<p>COMP3506 page</p>")

    fetcher = _make_fetcher(monkeypatch, handler, cache_dir=tmp_path)
    first = fetcher.fetch_html("COMP3506")
    second = fetcher.fetch_html("COMP3506")  # cache hit — no second HTTP call

    assert "COMP3506 page" in first
    assert first == second
    assert calls["n"] == 1
    assert (tmp_path / "COMP3506.html").exists()


def test_existing_cache_is_used_without_any_fetch(tmp_path, monkeypatch):
    (tmp_path / "MATH1051.html").write_text("<p>cached</p>", encoding="utf-8")

    def handler(_request):
        raise AssertionError("must not hit the network when the page is cached")

    fetcher = _make_fetcher(monkeypatch, handler, cache_dir=tmp_path)

    assert "cached" in fetcher.fetch_html("MATH1051")


def test_robots_disallowed_raises_before_fetching(monkeypatch):
    def handler(_request):
        raise AssertionError("must not fetch when robots.txt disallows it")

    fetcher = _make_fetcher(monkeypatch, handler, robots=_deny_robots)

    with pytest.raises(RobotsDisallowedError):
        fetcher.fetch_html("COMP3506")


def test_throttle_waits_between_live_fetches(monkeypatch):
    def handler(_request):
        return httpx.Response(200, text="ok")

    fetcher = _make_fetcher(monkeypatch, handler, throttle=0.2)
    fetcher._last_fetch = time.monotonic()  # pretend a fetch just happened

    start = time.monotonic()
    fetcher.fetch_html("COMP3506")

    assert time.monotonic() - start >= 0.18  # throttled ~0.2s before the request
