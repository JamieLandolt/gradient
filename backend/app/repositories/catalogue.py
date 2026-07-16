"""Read access to the shared course catalogue (public data).

Returns plain dicts / engine dataclasses; the API layer shapes responses.
"""

from typing import Any

from supabase import Client

from app.domain.planning.models import PrereqNode

# Ceiling on a full catalogue read. Comfortably above UQ's whole course list, so
# it never truncates in practice — it exists so a runaway import can't turn every
# planner request into an unbounded scan.
MAX_COURSES = 5000


def build_prereq_tree(rows: list[dict[str, Any]], code_by_id: dict[int, str]) -> PrereqNode | None:
    """Assemble a PrereqNode tree from prerequisite_nodes rows (adjacency list)."""
    if not rows:
        return None
    children_of: dict[int | None, list[dict[str, Any]]] = {}
    for row in rows:
        children_of.setdefault(row["parent_id"], []).append(row)
    for siblings in children_of.values():
        siblings.sort(key=lambda r: r["sort_order"])

    def to_node(row: dict[str, Any]) -> PrereqNode:
        node_type = row["node_type"]
        if node_type == "course":
            return PrereqNode.course(code_by_id[row["child_course_id"]])
        if node_type == "note":
            return PrereqNode.note(row["note_text"] or "")
        child_nodes = tuple(to_node(child) for child in children_of.get(row["id"], []))
        return PrereqNode(node_type=node_type, children=child_nodes)

    roots = children_of.get(None, [])
    if not roots:
        return None
    return to_node(roots[0])


