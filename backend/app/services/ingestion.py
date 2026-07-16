"""ECP ingestion orchestration (FR-3.5.x).

Extraction runs on PUBLIC course-profile text only — no student data is ever
given to the extraction provider (FR-3.5.5). Results are cached per profile
version (FR-3.5.6) and must be curator-verified before driving projections
(FR-3.5.3).
"""

import logging
from typing import Any

from app.core.errors import NotFoundError, ValidationFailedError
from app.ingestion.uq_fetcher import fetch_ecp_text
from app.providers.factory import ProviderBundle
from app.repositories.ingestion import IngestionRepository

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, repo: IngestionRepository, providers: ProviderBundle):
        self._repo = repo
        self._providers = providers

    def create_job(
        self, user_id: str, source_type: str, payload: str, source_ref: str = ""
    ) -> dict[str, Any]:
        """Persist a ``queued`` job and return it immediately (FR-3.5.3).

        The heavy LLM extraction runs off the request path in
        :meth:`run_extraction` (FastAPI ``BackgroundTasks``); the client polls
        ``GET /ingestion/jobs/{id}`` for the terminal status (NFR-5.1.5).
        """
        if not payload.strip():
            raise ValidationFailedError("Provide the course profile text to extract")
        return self._repo.create_job(
            user_id,
            {"course_code": "", "source_type": source_type,
             "source_ref": source_ref, "payload": payload, "status": "queued"},
        )

    def run_extraction(
        self, job_id: int, payload: str, source_type: str, source_ref: str = ""
    ) -> None:
        """Extract, draft, and embed off the request path; flip the job to
        ``extracted`` or ``failed``.

        Runs as a background task, so it must never propagate: any failure is
        recorded on the job (``status='failed'``, ``error``) for the poller.
        """
        try:
            self._extract_and_draft(job_id, payload, source_type, source_ref)
        except Exception as exc:  # noqa: BLE001 — background task must not propagate
            self._record_failure(job_id, exc)

    def create_url_job(self, user_id: str, course_code: str) -> dict[str, Any]:
        """Queue a course code for ECP web-scraping (FR-3.5.1). Unlike text/upload,
        the source text isn't known yet — the scrape itself happens in
        run_url_extraction (a background task), since it's a network call to an
        external site rather than fast local parsing."""
        code = course_code.strip().upper()
        if not code:
            raise ValidationFailedError("Provide a course code")
        return self._repo.create_job(
            user_id,
            {"course_code": code, "source_type": "url",
             "source_ref": code, "payload": "", "status": "queued"},
        )

    def run_url_extraction(self, job_id: int, course_code: str) -> None:
        """Scrape the course's current ECP, then run the same background
        extraction pipeline as a paste/upload (FR-3.5.1). The fetch itself is
        guarded separately from run_extraction's own guard, since a failure here
        (robots disallowed, no current profile, network error) happens before
        there is any payload to extract."""
        try:
            text = fetch_ecp_text(course_code)
        except Exception as exc:  # noqa: BLE001 — background task must not propagate
            self._record_failure(job_id, exc)
            return
        self.run_extraction(job_id, text, "url", course_code)

    def _record_failure(self, job_id: int, exc: Exception) -> None:
        """Best-effort: flip the job to ``failed``. If even this write raises
        (e.g. the DB is down — the very cause of the failure), swallow and log so
        the background task still never propagates."""
        try:
            self._repo.update_job(job_id, {"status": "failed", "error": str(exc)})
        except Exception:  # noqa: BLE001 — nothing left to do but log
            logger.exception("Could not record failure for ingestion job %s", job_id)

    def _extract_and_draft(
        self, job_id: int, payload: str, source_type: str, source_ref: str
    ) -> None:
        extracted = self._providers.extraction.extract(payload)
        course, course_was_created = self._repo.create_course_if_missing(extracted)

        cached = self._repo.find_profile_version(course["id"], extracted.version_label)
        if cached is not None:
            # Extraction runs once per profile version and is reused (FR-3.5.6).
            self._repo.update_job(
                job_id,
                {"status": "extracted", "course_code": course["code"],
                 "profile_version_id": cached["id"]},
            )
            return

        version = self._repo.create_draft_version(
            course["id"], extracted,
            source_type=source_type, source_ref=source_ref,
            provider_name=self._providers.name,
        )
        # Prerequisites are shared catalogue facts that the planner and the
        # prereq-status view treat as authoritative for EVERY student. Ingestion
        # is open to any authenticated student and the draft is unreviewed at
        # this point, so writing them here let one submission silently rewrite a
        # real course's prerequisites (e.g. re-submitting COMP3506 under a new
        # version label replaced its tree globally, flipping other students from
        # "met" to "not met"). Only a course this job just created has no
        # dependents and is safe to populate; for anything pre-existing the tree
        # is left alone and the curator reviews the draft.
        if course_was_created and extracted.prerequisite_raw:
            self._repo.replace_prereq_tree(
                course["id"], extracted.prerequisite_raw, extracted.prerequisite_tree
            )
        # Embedding only feeds semantic search — it's not needed for the draft
        # to be valid or curator-reviewable, so a flaky hosted-API call here
        # (the AI provider already retries transient errors, e.g. the known
        # intermittent Bailian "SSL: UNEXPECTED_EOF") shouldn't fail the whole
        # ingestion job. The course is just unsearchable until re-embedded.
        try:
            self._repo.upsert_embedding(
                course["id"],
                self._providers.embeddings.embed(
                    f"{course['code']} {extracted.course_title} {extracted.description}"
                ),
                self._providers.embeddings.model_name,
            )
        except Exception:  # noqa: BLE001 — non-fatal, see comment above
            logger.warning(
                "Embedding failed for course %s (job %s); draft saved without it",
                course["code"], job_id, exc_info=True,
            )
        self._repo.update_job(
            job_id,
            {"status": "extracted", "course_code": course["code"],
             "profile_version_id": version["id"]},
        )

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
