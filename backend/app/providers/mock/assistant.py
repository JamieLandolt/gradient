"""Deterministic mock assistant (FR-3.9.3).

Answers from the facts dict supplied by the deterministic engines; it never
invents figures. A real LLM provider would receive the same grounded facts.
"""

from typing import Any


class MockAssistantProvider:
    def answer(self, question: str, facts: dict[str, Any]) -> str:
        lines = [
            "Here is what I can tell you from your Gradient data "
            f'(you asked: "{question.strip()}"):'
        ]
        for key, value in sorted(facts.items()):
            label = key.replace("_", " ")
            lines.append(f"- {label}: {value}")
        lines.append(
            "These figures come from Gradient's deterministic calculators. "
            "Your course profile (ECP) and official university records remain authoritative."
        )
        return "\n".join(lines)
