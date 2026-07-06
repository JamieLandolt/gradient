"""Course standing: secured marks, best/worst case, projected grade (FR-3.2.4)."""

import pytest

from app.domain.calculation.models import AssessmentItem, InvalidAssessmentStructureError
from app.domain.calculation.standing import compute_standing


def item(name: str, weight: float, max_mark: float = 100, score: float | None = None,
         hurdle: float | None = None) -> AssessmentItem:
    return AssessmentItem(
        name=name, weight=weight, max_mark=max_mark, score=score, hurdle_min_percent=hurdle
    )


class TestSecuredAndRemaining:
    def test_no_marks_entered_yet(self):
        standing = compute_standing([item("A1", 40), item("Exam", 60)])

        assert standing.secured_percent == 0.0
        assert standing.remaining_weight == 100.0
        assert standing.best_case_percent == 100.0
        assert standing.worst_case_percent == 0.0

    def test_secured_is_weighted_sum_of_scored_items(self):
        # A1: 80/100 of 40% -> 32; Exam unscored
        standing = compute_standing([item("A1", 40, score=80), item("Exam", 60)])

        assert standing.secured_percent == pytest.approx(32.0)
        assert standing.remaining_weight == pytest.approx(60.0)
        assert standing.best_case_percent == pytest.approx(92.0)
        assert standing.worst_case_percent == pytest.approx(32.0)

    def test_score_out_of_non_100_max_mark_is_normalised(self):
        # 30/50 = 60% of a 25-weight item -> 15 percentage points
        standing = compute_standing([item("Mid", 25, max_mark=50, score=30), item("Exam", 75)])

        assert standing.secured_percent == pytest.approx(15.0)

    def test_all_items_scored_locks_the_result(self):
        standing = compute_standing(
            [item("A1", 40, score=90), item("Exam", 60, score=70)]
        )

        assert standing.remaining_weight == 0.0
        assert standing.secured_percent == pytest.approx(78.0)
        assert standing.best_case_percent == pytest.approx(78.0)
        assert standing.worst_case_percent == pytest.approx(78.0)


class TestProjectedGrade:
    def test_projection_extrapolates_current_average(self):
        # 80% average on the scored 40% -> projected final = 32 + 0.8*60 = 80 -> grade 6
        standing = compute_standing([item("A1", 40, score=80), item("Exam", 60)])

        assert standing.projected_percent == pytest.approx(80.0)
        assert standing.projected_grade == 6

    def test_no_scores_means_no_projection(self):
        standing = compute_standing([item("A1", 40), item("Exam", 60)])

        assert standing.projected_percent is None
        assert standing.projected_grade is None

    def test_locked_projection_uses_final_percentage(self):
        standing = compute_standing([item("A1", 50, score=50), item("Exam", 50, score=50)])

        assert standing.projected_percent == pytest.approx(50.0)
        assert standing.projected_grade == 4

    def test_custom_cutoffs_override_defaults(self):
        # 78% is grade 6 by default, but grade 7 with a cut-off of 78
        custom = {7: 78, 6: 70, 5: 60, 4: 50, 3: 45, 2: 20, 1: 0}
        standing = compute_standing(
            [item("A1", 100, score=78)], grade_cutoffs=custom
        )

        assert standing.projected_grade == 7

    def test_boundary_percent_maps_to_higher_grade(self):
        # exactly 85 -> grade 7; exactly 84.99 -> grade 6
        at_cutoff = compute_standing([item("All", 100, score=85)])
        below_cutoff = compute_standing([item("All", 100, score=84.99)])

        assert at_cutoff.projected_grade == 7
        assert below_cutoff.projected_grade == 6


class TestValidation:
    def test_weights_not_summing_to_100_rejected(self):
        with pytest.raises(InvalidAssessmentStructureError):
            compute_standing([item("A1", 40), item("Exam", 50)])

    def test_score_above_max_mark_rejected(self):
        with pytest.raises(InvalidAssessmentStructureError):
            compute_standing([item("A1", 40, max_mark=50, score=60), item("Exam", 60)])

    def test_empty_assessment_list_rejected(self):
        with pytest.raises(InvalidAssessmentStructureError):
            compute_standing([])

    def test_zero_weight_item_is_allowed(self):
        standing = compute_standing(
            [item("Practice", 0, score=100), item("A1", 40, score=80), item("Exam", 60)]
        )

        assert standing.secured_percent == pytest.approx(32.0)
