"""Mock ECP extraction: round-trips on the sample profile files (FR-3.5.1)."""

from pathlib import Path

import pytest

from app.domain.planning.models import PrereqStatus
from app.domain.planning.prereq_ast import evaluate_prereq
from app.providers.mock.extraction import MockExtractionProvider

SAMPLES = Path(__file__).resolve().parents[3].parent / "seed" / "data" / "ecp_samples"


@pytest.fixture()
def provider() -> MockExtractionProvider:
    return MockExtractionProvider()


def read_sample(name: str) -> str:
    return (SAMPLES / name).read_text()


class TestComp2140Sample:
    def test_extracts_structure(self, provider):
        profile = provider.extract(read_sample("COMP2140_2026S2.txt"))

        assert profile.course_code == "COMP2140"
        assert profile.version_label == "2026S2"
        assert [a.weight for a in profile.assessments] == [30, 30, 40]
        assert profile.grade_cutoffs[7] == 85

    def test_hurdle_attached_to_final_exam(self, provider):
        profile = provider.extract(read_sample("COMP2140_2026S2.txt"))

        exam = next(a for a in profile.assessments if a.name == "Final Exam")
        assert exam.hurdle_min_percent == 40
        others = [a for a in profile.assessments if a.name != "Final Exam"]
        assert all(a.hurdle_min_percent is None for a in others)

    def test_prerequisite_or_expression(self, provider):
        profile = provider.extract(read_sample("COMP2140_2026S2.txt"))

        met = evaluate_prereq(profile.prerequisite_tree, frozenset({"CSSE7030"}))
        assert met.status is PrereqStatus.MET


class TestStat2003Sample:
    def test_nested_and_or_expression(self, provider):
        profile = provider.extract(read_sample("STAT2003_2026S1.txt"))

        # MATH1051 and (STAT1201 or MATH1061)
        partial = evaluate_prereq(profile.prerequisite_tree, frozenset({"MATH1051"}))
        assert partial.status is PrereqStatus.PARTIALLY_MET
        met = evaluate_prereq(
            profile.prerequisite_tree, frozenset({"MATH1051", "MATH1061"})
        )
        assert met.status is PrereqStatus.MET


class TestBiol1020Sample:
    def test_unparseable_prereq_becomes_manual_check_note(self, provider):
        profile = provider.extract(read_sample("BIOL1020_2026S1.txt"))

        evaluation = evaluate_prereq(profile.prerequisite_tree, frozenset())
        assert evaluation.requires_manual_check is True
        assert any("manual" in w.lower() for w in profile.warnings)


def test_extraction_is_deterministic(provider):
    text = read_sample("COMP2140_2026S2.txt")

    assert provider.extract(text) == provider.extract(text)


def test_missing_course_code_raises(provider):
    with pytest.raises(ValueError):
        provider.extract("Some random text without a profile")
