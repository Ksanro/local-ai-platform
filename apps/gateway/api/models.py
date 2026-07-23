"""Models listing endpoint.

Provides ``GET /v1/models`` — standard OpenAI-compatible listing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/models")
def list_models(request: Request) -> dict[str, Any]:
    """List available models.

    Returns an OpenAI-compatible list of configured models.

    Args:
        request: The incoming request, used to reach ``app.state``.

    Returns:
        A dict with ``object`` set to ``"list"`` and ``data`` containing
        one entry per configured model.
    """
    model_router = getattr(request.app.state, "model_router", None)
    if model_router is None:
        return {"object": "list", "data": []}

    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "owned_by": "local-ai-platform"}
            for name in model_router.available_models()
        ],
    }
