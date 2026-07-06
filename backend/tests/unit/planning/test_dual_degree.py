"""Dual-degree reconciliation: shared courses count once (FR-3.6.3)."""

from app.domain.planning.dual_degree import merge_required_courses
from app.domain.planning.models import ProgramRequirements


def program(
    code: str, required: tuple[str, ...], elective: tuple[str, ...] = ()
) -> ProgramRequirements:
    return ProgramRequirements(
        program_code=code, required=frozenset(required), elective=frozenset(elective)
    )


class TestMergeRequiredCourses:
    def test_single_program_passes_through(self):
        merged = merge_required_courses([program("BCompSc", ("CSSE1001", "MATH1051"))])

        assert merged.required == frozenset({"CSSE1001", "MATH1051"})

    def test_shared_required_course_counts_once(self):
        merged = merge_required_courses([
            program("BCompSc", ("CSSE1001", "COMP3506")),
            program("BInfTech", ("CSSE1001", "INFS1200")),
        ])

        assert merged.required == frozenset({"CSSE1001", "COMP3506", "INFS1200"})

    def test_course_required_in_one_and_elective_in_other_is_required(self):
        merged = merge_required_courses([
            program("BCompSc", required=("COMP3506",), elective=("INFS2200",)),
            program("BInfTech", required=("INFS2200",), elective=("COMP3506",)),
        ])

        assert "INFS2200" in merged.required
        assert "COMP3506" in merged.required
        assert merged.elective == frozenset()

    def test_electives_union_minus_required(self):
        merged = merge_required_courses([
            program("BCompSc", required=("CSSE1001",), elective=("STAT1201", "COMP3400")),
            program("BInfTech", required=("INFS1200",), elective=("STAT1201", "DECO1400")),
        ])

        assert merged.elective == frozenset({"STAT1201", "COMP3400", "DECO1400"})
