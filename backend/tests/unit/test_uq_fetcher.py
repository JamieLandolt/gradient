"""Unit tests for the UQ course fetcher's pure helpers (no network)."""

from app.ingestion.uq_fetcher import MAX_TEXT_CHARS, course_url, html_to_text


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
