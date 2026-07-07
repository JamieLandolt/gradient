"""Ingestion, curator, and advisory endpoints with fakes."""

from pathlib import Path

from app.core.auth import AuthUser
from tests.api.fakes import FakeCatalogueRepository, FakeIngestionRepository, build_client

ALICE = AuthUser(id="user-alice", email="alice@uq.test")
SAMPLES = Path(__file__).resolve().parents[2].parent / "seed" / "data" / "ecp_samples"


def make_curator_client():
    catalogue = FakeCatalogueRepository()
    client, _, students = build_client(catalogue=catalogue, user=ALICE)
    students.profiles[ALICE.id] = {
        "id": ALICE.id, "display_name": "Alice", "role": "curator",
        "created_at": "2026-01-01T00:00:00Z",
    }
    return client, students


class TestIngestion:
    def test_submit_creates_draft_version(self):
        client, _ = make_curator_client()
        payload = (SAMPLES / "COMP2140_2026S2.txt").read_text()

        response = client.post(
            "/api/v1/ingestion/jobs", json={"source_type": "text", "payload": payload}
        )

        assert response.status_code == 201
        job = response.json()["data"]
        assert job["status"] == "extracted"
        assert job["cached"] is False

        drafts = client.get("/api/v1/curator/profile-versions").json()["data"]
        assert len(drafts) == 1
        assert drafts[0]["version_label"] == "2026S2"

    def test_resubmission_is_cached_per_version(self):
        client, _ = make_curator_client()
        payload = (SAMPLES / "COMP2140_2026S2.txt").read_text()

        first = client.post(
            "/api/v1/ingestion/jobs", json={"source_type": "text", "payload": payload}
        ).json()["data"]
        second = client.post(
            "/api/v1/ingestion/jobs", json={"source_type": "text", "payload": payload}
        ).json()["data"]

        assert first["cached"] is False
        assert second["cached"] is True
        assert second["profile_version_id"] == first["profile_version_id"]

    def test_students_cannot_use_curator_endpoints(self):
        client, _, students = build_client(user=ALICE)
        students.profiles[ALICE.id] = {
            "id": ALICE.id, "display_name": "Alice", "role": "student",
            "created_at": "2026-01-01T00:00:00Z",
        }

        response = client.get("/api/v1/curator/profile-versions")

        assert response.status_code == 403

    def test_verify_flips_status(self):
        client, _ = make_curator_client()
        payload = (SAMPLES / "COMP2140_2026S2.txt").read_text()
        job = client.post(
            "/api/v1/ingestion/jobs", json={"source_type": "text", "payload": payload}
        ).json()["data"]

        verified = client.post(
            f"/api/v1/curator/profile-versions/{job['profile_version_id']}/verify"
        ).json()["data"]

        assert verified["status"] == "verified"


class TestAdvisory:
    def test_recommendations_cite_engine_prereq_status(self):
        client, _, _ = build_client(user=ALICE)

        response = client.post(
            "/api/v1/recommendations/generate",
            json={"interests": ["algorithms"], "limit": 3},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["items"]
        assert all(
            item["prereq_status"] in ("met", "partially_met", "not_met")
            for item in data["items"]
        )
        assert "advisory" in data["disclaimer"]

    def test_study_plan_generation(self):
        client, _, _ = build_client(user=ALICE)
        enrolment = client.post(
            "/api/v1/enrolments",
            json={"course_code": "CSSE1001", "year": 2026, "semester": "S1"},
        ).json()["data"]

        response = client.post(
            "/api/v1/study-plans/generate",
            json={"enrolment_id": enrolment["id"], "target_grade": 6,
                  "start_date": "2026-03-01"},
        )

        assert response.status_code == 200
        plan = response.json()["data"]
        assert plan["course_code"] == "CSSE1001"
        assert plan["sessions"]

    def test_search_returns_similar_courses(self):
        catalogue = FakeCatalogueRepository()
        ingestion = FakeIngestionRepository(catalogue)
        from app.providers.mock.embeddings import embed_text

        for course in catalogue.courses.values():
            ingestion.upsert_embedding(
                course["id"],
                embed_text(f"{course['title']} {course['description']}"),
                "mock",
            )
        client, _, _ = build_client(catalogue=catalogue, ingestion=ingestion, user=None)

        response = client.get("/api/v1/search/courses", params={"q": "algorithms"})

        assert response.status_code == 200
        results = response.json()["data"]
        assert results[0]["code"] == "COMP3506"

    def test_assistant_answers_with_grounded_facts(self):
        client, _, _ = build_client(user=ALICE)

        response = client.post(
            "/api/v1/assistant/ask", json={"question": "How am I doing?"}
        )

        assert response.status_code == 200
        answer = response.json()["data"]["answer"]
        assert "GPA" in answer
        assert "authoritative" in answer
