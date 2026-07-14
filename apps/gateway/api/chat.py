"""Chat completions endpoint.

Routes chat requests to the configured provider and handles
both streaming and non-streaming responses.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import StreamingResponse

from packages.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderResponseError,
)
from packages.providers.factory import create_provider
from packages.providers.registry import get_registry

logger = logging.getLogger(__name__)

router = APIRouter()

# The provider name to use for chat requests. Defaults to "vllm".
# Change this env var to route to a different registered provider.
_DEFAULT_PROVIDER = os.environ.get("DEFAULT_PROVIDER", "vllm")


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

    Forwards the request to the configured provider and returns
    either a JSON response or an SSE streaming response depending
    on the ``stream`` flag.

    Args:
        request: The incoming FastAPI request (for request ID).
        body: The parsed chat completion request body.

    Returns:
        A StreamingResponse for SSE or a dict for JSON responses.

    Raises:
        HTTPException: If no provider is configured or the provider
            call fails.
    """
    request_id = request.headers.get("X-Request-ID", "unknown")
    provider_name: str | None = None
    model: str = body.model
    start_time: float = time.perf_counter()

    # Look up the configured provider via the factory.
    registry = get_registry()
    if not registry:
        raise HTTPException(status_code=501, detail="Provider not configured")

    provider_name = _DEFAULT_PROVIDER
    try:
        provider = create_provider(provider_name)
    except Exception:
        elapsed = time.perf_counter() - start_time
        logger.error(
            "provider=%s model=%s duration=%.3fs status=error request_id=%s "
            "error=provider creation failed",
            provider_name,
            model,
            elapsed,
            request_id,
        )
        raise HTTPException(
            status_code=501, detail="Provider not configured"
        ) from None

    # Build kwargs for the provider, passing through all fields.
    kwargs: dict[str, Any] = {
        "messages": body.messages,
        "model": body.model,
        "stream": body.stream,
    }
    if body.temperature is not None:
        kwargs["temperature"] = body.temperature
    if body.max_tokens is not None:
        kwargs["max_tokens"] = body.max_tokens

    try:
        result = await provider.chat(**kwargs)
        elapsed = time.perf_counter() - start_time

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

        # Streaming: log duration on exhaustion via a wrapper generator.
        generator = result.get("generator")
        media_type = result.get("media_type", "text/event-stream")
        if generator is None:
            # Unexpected shape – fall through to JSON.
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
                generator, provider_name, model, elapsed, request_id
            ),
            media_type=media_type,
        )

    except (
        ProviderAuthenticationError,
        ProviderConnectionError,
        ProviderResponseError,
    ) as exc:
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
    pre_time: float,
    request_id: str,
) -> Any:
    """Wrap a streaming generator to log total duration on exhaustion.

    Yields every event from the underlying generator so the caller
    sees the same stream, but logs the full wall-clock time once
    iteration is complete.

    Args:
        generator: The async generator returned by the provider.
        provider_name: Name of the provider for logging.
        model: Model identifier for logging.
        pre_time: Time elapsed before the generator was created.
        request_id: Request ID for logging.

    Returns:
        An async generator that yields the same events and logs
        duration after the last event.
    """
    async def _wrapped() -> Any:
        start = time.perf_counter()
        try:
            async for event in generator:
                yield event
        finally:
            elapsed = time.perf_counter() - start
            logger.info(
                "provider=%s model=%s duration=%.3fs status=stream_ok request_id=%s",
                provider_name,
                model,
                elapsed,
                request_id,
            )

    return _wrapped()
