"""Version endpoint.

Returns application metadata including name and version string.
Useful for debugging and API version compatibility checks.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/version")
async def version() -> dict[str, str]:
    """Return application version information.

    Returns:
        A dict with ``name`` and ``version`` keys describing the
        application and its current version.
    """
    return {
        "name": "Local AI Platform",
        "version": "0.1.0",
    }


