"""Courtesy crawler for public UQ course pages (programs-courses.uq.edu.au)
and Electronic Course Profiles (course-profiles.uq.edu.au).

Reads only PUBLIC pages (FR-3.5.1 / FR-3.5.5 — never student data): honours
each host's robots.txt, sends a descriptive User-Agent, throttles between
requests, and caches fetched HTML so a re-run doesn't re-hit the site. Returns
cleaned page text for the LLM extraction provider.
"""

import re
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path

import httpx

CATALOGUE_BASE = "https://programs-courses.uq.edu.au"
ECP_BASE = "https://course-profiles.uq.edu.au"
USER_AGENT = "GradientCourseImporter/0.1 (UQ student project; non-commercial)"
DEFAULT_THROTTLE_S = 1.5
MAX_TEXT_CHARS = 8000

_SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
# The catalogue page lists offerings newest-first; each has a "Course Profile"
# link. Current offerings link to course-profiles.uq.edu.au (matched here);
# older ones link to archive.course-profiles.uq.edu.au instead and are
# intentionally not matched — the first match is the current offering.
_ECP_LINK = re.compile(
    r'href="(https://course-profiles\.uq\.edu\.au/course-profiles/[^"]+)"'
    r'\s+target="_blank"\s+class="profile-available"'
)


class RobotsDisallowedError(RuntimeError):
    """Raised when robots.txt disallows fetching a page."""


class ECPNotFoundError(RuntimeError):
    """Raised when a course has no discoverable current Electronic Course Profile."""


def course_url(code: str) -> str:
    return f"{CATALOGUE_BASE}/course.html?course_code={urllib.parse.quote(code)}"


def find_current_ecp_url(catalogue_html: str) -> str | None:
    """Extract the current offering's ECP link from a catalogue page's HTML."""
    match = _ECP_LINK.search(catalogue_html)
    return match.group(1) if match else None


def html_to_text(html: str) -> str:
    """Strip scripts/styles/tags and collapse whitespace, bounded to MAX_TEXT_CHARS."""
    text = _SCRIPT_STYLE.sub(" ", html)
    text = _TAG.sub(" ", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip()[:MAX_TEXT_CHARS]


def _load_robots(base_url: str, user_agent: str) -> urllib.robotparser.RobotFileParser:
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(f"{base_url}/robots.txt")
    try:
        parser.read()
    except Exception:
        # No reachable robots.txt → default to allow (we still throttle + cap volume).
        parser.allow_all = True
    return parser


class UQCourseFetcher:
    def __init__(self, throttle_s: float = DEFAULT_THROTTLE_S, cache_dir: Path | None = None):
        self._throttle = throttle_s
        self._cache_dir = cache_dir
        self._http = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        self._robots = _load_robots(CATALOGUE_BASE, USER_AGENT)
        self._last_fetch = 0.0

    def _cache_path(self, code: str) -> Path | None:
        return None if self._cache_dir is None else self._cache_dir / f"{code}.html"

    def fetch_html(self, code: str) -> str:
        cache = self._cache_path(code)
        if cache is not None and cache.exists():
            return cache.read_text(encoding="utf-8", errors="replace")

        url = course_url(code)
        if not self._robots.can_fetch(USER_AGENT, url):
            raise RobotsDisallowedError(f"robots.txt disallows fetching {url}")

        elapsed = time.monotonic() - self._last_fetch
        if elapsed < self._throttle:
            time.sleep(self._throttle - elapsed)
        response = self._http.get(url)
        self._last_fetch = time.monotonic()
        response.raise_for_status()
        html = response.text

        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(html, encoding="utf-8")
        return html

    def fetch_text(self, code: str) -> str:
        return html_to_text(self.fetch_html(code))

    def close(self) -> None:
        self._http.close()


class ECPFetcher:
    """Fetches a course's current Electronic Course Profile as plain text.

    ECPs live on a different host (course-profiles.uq.edu.au) than the
    catalogue pages UQCourseFetcher reads, with their own robots.txt, so this
    keeps its own throttled/cached client rather than reusing UQCourseFetcher's.
    """

    def __init__(self, throttle_s: float = DEFAULT_THROTTLE_S, cache_dir: Path | None = None):
        self._throttle = throttle_s
        self._cache_dir = cache_dir
        self._http = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        self._robots = _load_robots(ECP_BASE, USER_AGENT)
        self._last_fetch = 0.0

    def _cache_path(self, code: str) -> Path | None:
        return None if self._cache_dir is None else self._cache_dir / f"{code}.ecp.html"

    def fetch_text(self, code: str, catalogue_html: str) -> str:
        """`catalogue_html` is the course's programs-courses.uq.edu.au page,
        used to find the current ECP's URL (there is no code-only ECP path)."""
        cache = self._cache_path(code)
        if cache is not None and cache.exists():
            return html_to_text(cache.read_text(encoding="utf-8", errors="replace"))

        url = find_current_ecp_url(catalogue_html)
        if url is None:
            raise ECPNotFoundError(f"No current course profile found for {code}")
        if not self._robots.can_fetch(USER_AGENT, url):
            raise RobotsDisallowedError(f"robots.txt disallows fetching {url}")

        elapsed = time.monotonic() - self._last_fetch
        if elapsed < self._throttle:
            time.sleep(self._throttle - elapsed)
        response = self._http.get(url)
        self._last_fetch = time.monotonic()
        response.raise_for_status()
        html = response.text

        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(html, encoding="utf-8")
        return html_to_text(html)

    def close(self) -> None:
        self._http.close()


def fetch_ecp_text(
    code: str, throttle_s: float = DEFAULT_THROTTLE_S, cache_dir: Path | None = None
) -> str:
    """Look up a course's current Electronic Course Profile and return its
    cleaned text: fetch the catalogue page, find that course's current ECP
    link on it, then fetch and clean the ECP page itself."""
    catalogue = UQCourseFetcher(throttle_s=throttle_s, cache_dir=cache_dir)
    ecp = ECPFetcher(throttle_s=throttle_s, cache_dir=cache_dir)
    try:
        catalogue_html = catalogue.fetch_html(code)
        return ecp.fetch_text(code, catalogue_html)
    finally:
        catalogue.close()
        ecp.close()
