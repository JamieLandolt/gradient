"""Advisory AI features: recommendations, search, assistant.

Every grade or prerequisite fact cited in an output is produced by the
deterministic engines and handed to the provider (FR-3.7.2, FR-3.9.3);
providers only rank and phrase. (Weekly study plans are a separate, fully
deterministic feature — see app.services.study_plan.)

Generated recommendations are persisted (FR-3.7.x) so they are revisitable
and regenerable; the assistant additionally supports token streaming (FR-3.9.3).
"""

import re
import time
from collections.abc import Iterator
from typing import Any

from app.core.errors import NotFoundError, ValidationFailedError
from app.domain.planning.prereq_ast import evaluate_prereq
from app.providers.factory import ProviderBundle
from app.repositories.artifacts import ArtifactRepository
from app.repositories.catalogue import CatalogueRepository
from app.repositories.ingestion import IngestionRepository
from app.repositories.students import StudentRepository
from app.services.tracking import TrackingService

DEFAULT_RECOMMENDATION_LIMIT = 5
DEFAULT_SEARCH_LIMIT = 10

# Bounds how many candidate courses are sent to the LLM per recommend() call —
# without this, the prompt payload (and cost/latency) grows with the whole
# catalogue. Interest-matching courses are kept first; the rest pad up to the cap.
MAX_RECOMMEND_CANDIDATES = 60
_WORD = re.compile(r"[a-z]{3,}")

# In-process cache so repeated "Regenerate" clicks with unchanged inputs skip
# the LLM call entirely. Keyed by everything that can change the result;
# module-level (not per-service-instance) since a new AdvisoryService is
# constructed per request. Deliberately simple: no eviction beyond TTL, and
# doesn't survive a process restart or share across multiple workers — both
# acceptable for this app's scale (see docs/REVIEW_efficiency_ux.md).
_RECOMMEND_CACHE_TTL_S = 300.0
_recommend_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _bounded_candidate_pool(
    courses: list[dict[str, Any]], interests: list[str], cap: int
) -> list[dict[str, Any]]:
    """Cap the candidate list, preferring courses matching the student's interests."""
    if len(courses) <= cap:
        return courses
    interest_words = _tokens(" ".join(interests))
    if not interest_words:
        return courses[:cap]
    matching = [
        c for c in courses
        if interest_words & _tokens(f"{c['title']} {c.get('description', '')}")
    ]
    if len(matching) >= cap:
        return matching[:cap]
    matched_codes = {c["code"] for c in matching}
    remainder = [c for c in courses if c["code"] not in matched_codes]
    return matching + remainder[: cap - len(matching)]


_RECOMMENDATION_DISCLAIMER = (
    "Recommendations are advisory only — your official program requirements and "
    "course profiles remain authoritative."
)


