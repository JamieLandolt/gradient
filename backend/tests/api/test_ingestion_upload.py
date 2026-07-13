"""ECP file-upload endpoint: PDF + .txt → the same async extraction pipeline."""

from pathlib import Path

from app.core.auth import AuthUser
from tests.api.fakes import build_client
from tests.unit.test_pdf import make_pdf

ALICE = AuthUser(id="user-alice", email="alice@uq.test")
SAMPLES = Path(__file__).resolve().parents[2].parent / "seed" / "data" / "ecp_samples"


def _curator_client():
    client, _, students = build_client(user=ALICE)
    students.profiles[ALICE.id] = {
        "id": ALICE.id, "display_name": "Alice", "role": "curator",
        "created_at": "2026-01-01T00:00:00Z",
    }
    return client


def _poll(client, job_id):
    return client.get(f"/api/v1/ingestion/jobs/{job_id}").json()["data"]


def test_upload_txt_queues_then_extracts():
    client = _curator_client()
    payload = (SAMPLES / "COMP2140_2026S2.txt").read_bytes()

    response = client.post(
        "/api/v1/ingestion/uploads",
        files={"file": ("COMP2140.txt", payload, "text/plain")},
    )

    assert response.status_code == 201
    queued = response.json()["data"]
    assert queued["status"] == "queued"
    assert queued["source_type"] == "upload"

    job = _poll(client, queued["id"])
    assert job["status"] == "extracted"
    assert job["course_code"] == "COMP2140"


def test_upload_pdf_is_parsed_and_extracted():
    client = _curator_client()
    pdf = make_pdf("Course code: TEST5000")

    response = client.post(
        "/api/v1/ingestion/uploads",
        files={"file": ("profile.pdf", pdf, "application/pdf")},
    )

    assert response.status_code == 201
    job = _poll(client, response.json()["data"]["id"])
    # The mock extractor only needs a valid "Course code:" line to draft a course.
    assert job["status"] == "extracted"
    assert job["course_code"] == "TEST5000"


def test_upload_rejects_an_empty_file():
    client = _curator_client()

    response = client.post(
        "/api/v1/ingestion/uploads",
        files={"file": ("blank.txt", b"   ", "text/plain")},
    )

    assert response.status_code == 422


def test_upload_rejects_a_corrupt_pdf():
    client = _curator_client()

    response = client.post(
        "/api/v1/ingestion/uploads",
        files={"file": ("broken.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")},
    )

    assert response.status_code == 422


def test_upload_rejects_text_over_the_char_cap():
    client = _curator_client()
    # Valid course code, but the body blows the 100k-character processing cap.
    payload = ("Course code: TEST6000\n" + "x" * 100_001).encode("utf-8")

    response = client.post(
        "/api/v1/ingestion/uploads",
        files={"file": ("huge.txt", payload, "text/plain")},
    )

    assert response.status_code == 422


def test_upload_requires_authentication():
    client, _, _ = build_client(user=None)

    response = client.post(
        "/api/v1/ingestion/uploads",
        files={"file": ("ecp.txt", b"Course code: TEST7000", "text/plain")},
    )

    assert response.status_code == 401
