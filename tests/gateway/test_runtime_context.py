"""Tests for GET /debug/runtime-context.

Covers the default no-router behavior, the models_config router, the
fallback single-provider router, settings-field reflection, and that
provider secrets are never serialized.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from starlette.testclient import TestClient

from apps.gateway.core.config import Settings
from apps.gateway.main import create_app
from packages.providers.registry_models import ModelRegistry
from packages.providers.router import FallbackModelRouter, ModelRouter


def _settings(**overrides: Any) -> Settings:
    """Build a Settings instance with deterministic known values."""
    base: dict[str, Any] = {
        "repository_context_enabled": True,
        "repository_context_max_tokens": 4096,
        "repository_context_intent_budgets": "SEARCH:2048,DEBUG:1024",
        "context_delta_injection": True,
        "session_log_enabled": True,
        "session_log_path": "logs/sessions.jsonl",
        "default_model": "qwen38-27b",
        "default_provider": "openai",
        "history_cap_enabled": True,
        "history_cap_tokens": 10000,
    }
    base.update(overrides)
    return Settings(**base)


def _client(model_router: Any = None, settings: Settings | None = None) -> TestClient:
    """Create a TestClient without running the lifespan.

    The lifespan is intentionally skipped so no provider connections, index
    building, or pipeline construction happens. ``model_router`` (when
    given) is placed on ``app.state`` to emulate the post-lifespan state.
    """
    app = create_app()
    if model_router is not None:
        app.state.model_router = model_router
    if settings is None:
        settings = _settings()
    return TestClient(app, raise_server_exceptions=False)


CONFIG_KEYS = [
    "repository_context_enabled",
    "repository_context_max_tokens",
    "repository_context_intent_budget_map",
    "context_delta_injection",
    "session_log_enabled",
    "session_log_path",
    "default_model",
    "default_provider",
    "history_cap_enabled",
    "history_cap_tokens",
    "routing_mode",
    "models",
]

def _collect_route_paths(app: Any) -> set[str]:
    """Collect route paths, recursing into included sub-routers.

    Included API routes are not top-level entries on ``app.routes``; this
    mirrors the helper in ``tests/gateway/test_main.py``.
    """
    paths: set[str] = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        elif hasattr(route, "original_router"):
            for sub_route in route.original_router.routes:
                if hasattr(sub_route, "path"):
                    paths.add(sub_route.path)
    return paths


def test_route_registered() -> None:
    """create_app() registers /debug/runtime-context."""
    app = create_app()
    assert "/debug/runtime-context" in _collect_route_paths(app)


def test_no_router_returns_none_and_empty_models() -> None:
    """With no model router in app.state, routing_mode is none, models is []."""
    client = _client(model_router=None, settings=_settings())
    with patch(
        "apps.gateway.api.runtime_context.get_settings", return_value=_settings()
    ) as patched:
        response = client.get("/debug/runtime-context")
    assert response.status_code == 200
    body = response.json()
    assert body["routing_mode"] == "none"
    assert body["models"] == []
    for key in CONFIG_KEYS:
        assert key in body
    # Settings-driven values are reflected.
    assert body["default_model"] == "qwen38-27b"
    assert body["default_provider"] == "openai"
    assert body["repository_context_max_tokens"] == 4096
    assert body["repository_context_intent_budget_map"] == {
        "SEARCH": 2048,
        "DEBUG": 1024,
    }
    assert body["context_delta_injection"] is True
    assert body["session_log_enabled"] is True
    assert body["session_log_path"] == "logs/sessions.jsonl"
    assert body["history_cap_enabled"] is True
    assert body["history_cap_tokens"] == 10000
    assert patched.call_count == 1

def test_models_config_router() -> None:
    """A ModelRouter exposes whitelisted model fields, no secrets."""
    raw = json.dumps(
        [
            {
                "model": "qwen38-27b",
                "backend_model": "qwen3.8-27b",
                "provider": "openai",
                "base_url": "http://127.0.0.1:30000/v1",
                "api_key": "top-secret-key",
                "context_window": 262144,
                "max_output_tokens": 8192,
            }
        ]
    )
    router = ModelRouter(ModelRegistry.from_json(raw))
    try:
        client = _client(model_router=router, settings=_settings())
        with patch(
            "apps.gateway.api.runtime_context.get_settings", return_value=_settings()
        ):
            response = client.get("/debug/runtime-context")
        assert response.status_code == 200
        body = response.json()
        assert body["routing_mode"] == "models_config"
        assert body["models"] == [
            {
                "model": "qwen38-27b",
                "backend_model": "qwen3.8-27b",
                "provider": "openai",
                "base_url": "http://127.0.0.1:30000/v1",
                "context_window": 262144,
                "max_output_tokens": 8192,
            }
        ]
        # api_key is never serialized.
        assert "api_key" not in response.text
        assert "top-secret-key" not in response.text
    finally:
        import asyncio

        asyncio.run(router.close_all())


def test_fallback_router() -> None:
    """A FallbackModelRouter yields routing_mode fallback with a single entry."""
    settings = _settings()
    router = FallbackModelRouter("openai")
    client = _client(model_router=router, settings=settings)
    with patch(
        "apps.gateway.api.runtime_context.get_settings", return_value=settings
    ):
        response = client.get("/debug/runtime-context")
    assert response.status_code == 200
    body = response.json()
    assert body["routing_mode"] == "fallback"
    assert body["models"] == [
        {
            "model": "qwen38-27b",
            "backend_model": None,
            "provider": "openai",
            "base_url": None,
            "context_window": None,
            "max_output_tokens": None,
        }
    ]

