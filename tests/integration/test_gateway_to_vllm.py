"""Integration tests: gateway communicates with a real vLLM instance.

These tests require:
- An actual vLLM server (``VLLM_BASE_URL``)
- A running gateway server (``GATEWAY_HOST:GATEWAY_PORT``)

Environment variables
---------------------
GATEWAY_HOST   - Gateway host (default ``localhost``)
GATEWAY_PORT   - Gateway port  (default ``8001``)
VLLM_BASE_URL  - vLLM server URL (required for integration tests)
DEFAULT_MODEL  - Model name to use (default ``default-model``)
REQUEST_TIMEOUT - Request timeout in seconds (default ``30``)
"""

import os

import httpx
import pytest

BASE_URL = os.environ.get("GATEWAY_HOST", "localhost")
PORT = os.environ.get("GATEWAY_PORT", "8001")
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "default-model")
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "30"))


def _gateway_reachable() -> bool:
    """Check whether the gateway server is reachable."""
    try:
        with httpx.Client() as client:
            client.get(f"http://{BASE_URL}:{PORT}/health", timeout=2)
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not VLLM_BASE_URL or not _gateway_reachable(),
    reason="VLLM_BASE_URL not set or gateway not reachable – skipping integration tests",
)


def _gateway_url(path: str) -> str:
    """Build a full gateway URL for *path*."""
    return f"http://{BASE_URL}:{PORT}{path}"


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

def test_health_returns_ok() -> None:
    """GET /health should return 200 with ``{"status": "ok"}``."""
    with httpx.Client() as client:
        response = client.get(_gateway_url("/health"), timeout=REQUEST_TIMEOUT)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# ------------------------------------------------------------------
# Chat (non-streaming)
# ------------------------------------------------------------------

def test_chat_completions_returns_valid_response() -> None:
    """POST /v1/chat/completions should return 200 with valid OpenAI JSON."""
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "user", "content": "Reply with exactly OK"}
        ],
        "stream": False,
        "max_tokens": 50,
    }

    with httpx.Client() as client:
        response = client.post(
            _gateway_url("/v1/chat/completions"),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

    assert response.status_code == 200
    data = response.json()

    # Valid OpenAI-compatible shape.
    assert "choices" in data
    assert len(data["choices"]) > 0
    choice = data["choices"][0]
    assert "message" in choice
    assert choice["message"]["role"] == "assistant"


# ------------------------------------------------------------------
# Streaming
# ------------------------------------------------------------------

def test_chat_completions_streaming() -> None:
    """POST /v1/chat/completions with stream=true should stream SSE chunks."""
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "user", "content": "Reply with exactly OK"}
        ],
        "stream": True,
        "max_tokens": 50,
    }

    chunks_received: list[str] = []

    with httpx.Client() as client:
        with client.stream(
            "POST",
            _gateway_url("/v1/chat/completions"),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")

            # Consume SSE lines incrementally.
            for line in response.iter_lines():
                if line:
                    chunks_received.append(line)

    assert len(chunks_received) > 0
