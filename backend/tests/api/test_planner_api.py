"""Planner endpoints with fakes: program selection, prereq status, sequence."""

from app.core.auth import AuthUser
from tests.api.fakes import build_client

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


def test_sequence_without_programs_is_a_validation_error():
    client, _, _ = build_client(user=ALICE)

    response = client.post(
        "/api/v1/planner/sequence",
        json={"start_year": 2026, "start_semester": "S1"},
    )

    assert response.status_code == 422


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
