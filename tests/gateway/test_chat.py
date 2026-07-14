"""Tests for the chat completions endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.gateway.api.chat import router as chat_router
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.exceptions import PipelineError
from packages.pipeline.response import PipelineResponse, PipelineStageResult
from packages.providers.exceptions import (
    ProviderConnectionError,
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
        app.state.pipeline = pipeline  # type: ignore[attr-defined]
    else:
        # Wire a stub pipeline so the endpoint has something to call.
        class _StubStage:
            @property
            def name(self) -> str:
                return "stub"

            async def before(self, context):  # type: ignore[no-untyped-def]
                return None

            async def execute(self, context):  # type: ignore[no-untyped-def]
                return PipelineStageResult(
                    stage_name="stub",
                    success=True,
                    data={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
                )

            async def after(self, context, result):  # type: ignore[no-untyped-def]
                return None

        engine = PipelineEngine()
        engine.register(_StubStage())
        app.state.pipeline = engine  # type: ignore[attr-defined]

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
            "FakeSettings", (), {"default_provider": "nonexistent"}
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
        app.state.pipeline = mock_engine  # type: ignore[attr-defined]
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
    app.state.pipeline = mock_engine  # type: ignore[attr-defined]
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
    app.state.pipeline = mock_engine  # type: ignore[attr-defined]
    client = TestClient(app)
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 501


def test_streaming_response_returns_multiple_chunks() -> None:
    """Verify streaming endpoint returns at least 2 SSE chunks from the
    real vLLM server."""
    from packages.providers.factory import create_provider
    from packages.pipeline.stages import ProviderStage

    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "qwen36",
        "stream": True,
        "max_tokens": 50,
    }
    # Build a real pipeline that connects to the actual vLLM server.
    provider = create_provider("vllm")
    engine = PipelineEngine()
    engine.register(ProviderStage(provider))
    app = _make_app(pipeline=engine)
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
    from packages.providers.factory import create_provider
    from packages.pipeline.stages import ProviderStage

    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "qwen36",
        "stream": True,
        "max_tokens": 20,
    }
    provider = create_provider("vllm")
    engine = PipelineEngine()
    engine.register(ProviderStage(provider))
    app = _make_app(pipeline=engine)
    client = TestClient(app)
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "data: [DONE]" in response.text


def test_chat_completions_non_streaming() -> None:
    """Verify non-streaming chat returns valid OpenAI JSON shape."""
    from packages.providers.factory import create_provider
    from packages.pipeline.stages import ProviderStage

    payload = {
        "messages": [{"role": "user", "content": "Reply with exactly OK"}],
        "model": "qwen36",
        "stream": False,
        "max_tokens": 10,
    }
    provider = create_provider("vllm")
    engine = PipelineEngine()
    engine.register(ProviderStage(provider))
    app = _make_app(pipeline=engine)
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
            "FakeSettings", (), {"default_provider": "vllm"}
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
        app.state.pipeline = mock_engine  # type: ignore[attr-defined]
        client = TestClient(app)
        response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 503
