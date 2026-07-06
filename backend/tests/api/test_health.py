def test_health_returns_ok_envelope(client):
    # Act
    response = client.get("/api/v1/health")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"status": "ok"}
    assert body["error"] is None


def test_unknown_route_returns_404(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
