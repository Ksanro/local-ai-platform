"""Tests for the FastAPI application factory.

Verifies that create_app() registers all expected routes and that
the pipeline is wired onto app.state during the lifespan.
"""

from fastapi.routing import APIRoute

from apps.gateway.main import create_app


def _collect_route_paths(app) -> set[str]:
    """Collect all route paths from a FastAPI app.

    Recurses into _IncludedRouter objects to find APIRoute paths.

    Args:
        app: The FastAPI application instance.

    Returns:
        A set of route path strings.
    """
    paths: set[str] = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            paths.add(route.path)
        elif hasattr(route, "original_router"):
            for sub_route in route.original_router.routes:
                if isinstance(sub_route, APIRoute):
                    paths.add(sub_route.path)
    return paths


def test_create_app_registers_routes() -> None:
    """Verify create_app() registers /health, /version, and /v1/chat/completions."""
    app = create_app()
    paths = _collect_route_paths(app)

    assert "/health" in paths
    assert "/version" in paths
    assert "/v1/chat/completions" in paths


def test_create_app_registers_all_routes() -> None:
    """Verify no unexpected routes are registered."""
    app = create_app()
    paths = _collect_route_paths(app)

    expected = {"/health", "/version", "/v1/chat/completions"}
    assert paths == expected


def test_lifespan_runs_without_error() -> None:
    """Verify the lifespan context manager runs without raising exceptions.

    This test enters the lifespan via TestClient to catch startup
    errors (e.g., TypeError from incorrect kwarg names) that route-
    only tests miss.
    """
    from contextlib import asynccontextmanager

    import pytest
    from starlette.testclient import TestClient

    app = create_app()
    # TestClient as a context manager enters and exits the lifespan.
    # If lifespan raises, the test fails.
    with TestClient(app, raise_server_exceptions=False) as client:
        # A basic request to verify the app is operational.
        response = client.get("/health")
        assert response.status_code == 200