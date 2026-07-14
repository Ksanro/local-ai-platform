"""Chat completions endpoint.

Routes chat requests through the pipeline (which delegates to the
configured provider) and handles both streaming and non-streaming
responses.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import StreamingResponse

from apps.gateway.core.config import get_settings
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.exceptions import PipelineError
from packages.pipeline.request import PipelineRequest

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatCompletionRequest(BaseModel):
    """Request body for chat completion endpoint.

    Mirrors the OpenAI Chat Completion API shape for compatibility.
    """

    messages: list[dict[str, Any]] = Field(
        ...,
        description="List of message objects with role and content.",
    )
    model: str = Field(
        default="default",
        description="Model identifier to use for completion.",
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream the response.",
    )
    temperature: float | None = Field(
        default=None,
        description="Sampling temperature (0-2).",
    )
    max_tokens: int | None = Field(
        default=None,
        description="Maximum number of tokens to generate.",
    )


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
) -> StreamingResponse | dict[str, Any]:
    """Chat completions endpoint.

    Forwards the request through the pipeline and returns
    either a JSON response or an SSE streaming response depending
    on the ``stream`` flag.

    Args:
        request: The incoming FastAPI request (for request ID).
        body: The parsed chat completion request body.

    Returns:
        A StreamingResponse for SSE or a dict for JSON responses.

    Raises:
        HTTPException: If the pipeline fails or no provider is configured.
    """
    request_id = request.headers.get("X-Request-ID", "unknown")
    provider_name: str | None = None
    model: str = body.model
    start_time: float = time.perf_counter()

    # Look up the configured provider via the factory.
    settings = get_settings()
    provider_name = settings.default_provider

    # Build the pipeline request.
    kwargs: dict[str, Any] = {
        "messages": body.messages,
        "model": body.model,
        "stream": body.stream,
    }
    if body.temperature is not None:
        kwargs["temperature"] = body.temperature
    if body.max_tokens is not None:
        kwargs["max_tokens"] = body.max_tokens

    pipeline_request = PipelineRequest(
        provider_name=provider_name,
        model=body.model,
        messages=body.messages,
        stream=body.stream,
        kwargs=kwargs,
        metadata={"request_id": request_id},
    )

    try:
        # Execute through the pipeline.
        response = await get_pipeline().execute(pipeline_request)
        elapsed = time.perf_counter() - start_time

        if not response.success:
            raise HTTPException(status_code=502, detail=response.error)

        result = response.data

        # Non-streaming: log duration immediately.
        if not body.stream:
            logger.info(
                "provider=%s model=%s duration=%.3fs status=ok request_id=%s",
                provider_name,
                model,
                elapsed,
                request_id,
            )
            return result

        # Streaming: log duration and TTFT on exhaustion via a wrapper generator.
        generator_fn = result.get("generator")
        media_type = result.get("media_type", "text/event-stream")
        if generator_fn is None:
            # Unexpected shape -- fall through to JSON.
            logger.warning(
                "provider=%s model=%s request_id=%s "
                "stream=true but no generator in result",
                provider_name,
                model,
                request_id,
            )
            return result

        return StreamingResponse(
            content=_wrap_stream_duration(
                generator_fn(), provider_name, model, start_time, request_id
            ),
            media_type=media_type,
        )

    except PipelineError as exc:
        elapsed = time.perf_counter() - start_time
        logger.error(
            "provider=%s model=%s duration=%.3fs status=error request_id=%s "
            "error=%s",
            provider_name,
            model,
            elapsed,
            request_id,
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _wrap_stream_duration(
    generator: Any,
    provider_name: str,
    model: str,
    start_time: float,
    request_id: str,
) -> Any:
    """Wrap a streaming generator to log total duration and TTFT on exhaustion.

    Yields every event from the underlying generator so the caller
    sees the same stream, but logs the full wall-clock time and
    time-to-first-token once iteration is complete.

    Args:
        generator: The async generator returned by the provider.
        provider_name: Name of the provider for logging.
        model: Model identifier for logging.
        start_time: perf_counter timestamp before the provider call.
        request_id: Request ID for logging.

    Returns:
        An async generator that yields the same events and logs
        duration after the last event.
    """
    async def _wrapped() -> Any:
        status = "stream_ok"
        ttft: float | None = None
        try:
            first = True
            async for event in generator:
                if first:
                    ttft = time.perf_counter() - start_time
                    first = False
                yield event
        except GeneratorExit:
            status = "stream_client_disconnect"
            raise
        except Exception:
            status = "stream_error"
            raise
        finally:
            elapsed = time.perf_counter() - start_time
            ttft_str = f" ttft={ttft:.3f}" if ttft is not None else ""
            logger.info(
                "provider=%s model=%s duration=%.3f%s status=%s request_id=%s",
                provider_name,
                model,
                elapsed,
                ttft_str,
                status,
                request_id,
            )

    return _wrapped()


# Module-level pipeline instance, initialized lazily.
_pipeline: PipelineEngine | None = None


def get_pipeline() -> PipelineEngine:
    """Get the pipeline engine, initializing it if needed.

    Returns:
        The global pipeline engine instance.
    """
    global _pipeline
    if _pipeline is None:
        from packages.pipeline.stages import ProviderStage

        _pipeline = PipelineEngine()
        _pipeline.register(ProviderStage())
    return _pipeline
