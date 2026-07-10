"""Shared recursive-descent parser for prerequisite expressions (FR-3.5.4).

Both the mock and the real (LLM) extraction providers reuse this so a course's
prerequisite string — e.g. "CSSE2002 and (MATH1061 or MATH1071)" — is turned
into the SAME deterministic `PrereqNode` AST the planner evaluates. The LLM is
never trusted to produce the tree structure: it returns a prerequisite string,
and this deterministic parser builds the AST. Unparseable input raises
`PrereqParseError`; callers keep it as a `note` leaf (never silently satisfied).
"""

import re

from app.domain.planning.models import PrereqNode

COURSE_CODE_PATTERN = re.compile(r"^[A-Z]{4}\d{4}[A-Z]?$")


class PrereqParseError(ValueError):
    """Raised when a prerequisite expression cannot be fully parsed."""


def _tokenise_prereq(text: str) -> list[str]:
    return re.findall(r"\(|\)|[A-Za-z]{4}\d{4}[A-Za-z]?|\band\b|\bor\b|[^\s()]+", text)


def parse_prereq_expression(text: str) -> PrereqNode:
    """Parse 'A and (B or C)' into a PrereqNode AST; unparseable → PrereqParseError."""
    tokens = _tokenise_prereq(text)
    position = 0

    def peek() -> str | None:
        return tokens[position] if position < len(tokens) else None

    def advance() -> str:
        nonlocal position
        token = tokens[position]
        position += 1
        return token

    def parse_atom() -> PrereqNode:
        token = peek()
        if token is None:
            raise PrereqParseError("unexpected end of expression")
        if token == "(":
            advance()
            node = parse_or()
            if peek() != ")":
                raise PrereqParseError("missing closing parenthesis")
            advance()
            return node
        if COURSE_CODE_PATTERN.match(token.upper()):
            advance()
            return PrereqNode.course(token.upper())
        raise PrereqParseError(f"unrecognised token: {token}")

    def parse_and() -> PrereqNode:
        operands = [parse_atom()]
        while peek() is not None and peek().lower() == "and":
            advance()
            operands.append(parse_atom())
        return operands[0] if len(operands) == 1 else PrereqNode.all_of(*operands)

    def parse_or() -> PrereqNode:
        operands = [parse_and()]
        while peek() is not None and peek().lower() == "or":
            advance()
            operands.append(parse_and())
        return operands[0] if len(operands) == 1 else PrereqNode.any_of(*operands)

    node = parse_or()
    if position != len(tokens):
        raise PrereqParseError("trailing tokens in expression")
    return node
