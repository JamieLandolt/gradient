"""Deterministic mock course recommendations (FR-3.7.x).

Scores candidates by keyword overlap with the student's interests plus a
prerequisite bonus. The prereq_status on each candidate is SUPPLIED BY THE
DETERMINISTIC PLANNER (FR-3.7.2) — this provider only ranks and explains.
"""

import re
from typing import Any

WORD = re.compile(r"[a-z]{3,}")

PREREQ_BONUS = {"met": 2.0, "partially_met": 0.5, "not_met": 0.0}
INTEREST_WEIGHT = 3.0


def _keywords(text: str) -> set[str]:
    return set(WORD.findall(text.lower()))


class MockRecommendationProvider:
    def recommend(
        self,
        candidates: list[dict[str, Any]],
        interests: list[str],
        completed_codes: frozenset[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        interest_words = _keywords(" ".join(interests))
        scored = []
        for candidate in candidates:
            if candidate["code"] in completed_codes:
                continue
            text_words = _keywords(f"{candidate['title']} {candidate.get('description', '')}")
            overlap = sorted(interest_words & text_words)
            score = len(overlap) * INTEREST_WEIGHT + PREREQ_BONUS.get(
                candidate.get("prereq_status", "not_met"), 0.0
            )
            scored.append((score, candidate, overlap))

        scored.sort(key=lambda entry: (-entry[0], entry[1]["code"]))

        results = []
        for rank, (score, candidate, overlap) in enumerate(scored[:limit], start=1):
            reason_parts = []
            if overlap:
                reason_parts.append(
                    f"matches your interest in {', '.join(overlap[:3])}"
                )
            status = candidate.get("prereq_status", "not_met")
            if status == "met":
                reason_parts.append("you already meet its prerequisites")
            elif status == "partially_met":
                reason_parts.append("you have completed part of its prerequisites")
            else:
                reason_parts.append("note: its prerequisites are not met yet")
            reason = (
                f"{candidate['title']} — " + " and ".join(reason_parts) + "."
            )
            results.append(
                {
                    "course_code": candidate["code"],
                    "rank": rank,
                    "reason": reason,
                    "prereq_status": status,
                    "score": score,
                }
            )
        return results
