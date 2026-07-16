"""Planner endpoints with fakes: program selection, prereq status, sequence."""

from app.core.auth import AuthUser
from app.domain.planning.models import PrereqNode
from tests.api.fakes import FakeCatalogueRepository, build_client

ALICE = AuthUser(id="user-alice", email="alice@uq.test")


def setup_programs(client):
    return client.put("/api/v1/planner/programs", json={"program_ids": [1]})


def test_program_selection_roundtrip():
    client, _, _ = build_client(user=ALICE)

    put = setup_programs(client)
    assert put.status_code == 200

    got = client.get("/api/v1/planner/programs").json()["data"]
    assert got[0]["programs"]["code"] == "BCompSc"


def test_prereq_status_reflects_completed_courses():
    client, _, students = build_client(user=ALICE)
    setup_programs(client)
    client.post(
        "/api/v1/enrolments",
        json={"course_code": "CSSE1001", "year": 2026, "semester": "S1",
              "status": "completed", "final_grade": 5},
    )

    statuses = client.get("/api/v1/planner/prereq-status").json()["data"]
    by_code = {s["course_code"]: s for s in statuses}

    assert by_code["CSSE1001"]["is_completed"] is True
    assert by_code["COMP3506"]["prereq_status"] == "met"
    assert by_code["MATH1051"]["prereq_status"] == "met"  # no prereqs


def test_sequence_orders_prerequisites():
    client, _, _ = build_client(user=ALICE)
    setup_programs(client)

    plan = client.post(
        "/api/v1/planner/sequence",
        json={"start_year": 2026, "start_semester": "S1"},
    ).json()["data"]

    assert plan["feasible"] is True
    placed = {
        entry["course_code"]: index
        for index, semester in enumerate(plan["semesters"])
        for entry in semester["entries"]
    }
    assert placed["CSSE1001"] < placed["COMP3506"]


def test_sequence_schedules_a_non_required_prerequisite_of_a_required_course():
    # COMP3506 is required, but here its prerequisite (CSSE2002) is only listed
    # as an ELECTIVE for the program — never in the required set. Without
    # pulling it in transitively, COMP3506 can never become eligible (its
    # prereq is neither completed nor ever scheduled), so the plan used to come
    # back infeasible instead of scheduling CSSE2002 first to unlock it.
    catalogue = FakeCatalogueRepository()
    catalogue.courses["CSSE2002"] = {
        "id": 4, "code": "CSSE2002", "title": "Object Oriented Design",
        "units": 2, "description": "OOP design",
    }
    catalogue.offerings.append({"id": 20, "course_id": 4, "year": 2026, "semester": "S1"})
    catalogue.offerings.append({"id": 21, "course_id": 4, "year": 2026, "semester": "S2"})
    catalogue.prereq_trees[3] = PrereqNode.course("CSSE2002")  # COMP3506's course_id is 3
    catalogue.raw_prereqs[3] = "CSSE2002"
    catalogue.program_courses[1].append(
        {"requirement_kind": "elective", "courses": {"code": "CSSE2002"}}
    )

    client, _, _ = build_client(catalogue=catalogue, user=ALICE)
    setup_programs(client)

    plan = client.post(
        "/api/v1/planner/sequence",
        json={"start_year": 2026, "start_semester": "S1"},
    ).json()["data"]

    assert plan["feasible"] is True
    placed = {
        entry["course_code"]: index
        for index, semester in enumerate(plan["semesters"])
        for entry in semester["entries"]
    }
    assert "CSSE2002" in placed  # pulled in even though it's only an elective
    assert placed["CSSE2002"] < placed["COMP3506"]


def test_sequence_without_programs_is_a_validation_error():
    client, _, _ = build_client(user=ALICE)

    response = client.post(
        "/api/v1/planner/sequence",
        json={"start_year": 2026, "start_semester": "S1"},
    )

    assert response.status_code == 422


