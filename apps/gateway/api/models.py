"""Models listing endpoint.

Provides ``GET /v1/models`` — standard OpenAI-compatible listing.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/models")
def list_models() -> dict:  # type: ignore[return-value]
    """List available models.

    Returns an OpenAI-compatible list of configured models.

    Returns:
        A dict with ``object`` set to ``"list"`` and ``data`` containing
        one entry per configured model.
    """
    from apps.gateway.main import app

    model_router = getattr(app.state, "model_router", None)
    if model_router is None:
        # Fallback: return empty list when no router is configured.
        return {"object": "list", "data": []}

    model_names = model_router.available_models()
    data = [
        {
            "id": name,
            "object": "model",
            "owned_by": "local-ai-platform",
        }
        for name in model_names
    ]
    return {"object": "list", "data": data}
