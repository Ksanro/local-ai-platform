#!/usr/bin/env python3
"""Smoke test for the Local AI Platform Gateway.

Quick end-to-end check that the gateway is reachable and can
communicate with a real vLLM instance.

Environment variables
---------------------
GATEWAY_HOST   - Gateway host (default ``localhost``)
GATEWAY_PORT   - Gateway port  (default ``8000``)
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
PORT = os.environ.get("GATEWAY_PORT", "8000")
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
# 1. Gateway reachable
# ------------------------------------------------------------------

def _check_gateway_reachable() -> None:
    """Verify the gateway process responds to basic requests."""
    import httpx

    with httpx.Client() as client:
        resp = client.get(f"{GATEWAY_URL}/health", timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()


# ------------------------------------------------------------------
# 2. Health endpoint
# ------------------------------------------------------------------

def _check_health() -> None:
    """GET /health should return 200 with status ok."""
    import httpx

    with httpx.Client() as client:
        resp = client.get(f"{GATEWAY_URL}/health", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        request_id = resp.headers.get("X-Request-ID", "unknown")
        duration = float(resp.headers.get("X-Process-Time", 0))
        _log("vllm", DEFAULT_MODEL, duration, "ok", request_id)


# ------------------------------------------------------------------
# 3. Chat endpoint (non-streaming)
# ------------------------------------------------------------------

def _check_chat() -> None:
    """POST /v1/chat/completions should return 200 with valid JSON."""
    import httpx

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly OK"}],
        "stream": False,
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
# 4. Streaming endpoint
# ------------------------------------------------------------------

def _check_streaming() -> None:
    """POST /v1/chat/completions with stream=true should return SSE."""
    import httpx

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly OK"}],
        "stream": True,
    }

    with httpx.Client() as client:
        resp = client.post(
            f"{GATEWAY_URL}/v1/chat/completions",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream"
        chunks = list(resp.iter_lines())
        assert len(chunks) > 0
        request_id = resp.headers.get("X-Request-ID", "unknown")
        duration = float(resp.headers.get("X-Process-Time", 0))
        _log("vllm", DEFAULT_MODEL, duration, "ok", request_id)


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
    check("Provider healthy", _check_health)

    if VLLM_BASE_URL:
        check("Chat successful", _check_chat)
        check("Streaming successful", _check_streaming)
    else:
        print("    Chat skipped (VLLM_BASE_URL not set)")
        print("    Streaming skipped (VLLM_BASE_URL not set)")

    print()
    if FAILED:
        print("RESULT: FAILED")
        sys.exit(1)
    else:
        print("RESULT: PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
