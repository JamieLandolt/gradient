"""Recommendation candidate-pool bounding (FR-3.7.x perf: prompt size must not
scale with the whole catalogue — see docs/REVIEW_efficiency_ux.md)."""

from app.services.advisory import _bounded_candidate_pool


def make_courses(n: int, matching_codes: set[str] | None = None) -> list[dict]:
    matching_codes = matching_codes or set()
    courses = []
    for i in range(n):
        code = f"C{i:03d}"
        is_match = code in matching_codes
        courses.append(
            {
                "code": code,
                "title": "Machine Learning" if is_match else "Unrelated Topic",
                "description": "neural networks" if is_match else "something else",
            }
        )
    return courses


class TestBoundedCandidatePool:
    def test_returns_all_courses_when_under_the_cap(self):
        courses = make_courses(10)
        assert _bounded_candidate_pool(courses, [], cap=60) == courses

    def test_caps_the_pool_when_over_the_limit(self):
        courses = make_courses(200)
        pool = _bounded_candidate_pool(courses, [], cap=60)
        assert len(pool) == 60

    def test_prefers_interest_matching_courses_when_capping(self):
        matching = {"C050", "C100", "C150"}
        courses = make_courses(200, matching_codes=matching)
        pool = _bounded_candidate_pool(courses, ["machine learning"], cap=60)

        pool_codes = {c["code"] for c in pool}
        assert len(pool) == 60
        assert matching <= pool_codes  # all interest matches survive the cap

    def test_falls_back_to_a_plain_cap_without_interests(self):
        courses = make_courses(200)
        pool = _bounded_candidate_pool(courses, [], cap=60)
        assert len(pool) == 60
        assert pool == courses[:60]
