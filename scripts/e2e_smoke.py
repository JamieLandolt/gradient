#!/usr/bin/env python3
"""End-to-end smoke suite against a live Gradient stack (backend + Supabase).

Covers the full student journey: register → enrol → record marks → standing →
required marks → what-if → planner → search → AI advisory → ingestion +
curator review → RLS isolation → account deletion (cleanup).

Run:  backend/.venv/bin/python scripts/e2e_smoke.py
Requires: backend running on localhost:8000, migrations applied, seed loaded.
Creates throwaway users (e2e+<timestamp>@example.com) and deletes them at the end.
"""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import httpx  # noqa: E402

API = "http://localhost:8000/api/v1"
PASSED: list[str] = []
FAILED: list[str] = []


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (REPO_ROOT / "backend" / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}  {detail}")


def api(token: str | None = None) -> httpx.Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=API, headers=headers, timeout=60)


def unwrap(response: httpx.Response):
    return response.json().get("data")


def make_confirmed_user(env: dict[str, str], email: str, password: str) -> None:
    """Create an email-confirmed user via the admin API (works regardless of
    the project's email-confirmation setting)."""
    response = httpx.post(
        f"{env['SUPABASE_URL']}/auth/v1/admin/users",
        headers={
            "apikey": env["SUPABASE_SERVICE_ROLE_KEY"],
            "Authorization": f"Bearer {env['SUPABASE_SERVICE_ROLE_KEY']}",
        },
        json={"email": email, "password": password, "email_confirm": True},
        timeout=30,
    )
    if response.status_code not in (200, 201):
        sys.exit(f"could not create test user: {response.status_code} {response.text[:200]}")


def login(env: dict[str, str], email: str, password: str) -> str:
    response = httpx.post(
        f"{env['SUPABASE_URL']}/auth/v1/token?grant_type=password",
        headers={"apikey": env["SUPABASE_ANON_KEY"]},
        json={"email": email, "password": password},
        timeout=30,
    )
    if response.status_code != 200:
        sys.exit(f"login failed: {response.status_code} {response.text[:200]}")
    return response.json()["access_token"]


