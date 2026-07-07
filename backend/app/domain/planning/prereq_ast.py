"""Prerequisite expression evaluation (FR-3.6.4).

Status semantics:
- MET: the boolean expression is true against the completed-course set.
- PARTIALLY_MET: false, but at least one course leaf is satisfied.
- NOT_MET: false with no satisfied leaf.
`note` leaves (unparseable fragments) are never silently satisfied; they set
requires_manual_check so the UI can tell the student to verify by hand.
"""

from dataclasses import dataclass

from app.domain.planning.models import PrereqEvaluation, PrereqNode, PrereqStatus


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
        satisfied = bool(child_outcomes) and all(o.satisfied for o in child_outcomes)
        outstanding = _dedupe(
            [code for o in child_outcomes if not o.satisfied for code in o.outstanding]
        )
        return _NodeOutcome(satisfied, any_leaf, outstanding, manual)

    if node.node_type == "or":
        satisfied = any(o.satisfied for o in child_outcomes)
        outstanding = () if satisfied else _dedupe(
            [code for o in child_outcomes for code in o.outstanding]
        )
        return _NodeOutcome(satisfied, any_leaf, outstanding, manual)

    raise ValueError(f"Unknown prerequisite node type: {node.node_type}")


def evaluate_prereq(node: PrereqNode | None, completed: frozenset[str]) -> PrereqEvaluation:
    """Evaluate a course's prerequisite tree against completed course codes."""
    if node is None:
        return PrereqEvaluation(status=PrereqStatus.MET, outstanding=())

    outcome = _evaluate(node, completed)
    if outcome.satisfied:
        status = PrereqStatus.MET
    elif outcome.any_leaf_satisfied:
        status = PrereqStatus.PARTIALLY_MET
    else:
        status = PrereqStatus.NOT_MET

    return PrereqEvaluation(
        status=status,
        outstanding=outcome.outstanding,
        requires_manual_check=outcome.requires_manual_check,
    )


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
