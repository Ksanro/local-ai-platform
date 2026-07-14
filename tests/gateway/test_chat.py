"""Tests for the chat completions endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.gateway.api.chat import router as chat_router
from packages.providers.exceptions import UnknownProviderError
from packages.providers.factory import create_provider
from packages.providers.registry import get_registry


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with the chat router.

    The TestClient does not run the application lifespan, so the
    provider must be wired into app.state.provider manually.
    """
    from apps.gateway.api.chat import _wrap_stream_duration  # noqa: F401

    app = FastAPI()
    app.include_router(chat_router)
    return app


def test_chat_completions_provider_not_found() -> None:
    """Verify chat completions returns 501 when DEFAULT_PROVIDER points to an
    unregistered provider name."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    with patch(
        "apps.gateway.api.chat.get_settings",
        return_value=type(
            "FakeSettings", (), {"default_provider": "nonexistent"}
        )(),
    ):
        app = _make_app()
        client = TestClient(app)
        response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 501
    data = response.json()
    assert "not registered" in data["detail"].lower() or "not found" in data["detail"].lower()


def test_chat_completions_no_providers_registered() -> None:
    """Verify 501 when the registry is empty."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    with patch("apps.gateway.api.chat.get_registry", return_value={}):
        app = _make_app()
        client = TestClient(app)
        response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 501
    data = response.json()
    assert data["detail"] == "No providers registered"


def test_chat_completions_streaming_error_on_provider_failure() -> None:
    """Verify 502 when the provider raises during streaming."""
    from packages.providers.exceptions import ProviderConnectionError

    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
        "stream": True,
    }
    mock_provider = MagicMock()
    mock_provider.chat.side_effect = ProviderConnectionError("vLLM unreachable")
    app = _make_app()
    app.state.provider = mock_provider
    client = TestClient(app)
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 502


def test_streaming_response_returns_multiple_chunks() -> None:
    """Verify streaming endpoint returns at least 2 SSE chunks from the
    real vLLM server."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "qwen36",
        "stream": True,
        "max_tokens": 50,
    }
    app = _make_app()
    # Use the real provider (reads VLLM_BASE_URL from env).
    app.state.provider = create_provider("vllm")
    client = TestClient(app)
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/event-stream")
    # Count SSE data lines (each "data: ..." line is one chunk).
    data_lines = [
        line for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert len(data_lines) >= 2, (
        f"Expected at least 2 SSE data lines, got {len(data_lines)}"
    )


def test_chat_completions_streaming_has_done_token() -> None:
    """Verify the streaming response ends with a [DONE] terminator."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "qwen36",
        "stream": True,
        "max_tokens": 20,
    }
    app = _make_app()
    app.state.provider = create_provider("vllm")
    client = TestClient(app)
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "data: [DONE]" in response.text


def test_chat_completions_non_streaming() -> None:
    """Verify non-streaming chat returns valid OpenAI JSON shape."""
    payload = {
        "messages": [{"role": "user", "content": "Reply with exactly OK"}],
        "model": "qwen36",
        "stream": False,
        "max_tokens": 10,
    }
    app = _make_app()
    app.state.provider = create_provider("vllm")
    client = TestClient(app)
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
    assert len(data["choices"]) > 0
    assert data["choices"][0]["message"]["role"] == "assistant"
