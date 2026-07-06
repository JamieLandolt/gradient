"""GPA / WGPA weighted by unit value (FR-3.2.5)."""

import pytest

from app.domain.calculation.gpa import compute_gpa
from app.domain.calculation.models import GpaEntry, InvalidAssessmentStructureError


class TestGpa:
    def test_single_course(self):
        result = compute_gpa([GpaEntry(grade=6, units=2)])

        assert result == pytest.approx(6.0)

    def test_weighted_by_units(self):
        # (7*2 + 4*4) / 6 = 30/6 = 5.0
        result = compute_gpa([GpaEntry(grade=7, units=2), GpaEntry(grade=4, units=4)])

        assert result == pytest.approx(5.0)

    def test_equal_units_is_plain_average(self):
        result = compute_gpa(
            [GpaEntry(grade=5, units=2), GpaEntry(grade=6, units=2), GpaEntry(grade=7, units=2)]
        )

        assert result == pytest.approx(6.0)

    def test_fails_count_toward_gpa(self):
        # (2*2 + 6*2) / 4 = 4.0 — failing grades drag the GPA down
        result = compute_gpa([GpaEntry(grade=2, units=2), GpaEntry(grade=6, units=2)])

        assert result == pytest.approx(4.0)

    def test_no_courses_returns_none(self):
        assert compute_gpa([]) is None

    def test_invalid_grade_rejected(self):
        with pytest.raises(InvalidAssessmentStructureError):
            compute_gpa([GpaEntry(grade=8, units=2)])

    def test_non_positive_units_rejected(self):
        with pytest.raises(InvalidAssessmentStructureError):
            compute_gpa([GpaEntry(grade=5, units=0)])