def test_sequence_study_load_changes_courses_placed_per_semester():
    # CSSE1001 (S1+S2) and MATH1051 (S1 only) have no prerequisites; COMP3506
    # (S2 only) requires CSSE1001. So S1 always has 2 eligible courses and S2
    # always has 1 (once CSSE1001 is done) — full_time (target 4) falls short
    # both semesters, part_time (target 2) hits its target exactly in S1.
    client, _, _ = build_client(user=ALICE)
    setup_programs(client)

    full_time = client.post(
        "/api/v1/planner/sequence",
        json={"start_year": 2026, "start_semester": "S1", "study_load": "full_time"},
    ).json()["data"]
    part_time = client.post(
        "/api/v1/planner/sequence",
        json={"start_year": 2026, "start_semester": "S1", "study_load": "part_time"},
    ).json()["data"]

    def counts(plan):
        return [len(s["entries"]) for s in plan["semesters"]]

    assert counts(full_time) == [2, 1]
    assert counts(part_time) == [2, 1]

    full_time_shortfalls = [d for d in full_time["diagnostics"] if d["severity"] == "info"]
    part_time_shortfalls = [d for d in part_time["diagnostics"] if d["severity"] == "info"]
    assert len(full_time_shortfalls) == 2  # both semesters fall short of a target of 4
    assert len(part_time_shortfalls) == 1  # only S2 falls short of a target of 2


def test_sequence_accepts_planner_preferences():
    client, _, _ = build_client(user=ALICE)
    setup_programs(client)

    plan = client.post(
        "/api/v1/planner/sequence",
        json={"start_year": 2026, "start_semester": "S1",
              "prioritise_available": True, "interests": ["algorithms"]},
    ).json()["data"]

    assert plan["feasible"] is True
    assert plan["semesters"]


def test_save_list_get_and_delete_a_degree_plan():
    client, _, _ = build_client(user=ALICE)
    setup_programs(client)

    saved = client.post(
        "/api/v1/planner/plans",
        json={"name": "My CS plan", "start_year": 2026, "start_semester": "S1"},
    )
    assert saved.status_code == 201
    plan = saved.json()["data"]
    assert plan["name"] == "My CS plan"
    assert plan["semesters"]
    placed = {
        entry["course_code"]
        for semester in plan["semesters"]
        for entry in semester["entries"]
    }
    assert "CSSE1001" in placed

    listing = client.get("/api/v1/planner/plans").json()["data"]
    assert listing[0]["id"] == plan["id"]
    assert listing[0]["name"] == "My CS plan"

    got = client.get(f"/api/v1/planner/plans/{plan['id']}").json()["data"]
    assert got["id"] == plan["id"]
    assert got["semesters"]

    assert client.delete(f"/api/v1/planner/plans/{plan['id']}").status_code == 200
    assert client.get("/api/v1/planner/plans").json()["data"] == []


def test_get_missing_degree_plan_is_404():
    client, _, _ = build_client(user=ALICE)

    assert client.get("/api/v1/planner/plans/9999").status_code == 404


def test_saved_plan_preserves_empty_gap_semesters_on_reload():
    # Complete CSSE1001 + MATH1051 so only COMP3506 (S2-only, prereq CSSE1001)
    # remains; a plan from S1 then has a deliberate empty S1 gap before S2.
    client, _, _ = build_client(user=ALICE)
    setup_programs(client)
    for code in ("CSSE1001", "MATH1051"):
        client.post(
            "/api/v1/enrolments",
            json={"course_code": code, "year": 2026, "semester": "S1",
                  "status": "completed", "final_grade": 5},
        )

    body = {"start_year": 2026, "start_semester": "S1"}
    live = client.post("/api/v1/planner/sequence", json=body).json()["data"]
    live_labels = [s["label"] for s in live["semesters"]]
    assert live_labels == ["2026 S1", "2026 S2"]  # leading empty gap kept

    saved = client.post("/api/v1/planner/plans", json={**body, "name": "gap"}).json()["data"]
    reloaded = client.get(f"/api/v1/planner/plans/{saved['id']}").json()["data"]

    # The reloaded plan must match the live preview, gap semester included.
    assert [s["label"] for s in reloaded["semesters"]] == live_labels
    assert reloaded["semesters"][0]["entries"] == []
    placed = {e["course_code"] for s in reloaded["semesters"] for e in s["entries"]}
    assert placed == {"COMP3506"}
