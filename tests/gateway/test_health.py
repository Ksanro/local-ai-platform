"""Tests for the health check endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.gateway.core.config import Settings
from apps.gateway.main import app

client = TestClient(app)


def test_health_check_returns_ok() -> None:
    """Verify health check returns status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "repository_context_enabled" in data


def test_health_includes_repository_context_when_enabled() -> None:
    """Verify health response includes enabled repository context status."""
    settings = Settings(repository_context_enabled=True)

    with patch("apps.gateway.api.health.get_settings", return_value=settings):
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["repository_context_enabled"] is True
    assert "repository_context" not in data


def test_health_includes_repository_context_when_disabled() -> None:
    """Verify health response includes disabled repository context status."""
    settings = Settings(repository_context_enabled=False)

    with patch("apps.gateway.api.health.get_settings", return_value=settings):
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["repository_context_enabled"] is False
    assert "repository_context" not in data


