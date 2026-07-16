"""Percent → 1–7 grade mapping, especially with partial ECP cut-offs.

An extracted ECP normally only states the 4–7 bands (most UQ profiles describe
where a pass/credit/distinction/HD starts and say nothing about 1–3), so the
partial-map cases here are the realistic ones, not edge cases.
"""

import pytest

from app.domain.calculation.constants import DEFAULT_GRADE_CUTOFFS
from app.domain.calculation.grading import grade_for_percent, resolve_cutoffs
from app.domain.calculation.models import AssessmentItem
from app.domain.calculation.required_marks import compute_required_marks
from app.domain.calculation.standing import compute_standing

# What an LLM typically extracts from a real ECP: the pass-and-above bands only.
PARTIAL_CUTOFFS = {7: 85.0, 6: 75.0, 5: 65.0, 4: 50.0}


class TestDefaultCutoffs:
    @pytest.mark.parametrize(
        ("percent", "expected"),
        [(100, 7), (85, 7), (84.9, 6), (75, 6), (65, 5), (50, 4), (49.9, 3),
         (45, 3), (20, 2), (19.9, 1), (0, 1)],
    )
    def test_boundaries_are_inclusive_at_the_cutoff(self, percent, expected):
        assert grade_for_percent(percent) == expected


class TestPartialEcpCutoffs:
    """A mark below every stated band must not be reported as the lowest stated
    grade — that band is a PASS, so a failing student would be shown passing."""

    @pytest.mark.parametrize(
        ("percent", "expected"),
        [(5, 1), (0, 1), (19.9, 1), (20, 2), (44.9, 2), (45, 3), (49.9, 3)],
    )
    def test_marks_below_the_lowest_stated_band_fall_back_to_uq_defaults(
        self, percent, expected
    ):
        assert grade_for_percent(percent, PARTIAL_CUTOFFS) == expected

    def test_a_failing_mark_is_never_reported_as_a_pass(self):
        assert grade_for_percent(5.0, PARTIAL_CUTOFFS) < 4

    def test_stated_bands_still_win_over_the_defaults(self):
        stricter = {4: 55.0}
        assert grade_for_percent(54.9, stricter) == 3
        assert grade_for_percent(55.0, stricter) == 4


class TestFloatAccumulationAtCutoffs:
    """Weighted totals arrive a few ulps off an exact cut-off. Comparing raw
    drops a whole grade, on precisely the marks students care about most."""

    @pytest.mark.parametrize(
        ("scores", "exact_total", "expected_grade"),
        [
            ((40, 40, 72, 41), 50.0, 4),  # 49.99999999999999 -> was 3 (fail)
            ((40, 94, 82, 94), 85.0, 7),  # 84.99999999999999 -> was 6
            ((40, 94, 82, 69), 75.0, 6),  # 74.99999999999999 -> was 5
        ],
    )
    def test_a_total_landing_exactly_on_a_cutoff_gets_that_grade(
        self, scores, exact_total, expected_grade
    ):
        weights = (10.0, 20.0, 30.0, 40.0)
        items = [
            AssessmentItem(name=f"i{n}", weight=w, max_mark=100.0, score=float(s))
            for n, (w, s) in enumerate(zip(weights, scores, strict=True))
        ]
        standing = compute_standing(items)

        assert standing.secured_percent == pytest.approx(exact_total)
        assert standing.projected_grade == expected_grade

    def test_a_mark_genuinely_below_a_cutoff_still_fails(self):
        # Guard against over-correcting: 49.9 is really below 50 and must stay a 3.
        assert grade_for_percent(49.9) == 3


class TestResolveCutoffs:
    def test_none_or_empty_yields_the_uq_defaults(self):
        assert resolve_cutoffs(None) == DEFAULT_GRADE_CUTOFFS
        assert resolve_cutoffs({}) == DEFAULT_GRADE_CUTOFFS

    def test_partial_map_is_completed_with_defaults_for_every_grade(self):
        resolved = resolve_cutoffs(PARTIAL_CUTOFFS)

        assert set(resolved) == {1, 2, 3, 4, 5, 6, 7}
        assert resolved[4] == 50.0  # stated
        assert resolved[3] == DEFAULT_GRADE_CUTOFFS[3]  # filled in

    def test_does_not_mutate_the_callers_mapping(self):
        supplied = dict(PARTIAL_CUTOFFS)
        resolve_cutoffs(supplied)

        assert supplied == PARTIAL_CUTOFFS


