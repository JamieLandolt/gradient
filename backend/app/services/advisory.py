"""Advisory AI features: recommendations, study plans, search, assistant.

Every grade or prerequisite fact cited in an output is produced by the
deterministic engines and handed to the provider (FR-3.7.2, FR-3.8.3);
providers only rank, schedule, and phrase.

Generated recommendations and study plans are persisted (FR-3.7.x/3.8.2) so they
are revisitable and regenerable; the assistant additionally supports token
streaming (FR-3.9.3).
"""

from collections.abc import Iterator
from datetime import date
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

_RECOMMENDATION_DISCLAIMER = (
    "Recommendations are advisory only — your official program requirements and "
    "course profiles remain authoritative."
)
_STUDY_PLAN_DISCLAIMER = (
    "Study plans are advisory; assessment details come from your course profile "
    "and your recorded marks."
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
        courses = self._catalogue.list_courses()
        code_to_id = {course["code"]: course["id"] for course in courses}
        candidates = []
        for course in courses:
            evaluation = evaluate_prereq(
                self._catalogue.get_prereq_tree(course["id"]), completed
            )
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
        return {
            "id": record["id"],
            "generated_at": record.get("generated_at"),
            "provider": self._providers.name,
            "items": [
                {
                    "course_code": item["course_code"],
                    "rank": item["rank"],
                    "reason": item["reason"],
                    "prereq_status": item["prereq_status"],
                }
                for item in items
                if item["course_code"] in seen
            ],
            "disclaimer": _RECOMMENDATION_DISCLAIMER,
        }

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

    # ── Study plans (FR-3.8.x) ────────────────────────────────────────────
    def study_plan(
        self,
        user_id: str,
        enrolment_id: int,
        target_grade: int,
        start_date: str | None,
    ) -> dict[str, Any]:
        enrolment = self._tracking.require_enrolment(user_id, enrolment_id)
        rows = self._tracking.assessment_rows(user_id, enrolment)
        if not rows:
            raise ValidationFailedError("This course has no assessment items yet")
        required = self._tracking.required_marks(user_id, enrolment_id, target_grade, {})
        course_code = enrolment["course_offerings"]["courses"]["code"]
        sessions = self._providers.study_plans.generate(
            course_code=course_code,
            items=rows,
            target_grade=target_grade,
            required_average_percent=required.required_average_percent,
            start_date=start_date or date.today().isoformat(),
        )
        record = self._artifacts.save_study_plan(
            user_id, enrolment_id, target_grade, self._providers.name, sessions
        )
        return {
            "id": record["id"],
            "generated_at": record.get("generated_at"),
            "provider": self._providers.name,
            "course_code": course_code,
            "target_grade": target_grade,
            "required_average_percent": required.required_average_percent,
            "target_status": required.status.value,
            "sessions": sessions,
            "disclaimer": _STUDY_PLAN_DISCLAIMER,
        }

    def list_study_plans(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._artifacts.list_study_plans(user_id)
        return [
            {
                "id": row["id"],
                "course_code": _plan_course_code(row),
                "target_grade": row["target_grade"],
                "provider": row["provider"],
                "generated_at": row.get("generated_at"),
            }
            for row in rows
        ]

    def get_study_plan(self, user_id: str, plan_id: int) -> dict[str, Any]:
        row = self._artifacts.get_study_plan(user_id, plan_id)
        if row is None:
            raise NotFoundError("Study plan not found")
        sessions = sorted(
            row.get("study_sessions") or [], key=lambda s: s.get("sort_order", 0)
        )
        return {
            "id": row["id"],
            "generated_at": row.get("generated_at"),
            "provider": row["provider"],
            "course_code": _plan_course_code(row),
            "target_grade": row["target_grade"],
            # These derived figures are recomputed live, not stored on the plan.
            "required_average_percent": None,
            "target_status": None,
            "sessions": [
                {
                    "session_date": s["session_date"],
                    "duration_minutes": s["duration_minutes"],
                    "focus": s["focus"],
                    "assessment_name": s.get("assessment_name", ""),
                    "sort_order": s.get("sort_order", 0),
                }
                for s in sessions
            ],
            "disclaimer": _STUDY_PLAN_DISCLAIMER,
        }

    def delete_study_plan(self, user_id: str, plan_id: int) -> None:
        if not self._artifacts.delete_study_plan(user_id, plan_id):
            raise NotFoundError("Study plan not found")

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


def _plan_course_code(row: dict[str, Any]) -> str | None:
    enrolment = row.get("enrolments") or {}
    offering = enrolment.get("course_offerings") or {}
    course = offering.get("courses") or {}
    return course.get("code")
