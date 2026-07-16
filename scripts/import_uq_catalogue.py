#!/usr/bin/env python3
"""Import real UQ courses from programs-courses.uq.edu.au into the catalogue.

For each curated course code (seed/data/uq_course_codes.json): fetch the public
course page, LLM-extract its structure, and store a DRAFT profile_version for
curator review (FR-3.5.1 / FR-3.5.3). Idempotent, throttled, and cached — safe
to re-run. Catalogue pages carry course metadata + prerequisites + description
(not the ECP assessment breakdown), so extracted drafts usually have no
assessment items; students/curators add those from the ECP.

Requires AI_PROVIDER=openai_compatible + DASHSCOPE_API_KEY in backend/.env.

Run:  AI_PROVIDER=openai_compatible backend/.venv/bin/python scripts/import_uq_catalogue.py
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "seed"))

from load_seed import load_backend_env  # noqa: E402

from app.config import Settings  # noqa: E402
from app.core.db import get_supabase_client  # noqa: E402
from app.ingestion.uq_fetcher import UQCourseFetcher, course_url  # noqa: E402
from app.providers.factory import get_providers  # noqa: E402
from app.repositories.ingestion import IngestionRepository  # noqa: E402

CACHE_DIR = REPO_ROOT / "seed" / "data" / "uq_html_cache"


def load_codes() -> list[str]:
    data = json.loads((REPO_ROOT / "seed" / "data" / "uq_course_codes.json").read_text())
    codes: list[str] = []
    for group in data["subjects"].values():
        for code in group:
            if code not in codes:
                codes.append(code)
    return codes


def import_course(repo: IngestionRepository, providers, fetcher: UQCourseFetcher, code: str) -> str:
    text = fetcher.fetch_text(code)
    # Anchor the extractor on the intended code (the page also names prereq codes).
    payload = f"Course code: {code}\n\n{text}"
    extracted = providers.extraction.extract(payload)

    # create_course_if_missing returns (course, was_created); the flag guards
    # untrusted student submissions from overwriting an existing course's shared
    # facts. This bulk importer runs against authoritative UQ data with the
    # service-role key, so it intentionally refreshes prerequisites either way.
    course, _was_created = repo.create_course_if_missing(extracted)
    version = repo.find_profile_version(course["id"], extracted.version_label)
    if version is None:
        version = repo.create_draft_version(
            course["id"],
            extracted,
            source_type="url",
            source_ref=course_url(code),
            provider_name=providers.name,
        )
    if extracted.prerequisite_raw:
        repo.replace_prereq_tree(
            course["id"], extracted.prerequisite_raw, extracted.prerequisite_tree
        )
    repo.upsert_embedding(
        course["id"],
        providers.embeddings.embed(
            f"{course['code']} {extracted.course_title} {extracted.description}"
        ),
        providers.embeddings.model_name,
    )
    return (
        f"{course['code']}: {version['status']} version, "
        f"{len(extracted.assessments)} assessments, "
        f"prereq={'yes' if extracted.prerequisite_raw else 'none'}"
    )


def main() -> None:
    env = load_backend_env()
    for key, value in env.items():
        os.environ.setdefault(key, value)
    settings = Settings(_env_file=None)
    if settings.ai_provider != "openai_compatible":
        sys.exit(
            "error: run with AI_PROVIDER=openai_compatible (real extraction needed) — e.g.\n"
            "  AI_PROVIDER=openai_compatible backend/.venv/bin/python scripts/import_uq_catalogue.py"
        )

    providers = get_providers(settings)
    repo = IngestionRepository(get_supabase_client(settings))
    fetcher = UQCourseFetcher(cache_dir=CACHE_DIR)

    codes = load_codes()
    print(f"Importing {len(codes)} UQ courses (draft, for curator review)…\n")
    ok, failed = 0, 0
    try:
        for code in codes:
            try:
                print("  " + import_course(repo, providers, fetcher, code))
                ok += 1
            except Exception as exc:  # keep going; log and skip
                print(f"  {code}: SKIPPED — {type(exc).__name__}: {str(exc)[:120]}")
                failed += 1
    finally:
        fetcher.close()
    print(f"\nDone — {ok} imported, {failed} skipped. Review drafts in the curator queue.")


if __name__ == "__main__":
    main()
