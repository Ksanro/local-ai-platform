"""FastAPI gateway application entry point.

Provides a ``create_app`` factory function and a module-level ``app``
instance for development servers and production WSGI servers.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.gateway.api.chat import router as chat_router
from apps.gateway.api.health import router as health_router
from apps.gateway.api.version import router as version_router
from apps.gateway.core.config import get_settings
from apps.gateway.core.logging import setup_logging
from apps.gateway.middleware import RequestMiddleware, TimingMiddleware
from packages.providers import _load_providers
from packages.providers.factory import create_provider
from packages.providers.registry import has_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.

    Runs once at startup: loads settings, configures logging, and
    creates the default provider instance. On shutdown, closes the
    provider's httpx client to release the connection pool.

    Args:
        app: The FastAPI application instance.
    """
    settings = get_settings()
    setup_logging(level=settings.log_level)

    # Register all available providers.
    _load_providers()

    # Create and cache the default provider instance.
    default = settings.default_provider
    if has_provider(default):
        app.state.provider = create_provider(default)

    yield

    # Clean up the provider's httpx client on shutdown.
    provider = getattr(app.state, "provider", None)
    if provider is not None:
        await provider.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Sets up CORS, request ID middleware, timing middleware, and
    mounts all API routers. Returns a fully configured ``FastAPI``
    instance ready for a server to serve.

    Returns:
        A configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Local AI Platform - Gateway Service",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RequestMiddleware)
    app.add_middleware(TimingMiddleware)

    app.include_router(health_router)
    app.include_router(version_router)
    app.include_router(chat_router)

    return app


app = create_app()


