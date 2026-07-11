"""Chat completions endpoint."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions() -> None:
    """Chat completions endpoint.

    Returns 501 when no provider is configured.
    """
    raise HTTPException(status_code=501, detail="Provider not configured")


