"""Tests for the chat completions endpoint."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.gateway.api.chat import router as chat_router
from apps.gateway.middleware import RequestMiddleware
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.exceptions import PipelineError
from packages.pipeline.response import PipelineResponse
from packages.pipeline.result import PipelineStageResult
from packages.providers.exceptions import (
    ProviderConnectionError,
    ProviderResponseError,
    UnknownProviderError,
)


def _make_app(pipeline: PipelineEngine | None = None) -> FastAPI:
    """Build a minimal FastAPI app with the chat router.

    The TestClient does not run the application lifespan, so the
    provider and pipeline must be wired into app.state manually.

    Args:
        pipeline: Optional pipeline engine. If None, a stub pipeline
            is created for mocked tests.

    Returns:
        A configured FastAPI application instance.
    """
    from apps.gateway.api.chat import _wrap_stream_duration  # noqa: F401

    app = FastAPI()
    app.include_router(chat_router)

    if pipeline is not None:
        app.state.pipeline = pipeline
    else:
        # Wire a stub pipeline so the endpoint has something to call.
        async def _stub_generator() -> AsyncGenerator[str, None]:
            """Yield SSE data lines for streaming tests."""
            yield 'data: {"id":"stub-1","choices":[{"delta":{"role":"assistant"}}]}\n'
            yield 'data: {"id":"stub-1","choices":[{"delta":{"content":"ok"}}]}\n'
            yield "data: [DONE]\n"

        class _StubStage:
            @property
            def name(self) -> str:
                return "stub"

            async def before(self, context: Any) -> Any:
                return None

            async def execute(self, context: Any) -> Any:
                stream = context.request.get("stream", False)
                if stream:
                    data: dict[str, Any] = {
                        "generator": _stub_generator,
                        "media_type": "text/event-stream",
                    }
                else:
                    data = {
                        "choices": [
                            {"message": {"role": "assistant", "content": "ok"}}
                        ]
                    }
                return PipelineStageResult(
                    stage_name="stub",
                    success=True,
                    data=data,
                )

            async def after(self, context: Any, result: Any) -> Any:
                return None

        engine = PipelineEngine()
        engine.register(_StubStage())  # type: ignore[arg-type]
        app.state.pipeline = engine

    return app


def test_chat_completions_provider_not_found() -> None:
    """Verify chat completions returns 501 when the pipeline reports
    an unregistered provider."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    with patch(
        "apps.gateway.api.chat.get_settings",
        return_value=type(
            "FakeSettings",
            (),
            {"default_provider": "nonexistent", "repository_context_enabled": True},
        )(),
    ):
        mock_engine = AsyncMock()
        resp = PipelineResponse(
            success=False,
            error="Provider 'nonexistent' is not registered",
        )
        # Manually set stage_results so the exception property works.
        resp.stage_results = {
            "provider": PipelineStageResult(
                stage_name="provider",
                success=False,
                error="Provider 'nonexistent' is not registered",
                exception=UnknownProviderError(
                    "Provider 'nonexistent' is not registered"
                ),
            )
        }
        mock_engine.execute = AsyncMock(return_value=resp)
        app = _make_app()
        app.state.pipeline = mock_engine
        client = TestClient(app)
        response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 501
    data = response.json()
    assert "not registered" in data["detail"].lower() or "not found" in data["detail"].lower()


def test_chat_completions_no_providers_registered() -> None:
    """Verify 501 when the pipeline has no stages (no providers)."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    mock_engine = AsyncMock()
    mock_engine.execute = AsyncMock(
        side_effect=PipelineError("No stages registered")
    )
    app = _make_app()
    app.state.pipeline = mock_engine
    client = TestClient(app)
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 501


def test_chat_completions_streaming_error_on_provider_failure() -> None:
    """Verify 501 when the pipeline raises during streaming."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
        "stream": True,
    }
    mock_engine = AsyncMock()
    mock_engine.execute = AsyncMock(
        side_effect=PipelineError("vLLM unreachable")
    )
    app = _make_app()
    app.state.pipeline = mock_engine
    client = TestClient(app)
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 501


