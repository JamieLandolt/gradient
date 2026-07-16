"""Prerequisite expression evaluation (FR-3.6.4).

Status semantics:
- MET: the boolean expression is true against the completed-course set.
- PARTIALLY_MET: false, but at least one course leaf is satisfied.
- NOT_MET: false with no satisfied leaf.
`note` leaves (unparseable fragments) are never silently satisfied; they set
requires_manual_check so the UI can tell the student to verify by hand.
"""

import logging
from dataclasses import dataclass

from app.domain.planning.models import PrereqEvaluation, PrereqNode, PrereqStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _NodeOutcome:
    satisfied: bool
    any_leaf_satisfied: bool
    outstanding: tuple[str, ...]
    requires_manual_check: bool


def _dedupe(codes: list[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for code in codes:
        seen.setdefault(code)
    return tuple(seen)


def _evaluate(node: PrereqNode, completed: frozenset[str]) -> _NodeOutcome:
    if node.node_type == "course":
        is_done = node.code in completed
        return _NodeOutcome(
            satisfied=is_done,
            any_leaf_satisfied=is_done,
            outstanding=() if is_done else (node.code,),
            requires_manual_check=False,
        )

    if node.node_type == "note":
        return _NodeOutcome(
            satisfied=False,
            any_leaf_satisfied=False,
            outstanding=(),
            requires_manual_check=True,
        )

    child_outcomes = [_evaluate(child, completed) for child in node.children]
    any_leaf = any(outcome.any_leaf_satisfied for outcome in child_outcomes)
    manual = any(outcome.requires_manual_check for outcome in child_outcomes)

    if node.node_type == "and":
        # A childless `and` is vacuously satisfied — it constrains nothing, the
        # same as having no prerequisite tree at all. Treating it as False made
        # such a course permanently unplaceable and the whole plan infeasible.
        satisfied = all(o.satisfied for o in child_outcomes)
        outstanding = _dedupe(
            [code for o in child_outcomes if not o.satisfied for code in o.outstanding]
        )
        return _NodeOutcome(satisfied, any_leaf, outstanding, manual)

    if node.node_type == "or":
        satisfied = any(o.satisfied for o in child_outcomes)
        outstanding = () if satisfied else _dedupe(
            [code for o in child_outcomes for code in o.outstanding]
        )
        # An OR already satisfied by a fully-parsed branch needs no manual check:
        # the unparsed sibling is an alternative route the student doesn't need.
        # "X or permission of head" is pervasive in UQ profiles, so propagating it
        # regardless warned on a large share of courses and buried the real ones.
        return _NodeOutcome(satisfied, any_leaf, outstanding, False if satisfied else manual)

    # An unrecognised node_type is bad data (the column is passed through from
    # the DB unchecked). Raising here escaped build_plan and took down the whole
    # plan request; degrading to "unparseable" blocks the one course instead and
    # tells the student to check it — never silently satisfied.
    logger.warning("Unknown prerequisite node type %r; treating as unparseable", node.node_type)
    return _NodeOutcome(
        satisfied=False, any_leaf_satisfied=False, outstanding=(), requires_manual_check=True
    )


def evaluate_prereq(node: PrereqNode | None, completed: frozenset[str]) -> PrereqEvaluation:
    """Evaluate a course's prerequisite tree against completed course codes."""
    if node is None:
        return PrereqEvaluation(status=PrereqStatus.MET, outstanding=())

    outcome = _evaluate(node, completed)
    if outcome.satisfied:
        status = PrereqStatus.MET
    elif outcome.requires_manual_check and not outcome.outstanding:
        # Nothing identifiable is missing — the expression is only unresolved
        # because part of it isn't machine-readable. Calling that NOT_MET told
        # first-year students their prerequisites were unmet when the real
        # requirement was high-school maths, and contradicted the planner, which
        # schedules these courses.
        status = PrereqStatus.NEEDS_MANUAL_CHECK
    elif outcome.any_leaf_satisfied:
        status = PrereqStatus.PARTIALLY_MET
    else:
        status = PrereqStatus.NOT_MET

    return PrereqEvaluation(
        status=status,
        outstanding=outcome.outstanding,
        requires_manual_check=outcome.requires_manual_check,
    )


def eligibility(node: PrereqNode | None, available: frozenset[str]) -> tuple[bool, bool]:
    """(can_take, needs_manual_check) for a prerequisite tree.

    The single source of truth for "can this course be taken given these
    completed courses", shared by the scheduler and the cycle detector so the
    two can never disagree about what is satisfiable. An expression blocked
    ONLY by unparseable note fragments (no outstanding courses) is let through
    with a manual-check warning rather than blocking the plan forever; it is
    never silently treated as satisfied.
    """
    evaluation = evaluate_prereq(node, available)
    if evaluation.status is PrereqStatus.MET:
        return True, evaluation.requires_manual_check
    if evaluation.status is PrereqStatus.NEEDS_MANUAL_CHECK:
        return True, True
    return False, False


def collect_course_codes(node: PrereqNode | None) -> frozenset[str]:
    """All course codes referenced anywhere in a prerequisite tree."""
    if node is None:
        return frozenset()
    if node.node_type == "course":
        return frozenset({node.code}) if node.code else frozenset()
    codes: set[str] = set()
    for child in node.children:
        codes |= collect_course_codes(child)
    return frozenset(codes)
