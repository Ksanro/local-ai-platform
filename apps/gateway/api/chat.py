"""Chat completions endpoint.

Routes chat requests to the configured provider and handles
both streaming and non-streaming responses.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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


@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> Any:
    """Chat completions endpoint.

    Forwards the request to the configured provider and returns
    either a JSON response or an SSE streaming response depending
    on the ``stream`` flag.
    """
    raise HTTPException(status_code=501, detail="Provider not configured")


