"""ECP ingestion orchestration (FR-3.5.x).

Extraction runs on PUBLIC course-profile text only — no student data is ever
given to the extraction provider (FR-3.5.5). Results are cached per profile
version (FR-3.5.6) and must be curator-verified before driving projections
(FR-3.5.3).
"""

from typing import Any

from app.core.errors import NotFoundError, ValidationFailedError
from app.providers.factory import ProviderBundle
from app.repositories.ingestion import IngestionRepository


class IngestionService:
    def __init__(self, repo: IngestionRepository, providers: ProviderBundle):
        self._repo = repo
        self._providers = providers

    def submit(
        self, user_id: str, source_type: str, payload: str, source_ref: str = ""
    ) -> dict[str, Any]:
        if not payload.strip():
            raise ValidationFailedError("Provide the course profile text to extract")
        job = self._repo.create_job(
            user_id,
            {"course_code": "", "source_type": source_type,
             "source_ref": source_ref, "payload": payload, "status": "queued"},
        )
        try:
            extracted = self._providers.extraction.extract(payload)
        except (ValueError, RuntimeError) as exc:
            self._repo.update_job(job["id"], {"status": "failed", "error": str(exc)})
            raise ValidationFailedError(f"Extraction failed: {exc}") from exc

        course = self._repo.create_course_if_missing(extracted)

        cached = self._repo.find_profile_version(course["id"], extracted.version_label)
        if cached is not None:
            # Extraction runs once per profile version and is reused (FR-3.5.6).
            updated = self._repo.update_job(
                job["id"],
                {"status": "extracted", "course_code": course["code"],
                 "profile_version_id": cached["id"]},
            )
            return {**updated, "cached": True, "warnings": []}

        version = self._repo.create_draft_version(
            course["id"], extracted,
            source_type=source_type, source_ref=source_ref,
            provider_name=self._providers.name,
        )
        if extracted.prerequisite_raw:
            self._repo.replace_prereq_tree(
                course["id"], extracted.prerequisite_raw, extracted.prerequisite_tree
            )
        self._repo.upsert_embedding(
            course["id"],
            self._providers.embeddings.embed(
                f"{course['code']} {extracted.course_title} {extracted.description}"
            ),
            self._providers.embeddings.model_name,
        )
        updated = self._repo.update_job(
            job["id"],
            {"status": "extracted", "course_code": course["code"],
             "profile_version_id": version["id"]},
        )
        return {**updated, "cached": False, "warnings": list(extracted.warnings)}

    def get_job(self, user_id: str, job_id: int) -> dict[str, Any]:
        job = self._repo.get_job(user_id, job_id)
        if job is None:
            raise NotFoundError("Ingestion job not found")
        return job

    # ── Curator actions (FR-3.5.3) ────────────────────────────────────────
    def list_drafts(self) -> list[dict[str, Any]]:
        return self._repo.list_versions("draft")

    def verify(self, version_id: int, curator_id: str) -> dict[str, Any]:
        version = self._repo.get_version(version_id)
        if version is None:
            raise NotFoundError("Profile version not found")
        updated = self._repo.set_version_status(version_id, "verified", curator_id)
        return updated or version

    def reject(self, version_id: int, curator_id: str) -> dict[str, Any]:
        version = self._repo.get_version(version_id)
        if version is None:
            raise NotFoundError("Profile version not found")
        updated = self._repo.set_version_status(version_id, "rejected", curator_id)
        return updated or version