class TestRequiredMarksWithPartialCutoffs:
    """required_marks does cutoffs[target_grade] — a grade the ECP never stated
    used to raise KeyError and surface as a 500."""

    @pytest.mark.parametrize("target", [1, 2, 3, 4, 5, 6, 7])
    def test_every_valid_target_grade_resolves_against_a_partial_map(self, target):
        items = [AssessmentItem(name="Exam", weight=100.0, max_mark=100.0, score=None)]

        result = compute_required_marks(
            items, target_grade=target, grade_cutoffs=PARTIAL_CUTOFFS
        )

        assert result.target_grade == target


class TestFailedHurdleCapsTheGrade:
    """A hurdle exists precisely so the weighted total can't carry a student who
    missed it. Reporting the raw weighted grade told a failing student they passed."""

    def _items_with_failed_hurdle(self):
        # 95/100 on half the course, but the exam hurdle (40%) was missed.
        return [
            AssessmentItem(name="A1", weight=50.0, max_mark=100.0, score=95.0),
            AssessmentItem(
                name="Exam", weight=50.0, max_mark=100.0, score=30.0,
                hurdle_min_percent=40.0,
                hurdle_description="Must score at least 40% on the final exam.",
            ),
        ]

    def test_projected_grade_cannot_be_a_pass(self):
        standing = compute_standing(self._items_with_failed_hurdle())

        assert standing.secured_percent == pytest.approx(62.5)
        assert standing.projected_grade == 3  # was 4 on the weighted total alone
        assert standing.hurdle_blocked is True
        assert standing.hurdle_warnings

    def test_locked_final_grade_cannot_be_a_pass(self):
        result = compute_required_marks(self._items_with_failed_hurdle(), target_grade=4)

        assert result.final_percent == pytest.approx(62.5)
        assert result.final_grade == 3
        assert result.hurdle_blocked is True

    def test_a_passing_target_is_not_reachable_once_a_hurdle_is_failed(self):
        # Plenty of weight left, so the arithmetic alone would say "reachable".
        items = [
            AssessmentItem(name="Quiz", weight=10.0, max_mark=100.0, score=10.0,
                           hurdle_min_percent=50.0),
            AssessmentItem(name="A1", weight=40.0, max_mark=100.0, score=90.0),
            AssessmentItem(name="Exam", weight=50.0, max_mark=100.0, score=None),
        ]

        result = compute_required_marks(items, target_grade=4)

        assert result.status.value == "not_reachable"
        assert result.required_average_percent is None
        assert result.hurdle_blocked is True

    def test_a_target_below_a_pass_is_still_reachable(self):
        items = [
            AssessmentItem(name="Quiz", weight=10.0, max_mark=100.0, score=10.0,
                           hurdle_min_percent=50.0),
            AssessmentItem(name="Exam", weight=90.0, max_mark=100.0, score=None),
        ]

        result = compute_required_marks(items, target_grade=3)

        assert result.status.value in {"reachable", "already_secured"}

    def test_a_hurdle_met_exactly_does_not_cap_anything(self):
        items = [
            AssessmentItem(name="A1", weight=50.0, max_mark=100.0, score=95.0),
            AssessmentItem(name="Exam", weight=50.0, max_mark=100.0, score=40.0,
                           hurdle_min_percent=40.0),
        ]

        standing = compute_standing(items)

        assert standing.hurdle_blocked is False
        assert standing.projected_grade == grade_for_percent(67.5)


class TestItemValidation:
    def test_an_out_of_range_hurdle_is_rejected(self):
        from app.domain.calculation.models import InvalidAssessmentStructureError

        items = [AssessmentItem(name="X", weight=100.0, max_mark=100.0,
                                hurdle_min_percent=150.0)]

        with pytest.raises(InvalidAssessmentStructureError, match="outside 0–100"):
            compute_standing(items)
