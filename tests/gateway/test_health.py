"""Tests for the health check endpoint."""

from fastapi.testclient import TestClient

from apps.gateway.main import app

client = TestClient(app)


def test_health_check_returns_ok() -> None:
    """Verify health check returns status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


