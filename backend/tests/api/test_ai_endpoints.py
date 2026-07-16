"""Ingestion, curator, and advisory endpoints with fakes."""

from pathlib import Path

from app.core.auth import AuthUser
from app.domain.planning.models import PrereqNode
from tests.api.fakes import (
    FakeArtifactRepository,
    FakeCatalogueRepository,
    FakeIngestionRepository,
    FakeStudentRepository,
    build_client,
)

ALICE = AuthUser(id="user-alice", email="alice@uq.test")
BOB = AuthUser(id="user-bob", email="bob@uq.test")


def _enrol(client, code="CSSE1001", year=2026, semester="S1"):
    return client.post(
        "/api/v1/enrolments",
        json={"course_code": code, "year": year, "semester": semester},
    ).json()["data"]
SAMPLES = Path(__file__).resolve().parents[2].parent / "seed" / "data" / "ecp_samples"


def make_curator_client():
    catalogue = FakeCatalogueRepository()
    client, _, students = build_client(catalogue=catalogue, user=ALICE)
    students.profiles[ALICE.id] = {
        "id": ALICE.id, "display_name": "Alice", "role": "curator",
        "created_at": "2026-01-01T00:00:00Z",
    }
    return client, students


def _poll_job(client, job_id):
    """Fetch a job after submission. Under TestClient the BackgroundTasks run
    inline before the POST returns, so a single GET reflects the terminal state
    the real client reaches by polling (FR-3.5.3 / NFR-5.1.5)."""
    return client.get(f"/api/v1/ingestion/jobs/{job_id}").json()["data"]


