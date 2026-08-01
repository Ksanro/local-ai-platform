"""Health check endpoint.

Returns a simple status response used by load balancers and
orchestration tools to verify the service is running.
"""

from fastapi import APIRouter

from apps.gateway.core.config import get_settings

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint.

    Returns service status and whether repository context is enabled.

    Returns:
        A dict with ``status`` and repository-context enablement.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "repository_context_enabled": settings.repository_context_enabled,
    }