def test_streaming_response_returns_multiple_chunks() -> None:
    """Verify streaming endpoint returns at least 2 SSE chunks from the
    stub pipeline."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "qwen36",
        "stream": True,
        "max_tokens": 50,
    }
    app = _make_app()
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
    client = TestClient(app)
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
    assert len(data["choices"]) > 0
    assert data["choices"][0]["message"]["role"] == "assistant"


def test_chat_completions_provider_connection_error_returns_503() -> None:
    """Verify ProviderConnectionError surfaces as HTTP 503."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    with patch(
        "apps.gateway.api.chat.get_settings",
        return_value=type(
            "FakeSettings",
            (),
            {"default_provider": "vllm", "repository_context_enabled": True},
        )(),
    ):
        mock_engine = AsyncMock()
        resp = PipelineResponse(
            success=False,
            error="Connection refused",
        )
        resp.stage_results = {
            "provider": PipelineStageResult(
                stage_name="provider",
                success=False,
                error="Connection refused",
                exception=ProviderConnectionError("Connection refused"),
            )
        }
        mock_engine.execute = AsyncMock(return_value=resp)
        app = _make_app()
        app.state.pipeline = mock_engine
        client = TestClient(app)
        response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Bug 1 — upstream HTTP status is discarded
# ---------------------------------------------------------------------------


def _make_engine_for_exception(exc: Exception) -> AsyncMock:
    """Return a mock pipeline engine that returns a failed response with
    the given exception set on the provider stage result.

    Args:
        exc: The exception to attach to the stage result.

    Returns:
        An AsyncMock configured as a PipelineEngine with a failing response.
    """
    mock_engine = AsyncMock()
    resp = PipelineResponse(success=False, error=str(exc))
    resp.stage_results = {
        "provider": PipelineStageResult(
            stage_name="provider",
            success=False,
            error=str(exc),
            exception=exc,
        )
    }
    mock_engine.execute = AsyncMock(return_value=resp)
    return mock_engine


def test_chat_completions_404_passthrough() -> None:
    """Verify upstream 404 passes through as HTTP 404."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    with patch(
        "apps.gateway.api.chat.get_settings",
        return_value=type(
            "FakeSettings",
            (),
            {"default_provider": "vllm", "repository_context_enabled": True},
        )(),
    ):
        mock_engine = _make_engine_for_exception(
            ProviderResponseError("model not found", status_code=404)
        )
        app = _make_app()
        app.state.pipeline = mock_engine
        client = TestClient(app)
        response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 404


def test_chat_completions_400_passthrough() -> None:
    """Verify upstream 400 passes through as HTTP 400."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    with patch(
        "apps.gateway.api.chat.get_settings",
        return_value=type(
            "FakeSettings",
            (),
            {"default_provider": "vllm", "repository_context_enabled": True},
        )(),
    ):
        mock_engine = _make_engine_for_exception(
            ProviderResponseError("bad request", status_code=400)
        )
        app = _make_app()
        app.state.pipeline = mock_engine
        client = TestClient(app)
        response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 400


def test_chat_completions_422_passthrough() -> None:
    """Verify upstream 422 passes through as HTTP 422."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    with patch(
        "apps.gateway.api.chat.get_settings",
        return_value=type(
            "FakeSettings",
            (),
            {"default_provider": "vllm", "repository_context_enabled": True},
        )(),
    ):
        mock_engine = _make_engine_for_exception(
            ProviderResponseError("validation error", status_code=422)
        )
        app = _make_app()
        app.state.pipeline = mock_engine
        client = TestClient(app)
        response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 422


def test_chat_completions_500_becomes_502() -> None:
    """Verify upstream 500 maps to HTTP 502."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    with patch(
        "apps.gateway.api.chat.get_settings",
        return_value=type(
            "FakeSettings",
            (),
            {"default_provider": "vllm", "repository_context_enabled": True},
        )(),
    ):
        mock_engine = _make_engine_for_exception(
            ProviderResponseError("internal error", status_code=500)
        )
        app = _make_app()
        app.state.pipeline = mock_engine
        client = TestClient(app)
        response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 502