class TestIngestion:
    def test_submit_queues_then_extracts_a_draft_version(self):
        client, _ = make_curator_client()
        payload = (SAMPLES / "COMP2140_2026S2.txt").read_text()

        response = client.post(
            "/api/v1/ingestion/jobs", json={"source_type": "text", "payload": payload}
        )

        assert response.status_code == 201
        queued = response.json()["data"]
        assert queued["status"] == "queued"
        assert queued["profile_version_id"] is None

        job = _poll_job(client, queued["id"])
        assert job["status"] == "extracted"
        assert job["course_code"] == "COMP2140"

        drafts = client.get("/api/v1/curator/profile-versions").json()["data"]
        assert len(drafts) == 1
        assert drafts[0]["version_label"] == "2026S2"

    def test_submission_cannot_rewrite_an_existing_courses_prerequisites(self):
        """Ingestion is open to any authenticated student and the draft is
        unreviewed, but prerequisites are shared facts the planner treats as
        authoritative for everyone. Re-submitting an existing course under a new
        version label used to replace its tree globally."""
        catalogue = FakeCatalogueRepository()
        client, _, _ = build_client(catalogue=catalogue, user=BOB)
        before = catalogue.prereq_trees[catalogue.courses["COMP3506"]["id"]]

        payload = (
            "Course code: COMP3506\n"
            "Course title: Algorithms & Data Structures\n"
            "Units: 2\n"
            "Semester: Semester 1, 2099\n"
            "Description: Free marks for everyone.\n"
            "Assessment:\n"
            "- Exam | weight: 100% | max mark: 100\n"
            "Prerequisite: MATH1051\n"
        )
        job_id = client.post(
            "/api/v1/ingestion/jobs", json={"source_type": "text", "payload": payload}
        ).json()["data"]["id"]
        job = _poll_job(client, job_id)

        # The draft is still created for the curator to review…
        assert job["status"] == "extracted"
        # …but the live prerequisite tree is untouched.
        assert catalogue.prereq_trees[catalogue.courses["COMP3506"]["id"]] == before

    def test_a_brand_new_course_still_gets_its_prerequisites(self):
        """The guard must not break the legitimate import path: a course this
        submission creates has no dependents, so its tree is safe to populate."""
        catalogue = FakeCatalogueRepository()
        client, _, _ = build_client(catalogue=catalogue, user=BOB)

        payload = (
            "Course code: COMP9999\n"
            "Course title: Brand New Course\n"
            "Units: 2\n"
            "Semester: Semester 1, 2026\n"
            "Description: A course that did not exist before.\n"
            "Assessment:\n"
            "- Exam | weight: 100% | max mark: 100\n"
            "Prerequisite: CSSE1001\n"
        )
        job_id = client.post(
            "/api/v1/ingestion/jobs", json={"source_type": "text", "payload": payload}
        ).json()["data"]["id"]
        job = _poll_job(client, job_id)

        assert job["status"] == "extracted"
        new_id = catalogue.courses["COMP9999"]["id"]
        assert catalogue.prereq_trees[new_id] == PrereqNode.course("CSSE1001")

    def test_resubmission_reuses_the_same_version(self):
        client, _ = make_curator_client()
        payload = (SAMPLES / "COMP2140_2026S2.txt").read_text()

        first_id = client.post(
            "/api/v1/ingestion/jobs", json={"source_type": "text", "payload": payload}
        ).json()["data"]["id"]
        second_id = client.post(
            "/api/v1/ingestion/jobs", json={"source_type": "text", "payload": payload}
        ).json()["data"]["id"]

        first = _poll_job(client, first_id)
        second = _poll_job(client, second_id)
        assert first["profile_version_id"] == second["profile_version_id"]
        # Extraction runs once per profile version (FR-3.5.6): no duplicate draft.
        drafts = client.get("/api/v1/curator/profile-versions").json()["data"]
        assert len(drafts) == 1

    def test_bad_payload_marks_the_job_failed(self):
        client, _ = make_curator_client()

        queued = client.post(
            "/api/v1/ingestion/jobs",
            json={"source_type": "text", "payload": "no course code here at all"},
        ).json()["data"]
        assert queued["status"] == "queued"

        job = _poll_job(client, queued["id"])
        assert job["status"] == "failed"
        assert job["error"]
        assert client.get("/api/v1/curator/profile-versions").json()["data"] == []

    def test_url_import_scrapes_then_extracts_a_draft_version(self, monkeypatch):
        # The network fetch is the only untested-elsewhere piece here (covered
        # in isolation by test_uq_fetcher.py); stub it so this test exercises
        # the job/extraction wiring without touching the network.
        import app.services.ingestion as ingestion_module

        payload = (SAMPLES / "COMP2140_2026S2.txt").read_text()
        monkeypatch.setattr(ingestion_module, "fetch_ecp_text", lambda code: payload)

        client, _ = make_curator_client()

        response = client.post("/api/v1/ingestion/from-url", json={"course_code": "comp2140"})

        assert response.status_code == 201
        queued = response.json()["data"]
        assert queued["status"] == "queued"
        assert queued["course_code"] == "COMP2140"  # normalised immediately, unlike text/upload

        job = _poll_job(client, queued["id"])
        assert job["status"] == "extracted"
        assert job["course_code"] == "COMP2140"

    def test_url_import_fails_the_job_when_no_current_profile_is_found(self, monkeypatch):
        import app.services.ingestion as ingestion_module
        from app.ingestion.uq_fetcher import ECPNotFoundError

        def raise_not_found(code):
            raise ECPNotFoundError(f"No current course profile found for {code}")

        monkeypatch.setattr(ingestion_module, "fetch_ecp_text", raise_not_found)

        client, _ = make_curator_client()
        queued = client.post(
            "/api/v1/ingestion/from-url", json={"course_code": "GHOST9999"}
        ).json()["data"]

        job = _poll_job(client, queued["id"])
        assert job["status"] == "failed"
        assert "No current course profile found" in job["error"]

    def test_url_import_rejects_an_invalid_course_code(self):
        client, _, _ = build_client(user=ALICE)

        response = client.post(
            "/api/v1/ingestion/from-url", json={"course_code": "not a code!"}
        )

        assert response.status_code == 422

    def test_embedding_failure_does_not_fail_the_ingestion_job(self, monkeypatch):
        # Embeddings only feed semantic search; a flaky hosted-API call there
        # (e.g. the intermittent Bailian "SSL: UNEXPECTED_EOF") shouldn't sink
        # an otherwise-successful extraction + draft.
        from app.providers.mock.embeddings import MockEmbeddingProvider

        def raise_ssl_error(self, text):
            raise RuntimeError(
                "AI request to /embeddings failed: [SSL: UNEXPECTED_EOF_WHILE_READING]"
            )

        monkeypatch.setattr(MockEmbeddingProvider, "embed", raise_ssl_error)

        client, _ = make_curator_client()
        payload = (SAMPLES / "COMP2140_2026S2.txt").read_text()

        queued = client.post(
            "/api/v1/ingestion/jobs", json={"source_type": "text", "payload": payload}
        ).json()["data"]

        job = _poll_job(client, queued["id"])
        assert job["status"] == "extracted"
        assert job["course_code"] == "COMP2140"

        drafts = client.get("/api/v1/curator/profile-versions").json()["data"]
        assert len(drafts) == 1

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
        queued = client.post(
            "/api/v1/ingestion/jobs", json={"source_type": "text", "payload": payload}
        ).json()["data"]
        job = _poll_job(client, queued["id"])

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

    def test_regenerating_with_unchanged_inputs_hits_the_cache(self):
        # Same user/interests/limit twice in a row should return the exact same
        # persisted recommendation (same id) instead of generating + saving a
        # new one each time (docs/REVIEW_efficiency_ux.md perf finding).
        client, _, _ = build_client(user=ALICE)
        body = {"interests": ["algorithms"], "limit": 3}

        first = client.post("/api/v1/recommendations/generate", json=body).json()["data"]
        second = client.post("/api/v1/recommendations/generate", json=body).json()["data"]
        assert second["id"] == first["id"]

        changed = client.post(
            "/api/v1/recommendations/generate",
            json={"interests": ["genetics"], "limit": 3},
        ).json()["data"]
        assert changed["id"] != first["id"]

    def test_weekly_study_plan_generation(self):
        client, _, _ = build_client(user=ALICE)
        client.post(
            "/api/v1/enrolments",
            json={"course_code": "CSSE1001", "year": 2026, "semester": "S1"},
        )

        study_hours = client.put(
            "/api/v1/study-availability",
            json={"slots": [
                {"day_of_week": 0, "start_hour": h, "slot_type": "study"}
                for h in range(9, 17)
            ]},
        )
        assert study_hours.status_code == 200

        response = client.post(
            "/api/v1/study-plans/generate", json={"week_start": "2026-03-02"}
        )

        assert response.status_code == 200
        plan = response.json()["data"]
        assert plan["blocks"]
        assert all(b["course_code"] == "CSSE1001" for b in plan["blocks"])

    def test_remaining_assessments_excludes_graded_items_and_targets_roundtrip(self):
        client, _, _ = build_client(user=ALICE)
        enrolment = _enrol(client)

        remaining = client.get("/api/v1/study-plans/remaining-assessments").json()["data"]
        assert len(remaining) == 3  # all of CSSE1001_ASSESSMENTS, ungraded
        assert all(item["target_percent"] is None for item in remaining)

        first = remaining[0]
        saved = client.put(
            "/api/v1/study-plans/targets",
            json={"targets": [{
                "enrolment_id": first["enrolment_id"],
                "assessment_id": first["assessment_id"],
                "custom_assessment_id": first["custom_assessment_id"],
                "target_percent": 85,
            }]},
        )
        assert saved.status_code == 200
        updated = client.get("/api/v1/study-plans/remaining-assessments").json()["data"]
        updated_first = next(i for i in updated if i["name"] == first["name"])
        assert updated_first["target_percent"] == 85

        # Grading an item removes it from what's "remaining".
        client.put(
            f"/api/v1/enrolments/{enrolment['id']}/grades",
            json={"assessment_id": first["assessment_id"], "score": 90},
        )
        after_grading = client.get("/api/v1/study-plans/remaining-assessments").json()["data"]
        assert len(after_grading) == 2

    def test_generate_fails_without_any_study_slots(self):
        client, _, _ = build_client(user=ALICE)
        _enrol(client)

        response = client.post(
            "/api/v1/study-plans/generate", json={"week_start": "2026-03-02"}
        )

        assert response.status_code == 422

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


