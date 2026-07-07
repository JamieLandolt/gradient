"""Error-handling contract: every error uses the standard envelope."""

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.errors import NotFoundError
from app.main import create_app


def build_client_with_failing_routes(settings: Settings) -> TestClient:
    app = create_app(settings)
    router = APIRouter(prefix="/api/v1")

    @router.get("/boom-app-error")
    async def boom_app_error():
        raise NotFoundError("Course not found")

    @router.get("/boom-unexpected")
    async def boom_unexpected():
        raise RuntimeError("secret internal detail")

    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_app_error_uses_envelope_and_status(settings):
    client = build_client_with_failing_routes(settings)

    response = client.get("/api/v1/boom-app-error")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "Course not found"
    assert body["data"] is None


def test_unexpected_error_hides_internal_details(settings):
    client = build_client_with_failing_routes(settings)

    response = client.get("/api/v1/boom-unexpected")

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "Internal server error"
    assert "secret" not in response.text