def test_chat_completions_503_becomes_502() -> None:
    """Verify upstream 503 maps to HTTP 502 (bad gateway)."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    with patch(
        "apps.gateway.api.chat.get_settings",
        return_value=type(
            "FakeSettings",
            (),
            {"default_provider": "vllm", "repository_context_enabled": True},
        )(),
    ):
        mock_engine = _make_engine_for_exception(
            ProviderResponseError("service unavailable", status_code=503)
        )
        app = _make_app()
        app.state.pipeline = mock_engine
        client = TestClient(app)
        response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 502


# ---------------------------------------------------------------------------
# Bug 2 — request_id is "unknown" when no header is supplied
# ---------------------------------------------------------------------------


def test_request_id_generated_when_no_header() -> None:
    """Verify a valid UUID request_id is generated when no X-Request-ID
    header is supplied by the client."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    with patch(
        "apps.gateway.api.chat.get_settings",
        return_value=type(
            "FakeSettings",
            (),
            {"default_provider": "vllm", "repository_context_enabled": True},
        )(),
    ):
        mock_engine = _make_engine_for_exception(
            ProviderConnectionError("connection failed")
        )
        app = _make_app()
        app.state.pipeline = mock_engine
        app.add_middleware(RequestMiddleware)
        client = TestClient(app)
        response = client.post("/v1/chat/completions", json=payload)
    # The X-Request-ID response header should be a valid UUID
    req_id = response.headers.get("X-Request-ID")
    assert req_id is not None
    assert req_id != "unknown"
    uuid.UUID(req_id)  # Raises if not a valid UUID


def test_request_id_passed_when_header_supplied() -> None:
    """Verify the X-Request-ID header value is used when supplied by the
    client."""
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "test-model",
    }
    with patch(
        "apps.gateway.api.chat.get_settings",
        return_value=type(
            "FakeSettings",
            (),
            {"default_provider": "vllm", "repository_context_enabled": True},
        )(),
    ):
        mock_engine = _make_engine_for_exception(
            ProviderConnectionError("connection failed")
        )
        app = _make_app()
        app.state.pipeline = mock_engine
        app.add_middleware(RequestMiddleware)
        client = TestClient(app)
        response = client.post(
            "/v1/chat/completions",
            json=payload,
            headers={"X-Request-ID": "my-uuid-1234"},
        )
    # The response X-Request-ID should match the client-supplied value
    assert response.headers.get("X-Request-ID") == "my-uuid-1234"


def test_concurrent_requests_get_different_request_ids() -> None:
    """Verify two concurrent requests without the header receive different
    IDs."""
    from concurrent.futures import ThreadPoolExecutor

    def _make_request(client: TestClient) -> str | None:
        """Make a request and return the X-Request-ID from the response."""
        payload = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "test-model",
        }
        response = client.post("/v1/chat/completions", json=payload)
        return response.headers.get("X-Request-ID")

    with patch(
        "apps.gateway.api.chat.get_settings",
        return_value=type(
            "FakeSettings",
            (),
            {"default_provider": "vllm", "repository_context_enabled": True},
        )(),
    ):
        mock_engine = _make_engine_for_exception(
            ProviderConnectionError("connection failed")
        )

        def _client() -> TestClient:
            app = _make_app()
            app.state.pipeline = mock_engine
            app.add_middleware(RequestMiddleware)
            return TestClient(app)

        c1 = _client()
        c2 = _client()

        # Run requests concurrently via thread pool
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_make_request, c1)
            f2 = pool.submit(_make_request, c2)
            id1, id2 = f1.result(), f2.result()

        assert id1 is not None and id2 is not None
        assert id1 != id2, "Concurrent requests must get different request IDs"
        uuid.UUID(id1)
        uuid.UUID(id2)
