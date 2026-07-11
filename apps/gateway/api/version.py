"""Version endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/version")
async def version() -> dict[str, str]:
    """Return application version information."""
    return {
        "name": "Local AI Platform",
        "version": "0.1.0",
    }


