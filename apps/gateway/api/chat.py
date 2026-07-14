"""Chat completions endpoint.

Routes chat requests through the pipeline (which delegates to the
configured provider) and handles both streaming and non-streaming
responses.
"""

from __future__ import annotations

import logging
import time
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from apps.gateway.core.config import get_settings
from packages.pipeline.exceptions import PipelineError
from packages.pipeline.request import PipelineRequest
from packages.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderResponseError,
    UnknownProviderError,
)

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


def _status_for_exception(exc: Exception | None) -> int:
    """Map a pipeline exception to an HTTP status code.

    Args:
        exc: The exception to map, or ``None`` for the default.

    Returns:
        An HTTP status code integer.
    """
    if exc is None:
        return 502
    if isinstance(exc, UnknownProviderError):
        return 501
    if isinstance(exc, PipelineError):
        return 501
    if isinstance(exc, ProviderAuthenticationError):
        return 502
    if isinstance(exc, ProviderConnectionError):
        return 503
    if isinstance(exc, ProviderResponseError):
        return 502
    return 502


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
    model: str = body.model
    start_time: float = time.perf_counter()

    # Look up the configured provider via the factory.
    settings = get_settings()
    provider_name = settings.default_provider

    # Build the pipeline request.
    # Only optional passthrough params go in kwargs; messages/model/stream
    # are the sole source of truth via the dedicated PipelineRequest fields.
    kwargs: dict[str, Any] = {}
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
        engine = request.app.state.pipeline
        response = await engine.execute(pipeline_request)
        elapsed = time.perf_counter() - start_time

        if not response.success:
            status_code = _status_for_exception(response.exception)
            raise HTTPException(status_code=status_code, detail=response.error)

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
            return cast(dict[str, Any], result)

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
            return cast(dict[str, Any], result)

        return StreamingResponse(
            content=_wrap_stream_duration(
                generator_fn(), provider_name, model, start_time, request_id
            ),
            media_type=media_type,
        )

    except HTTPException:
        raise
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
        raise HTTPException(status_code=501, detail=str(exc)) from exc


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
