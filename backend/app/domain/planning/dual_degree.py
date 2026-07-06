"""Dual-degree reconciliation (FR-3.6.3).

A course required by either program is required once in the merged plan;
electives are the union of both programs' electives minus anything required.
"""

from app.domain.planning.models import MergedRequirements, ProgramRequirements


def merge_required_courses(programs: list[ProgramRequirements]) -> MergedRequirements:
    required: frozenset[str] = frozenset()
    elective: frozenset[str] = frozenset()
    for program in programs:
        required |= program.required
        elective |= program.elective
    return MergedRequirements(required=required, elective=elective - required)