class AdvisoryService:
    def __init__(
        self,
        catalogue: CatalogueRepository,
        students: StudentRepository,
        ingestion: IngestionRepository,
        tracking: TrackingService,
        providers: ProviderBundle,
        artifacts: ArtifactRepository,
    ):
        self._catalogue = catalogue
        self._students = students
        self._ingestion = ingestion
        self._tracking = tracking
        self._providers = providers
        self._artifacts = artifacts

    # ── Recommendations (FR-3.7.x) ────────────────────────────────────────
    def recommend(
        self, user_id: str, interests: list[str], limit: int = DEFAULT_RECOMMENDATION_LIMIT
    ) -> dict[str, Any]:
        completed = self._students.completed_course_codes(user_id)
        cache_key = (user_id, tuple(sorted(interests)), completed, limit)
        cached = _recommend_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and now - cached[0] < _RECOMMEND_CACHE_TTL_S:
            return cached[1]

        courses = [
            c for c in self._catalogue.list_courses() if c["code"] not in completed
        ]
        courses = _bounded_candidate_pool(courses, interests, MAX_RECOMMEND_CANDIDATES)
        code_to_id = {course["code"]: course["id"] for course in courses}
        # One batched query instead of two per course (was N+1 over the catalogue).
        trees = self._catalogue.get_prereq_trees([course["id"] for course in courses])
        candidates = []
        for course in courses:
            evaluation = evaluate_prereq(trees.get(course["id"]), completed)
            candidates.append(
                {
                    "code": course["code"],
                    "title": course["title"],
                    "description": course.get("description", ""),
                    # Deterministic engine supplies this fact (FR-3.7.2):
                    "prereq_status": evaluation.status.value,
                }
            )
        items = self._providers.recommendations.recommend(
            candidates, interests, completed, limit
        )
        # De-duplicate by course before persisting: recommendation_items has a
        # unique(recommendation_id, course_id) constraint, and a model could return
        # the same course twice. Keep the first (best-ranked) occurrence.
        persisted_items = []
        seen: set[str] = set()
        for item in items:
            code = item["course_code"]
            if code not in code_to_id or code in seen:
                continue
            seen.add(code)
            persisted_items.append(
                {
                    "course_id": code_to_id[code],
                    "rank": item["rank"],
                    "reason": item["reason"],
                    "prereq_status": item["prereq_status"],
                }
            )
        record = self._artifacts.save_recommendation(
            user_id, self._providers.name, persisted_items
        )
        result = {
            "id": record["id"],
            "generated_at": record.get("generated_at"),
            "provider": self._providers.name,
            "items": items,
            "disclaimer": _RECOMMENDATION_DISCLAIMER,
        }
        _recommend_cache[cache_key] = (now, result)
        return result

    def latest_recommendation(self, user_id: str) -> dict[str, Any] | None:
        row = self._artifacts.latest_recommendation(user_id)
        if row is None:
            return None
        return self._shape_recommendation(row)

    def list_recommendations(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._artifacts.list_recommendations(user_id)
        return [
            {
                "id": row["id"],
                "provider": row["provider"],
                "generated_at": row.get("generated_at"),
                "item_count": len(row.get("recommendation_items") or []),
            }
            for row in rows
        ]

    def delete_recommendation(self, user_id: str, recommendation_id: int) -> None:
        if not self._artifacts.delete_recommendation(user_id, recommendation_id):
            raise NotFoundError("Recommendation not found")

    @staticmethod
    def _shape_recommendation(row: dict[str, Any]) -> dict[str, Any]:
        items = sorted(
            row.get("recommendation_items") or [], key=lambda item: item["rank"]
        )
        return {
            "id": row["id"],
            "generated_at": row.get("generated_at"),
            "provider": row["provider"],
            "items": [
                {
                    "course_code": (item.get("courses") or {}).get("code"),
                    "rank": item["rank"],
                    "reason": item["reason"],
                    "prereq_status": item["prereq_status"],
                }
                for item in items
            ],
            "disclaimer": _RECOMMENDATION_DISCLAIMER,
        }

    # ── Search (FR-3.9.1) ─────────────────────────────────────────────────
    def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[dict[str, Any]]:
        if not query.strip():
            raise ValidationFailedError("Provide a search query")
        embedding = self._providers.embeddings.embed(query)
        return self._ingestion.match_courses(embedding, limit)

    # ── Assistant (FR-3.9.3) ──────────────────────────────────────────────
    def _assemble_facts(self, user_id: str, enrolment_id: int | None) -> dict[str, Any]:
        """Deterministic, PII-free facts handed to the assistant provider."""
        facts: dict[str, Any] = {}
        gpa = self._tracking.gpa(user_id)
        facts["GPA"] = gpa["gpa"]
        facts["completed courses"] = gpa["completed_courses"]
        if enrolment_id is not None:
            standing = self._tracking.standing(user_id, enrolment_id)
            facts["secured percent"] = standing["secured_percent"]
            facts["projected grade"] = standing["projected_grade"]
        return facts

    def ask(self, user_id: str, question: str, enrolment_id: int | None) -> dict[str, Any]:
        if not question.strip():
            raise ValidationFailedError("Ask a question")
        facts = self._assemble_facts(user_id, enrolment_id)
        answer = self._providers.assistant.answer(question, facts)
        return {"provider": self._providers.name, "answer": answer}

    def ask_stream(
        self, user_id: str, question: str, enrolment_id: int | None
    ) -> Iterator[str]:
        """Yield the assistant's answer token-by-token (FR-3.9.3).

        Validation and fact assembly happen eagerly (before any token is
        produced) so input errors surface as normal HTTP errors, not mid-stream.
        """
        if not question.strip():
            raise ValidationFailedError("Ask a question")
        facts = self._assemble_facts(user_id, enrolment_id)
        return self._providers.assistant.stream_answer(question, facts)
