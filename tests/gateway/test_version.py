"""Tests for the version endpoint."""

from fastapi.testclient import TestClient

from apps.gateway.main import app

client = TestClient(app)


def test_version_returns_correct_data() -> None:
    """Verify version endpoint returns correct application info."""
    response = client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Local AI Platform"
    assert data["version"] == "0.1.0"


