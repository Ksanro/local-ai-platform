"""Health check endpoint.

Returns a simple status response used by load balancers and
orchestration tools to verify the service is running.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns ``{"status": "ok"}`` when the gateway is running.
    This endpoint does not check downstream provider health.

    Returns:
        A dict with a ``status`` key set to ``"ok"``.
    """
    return {"status": "ok"}


