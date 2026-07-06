"""Prerequisite expression evaluation: met / partially met / not met (FR-3.6.4)."""

from app.domain.planning.models import PrereqNode, PrereqStatus
from app.domain.planning.prereq_ast import evaluate_prereq

COMP1000 = PrereqNode.course("COMP1000")
MATH1051 = PrereqNode.course("MATH1051")
MATH1071 = PrereqNode.course("MATH1071")

# The SRS example: COMP1000 and (MATH1051 or MATH1071)
SRS_EXAMPLE = PrereqNode.all_of(COMP1000, PrereqNode.any_of(MATH1051, MATH1071))


class TestLeafEvaluation:
    def test_no_prerequisites_is_met(self):
        result = evaluate_prereq(None, completed=frozenset())

        assert result.status is PrereqStatus.MET
        assert result.outstanding == ()

    def test_completed_course_leaf_is_met(self):
        result = evaluate_prereq(COMP1000, completed=frozenset({"COMP1000"}))

        assert result.status is PrereqStatus.MET

    def test_missing_course_leaf_is_not_met_and_named(self):
        result = evaluate_prereq(COMP1000, completed=frozenset())

        assert result.status is PrereqStatus.NOT_MET
        assert result.outstanding == ("COMP1000",)


class TestBooleanOperators:
    def test_and_with_all_completed_is_met(self):
        result = evaluate_prereq(
            SRS_EXAMPLE, completed=frozenset({"COMP1000", "MATH1051"})
        )

        assert result.status is PrereqStatus.MET

    def test_or_needs_only_one_branch(self):
        result = evaluate_prereq(
            SRS_EXAMPLE, completed=frozenset({"COMP1000", "MATH1071"})
        )

        assert result.status is PrereqStatus.MET

    def test_and_with_one_side_done_is_partially_met(self):
        result = evaluate_prereq(SRS_EXAMPLE, completed=frozenset({"COMP1000"}))

        assert result.status is PrereqStatus.PARTIALLY_MET
        assert set(result.outstanding) == {"MATH1051", "MATH1071"}

    def test_nothing_done_is_not_met(self):
        result = evaluate_prereq(SRS_EXAMPLE, completed=frozenset())

        assert result.status is PrereqStatus.NOT_MET
        assert set(result.outstanding) == {"COMP1000", "MATH1051", "MATH1071"}

    def test_met_or_branch_contributes_no_outstanding(self):
        result = evaluate_prereq(
            PrereqNode.any_of(MATH1051, MATH1071), completed=frozenset({"MATH1051"})
        )

        assert result.status is PrereqStatus.MET
        assert result.outstanding == ()


class TestNoteNodes:
    def test_note_is_never_silently_satisfied(self):
        node = PrereqNode.note("Year 12 Biology or equivalent")
        result = evaluate_prereq(node, completed=frozenset())

        assert result.status is not PrereqStatus.MET
        assert result.requires_manual_check is True

    def test_note_inside_or_with_met_branch_is_met_but_flagged(self):
        node = PrereqNode.any_of(COMP1000, PrereqNode.note("permission of course coordinator"))
        result = evaluate_prereq(node, completed=frozenset({"COMP1000"}))

        assert result.status is PrereqStatus.MET
        assert result.requires_manual_check is True