class TestPersistence:
    def test_recommendations_persist_reload_list_and_delete(self):
        client, _, _ = build_client(user=ALICE)

        generated = client.post(
            "/api/v1/recommendations/generate",
            json={"interests": ["algorithms"], "limit": 3},
        ).json()["data"]
        assert isinstance(generated["id"], int)

        latest = client.get("/api/v1/recommendations/latest").json()["data"]
        assert latest["id"] == generated["id"]

        def fields(item):
            return (item["course_code"], item["rank"], item["reason"], item["prereq_status"])

        # rank, reason, and the deterministic prereq_status must all round-trip.
        assert [fields(i) for i in latest["items"]] == [fields(i) for i in generated["items"]]

        listing = client.get("/api/v1/recommendations").json()["data"]
        assert listing[0]["id"] == generated["id"]

        deleted = client.delete(f"/api/v1/recommendations/{generated['id']}")
        assert deleted.status_code == 200
        assert client.get("/api/v1/recommendations/latest").json()["data"] is None

    def test_latest_recommendation_is_null_when_none_saved(self):
        client, _, _ = build_client(user=ALICE)

        assert client.get("/api/v1/recommendations/latest").json()["data"] is None

    def test_weekly_study_plan_persists_lists_and_is_fetchable(self):
        client, _, _ = build_client(user=ALICE)
        _enrol(client)
        client.put(
            "/api/v1/study-availability",
            json={"slots": [{"day_of_week": 0, "start_hour": 9, "slot_type": "study"}]},
        )

        generated = client.post(
            "/api/v1/study-plans/generate", json={"week_start": "2026-03-02"}
        ).json()["data"]
        assert isinstance(generated["id"], int)

        listing = client.get("/api/v1/study-plans").json()["data"]
        assert listing[0]["id"] == generated["id"]
        assert listing[0]["week_start"] == "2026-03-02"

        full = client.get(f"/api/v1/study-plans/{generated['id']}").json()["data"]
        assert full["blocks"]
        assert full["blocks"][0]["course_code"] == "CSSE1001"

        assert client.delete(f"/api/v1/study-plans/{generated['id']}").status_code == 200
        assert client.get("/api/v1/study-plans").json()["data"] == []

    def test_another_user_cannot_read_a_saved_weekly_study_plan(self):
        catalogue = FakeCatalogueRepository()
        students = FakeStudentRepository(catalogue)
        artifacts = FakeArtifactRepository(catalogue, students)
        alice, _, _ = build_client(
            catalogue=catalogue, students=students, artifacts=artifacts, user=ALICE
        )
        _enrol(alice)
        alice.put(
            "/api/v1/study-availability",
            json={"slots": [{"day_of_week": 0, "start_hour": 9, "slot_type": "study"}]},
        )
        plan = alice.post(
            "/api/v1/study-plans/generate", json={"week_start": "2026-03-02"}
        ).json()["data"]

        bob, _, _ = build_client(
            catalogue=catalogue, students=students, artifacts=artifacts, user=BOB
        )
        assert bob.get(f"/api/v1/study-plans/{plan['id']}").status_code == 404

    def test_another_user_cannot_write_a_target_on_someone_elses_enrolment(self):
        """enrolment_id comes from the request body, and the upsert's conflict
        key has no user_id in it — so an unchecked id lets one student overwrite
        (and, on real Supabase, take ownership of) another student's target."""
        catalogue = FakeCatalogueRepository()
        students = FakeStudentRepository(catalogue)
        artifacts = FakeArtifactRepository(catalogue, students)
        alice, _, _ = build_client(
            catalogue=catalogue, students=students, artifacts=artifacts, user=ALICE
        )
        enrolment = _enrol(alice)
        items = alice.get("/api/v1/study-plans/remaining-assessments").json()["data"]
        assessment_id = items[0]["assessment_id"]
        alice.put(
            "/api/v1/study-plans/targets",
            json={
                "targets": [
                    {
                        "enrolment_id": enrolment["id"],
                        "assessment_id": assessment_id,
                        "target_percent": 90.0,
                    }
                ]
            },
        )

        bob, _, _ = build_client(
            catalogue=catalogue, students=students, artifacts=artifacts, user=BOB
        )
        response = bob.put(
            "/api/v1/study-plans/targets",
            json={
                "targets": [
                    {
                        "enrolment_id": enrolment["id"],
                        "assessment_id": assessment_id,
                        "target_percent": 1.0,
                    }
                ]
            },
        )

        assert response.status_code == 404
        after = alice.get("/api/v1/study-plans/remaining-assessments").json()["data"]
        untouched = next(i for i in after if i["assessment_id"] == assessment_id)
        assert untouched["target_percent"] == 90.0

    def test_one_invalid_target_rejects_the_whole_batch(self):
        """Validation must run before any write, or a bad target midway through
        leaves the earlier ones committed behind a 422."""
        catalogue = FakeCatalogueRepository()
        students = FakeStudentRepository(catalogue)
        artifacts = FakeArtifactRepository(catalogue, students)
        alice, _, _ = build_client(
            catalogue=catalogue, students=students, artifacts=artifacts, user=ALICE
        )
        enrolment = _enrol(alice)
        items = alice.get("/api/v1/study-plans/remaining-assessments").json()["data"]

        response = alice.put(
            "/api/v1/study-plans/targets",
            json={
                "targets": [
                    {
                        "enrolment_id": enrolment["id"],
                        "assessment_id": items[0]["assessment_id"],
                        "target_percent": 70.0,
                    },
                    # Neither id supplied — invalid.
                    {"enrolment_id": enrolment["id"], "target_percent": 80.0},
                ]
            },
        )

        assert response.status_code == 422
        after = alice.get("/api/v1/study-plans/remaining-assessments").json()["data"]
        assert all(item["target_percent"] is None for item in after)


class TestAssistantStreaming:
    def test_streamed_answer_matches_the_non_streamed_answer(self):
        client, _, _ = build_client(user=ALICE)
        question = {"question": "How am I doing?"}

        whole = client.post("/api/v1/assistant/ask", json=question).json()["data"]["answer"]
        with client.stream("POST", "/api/v1/assistant/ask/stream", json=question) as stream:
            assert stream.status_code == 200
            streamed = "".join(chunk for chunk in stream.iter_text())

        assert streamed == whole
        assert "GPA" in streamed

    def test_stream_rejects_a_blank_question(self):
        client, _, _ = build_client(user=ALICE)

        response = client.post("/api/v1/assistant/ask/stream", json={"question": "   "})

        assert response.status_code == 422