def main() -> None:
    env = load_env()
    stamp = int(time.time())
    email_a = f"e2e+{stamp}a@example.com"
    email_b = f"e2e+{stamp}b@example.com"
    password = f"E2e-test-{stamp}!"

    print("== Auth ==")
    make_confirmed_user(env, email_a, password)
    make_confirmed_user(env, email_b, password)
    token_a = login(env, email_a, password)
    token_b = login(env, email_b, password)
    check("register + login two users", bool(token_a) and bool(token_b))

    a = api(token_a)
    b = api(token_b)
    guest = api()

    print("== Catalogue ==")
    courses = unwrap(a.get("/courses"))
    check("catalogue lists 21+ seeded courses", len(courses) >= 21, f"got {len(courses)}")
    profile = unwrap(a.get("/courses/CSSE1001/profile"))
    names = [item["name"] for item in profile["assessments"]]
    check(
        "CSSE1001 profile is verified with 3 assessments",
        profile["status"] == "verified" and len(names) == 3,
        f"status={profile.get('status')} items={names}",
    )

    print("== Enrolment & grades ==")
    enrolment = unwrap(
        a.post("/enrolments", json={"course_code": "CSSE1001", "year": 2026, "semester": "S1"})
    )
    enrolment_id = enrolment["id"]
    check(
        "enrol in CSSE1001 2026 S1",
        enrolment["course_offerings"]["courses"]["code"] == "CSSE1001",
    )

    standing = unwrap(a.get(f"/enrolments/{enrolment_id}/standing"))
    a1 = next(item for item in standing["items"] if item["name"] == "Assignment 1")
    grade = unwrap(
        a.put(
            f"/enrolments/{enrolment_id}/grades",
            json={"assessment_id": a1["id"], "score": 80},
        )
    )
    check("record 80/100 on Assignment 1", grade is not None)

    standing = unwrap(a.get(f"/enrolments/{enrolment_id}/standing"))
    check(
        "standing: secured 16%, best case 96%",
        abs(standing["secured_percent"] - 16.0) < 1e-6
        and abs(standing["best_case_percent"] - 96.0) < 1e-6,
        f"secured={standing['secured_percent']} best={standing['best_case_percent']}",
    )

    print("== Target-grade calculator ==")
    required = unwrap(
        a.post(f"/enrolments/{enrolment_id}/required-marks", json={"target_grade": 6})
    )
    # secured 16; target 75 -> (75-16)/80*100 = 73.75
    check(
        "required marks for grade 6 = 73.75% avg",
        required["status"] == "reachable"
        and abs(required["required_average_percent"] - 73.75) < 1e-6,
        str(required)[:160],
    )
    what_if = unwrap(
        a.post(
            f"/enrolments/{enrolment_id}/required-marks",
            json={"target_grade": 6, "what_if_scores": {"Assignment 2": 90}},
        )
    )
    # secured 16+27=43; remaining 50 -> (75-43)/50*100 = 64
    check(
        "what-if 90 on A2 shifts exam requirement to 64%",
        abs(what_if["required_average_percent"] - 64.0) < 1e-6,
        str(what_if.get("required_average_percent")),
    )
    hurdle = unwrap(a.post(f"/enrolments/{enrolment_id}/required-marks", json={"target_grade": 4}))
    check(
        "hurdle on final exam surfaced per-item",
        any(item.get("hurdle_min_percent") == 40 for item in hurdle["per_item"]),
        str(hurdle["per_item"])[:160],
    )

    print("== Guest calculator (no auth) ==")
    guest_calc = unwrap(
        guest.post(
            "/calculator/what-if",
            json={
                "items": [
                    {"name": "A1", "weight": 40, "score": 80},
                    {"name": "Exam", "weight": 60},
                ],
                "target_grade": 4,
            },
        )
    )
    check(
        "guest what-if returns 30% required",
        abs(guest_calc["required_average_percent"] - 30.0) < 1e-6,
        str(guest_calc.get("required_average_percent")),
    )

    print("== Planner ==")
    programs = unwrap(a.get("/programs"))
    ids = {p["code"]: p["id"] for p in programs}
    unwrap(a.put("/planner/programs", json={"program_ids": [ids["BCompSc"], ids["BInfTech"]]}))
    prereq_status = unwrap(a.get("/planner/prereq-status"))
    csse2002 = next(row for row in prereq_status if row["course_code"] == "CSSE2002")
    check(
        "CSSE2002 prereq not met before CSSE1001 completed",
        csse2002["prereq_status"] in ("not_met", "partially_met"),
        csse2002["prereq_status"],
    )
    sequence = unwrap(
        a.post("/planner/sequence", json={"start_year": 2026, "start_semester": "S2"})
    )
    scheduled = [e["course_code"] for s in sequence["semesters"] for e in s["entries"]]
    # Union of both programs' required courses is 12 unique codes:
    # 8 (BCompSc) + 6 (BInfTech) − 2 shared (CSSE1001, CSSE2002) — FR-3.6.3.
    check(
        "dual-degree sequence feasible; 12 merged required courses, no duplicates",
        sequence["feasible"] and len(scheduled) == 12 and len(set(scheduled)) == 12,
        f"feasible={sequence['feasible']} n={len(scheduled)}",
    )
    order = {code: i for i, code in enumerate(scheduled)}
    check(
        "sequence places CSSE1001 before CSSE2002",
        order.get("CSSE1001", -1) < order.get("CSSE2002", 10**6),
    )

    print("== Search & AI advisory ==")
    results = unwrap(a.get("/search/courses", params={"q": "machine learning"}))
    check(
        "semantic search ranks COMP4702 (ML) first",
        results and results[0]["code"] == "COMP4702",
        str([r["code"] for r in results[:5]]),
    )
    recs = unwrap(a.post("/recommendations/generate", json={"interests": ["databases"]}))
    check(
        "recommendations carry reasons + deterministic prereq status",
        len(recs["items"]) > 0 and all(r["reason"] and r["prereq_status"] for r in recs["items"]),
    )
    # Study plan for a course whose assessment is still upcoming (2026 S2)
    s2_enrolment = unwrap(
        a.post("/enrolments", json={"course_code": "COMP3506", "year": 2026, "semester": "S2"})
    )
    plan = unwrap(
        a.post(
            "/study-plans/generate",
            json={"enrolment_id": s2_enrolment["id"], "target_grade": 6},
        )
    )
    check("study plan has sessions for upcoming assessment", len(plan["sessions"]) > 0)
    answer = unwrap(
        a.post(
            "/assistant/ask",
            json={"question": "What do I need on the final?", "enrolment_id": enrolment_id},
        )
    )
    check("assistant answers with deterministic figures", bool(answer["answer"]))

    print("== Account ==")
    gpa = unwrap(a.get("/me/gpa"))
    check("GPA endpoint responds", "gpa" in gpa)
    history = unwrap(a.get("/me/history"))
    in_progress = [h for h in history if h["status"] == "in_progress"]
    check("history lists both in-progress enrolments", len(in_progress) == 2,
          f"got {len(in_progress)}")

    print("== Ingestion + curator ==")
    ecp_text = (REPO_ROOT / "seed/data/ecp_samples/COMP2140_2026S2.txt").read_text()
    job = unwrap(a.post("/ingestion/jobs", json={"source_type": "text", "payload": ecp_text}))
    check("ECP ingestion extracts COMP2140", job["status"] == "extracted", str(job)[:160])

    admin = httpx.Client(
        base_url=env["SUPABASE_URL"],
        headers={
            "apikey": env["SUPABASE_SERVICE_ROLE_KEY"],
            "Authorization": f"Bearer {env['SUPABASE_SERVICE_ROLE_KEY']}",
        },
        timeout=30,
    )
    users = admin.get("/auth/v1/admin/users", params={"per_page": 100}).json()["users"]
    user_a_id = next(u["id"] for u in users if u["email"] == email_a)
    admin.patch(
        "/rest/v1/profiles",
        params={"id": f"eq.{user_a_id}"},
        json={"role": "curator"},
        headers={"Prefer": "return=minimal"},
    )
    drafts = unwrap(a.get("/curator/profile-versions", params={"status": "draft"}))
    draft_id = next((v["id"] for v in drafts if v["courses"]["code"] == "COMP2140"), None)
    if draft_id is not None:
        verified = unwrap(a.post(f"/curator/profile-versions/{draft_id}/verify"))
        check("curator verifies COMP2140 draft", verified["status"] == "verified")
    else:
        # A previous run already verified this version; ingestion must have
        # reused it rather than re-extracting (FR-3.5.6).
        check("ingestion reused the already-verified version (cached)", job.get("cached") is True)
    comp2140 = unwrap(a.get("/courses/COMP2140/profile"))
    check(
        "verified COMP2140 profile served with hurdle",
        comp2140["status"] == "verified"
        and any(item["hurdle_min_percent"] for item in comp2140["assessments"]),
    )

    print("== Isolation (RLS + API scoping) ==")
    b_enrolments = unwrap(b.get("/enrolments"))
    check("user B sees none of user A's enrolments", b_enrolments == [])
    foreign = b.get(f"/enrolments/{enrolment_id}/standing")
    check(
        "user B blocked from user A's enrolment",
        foreign.status_code == 404,
        f"status={foreign.status_code}",
    )
    anon_headers = {
        "apikey": env["SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {env['SUPABASE_ANON_KEY']}",
    }
    anon_rest = httpx.get(
        f"{env['SUPABASE_URL']}/rest/v1/enrolments?select=*", headers=anon_headers, timeout=30
    )
    check("anon PostgREST sees zero enrolment rows (RLS)", anon_rest.json() == [])
    anon_courses = httpx.get(
        f"{env['SUPABASE_URL']}/rest/v1/courses?select=code&limit=3",
        headers=anon_headers,
        timeout=30,
    )
    check("anon PostgREST reads public catalogue (RLS)", len(anon_courses.json()) == 3)

    print("== Cleanup: account deletion (FR-3.1.4) ==")
    deleted = a.delete("/me")
    check("user A deletes own account", deleted.status_code == 200)
    relogin = httpx.post(
        f"{env['SUPABASE_URL']}/auth/v1/token?grant_type=password",
        headers={"apikey": env["SUPABASE_ANON_KEY"]},
        json={"email": email_a, "password": password},
        timeout=30,
    )
    check("deleted user can no longer log in", relogin.status_code != 200)
    b.delete("/me")

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
