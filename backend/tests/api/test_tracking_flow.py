"""End-to-end API flow with fakes: enrol → grades → standing → required marks → GPA."""

import pytest

from app.core.auth import AuthUser
from tests.api.fakes import build_client

ALICE = AuthUser(id="user-alice", email="alice@uq.test")


@pytest.fixture()
def flow():
    client, catalogue, students = build_client(user=ALICE)
    students.profiles[ALICE.id] = {
        "id": ALICE.id, "display_name": "Alice", "role": "student",
        "created_at": "2026-01-01T00:00:00Z",
    }
    return client, catalogue, students


def enrol(client, code="CSSE1001", year=2026, semester="S1", **extra):
    response = client.post(
        "/api/v1/enrolments",
        json={"course_code": code, "year": year, "semester": semester, **extra},
    )
    return response


def test_enrol_and_see_profile_assessments(flow):
    client, _, _ = flow

    response = enrol(client)

    assert response.status_code == 201
    enrolment = response.json()["data"]
    assert enrolment["course_offerings"]["courses"]["code"] == "CSSE1001"

    standing = client.get(f"/api/v1/enrolments/{enrolment['id']}/standing").json()["data"]
    assert [item["name"] for item in standing["items"]] == [
        "Assignment 1", "Assignment 2", "Final Exam",
    ]


def test_enrolment_to_required_marks_flow(flow):
    client, _, _ = flow
    enrolment_id = enrol(client).json()["data"]["id"]

    # Record 80/100 on Assignment 1 (assessment_id 1, weight 20)
    put = client.put(
        f"/api/v1/enrolments/{enrolment_id}/grades",
        json={"assessment_id": 1, "score": 80},
    )
    assert put.status_code == 200

    standing = client.get(f"/api/v1/enrolments/{enrolment_id}/standing").json()["data"]
    assert standing["secured_percent"] == pytest.approx(16.0)  # 80% of 20

    required = client.post(
        f"/api/v1/enrolments/{enrolment_id}/required-marks",
        json={"target_grade": 4},
    ).json()["data"]
    # (50 - 16) / 80 * 100 = 42.5
    assert required["status"] == "reachable"
    assert required["required_average_percent"] == pytest.approx(42.5)


def test_unknown_offering_rejected_unless_transfer(flow):
    client, _, _ = flow

    rejected = enrol(client, code="CSSE1001", year=2020, semester="S1")
    assert rejected.status_code == 422

    transfer = enrol(
        client, code="CSSE1001", year=2020, semester="S1",
        is_transfer=True, status="completed", final_grade=6,
    )
    assert transfer.status_code == 201


def test_gpa_over_completed_courses(flow):
    client, _, _ = flow
    enrol(client, code="CSSE1001", year=2026, semester="S1",
          status="completed", final_grade=6)
    enrol(client, code="MATH1051", year=2026, semester="S1",
          status="completed", final_grade=4)

    gpa = client.get("/api/v1/me/gpa").json()["data"]

    assert gpa["gpa"] == pytest.approx(5.0)
    assert gpa["completed_courses"] == 2


def test_cross_user_enrolment_is_invisible():
    client_alice, catalogue, students = build_client(user=ALICE)
    enrolment_id = enrol(client_alice).json()["data"]["id"]

    bob = AuthUser(id="user-bob", email="bob@uq.test")
    client_bob, _, _ = build_client(catalogue=catalogue, students=students, user=bob)

    response = client_bob.get(f"/api/v1/enrolments/{enrolment_id}/standing")

    assert response.status_code == 404


def test_requests_without_token_are_unauthorized():
    client, _, _ = build_client(user=None)  # no auth override -> real dependency

    response = client.get("/api/v1/enrolments")

    assert response.status_code == 401
    assert response.json()["success"] is False


def test_account_deletion(flow):
    client, _, students = flow

    response = client.delete("/api/v1/me")

    assert response.status_code == 200
    assert students.deleted_accounts == [ALICE.id]
