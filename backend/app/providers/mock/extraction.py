"""Deterministic rule-based ECP extraction (mock for the LLM pipeline, FR-3.5.1).

Parses the ECP-shaped text format used by UQ-style course profiles:
    Course code: COMP2140
    Course title: Web/Mobile Programming
    Units: 2
    Semester: Semester 2, 2026
    Description: ...
    Assessment:
    - Name | weight: 30% | max mark: 100 | due: 2026-09-05
    Hurdle: Must score at least 40% on the Final Exam ...
    Grade cut-offs: 7: 85, 6: 75, ...
    Prerequisite: CSSE1001 and (MATH1051 or MATH1061)

A real LLM provider replaces this class and returns the same ExtractedProfile.
"""

import re

from app.domain.planning.models import PrereqNode
from app.providers.interfaces import ExtractedAssessment, ExtractedProfile

COURSE_CODE_PATTERN = re.compile(r"^[A-Z]{4}\d{4}[A-Z]?$")
ASSESSMENT_LINE = re.compile(
    r"^-\s*(?P<name>[^|]+?)\s*\|\s*weight:\s*(?P<weight>[\d.]+)%"
    r"(?:\s*\|\s*max mark:\s*(?P<max_mark>[\d.]+))?"
    r"(?:\s*\|\s*due:\s*(?P<due>\d{4}-\d{2}-\d{2}))?\s*$"
)
HURDLE_MIN = re.compile(r"at least\s+([\d.]+)%", re.IGNORECASE)
SEMESTER_LINE = re.compile(r"Semester\s+(\d),\s*(\d{4})", re.IGNORECASE)


class PrereqParseError(ValueError):
    pass


def _tokenise_prereq(text: str) -> list[str]:
    return re.findall(r"\(|\)|[A-Za-z]{4}\d{4}[A-Za-z]?|\band\b|\bor\b|[^\s()]+", text)


def parse_prereq_expression(text: str) -> PrereqNode:
    """Recursive-descent parse of 'A and (B or C)'; unparseable → error."""
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


def _field(text: str, label: str) -> str | None:
    match = re.search(rf"^{label}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _parse_description(text: str) -> str:
    match = re.search(
        r"^Description:\s*(.+?)(?=\n\s*\n|\nAssessment:)", text, re.MULTILINE | re.DOTALL
    )
    if not match:
        return ""
    return " ".join(line.strip() for line in match.group(1).splitlines()).strip()


def _parse_cutoffs(text: str) -> dict[int, float] | None:
    line = _field(text, "Grade cut-offs")
    if not line:
        return None
    cutoffs: dict[int, float] = {}
    for pair in re.finditer(r"(\d)\s*:\s*([\d.]+)", line):
        cutoffs[int(pair.group(1))] = float(pair.group(2))
    return cutoffs or None


class MockExtractionProvider:
    def extract(self, text: str) -> ExtractedProfile:
        warnings: list[str] = []

        code = _field(text, "Course code")
        if not code or not COURSE_CODE_PATTERN.match(code):
            raise ValueError("Could not find a valid 'Course code:' line in the profile text")
        title = _field(text, "Course title") or code
        units = float(_field(text, "Units") or 2)

        semester_match = SEMESTER_LINE.search(text)
        if semester_match:
            version_label = f"{semester_match.group(2)}S{semester_match.group(1)}"
        else:
            version_label = "unknown"
            warnings.append("Could not determine the semester; version label set to 'unknown'")

        hurdle_line = _field(text, "Hurdle")
        assessments: list[ExtractedAssessment] = []
        for raw_line in text.splitlines():
            match = ASSESSMENT_LINE.match(raw_line.strip())
            if not match:
                continue
            name = match.group("name").strip()
            hurdle_min = None
            hurdle_description = None
            if hurdle_line and name.lower() in hurdle_line.lower():
                min_match = HURDLE_MIN.search(hurdle_line)
                if min_match:
                    hurdle_min = float(min_match.group(1))
                    hurdle_description = hurdle_line
            assessments.append(
                ExtractedAssessment(
                    name=name,
                    weight=float(match.group("weight")),
                    max_mark=float(match.group("max_mark") or 100),
                    due_date=match.group("due"),
                    hurdle_min_percent=hurdle_min,
                    hurdle_description=hurdle_description,
                )
            )
        if not assessments:
            warnings.append("No assessment items were recognised")
        else:
            total = sum(a.weight for a in assessments)
            if abs(total - 100.0) > 0.01:
                warnings.append(f"Assessment weights sum to {total:g}, not 100")

        prereq_raw = _field(text, "Prerequisite")
        prereq_tree: PrereqNode | None = None
        if prereq_raw:
            try:
                prereq_tree = parse_prereq_expression(prereq_raw)
            except PrereqParseError:
                # Never silently satisfied: keep as a note for manual checking.
                prereq_tree = PrereqNode.note(prereq_raw)
                warnings.append(
                    "Prerequisite text could not be fully parsed; flagged for manual check"
                )

        return ExtractedProfile(
            course_code=code,
            course_title=title,
            units=units,
            description=_parse_description(text),
            version_label=version_label,
            assessments=tuple(assessments),
            grade_cutoffs=_parse_cutoffs(text),
            prerequisite_raw=prereq_raw,
            prerequisite_tree=prereq_tree,
            warnings=tuple(warnings),
        )
