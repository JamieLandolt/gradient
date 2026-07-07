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
