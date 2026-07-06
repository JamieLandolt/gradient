"""Advisory AI features: recommendations, study plans, search, assistant.

Every grade or prerequisite fact cited in an output is produced by the
deterministic engines and handed to the provider (FR-3.7.2, FR-3.8.3);
providers only rank, schedule, and phrase.
"""

from datetime import date
from typing import Any

from app.core.errors import ValidationFailedError
from app.domain.planning.prereq_ast import evaluate_prereq
from app.providers.factory import ProviderBundle
from app.repositories.catalogue import CatalogueRepository
from app.repositories.ingestion import IngestionRepository
from app.repositories.students import StudentRepository
from app.services.tracking import TrackingService

DEFAULT_RECOMMENDATION_LIMIT = 5
DEFAULT_SEARCH_LIMIT = 10


class AdvisoryService:
    def __init__(
        self,
        catalogue: CatalogueRepository,
        students: StudentRepository,
        ingestion: IngestionRepository,
        tracking: TrackingService,
        providers: ProviderBundle,
    ):
        self._catalogue = catalogue
        self._students = students
        self._ingestion = ingestion
        self._tracking = tracking
        self._providers = providers

    # ── Recommendations (FR-3.7.x) ────────────────────────────────────────
    def recommend(
        self, user_id: str, interests: list[str], limit: int = DEFAULT_RECOMMENDATION_LIMIT
    ) -> dict[str, Any]:
        completed = self._students.completed_course_codes(user_id)
        candidates = []
        for course in self._catalogue.list_courses():
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
        return {
            "provider": self._providers.name,
            "items": items,
            "disclaimer": (
                "Recommendations are advisory only — your official program "
                "requirements and course profiles remain authoritative."
            ),
        }

    # ── Study plans (FR-3.8.x) ────────────────────────────────────────────
    def study_plan(
        self,
        user_id: str,
        enrolment_id: int,
        target_grade: int,
        start_date: str | None,
    ) -> dict[str, Any]:
        enrolment = self._tracking._require_enrolment(user_id, enrolment_id)
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
        return {
            "provider": self._providers.name,
            "course_code": course_code,
            "target_grade": target_grade,
            "required_average_percent": required.required_average_percent,
            "target_status": required.status.value,
            "sessions": sessions,
            "disclaimer": (
                "Study plans are advisory; assessment details come from your "
                "course profile and your recorded marks."
            ),
        }

    # ── Search (FR-3.9.1) ─────────────────────────────────────────────────
    def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[dict[str, Any]]:
        if not query.strip():
            raise ValidationFailedError("Provide a search query")
        embedding = self._providers.embeddings.embed(query)
        return self._ingestion.match_courses(embedding, limit)

    # ── Assistant (FR-3.9.3) ──────────────────────────────────────────────
    def ask(self, user_id: str, question: str, enrolment_id: int | None) -> dict[str, Any]:
        if not question.strip():
            raise ValidationFailedError("Ask a question")
        facts: dict[str, Any] = {}
        gpa = self._tracking.gpa(user_id)
        facts["GPA"] = gpa["gpa"]
        facts["completed courses"] = gpa["completed_courses"]
        if enrolment_id is not None:
            standing = self._tracking.standing(user_id, enrolment_id)
            facts["secured percent"] = standing["secured_percent"]
            facts["projected grade"] = standing["projected_grade"]
        answer = self._providers.assistant.answer(question, facts)
        return {"provider": self._providers.name, "answer": answer}
