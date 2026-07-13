"""Chat completions endpoint.

Routes chat requests to the configured provider and handles
both streaming and non-streaming responses.
"""

from __future__ import annotations

import logging
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

    # Look up the first registered provider via the factory.
    registry = get_registry()
    if not registry:
        raise HTTPException(status_code=501, detail="Provider not configured")

    provider_name = next(iter(registry))
    try:
        provider = create_provider(provider_name)
    except Exception:
        raise HTTPException(
            status_code=501, detail="Provider not configured"
        )

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
        status = "ok"

        logger.info(
            "provider=%s model=%s duration=%.3fs status=%s request_id=%s",
            provider_name,
            model,
            elapsed,
            status,
            request_id,
        )

        # Streaming responses carry a generator + media_type.
        if isinstance(result, dict) and "generator" in result:
            return StreamingResponse(
                content=result["generator"](),
                media_type=result.get("media_type", "text/event-stream"),
            )

        return result

    except (
        ProviderAuthenticationError,
        ProviderConnectionError,
        ProviderResponseError,
    ) as exc:
        elapsed = time.perf_counter() - start_time
        logger.error(
            "provider=%s model=%s duration=%.3fs status=error request_id=%s error=%s",
            provider_name,
            model,
            elapsed,
            request_id,
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