class CatalogueRepository:
    def __init__(self, db: Client):
        self._db = db

    # ── Courses ───────────────────────────────────────────────────────────
    def list_courses(self, limit: int = MAX_COURSES) -> list[dict[str, Any]]:
        """The catalogue, hard-bounded.

        This feeds the planner, the recommendation candidate pool and the course
        pickers, none of which want an unbounded read as the catalogue grows.
        """
        return (
            self._db.table("courses")
            .select("id, code, title, units, description")
            .order("code")
            .limit(limit)
            .execute()
            .data
        )

    def get_course(self, code: str) -> dict[str, Any] | None:
        rows = (
            self._db.table("courses")
            .select("id, code, title, units, description")
            .eq("code", code)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def get_offering_periods(self, course_id: int) -> frozenset[str]:
        rows = (
            self._db.table("course_offerings")
            .select("semester")
            .eq("course_id", course_id)
            .execute()
            .data
        )
        return frozenset(row["semester"] for row in rows)

    def find_offering(self, course_id: int, year: int, semester: str) -> dict[str, Any] | None:
        rows = (
            self._db.table("course_offerings")
            .select("id, course_id, year, semester")
            .eq("course_id", course_id)
            .eq("year", year)
            .eq("semester", semester)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def create_offering(self, course_id: int, year: int, semester: str) -> dict[str, Any]:
        return (
            self._db.table("course_offerings")
            .insert({"course_id": course_id, "year": year, "semester": semester})
            .execute()
            .data[0]
        )

    def sync_offerings(self, course_id: int, offerings: list[tuple[int, str]]) -> int:
        """Create any (year, semester) pair not already recorded for this course.

        Never deletes — a semester a course was once offered in stays a valid
        historical fact even if a later catalogue snapshot omits it (e.g. the
        site trims very old archived rows). Returns how many were newly created.
        """
        existing = {
            (row["year"], row["semester"])
            for row in self._db.table("course_offerings")
            .select("year, semester")
            .eq("course_id", course_id)
            .execute()
            .data
        }
        created = 0
        for year, semester in offerings:
            if (year, semester) not in existing:
                self.create_offering(course_id, year, semester)
                created += 1
        return created

    # ── Profile versions & assessments ────────────────────────────────────
    def get_verified_profile(self, course_id: int) -> dict[str, Any] | None:
        """Latest verified profile version with assessments and cut-offs."""
        versions = (
            self._db.table("profile_versions")
            .select("id, version_label, status, extracted_at, extraction_provider")
            .eq("course_id", course_id)
            .eq("status", "verified")
            .order("version_label", desc=True)
            .limit(1)
            .execute()
            .data
        )
        if not versions:
            return None
        version = versions[0]
        version["assessments"] = (
            self._db.table("assessments")
            .select(
                "id, name, weight, max_mark, due_date, hurdle_min_percent, "
                "hurdle_description, sort_order"
            )
            .eq("profile_version_id", version["id"])
            .order("sort_order")
            .execute()
            .data
        )
        cutoff_rows = (
            self._db.table("grade_cutoffs")
            .select("grade, min_percent")
            .eq("profile_version_id", version["id"])
            .execute()
            .data
        )
        version["grade_cutoffs"] = {
            row["grade"]: float(row["min_percent"]) for row in cutoff_rows
        } or None
        return version

    # ── Prerequisites ─────────────────────────────────────────────────────
    def get_prereq_tree(self, course_id: int) -> PrereqNode | None:
        rows = (
            self._db.table("prerequisite_nodes")
            .select("id, parent_id, node_type, child_course_id, note_text, sort_order")
            .eq("course_id", course_id)
            .execute()
            .data
        )
        if not rows:
            return None
        referenced_ids = [r["child_course_id"] for r in rows if r["child_course_id"] is not None]
        code_by_id: dict[int, str] = {}
        if referenced_ids:
            course_rows = (
                self._db.table("courses")
                .select("id, code")
                .in_("id", referenced_ids)
                .execute()
                .data
            )
            code_by_id = {row["id"]: row["code"] for row in course_rows}
        return build_prereq_tree(rows, code_by_id)

    def get_prereq_raw_text(self, course_id: int) -> str | None:
        rows = (
            self._db.table("course_prerequisites_raw")
            .select("raw_text")
            .eq("course_id", course_id)
            .execute()
            .data
        )
        return rows[0]["raw_text"] if rows else None

    # ── Batch prerequisite loads (avoid N+1: one query for many courses) ──
    def get_prereq_trees(self, course_ids: list[int]) -> dict[int, PrereqNode | None]:
        """Prerequisite AST for each course id, in two queries total (not 2·N)."""
        if not course_ids:
            return {}
        rows = (
            self._db.table("prerequisite_nodes")
            .select("id, course_id, parent_id, node_type, child_course_id, note_text, sort_order")
            .in_("course_id", course_ids)
            .execute()
            .data
        )
        by_course: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            by_course.setdefault(row["course_id"], []).append(row)
        referenced = [r["child_course_id"] for r in rows if r["child_course_id"] is not None]
        code_by_id: dict[int, str] = {}
        if referenced:
            course_rows = (
                self._db.table("courses").select("id, code").in_("id", referenced).execute().data
            )
            code_by_id = {row["id"]: row["code"] for row in course_rows}
        return {cid: build_prereq_tree(by_course.get(cid, []), code_by_id) for cid in course_ids}

    def get_prereq_raw_texts(self, course_ids: list[int]) -> dict[int, str]:
        if not course_ids:
            return {}
        rows = (
            self._db.table("course_prerequisites_raw")
            .select("course_id, raw_text")
            .in_("course_id", course_ids)
            .execute()
            .data
        )
        return {row["course_id"]: row["raw_text"] for row in rows}

    def get_offering_periods_batch(self, course_ids: list[int]) -> dict[int, frozenset[str]]:
        """Offered study periods for each course id, in one query (not N)."""
        if not course_ids:
            return {}
        rows = (
            self._db.table("course_offerings")
            .select("course_id, semester")
            .in_("course_id", course_ids)
            .execute()
            .data
        )
        by_course: dict[int, set[str]] = {}
        for row in rows:
            by_course.setdefault(row["course_id"], set()).add(row["semester"])
        return {cid: frozenset(by_course.get(cid, set())) for cid in course_ids}

    # ── Programs ──────────────────────────────────────────────────────────
    def list_programs(self) -> list[dict[str, Any]]:
        return (
            self._db.table("programs")
            .select("id, code, title, total_units, is_sample")
            .order("code")
            .execute()
            .data
        )

    def get_program_courses(self, program_id: int) -> list[dict[str, Any]]:
        return (
            self._db.table("program_courses")
            .select("requirement_kind, courses(code)")
            .eq("program_id", program_id)
            .execute()
            .data
        )

