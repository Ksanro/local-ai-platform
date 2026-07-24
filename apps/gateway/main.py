"""FastAPI gateway application entry point.

Provides a ``create_app`` factory function and a module-level ``app``
instance for development servers and production WSGI servers.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.gateway.api.chat import router as chat_router
from apps.gateway.api.health import router as health_router
from apps.gateway.api.models import router as models_router
from apps.gateway.api.version import router as version_router
from apps.gateway.core.config import get_settings
from apps.gateway.core.logging import setup_logging
from apps.gateway.middleware import RequestMiddleware, TimingMiddleware
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.stages import (
    ModelResolutionStage,
    PlanningStage,
    ProviderStage,
)
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.providers import _load_providers
from packages.providers.exceptions import UnknownModelError
from packages.providers.registry import has_provider
from packages.providers.registry_models import ModelRegistry
from packages.providers.router import FallbackModelRouter, ModelRouter
from packages.repository import StructIndex
from packages.repository.index.builder import RepositoryIndexBuilder

logger = logging.getLogger(__name__)


# Load .env file from project root at module import time.
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.is_file():
    load_dotenv(dotenv_path=_env_path, override=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.

    Runs once at startup: loads settings, configures logging, builds
    the ModelRouter, builds the RepositoryIndex, and builds the pipeline
    engine. On shutdown, closes the router's provider instances.

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
            builder = RepositoryIndexBuilder(
                exclude_tests=settings.repository_exclude_tests,
                exclude_globs=settings.repository_exclude_globs,
            )
            index = builder.build(repo_path)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Extract metrics from the built index.
            if index is not None:
                if isinstance(index, StructIndex):
                    indexed_modules = index.statistics().module_count
                    indexed_symbols = index.statistics().symbol_count
                    indexed_relationships = len(index.relationships())

                    # Count files by iterating modules.
                    indexed_files = len(index.modules)

                    indexing_duration_ms = elapsed_ms

                    logger.info(
                        "repository_index path=%s files=%d modules=%d "
                        "symbols=%d relationships=%d excluded_tests=%d "
                        "excluded_globs=%d duration_ms=%.1f",
                        repo_path,
                        indexed_files,
                        indexed_modules,
                        indexed_symbols,
                        indexed_relationships,
                        builder.excluded_test_count,
                        builder.excluded_glob_count,
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

    # Build the ModelRouter from models_config.
    model_router: ModelRouter | FallbackModelRouter | None = None
    models_config = settings.models_config.strip()

    if models_config:
        # Parse config — fail loudly if invalid.
        registry = ModelRegistry.from_json(models_config)
        model_router = ModelRouter(registry)
        app.state.model_router = model_router

        backends = len(model_router._providers)
        model_names = registry.available_models()
        logger.info(
            "model_router models=%s backends=%d",
            json.dumps(model_names),
            backends,
        )
    else:
        # Fallback: single-provider mode.
        default = settings.default_provider
        if has_provider(default):
            model_router = FallbackModelRouter(default)
            app.state.model_router = model_router
            logger.info(
                "model_router fallback provider=%s",
                default,
            )

    # Cast index to the expected type for RepositoryContextStage.
    typed_index: StructIndex | None = (
        index if isinstance(index, StructIndex) else None
    )

    if model_router is not None:
        engine = PipelineEngine()
        # ModelResolutionStage runs first — before PlanningStage.
        engine.register(ModelResolutionStage(model_router))
        # Planning stage runs before repository context.
        engine.register(PlanningStage())
        # Repository context stage runs before provider execution.
        engine.register(RepositoryContextStage(index=typed_index))
        # ProviderStage is routing-agnostic — reads from context.resolved_model.
        engine.register(ProviderStage())
        app.state.pipeline = engine

    yield

    # Clean up the router's provider instances on shutdown.
    router = getattr(app.state, "model_router", None)
    if router is not None:
        await router.close_all()


def _unknown_model_handler(_: RequestValidationError) -> JSONResponse:
    """Default handler — won't be called for UnknownModelError but required by signature."""
    return JSONResponse(status_code=404, content={"detail": "Not found"})


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

    # Register custom exception handler for UnknownModelError → HTTP 404.
    app.add_exception_handler(UnknownModelError, lambda req, exc: JSONResponse(
        status_code=404,
        content={
            "error": {
                "message": str(exc),
                "type": "invalid_request_error",
                "param": "model",
                "code": "model_not_found",
                "available_models": exc.available_models,
            }
        },
    ))

    app.include_router(health_router)
    app.include_router(version_router)
    app.include_router(chat_router)
    app.include_router(models_router)

    return app


app = create_app()
