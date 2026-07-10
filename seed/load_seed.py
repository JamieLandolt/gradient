#!/usr/bin/env python3
"""Idempotent seed loader for the Gradient sample catalogue.

Reads seed/data/*.json and upserts courses, offerings, profile versions,
assessments, grade cut-offs, prerequisite trees, programs, and course
embeddings into the Supabase project configured in backend/.env.

Run:  backend/.venv/bin/python seed/load_seed.py
Safe to run repeatedly — existing rows are updated or replaced, never duplicated.
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "seed" / "data"
OFFERING_YEARS = (2024, 2025, 2026, 2027)

sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.providers.factory import get_providers  # noqa: E402


def load_backend_env() -> dict[str, str]:
    env_path = REPO_ROOT / "backend" / ".env"
    if not env_path.exists():
        sys.exit(f"error: {env_path} not found — copy .env.example and fill in Supabase keys")
    values: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    missing = [k for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY") if not values.get(k)]
    if missing:
        sys.exit(f"error: missing {', '.join(missing)} in backend/.env")
    return values


def read_json(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text())


def upsert_courses(db, courses: list[dict]) -> dict[str, int]:
    """Upsert courses; returns code -> id."""
    rows = [
        {
            "code": c["code"],
            "title": c["title"],
            "units": c["units"],
            "description": c["description"],
            "data_source": "seed",
        }
        for c in courses
    ]
    db.table("courses").upsert(rows, on_conflict="code").execute()
    fetched = db.table("courses").select("id, code").execute().data
    return {row["code"]: row["id"] for row in fetched}


def upsert_offerings(db, courses: list[dict], course_ids: dict[str, int]) -> None:
    rows = [
        {"course_id": course_ids[c["code"]], "year": year, "semester": semester}
        for c in courses
        for year in OFFERING_YEARS
        for semester in c["offering_semesters"]
    ]
    db.table("course_offerings").upsert(
        rows, on_conflict="course_id,year,semester", ignore_duplicates=True
    ).execute()


def upsert_profile_version(db, course: dict, course_id: int) -> int:
    db.table("profile_versions").upsert(
        {
            "course_id": course_id,
            "version_label": course["version_label"],
            "source_type": "seed",
            "source_ref": "seed/data/courses.json",
            "extraction_provider": "seed",
            "status": "verified",
        },
        on_conflict="course_id,version_label",
    ).execute()
    fetched = (
        db.table("profile_versions")
        .select("id")
        .eq("course_id", course_id)
        .eq("version_label", course["version_label"])
        .execute()
        .data
    )
    return fetched[0]["id"]


def replace_assessments(db, course: dict, version_id: int) -> None:
    db.table("assessments").delete().eq("profile_version_id", version_id).execute()
    rows = [
        {
            "profile_version_id": version_id,
            "name": item["name"],
            "weight": item["weight"],
            "max_mark": item["max_mark"],
            "due_date": item.get("due_date"),
            "hurdle_min_percent": item.get("hurdle_min_percent"),
            "hurdle_description": item.get("hurdle_description"),
            "sort_order": order,
        }
        for order, item in enumerate(course["assessments"])
    ]
    db.table("assessments").insert(rows).execute()


def replace_grade_cutoffs(db, course: dict, version_id: int) -> None:
    db.table("grade_cutoffs").delete().eq("profile_version_id", version_id).execute()
    cutoffs = course.get("grade_cutoffs")
    if not cutoffs:
        return
    rows = [
        {"profile_version_id": version_id, "grade": int(grade), "min_percent": min_percent}
        for grade, min_percent in cutoffs.items()
    ]
    db.table("grade_cutoffs").insert(rows).execute()


def insert_prereq_tree(db, course_id: int, node: dict, course_ids: dict[str, int],
                       parent_id: int | None = None, sort_order: int = 0) -> None:
    row = {
        "course_id": course_id,
        "parent_id": parent_id,
        "node_type": node["type"],
        "sort_order": sort_order,
    }
    if node["type"] == "course":
        code = node["code"]
        if code not in course_ids:
            sys.exit(f"error: prerequisite references unknown course {code}")
        row["child_course_id"] = course_ids[code]
    elif node["type"] == "note":
        row["note_text"] = node["text"]
    inserted = db.table("prerequisite_nodes").insert(row).execute().data
    node_id = inserted[0]["id"]
    for index, child in enumerate(node.get("operands", [])):
        insert_prereq_tree(db, course_id, child, course_ids, node_id, index)


def replace_prerequisites(db, prereqs: list[dict], course_ids: dict[str, int]) -> None:
    for entry in prereqs:
        code = entry["course"]
        if code not in course_ids:
            sys.exit(f"error: prerequisites listed for unknown course {code}")
        course_id = course_ids[code]
        db.table("prerequisite_nodes").delete().eq("course_id", course_id).execute()
        insert_prereq_tree(db, course_id, entry["expr"], course_ids)
        db.table("course_prerequisites_raw").upsert(
            {"course_id": course_id, "raw_text": entry["raw_text"]},
            on_conflict="course_id",
        ).execute()


def replace_programs(db, programs: list[dict], course_ids: dict[str, int]) -> None:
    for program in programs:
        db.table("programs").upsert(
            {
                "code": program["code"],
                "title": program["title"],
                "total_units": program["total_units"],
                "is_sample": True,
            },
            on_conflict="code",
        ).execute()
        program_id = (
            db.table("programs").select("id").eq("code", program["code"]).execute().data[0]["id"]
        )
        db.table("program_courses").delete().eq("program_id", program_id).execute()
        rows = [
            {
                "program_id": program_id,
                "course_id": course_ids[code],
                "requirement_kind": kind,
            }
            for kind in ("required", "elective")
            for code in program["courses"][kind]
        ]
        db.table("program_courses").insert(rows).execute()


def build_embedder():
    """The configured embedding provider (mock or hosted), from backend/.env."""
    env = load_backend_env()
    for key, value in env.items():
        os.environ.setdefault(key, value)
    return get_providers(Settings(_env_file=None)).embeddings


def upsert_embeddings(db, courses: list[dict], course_ids: dict[str, int], embedder) -> None:
    rows = [
        {
            "course_id": course_ids[c["code"]],
            "embedding": embedder.embed(f"{c['code']} {c['title']} {c['description']}"),
            "model": embedder.model_name,
        }
        for c in courses
    ]
    db.table("course_embeddings").upsert(rows, on_conflict="course_id").execute()


def main() -> None:
    env = load_backend_env()
    try:
        from supabase import create_client
    except ImportError:
        sys.exit("error: supabase package not installed — run: "
                 "backend/.venv/bin/pip install -r backend/requirements.txt")

    db = create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])

    courses = read_json("courses.json")["courses"]
    prereqs = read_json("prerequisites.json")["prerequisites"]
    programs = read_json("programs.json")["programs"]

    print(f"Seeding {len(courses)} courses…")
    course_ids = upsert_courses(db, courses)
    upsert_offerings(db, courses, course_ids)
    for course in courses:
        version_id = upsert_profile_version(db, course, course_ids[course["code"]])
        replace_assessments(db, course, version_id)
        replace_grade_cutoffs(db, course, version_id)
    print(f"Seeding prerequisites for {len(prereqs)} courses…")
    replace_prerequisites(db, prereqs, course_ids)
    print(f"Seeding {len(programs)} programs…")
    replace_programs(db, programs, course_ids)
    embedder = build_embedder()
    print(f"Seeding course embeddings via {embedder.model_name}…")
    upsert_embeddings(db, courses, course_ids, embedder)
    print("Done — seed is idempotent; re-running updates in place.")


if __name__ == "__main__":
    main()
