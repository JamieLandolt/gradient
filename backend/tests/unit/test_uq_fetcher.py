"""Unit tests for the UQ course fetcher: pure helpers + cache/robots/throttle (no network)."""

import time
from urllib.robotparser import RobotFileParser

import httpx
import pytest

from app.ingestion import uq_fetcher
from app.ingestion.uq_fetcher import (
    MAX_TEXT_CHARS,
    ECPFetcher,
    ECPNotFoundError,
    RobotsDisallowedError,
    UQCourseFetcher,
    course_url,
    fetch_ecp_text,
    find_current_ecp_url,
    html_to_text,
)

# A trimmed excerpt of a real programs-courses.uq.edu.au offerings table (the
# current offering's link is listed first; older ones point to
# archive.course-profiles.uq.edu.au and must not be matched).
CATALOGUE_HTML_WITH_ECP = """
<tr id='course-offering-2'>
<td class="course-offering-profile" id='course-offering-2-profile'>
<a href="https://course-profiles.uq.edu.au/course-profiles/COMP3506-60808-7560"
   target="_blank" class="profile-available">
Course Profile
</a>
</td>
</tr>
<tr id='course-offering-3'>
<td class="course-offering-profile" id='course-offering-3-profile'>
<a href="https://archive.course-profiles.uq.edu.au/student_section_loader/section_1/130391"
   target="_blank" class="profile-available">
Course Profile
</a>
</td>
</tr>
"""


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


# ── ECP discovery + fetch ─────────────────────────────────────────────────────
def test_find_current_ecp_url_picks_the_first_non_archive_link():
    url = find_current_ecp_url(CATALOGUE_HTML_WITH_ECP)
    assert url == "https://course-profiles.uq.edu.au/course-profiles/COMP3506-60808-7560"


def test_find_current_ecp_url_is_none_when_only_archived_offerings_exist():
    archive_only = CATALOGUE_HTML_WITH_ECP.split("</tr>", 1)[1]  # drop the current offering
    assert find_current_ecp_url(archive_only) is None


def _make_ecp_fetcher(monkeypatch, handler, robots=_allow_robots, cache_dir=None, throttle=0.0):
    monkeypatch.setattr(uq_fetcher, "_load_robots", robots)
    fetcher = ECPFetcher(throttle_s=throttle, cache_dir=cache_dir)
    fetcher._http = httpx.Client(transport=httpx.MockTransport(handler))
    return fetcher


def test_ecp_fetcher_fetches_and_cleans_the_current_offering(monkeypatch):
    def handler(request):
        assert str(request.url) == (
            "https://course-profiles.uq.edu.au/course-profiles/COMP3506-60808-7560"
        )
        return httpx.Response(200, text="<h2>Assessment</h2><p>Weight: 50%</p>")

    fetcher = _make_ecp_fetcher(monkeypatch, handler)
    text = fetcher.fetch_text("COMP3506", CATALOGUE_HTML_WITH_ECP)

    assert "Assessment" in text
    assert "Weight: 50%" in text


def test_ecp_fetcher_raises_when_no_current_profile_is_linked(monkeypatch):
    def handler(_request):
        raise AssertionError("must not fetch when no current ECP link is found")

    fetcher = _make_ecp_fetcher(monkeypatch, handler)

    with pytest.raises(ECPNotFoundError):
        fetcher.fetch_text("COMP3506", "<p>no offerings table here</p>")


def test_ecp_fetcher_respects_robots_disallow(monkeypatch):
    def handler(_request):
        raise AssertionError("must not fetch when robots.txt disallows it")

    fetcher = _make_ecp_fetcher(monkeypatch, handler, robots=_deny_robots)

    with pytest.raises(RobotsDisallowedError):
        fetcher.fetch_text("COMP3506", CATALOGUE_HTML_WITH_ECP)


def test_ecp_fetcher_caches_to_disk(tmp_path, monkeypatch):
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(200, text="<p>ECP text</p>")

    fetcher = _make_ecp_fetcher(monkeypatch, handler, cache_dir=tmp_path)
    first = fetcher.fetch_text("COMP3506", CATALOGUE_HTML_WITH_ECP)
    second = fetcher.fetch_text("COMP3506", CATALOGUE_HTML_WITH_ECP)  # cache hit

    assert "ECP text" in first
    assert first == second
    assert calls["n"] == 1
    assert (tmp_path / "COMP3506.ecp.html").exists()


def test_fetch_ecp_text_composes_both_fetchers(monkeypatch):
    def handler(request):
        if "programs-courses" in str(request.url):
            return httpx.Response(200, text=CATALOGUE_HTML_WITH_ECP)
        return httpx.Response(200, text="<p>Composed ECP text</p>")

    monkeypatch.setattr(uq_fetcher, "_load_robots", _allow_robots)

    # Patch httpx.Client so both the catalogue and ECP fetchers created inside
    # fetch_ecp_text share the same mock transport instead of hitting the network.
    real_client = httpx.Client

    def mock_client(*_args, **kwargs):
        kwargs.pop("base_url", None)
        return real_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", mock_client)

    text = fetch_ecp_text("COMP3506")
    assert "Composed ECP text" in text
