"""Ingestion pipeline data access: jobs, draft profile versions, prerequisite
trees, and course embeddings (FR-3.5.x, FR-3.9.1)."""

from typing import Any

from supabase import Client

from app.domain.planning.models import PrereqNode
from app.providers.interfaces import ExtractedProfile


class IngestionRepository:
    def __init__(self, db: Client):
        self._db = db

    # ── Courses ───────────────────────────────────────────────────────────
    def create_course_if_missing(
        self, extracted: ExtractedProfile
    ) -> tuple[dict[str, Any], bool]:
        """Return (course, was_created).

        `was_created` matters for authorisation: ingestion is open to any
        student, so a submission must never mutate catalogue facts an existing
        course's dependents already rely on. Only a course this call brought
        into existence is safe to attach extracted prerequisites to.
        """
        existing = (
            self._db.table("courses")
            .select("id, code, title, units, description")
            .eq("code", extracted.course_code)
            .execute()
            .data
        )
        if existing:
            return existing[0], False
        created = (
            self._db.table("courses")
            .insert(
                {
                    "code": extracted.course_code,
                    "title": extracted.course_title,
                    "units": extracted.units,
                    "description": extracted.description,
                    "data_source": "import",
                }
            )
            .execute()
            .data[0]
        )
        return created, True

    # ── Profile versions ──────────────────────────────────────────────────
    def find_profile_version(self, course_id: int, version_label: str) -> dict[str, Any] | None:
        rows = (
            self._db.table("profile_versions")
            .select("id, course_id, version_label, status")
            .eq("course_id", course_id)
            .eq("version_label", version_label)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def create_draft_version(
        self,
        course_id: int,
        extracted: ExtractedProfile,
        source_type: str,
        source_ref: str,
        provider_name: str,
    ) -> dict[str, Any]:
        version = (
            self._db.table("profile_versions")
            .insert(
                {
                    "course_id": course_id,
                    "version_label": extracted.version_label,
                    "source_type": source_type,
                    "source_ref": source_ref,
                    "extraction_provider": provider_name,
                    "status": "draft",
                }
            )
            .execute()
            .data[0]
        )
        assessment_rows = [
            {
                "profile_version_id": version["id"],
                "name": item.name,
                "weight": item.weight,
                "max_mark": item.max_mark,
                "due_date": item.due_date,
                "hurdle_min_percent": item.hurdle_min_percent,
                "hurdle_description": item.hurdle_description,
                "sort_order": order,
            }
            for order, item in enumerate(extracted.assessments)
        ]
        if assessment_rows:
            self._db.table("assessments").insert(assessment_rows).execute()
        if extracted.grade_cutoffs:
            cutoff_rows = [
                {"profile_version_id": version["id"], "grade": grade, "min_percent": value}
                for grade, value in extracted.grade_cutoffs.items()
            ]
            self._db.table("grade_cutoffs").insert(cutoff_rows).execute()
        return version

    def get_version(self, version_id: int) -> dict[str, Any] | None:
        rows = (
            self._db.table("profile_versions")
            .select("id, course_id, version_label, status, courses(code, title)")
            .eq("id", version_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def list_versions(self, status: str) -> list[dict[str, Any]]:
        return (
            self._db.table("profile_versions")
            .select(
                "id, course_id, version_label, status, extracted_at, "
                "extraction_provider, courses(code, title)"
            )
            .eq("status", status)
            .order("id")
            .execute()
            .data
        )

    def set_version_status(
        self, version_id: int, status: str, verified_by: str | None
    ) -> dict[str, Any] | None:
        values: dict[str, Any] = {"status": status}
        if status == "verified":
            values["verified_by"] = verified_by
            values["verified_at"] = "now()"
        rows = (
            self._db.table("profile_versions")
            .update(values)
            .eq("id", version_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    # ── Prerequisites ─────────────────────────────────────────────────────
    def replace_prereq_tree(
        self, course_id: int, raw_text: str, tree: PrereqNode | None
    ) -> None:
        self._db.table("course_prerequisites_raw").upsert(
            {"course_id": course_id, "raw_text": raw_text}, on_conflict="course_id"
        ).execute()
        self._db.table("prerequisite_nodes").delete().eq("course_id", course_id).execute()
        if tree is not None:
            self._insert_node(course_id, tree, parent_id=None, sort_order=0)

    def _insert_node(
        self, course_id: int, node: PrereqNode, parent_id: int | None, sort_order: int
    ) -> None:
        row: dict[str, Any] = {
            "course_id": course_id,
            "parent_id": parent_id,
            "node_type": node.node_type,
            "sort_order": sort_order,
        }
        if node.node_type == "course":
            course_rows = (
                self._db.table("courses").select("id").eq("code", node.code).execute().data
            )
            if not course_rows:
                # Referenced course unknown to the catalogue: keep as a note so it
                # is never silently satisfied.
                row["node_type"] = "note"
                row["note_text"] = f"requires {node.code} (not in catalogue)"
            else:
                row["child_course_id"] = course_rows[0]["id"]
        elif node.node_type == "note":
            row["note_text"] = node.text or ""
        inserted = self._db.table("prerequisite_nodes").insert(row).execute().data[0]
        for index, child in enumerate(node.children):
            self._insert_node(course_id, child, inserted["id"], index)

    # ── Jobs ──────────────────────────────────────────────────────────────
    def create_job(self, user_id: str, values: dict[str, Any]) -> dict[str, Any]:
        return (
            self._db.table("ingestion_jobs")
            .insert({**values, "submitted_by": user_id})
            .execute()
            .data[0]
        )

    def update_job(self, job_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
        rows = (
            self._db.table("ingestion_jobs").update(values).eq("id", job_id).execute().data
        )
        return rows[0] if rows else None

    def get_job(self, user_id: str, job_id: int) -> dict[str, Any] | None:
        rows = (
            self._db.table("ingestion_jobs")
            .select("*")
            .eq("submitted_by", user_id)
            .eq("id", job_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    # ── Embeddings & search ───────────────────────────────────────────────
    def upsert_embedding(self, course_id: int, embedding: list[float], model: str) -> None:
        self._db.table("course_embeddings").upsert(
            {"course_id": course_id, "embedding": embedding, "model": model},
            on_conflict="course_id",
        ).execute()

    def match_courses(self, embedding: list[float], limit: int) -> list[dict[str, Any]]:
        return self._db.rpc(
            "match_courses", {"query_embedding": embedding, "match_count": limit}
        ).execute().data
