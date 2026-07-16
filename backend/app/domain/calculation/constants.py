"""Grading constants (SRS §1.2).

DEFAULT_GRADE_CUTOFFS are the default UQ 1–7 bands. They are not authoritative:
a course's ECP may override them via per-version grade_cutoffs rows.
"""

from types import MappingProxyType

# grade -> minimum final percentage for that grade
DEFAULT_GRADE_CUTOFFS: MappingProxyType[int, float] = MappingProxyType(
    {7: 85.0, 6: 75.0, 5: 65.0, 4: 50.0, 3: 45.0, 2: 20.0, 1: 0.0}
)

MIN_GRADE = 1
MAX_GRADE = 7
PASS_GRADE = 4

# A failed mandatory hurdle caps the course result below a pass regardless of the
# weighted total — the whole point of a hurdle. Reporting the raw weighted grade
# would tell a student who has already failed the hurdle that they passed.
MAX_GRADE_WITH_FAILED_HURDLE = 3

# Weights are validated to sum to 100 within this tolerance.
WEIGHT_SUM_TOLERANCE = 0.01
