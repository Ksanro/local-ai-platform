"""Tests for the chat completions endpoint."""

from fastapi.testclient import TestClient

from apps.gateway.main import app

client = TestClient(app)


def test_chat_completions_returns_501() -> None:
    """Verify chat completions returns 501 when no provider is configured."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 501
    data = response.json()
    assert data["detail"] == "Provider not configured"


