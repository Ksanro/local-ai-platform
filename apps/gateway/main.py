"""FastAPI gateway application entry point.

Provides a ``create_app`` factory function and a module-level ``app``
instance for development servers and production WSGI servers.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.gateway.api.chat import router as chat_router
from apps.gateway.api.health import router as health_router
from apps.gateway.api.version import router as version_router
from apps.gateway.core.config import get_settings
from apps.gateway.core.logging import setup_logging
from apps.gateway.middleware import RequestMiddleware, TimingMiddleware
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.stages import PlanningStage, ProviderStage
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.providers import _load_providers
from packages.providers.factory import create_provider
from packages.providers.registry import has_provider
from packages.repository import build_index

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.

    Runs once at startup: loads settings, configures logging, creates
    a single provider instance, builds the RepositoryIndex, and builds
    the pipeline engine. On shutdown, closes the provider's httpx client
    to release the connection pool.

    Args:
        app: The FastAPI application instance.
    """
    settings = get_settings()
    setup_logging(level=settings.log_level)

    # Register all available providers.
    _load_providers()

    # Build the RepositoryIndex during startup.
    repo_path = Path(settings.repository_path)
    index: object | None = None
    indexed_files = 0
    indexed_modules = 0
    indexed_symbols = 0
    indexed_relationships = 0
    indexing_duration_ms = 0.0

    if repo_path.is_dir():
        start_time = time.perf_counter()
        try:
            index = build_index(repo_path)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Extract metrics from the built index.
            if index is not None:
                from packages.repository.index.models import (
                    RepositoryIndex as _Index,
                )

                if isinstance(index, _Index):
                    indexed_modules = index.statistics().module_count
                    indexed_symbols = index.statistics().symbol_count
                    indexed_relationships = len(index.relationships())

                    # Count files by iterating modules.
                    indexed_files = len(index.modules)

                    indexing_duration_ms = elapsed_ms

                    logger.info(
                        "repository_index path=%s files=%d modules=%d "
                        "symbols=%d relationships=%d duration_ms=%.1f",
                        repo_path,
                        indexed_files,
                        indexed_modules,
                        indexed_symbols,
                        indexed_relationships,
                        indexing_duration_ms,
                    )
                else:
                    logger.warning(
                        "build_index returned unexpected type: %s", type(index).__name__
                    )
                    index = None
            else:
                logger.warning("repository_index path=%s returned None", repo_path)
        except Exception:
            logger.exception(
                "repository_index path=%s failed to build", repo_path
            )
            index = None

    # Create a single provider instance, build the pipeline, and wire
    # both onto app.state so every request reuses the same instance.
    default = settings.default_provider
    if has_provider(default):
        provider = create_provider(default)
        app.state.provider = provider

        # Cast index to the expected type for RepositoryContextStage.
        from packages.repository.index.models import RepositoryIndex

        typed_index: RepositoryIndex | None = (
            index if isinstance(index, RepositoryIndex) else None
        )

        engine = PipelineEngine()
        # Planning stage runs before repository context to produce
        # context_plan metadata that RepositoryContextStage consumes.
        engine.register(PlanningStage())
        # Repository context stage runs before provider execution.
        # Pass the real index; the stage handles None gracefully.
        engine.register(RepositoryContextStage(index=typed_index))
        engine.register(ProviderStage(provider))
        app.state.pipeline = engine

    yield

    # Clean up the provider's httpx client on shutdown.
    provider = getattr(app.state, "provider", None)  # type: ignore[assignment]
    if provider is not None:
        await provider.close()  # type: ignore[attr-defined]


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
