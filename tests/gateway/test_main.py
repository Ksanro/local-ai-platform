"""Tests for the FastAPI application factory.

Verifies that create_app() registers all expected routes and that
the pipeline is wired onto app.state during the lifespan.
"""

import pytest
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

    expected = {
        "/health",
        "/version",
        "/v1/chat/completions",
        "/v1/models",
        "/debug/runtime-context",
    }
    assert paths == expected


def test_lifespan_runs_without_error() -> None:
    """Verify the lifespan context manager runs without raising exceptions.

    This test enters the lifespan via TestClient to catch startup
    errors (e.g., TypeError from incorrect kwarg names) that route-
    only tests miss.
    """

    from starlette.testclient import TestClient

    app = create_app()
    # TestClient as a context manager enters and exits the lifespan.
    # If lifespan raises, the test fails.
    with TestClient(app, raise_server_exceptions=False) as client:
        # A basic request to verify the app is operational.
        response = client.get("/health")
        assert response.status_code == 200


def _repository_context_stage(client):
    """Return the RepositoryContextStage the lifespan registered."""
    from packages.pipeline.stages.repository_context import RepositoryContextStage

    stages = getattr(client.app.state.pipeline, "_stages", [])
    return next(stage for stage in stages if isinstance(stage, RepositoryContextStage))


def test_lifespan_leaves_change_signal_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Default settings must not attach a change-aware source."""
    from starlette.testclient import TestClient

    import apps.gateway.main as gateway_main
    from apps.gateway.core.config import Settings

    monkeypatch.setattr(
        gateway_main,
        "get_settings",
        lambda: Settings(repository_path=str(tmp_path), models_config=""),
    )

    with TestClient(
        gateway_main.create_app(), raise_server_exceptions=False
    ) as client:
        assert _repository_context_stage(client)._changed_files is None


def test_lifespan_wires_change_signal_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """The opt-in setting reaches the stage and startup survives no Git here."""
    from starlette.testclient import TestClient

    import apps.gateway.main as gateway_main
    from apps.gateway.core.config import Settings
    from packages.repository.changed_files import ChangedFilesSignal

    def _settings() -> Settings:
        return Settings(
            repository_path=str(tmp_path),
            models_config="",
            repository_context_changed_files_enabled=True,
        )

    monkeypatch.setattr(gateway_main, "get_settings", _settings)

    with TestClient(
        gateway_main.create_app(), raise_server_exceptions=False
    ) as client:
        signal = _repository_context_stage(client)._changed_files
        refresher = client.app.state.changed_files_refresher

    assert isinstance(signal, ChangedFilesSignal)
    assert signal.capture_count == 1
    assert isinstance(signal.module_paths(), frozenset)
    # The default TTL captures once at startup and never again, so there is
    # nothing to refresh and no background task to cancel.
    assert refresher.start() is None
    assert refresher.running is False


def test_lifespan_schedules_background_refresh_for_a_positive_ttl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """A TTL above zero warms the snapshot off the request path."""
    from starlette.testclient import TestClient

    import apps.gateway.main as gateway_main
    from apps.gateway.core.config import Settings

    def _settings() -> Settings:
        return Settings(
            repository_path=str(tmp_path),
            models_config="",
            repository_context_changed_files_enabled=True,
            repository_context_changed_files_ttl_seconds=3600,
        )

    monkeypatch.setattr(gateway_main, "get_settings", _settings)

    with TestClient(
        gateway_main.create_app(), raise_server_exceptions=False
    ) as client:
        refresher = client.app.state.changed_files_refresher
        signal = _repository_context_stage(client)._changed_files
        assert refresher.running is True
        assert refresher.interval_seconds == 3600.0
        assert signal.capture_count == 1

    # Leaving the lifespan cancels the task instead of orphaning it.
    assert refresher.running is False
