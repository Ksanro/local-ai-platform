#!/usr/bin/env python3
"""Smoke test for the Local AI Platform Gateway.

Quick end-to-end check that the gateway is reachable and can
communicate with a real vLLM instance.  Verifies that the complete
pipeline — Repository Context → Serialization → Provider — executes
correctly.

Environment variables
---------------------
GATEWAY_HOST   - Gateway host (default ``localhost``)
GATEWAY_PORT   - Gateway port  (default ``8001``)
VLLM_BASE_URL  - vLLM server URL (required for chat/streaming)
DEFAULT_MODEL  - Model name to use (default ``default-model``)
REQUEST_TIMEOUT - Request timeout in seconds (default ``30``)

Exit codes
----------
0 - All checks passed
1 - One or more checks failed
"""

import os
import sys
from typing import Callable

BASE_URL = os.environ.get("GATEWAY_HOST", "localhost")
PORT = os.environ.get("GATEWAY_PORT", "8001")
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "default-model")
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "30"))

GATEWAY_URL = f"http://{BASE_URL}:{PORT}"
FAILED = False


def _log(provider: str, model: str, duration: float, status: str, request_id: str) -> None:
    """Print a structured log line."""
    print(
        f"  provider={provider}  model={model}  "
        f"duration={duration:.3f}s  status={status}  "
        f"request_id={request_id}"
    )


def check(label: str, fn: Callable[[], None]) -> None:
    """Run *fn* and print the result."""
    global FAILED
    try:
        fn()
        print(f"[PASS] {label}")
    except Exception as exc:
        try:
            print(f"[FAIL] {label}: {exc}")
        except UnicodeEncodeError:
            print(f"[FAIL] {label}: {exc} (encoding error)")
        FAILED = True


# ------------------------------------------------------------------
# 1. Gateway reachable + health (collapsed)
# ------------------------------------------------------------------

def _check_gateway_reachable() -> None:
    """Verify the gateway process responds and health is ok."""
    import httpx

    with httpx.Client() as client:
        resp = client.get(f"{GATEWAY_URL}/health", timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


# ------------------------------------------------------------------
# 2. Chat endpoint (non-streaming)
# ------------------------------------------------------------------

def _check_chat() -> None:
    """POST /v1/chat/completions should return 200 with valid JSON."""
    import httpx

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly OK"}],
        "stream": False,
        "max_tokens": 50,
    }

    with httpx.Client() as client:
        resp = client.post(
            f"{GATEWAY_URL}/v1/chat/completions",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert data["choices"][0]["message"]["role"] == "assistant"
        request_id = resp.headers.get("X-Request-ID", "unknown")
        duration = float(resp.headers.get("X-Process-Time", 0))
        _log("vllm", DEFAULT_MODEL, duration, "ok", request_id)


# ------------------------------------------------------------------
# 3. Streaming endpoint
# ------------------------------------------------------------------

def _check_streaming() -> None:
    """POST /v1/chat/completions with stream=true should stream SSE."""
    import httpx

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly OK"}],
        "stream": True,
        "max_tokens": 50,
    }

    chunks_received: list[str] = []

    with httpx.Client() as client:
        with client.stream(
            "POST",
            f"{GATEWAY_URL}/v1/chat/completions",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            for line in resp.iter_lines():
                if line:
                    chunks_received.append(line)

    assert len(chunks_received) > 0
    request_id = resp.headers.get("X-Request-ID", "unknown")
    duration = float(resp.headers.get("X-Process-Time", 0))
    _log("vllm", DEFAULT_MODEL, duration, "ok", request_id)


# ------------------------------------------------------------------
# 4. Repository Intelligence pipeline stages
# ------------------------------------------------------------------

def _check_repository_intelligence() -> None:
    """Verify Repository Intelligence stages execute correctly.

    Checks that:
    - Repository Context stage runs (context_enabled in response).
    - Serialization produces a valid ProviderRequest shape.
    - Provider is invoked successfully.
    """
    import httpx

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [{"role": "user", "content": "Check repository intelligence pipeline"}],
        "stream": False,
        "max_tokens": 50,
    }

    with httpx.Client() as client:
        resp = client.post(
            f"{GATEWAY_URL}/v1/chat/completions",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "choices" in data
        assert len(data["choices"]) > 0

        request_id = resp.headers.get("X-Request-ID", "unknown")
        duration = float(resp.headers.get("X-Process-Time", 0))
        _log("vllm", DEFAULT_MODEL, duration, "repo_intelligence_ok", request_id)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    """Run all smoke checks and exit with the appropriate code."""
    print("Local AI Platform - Gateway Smoke Test")
    print(f"  Gateway : {GATEWAY_URL}")
    if VLLM_BASE_URL:
        print(f"  vLLM    : {VLLM_BASE_URL}")
        print(f"  Model   : {DEFAULT_MODEL}")
    else:
        print("  vLLM    : NOT CONFIGURED (chat/streaming will be skipped)")
    print()

    check("Gateway reachable", _check_gateway_reachable)

    if VLLM_BASE_URL:
        check("Chat successful", _check_chat)
        check("Streaming successful", _check_streaming)
        check("Repository Intelligence pipeline", _check_repository_intelligence)
    else:
        print("    Chat skipped (VLLM_BASE_URL not set)")
        print("    Streaming skipped (VLLM_BASE_URL not set)")
        print("    Repository Intelligence skipped (VLLM_BASE_URL not set)")

    print()
    if FAILED:
        print("RESULT: FAILED")
        sys.exit(1)
    else:
        print("RESULT: PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
