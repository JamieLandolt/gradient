"""Target-grade calculator: required marks on remaining assessment (FR-3.3.x)."""

import pytest

from app.domain.calculation.models import (
    AssessmentItem,
    InvalidAssessmentStructureError,
    TargetStatus,
)
from app.domain.calculation.required_marks import compute_required_marks


def item(name: str, weight: float, max_mark: float = 100, score: float | None = None,
         hurdle: float | None = None) -> AssessmentItem:
    return AssessmentItem(
        name=name, weight=weight, max_mark=max_mark, score=score, hurdle_min_percent=hurdle
    )


class TestRequiredAverageFormula:
    def test_required_average_matches_srs_formula(self):
        # secured = 80% of 40 = 32; target grade 4 -> 50%; remaining weight 60
        # required = (50 - 32) / 60 * 100 = 30%
        result = compute_required_marks(
            [item("A1", 40, score=80), item("Exam", 60)], target_grade=4
        )

        assert result.status is TargetStatus.REACHABLE
        assert result.required_average_percent == pytest.approx(30.0)

    def test_higher_target_requires_more(self):
        # target 6 -> 75%: required = (75 - 32) / 60 * 100 = 71.67%
        result = compute_required_marks(
            [item("A1", 40, score=80), item("Exam", 60)], target_grade=6
        )

        assert result.required_average_percent == pytest.approx(71.6667, abs=1e-3)

    def test_default_target_is_a_pass(self):
        result = compute_required_marks([item("A1", 40, score=80), item("Exam", 60)])

        assert result.target_grade == 4
        assert result.target_percent == pytest.approx(50.0)

    def test_custom_cutoffs_change_the_target_percent(self):
        custom = {7: 80, 6: 70, 5: 60, 4: 50, 3: 45, 2: 20, 1: 0}
        result = compute_required_marks(
            [item("A1", 40, score=80), item("Exam", 60)],
            target_grade=7,
            grade_cutoffs=custom,
        )

        # required = (80 - 32) / 60 * 100 = 80%
        assert result.required_average_percent == pytest.approx(80.0)


class TestBoundaryCases:
    def test_already_secured(self):
        # secured = 90% of 60 = 54 >= 50 -> pass already secured
        result = compute_required_marks(
            [item("A1", 60, score=90), item("Exam", 40)], target_grade=4
        )

        assert result.status is TargetStatus.ALREADY_SECURED
        assert result.required_average_percent == 0.0

    def test_not_reachable(self):
        # secured = 10% of 60 = 6; target 7 -> 85; required = (85-6)/40*100 = 197.5
        result = compute_required_marks(
            [item("A1", 60, score=10), item("Exam", 40)], target_grade=7
        )

        assert result.status is TargetStatus.NOT_REACHABLE
        assert result.required_average_percent is None

    def test_locked_when_no_assessment_remains(self):
        result = compute_required_marks(
            [item("A1", 50, score=80), item("Exam", 50, score=60)], target_grade=7
        )

        assert result.status is TargetStatus.LOCKED
        assert result.final_percent == pytest.approx(70.0)
        assert result.final_grade == 5

    def test_exactly_reachable_at_100_percent(self):
        # secured = 40% of 50 = 20; target 5 -> 65:
        # required = (65-20)/50*100 = 90 -> reachable (barely)
        result = compute_required_marks(
            [item("A1", 50, score=40), item("Exam", 50)], target_grade=5
        )

        assert result.status is TargetStatus.REACHABLE
        assert result.required_average_percent == pytest.approx(90.0)


class TestHurdles:
    def test_failed_hurdle_on_completed_item_blocks_target(self):
        # Exam hurdle 40%, scored 30% -> blocked even though weighted total fine
        result = compute_required_marks(
            [item("A1", 50, score=95), item("Exam", 50, score=30, hurdle=40)],
            target_grade=4,
        )

        assert result.hurdle_blocked is True
        assert any("Exam" in warning for warning in result.hurdle_warnings)

    def test_remaining_hurdle_item_requirement_is_at_least_the_hurdle(self):
        # secured = 90% of 80 = 72; target 4 -> required avg = (50-72)/20*100 <= 0
        # -> ALREADY_SECURED by weight, but the exam still carries a 40% hurdle
        result = compute_required_marks(
            [item("A1", 80, score=90), item("Exam", 20, hurdle=40)], target_grade=4
        )

        assert result.status is TargetStatus.ALREADY_SECURED
        exam_row = next(r for r in result.per_item if r.name == "Exam")
        assert exam_row.required_percent == pytest.approx(40.0)
        assert result.hurdle_blocked is False

    def test_per_item_requirement_is_max_of_uniform_and_hurdle(self):
        # secured = 32; target 6 -> uniform required = 71.67 > hurdle 40
        result = compute_required_marks(
            [item("A1", 40, score=80), item("Exam", 60, hurdle=40)], target_grade=6
        )

        exam_row = next(r for r in result.per_item if r.name == "Exam")
        assert exam_row.required_percent == pytest.approx(71.6667, abs=1e-3)


class TestWhatIf:
    def test_what_if_score_shifts_requirement_to_other_items(self):
        # Hypothetical 90 on A2 (30 weight): secured = 32 + 27 = 59
        # remaining = Exam 30; target 6 -> (75-59)/30*100 = 53.33
        result = compute_required_marks(
            [item("A1", 40, score=80), item("A2", 30), item("Exam", 30)],
            target_grade=6,
            what_if_scores={"A2": 90},
        )

        assert result.required_average_percent == pytest.approx(53.3333, abs=1e-3)
        per_item_names = [r.name for r in result.per_item]
        assert "A2" not in per_item_names  # treated as completed under the hypothesis

    def test_what_if_for_unknown_item_rejected(self):
        with pytest.raises(InvalidAssessmentStructureError):
            compute_required_marks(
                [item("A1", 100, score=50)], what_if_scores={"Nope": 90}
            )


class TestValidation:
    def test_invalid_target_grade_rejected(self):
        with pytest.raises(InvalidAssessmentStructureError):
            compute_required_marks([item("A1", 100)], target_grade=8)

    def test_weights_must_sum_to_100(self):
        with pytest.raises(InvalidAssessmentStructureError):
            compute_required_marks([item("A1", 30), item("Exam", 30)])
