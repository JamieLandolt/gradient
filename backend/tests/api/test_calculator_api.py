"""Guest what-if calculator: public, stateless (FR-3.1.5)."""

import pytest

from tests.api.fakes import build_client


def test_guest_calculator_requires_no_auth():
    client, _, _ = build_client(user=None)

    response = client.post(
        "/api/v1/calculator/what-if",
        json={
            "items": [
                {"name": "A1", "weight": 40, "score": 80},
                {"name": "Exam", "weight": 60},
            ],
            "target_grade": 4,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "reachable"
    assert data["required_average_percent"] == pytest.approx(30.0)
    assert data["standing"]["secured_percent"] == pytest.approx(32.0)


def test_guest_calculator_validates_structure():
    client, _, _ = build_client(user=None)

    response = client.post(
        "/api/v1/calculator/what-if",
        json={"items": [{"name": "A1", "weight": 30}], "target_grade": 4},
    )

    assert response.status_code == 422
    assert "100" in response.json()["error"]
