"""Tests for GET /debug/runtime-context.

Covers the default no-router behavior, the models_config router, the
fallback single-provider router, settings-field reflection, that provider
secrets are never serialized, the read-only ``quality_baseline`` summary
(available, empty-history, and loader-exception cases), and the read-only
``gateway_session_summary`` (success, empty-history, loader-exception, and
summarizer-exception cases).

Both history loaders (``EngineeringMemory`` and
``build_session_log_summary`` imported into
``apps.gateway.api.runtime_context``) are patched in every test so no real
memory storage file is ever read.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import patch

from starlette.testclient import TestClient

from apps.gateway.core.config import Settings
from apps.gateway.main import create_app
from packages.engineering_memory.models import EngineeringSessionRecord
from packages.observability.session_log_history import SessionLogSummary
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


def _quality_record(
    session_id: str,
    *,
    completed_at: str,
    model: str,
    total_score: int,
    total_maximum: int,
    probes: list[dict[str, Any]] | None = None,
) -> EngineeringSessionRecord:
    """Build a quality_harness EngineeringSessionRecord for tests."""
    return EngineeringSessionRecord(
        session_id=session_id,
        workflow_name="quality_harness",
        request_summary=f"quality harness run against model {model}",
        transaction_id=session_id,
        evaluation_report={
            "probes": probes if probes is not None else [],
            "total_score": total_score,
            "total_maximum": total_maximum,
            "total_prompt_tokens": 0,
            "total_seconds": 0.0,
            "style_ok_count": 0,
            "total_style_violations": 0,
        },
        controller_decision="COMPLETE",
        completed_at=completed_at,
        metadata={"model": model},
    )


@contextmanager
def patch_quality_history(records: list[EngineeringSessionRecord]) -> Iterator[None]:
    """Patch the history loaders used by the endpoint.

    Replaces ``apps.gateway.api.runtime_context.EngineeringMemory`` with a
    stub whose ``reload()`` is a no-op and whose ``list_sessions()`` yields
    the given records, so tests never read the real memory storage file.
    Also pins ``build_session_log_summary`` to an empty summary so the
    gateway-session path stays deterministic unless a test overrides it.
    """

    class _MemoryStub:
        def __init__(self, storage_path: str | None = None, in_memory_only: bool = False) -> None:
            del storage_path, in_memory_only

        def reload(self) -> int:
            return len(records)

        def list_sessions(self) -> tuple[EngineeringSessionRecord, ...]:
            return tuple(records)

        def find_by_workflow(
            self, workflow_name: str
        ) -> tuple[EngineeringSessionRecord, ...]:
            return tuple(r for r in records if r.workflow_name == workflow_name)

    with patch("apps.gateway.api.runtime_context.EngineeringMemory", _MemoryStub):
        with patch(
            "apps.gateway.api.runtime_context.build_session_log_summary",
            return_value=SessionLogSummary(),
        ):
            yield


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
    "quality_baseline",
    "gateway_session_summary",
]

UNAVAILABLE_QUALITY_BASELINE = {
    "available": False,
    "latest_score": None,
    "best_score": None,
    "latest_session_id": None,
    "latest_model": None,
    "recent_missing_facts": [],
}

UNAVAILABLE_GATEWAY_SESSION_SUMMARY = {
    "available": False,
    "total_records": 0,
    "success_rate": None,
    "failure_count": 0,
    "avg_total_ms": None,
    "avg_provider_wait_ms": None,
    "history_cap_rate": None,
    "intent_distribution": {},
    "model_distribution": {},
    "recent_errors": [],
}


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
    with patch_quality_history([]):
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
    assert body["quality_baseline"] == UNAVAILABLE_QUALITY_BASELINE
    assert body["gateway_session_summary"] == UNAVAILABLE_GATEWAY_SESSION_SUMMARY
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
        with patch_quality_history([]):
            with patch(
                "apps.gateway.api.runtime_context.get_settings",
                return_value=_settings(),
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
        assert body["gateway_session_summary"] == UNAVAILABLE_GATEWAY_SESSION_SUMMARY
    finally:
        import asyncio

        asyncio.run(router.close_all())


def test_fallback_router() -> None:
    """A FallbackModelRouter yields routing_mode fallback with a single entry."""
    settings = _settings()
    router = FallbackModelRouter("openai")
    client = _client(model_router=router, settings=settings)
    with patch_quality_history([]):
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
    assert body["quality_baseline"] == UNAVAILABLE_QUALITY_BASELINE
    assert body["gateway_session_summary"] == UNAVAILABLE_GATEWAY_SESSION_SUMMARY


def test_quality_baseline_summary() -> None:
    """quality_baseline exposes latest/best score, latest session/model, missing facts."""
    records = [
        _quality_record(
            "qh-2026-01-01T00",
            completed_at="2026-01-01T00:00:00+00:00",
            model="qwen36",
            total_score=4,
            total_maximum=10,
            probes=[
                {
                    "id": "probe_alpha",
                    "missing_facts": ["fact_one", "fact_two"],
                }
            ],
        ),
        _quality_record(
            "qh-2026-03-01T00",
            completed_at="2026-03-01T00:00:00+00:00",
            model="qwen38-27b",
            total_score=9,
            total_maximum=10,
        ),
    ]
    client = _client(model_router=None, settings=_settings())
    with patch_quality_history(records):
        with patch(
            "apps.gateway.api.runtime_context.get_settings", return_value=_settings()
        ):
            response = client.get("/debug/runtime-context")
    assert response.status_code == 200
    assert response.json()["quality_baseline"] == {
        "available": True,
        "latest_score": 0.9,
        "best_score": 0.9,
        "latest_session_id": "qh-2026-03-01T00",
        "latest_model": "qwen38-27b",
        "recent_missing_facts": [
            {
                "session_id": "qh-2026-01-01T00",
                "probe_id": "probe_alpha",
                "missing_facts": "fact_one, fact_two",
            }
        ],
    }
    # No gateway-session records, so the gateway summary stays unavailable.
    assert response.json()["gateway_session_summary"] == UNAVAILABLE_GATEWAY_SESSION_SUMMARY


def test_quality_baseline_missing_history_unavailable() -> None:
    """Empty history yields available=false with null fields and 200."""
    client = _client(model_router=None, settings=_settings())
    with patch_quality_history([]):
        with patch(
            "apps.gateway.api.runtime_context.get_settings", return_value=_settings()
        ):
            response = client.get("/debug/runtime-context")
    assert response.status_code == 200
    assert response.json()["quality_baseline"] == UNAVAILABLE_QUALITY_BASELINE
    assert response.json()["gateway_session_summary"] == UNAVAILABLE_GATEWAY_SESSION_SUMMARY


def test_quality_baseline_loader_exception_unavailable() -> None:
    """A loader exception yields available=false and the endpoint still returns 200."""

    class _ExplodingMemory:
        def __init__(self, storage_path: str | None = None, in_memory_only: bool = False) -> None:
            raise RuntimeError("memory storage unavailable")

    client = _client(model_router=None, settings=_settings())
    with patch(
        "apps.gateway.api.runtime_context.EngineeringMemory", _ExplodingMemory
    ):
        with patch(
            "apps.gateway.api.runtime_context.get_settings", return_value=_settings()
        ):
            response = client.get("/debug/runtime-context")
    assert response.status_code == 200
    assert response.json()["quality_baseline"] == UNAVAILABLE_QUALITY_BASELINE
    assert response.json()["gateway_session_summary"] == UNAVAILABLE_GATEWAY_SESSION_SUMMARY


def test_quality_baseline_summarizer_exception_unavailable() -> None:
    """A malformed summary path yields available=false and still returns 200."""
    client = _client(model_router=None, settings=_settings())
    records = [
        _quality_record(
            "qh-2026-01-01T00",
            completed_at="2026-01-01T00:00:00+00:00",
            model="qwen38-27b",
            total_score=1,
            total_maximum=1,
        )
    ]
    with patch_quality_history(records):
        with patch(
            "apps.gateway.api.runtime_context.summarize_quality_history",
            side_effect=ValueError("malformed quality history"),
        ):
            with patch(
                "apps.gateway.api.runtime_context.get_settings",
                return_value=_settings(),
            ):
                response = client.get("/debug/runtime-context")
    assert response.status_code == 200
    assert response.json()["quality_baseline"] == UNAVAILABLE_QUALITY_BASELINE
    assert response.json()["gateway_session_summary"] == UNAVAILABLE_GATEWAY_SESSION_SUMMARY


def test_gateway_session_summary_success() -> None:
    """gateway_session_summary maps a populated summary, capping/sorting errors."""
    summary = SessionLogSummary(
        total_records=9,
        success_count=2,
        failure_count=7,
        success_rate=0.222222,
        error_breakdown={
            "Connection timeout: backend": 3,
            "Rate limit exceeded": 2,
            "Provider 500 error": 1,
            "Provider 502 error": 1,
            "Bad gateway downstream": 1,
            "Invalid API key": 1,
        },
        avg_total_ms=200.0,
        avg_provider_wait_ms=40.0,
        intent_distribution={"SEARCH": 2, "DEBUG": 2, "REPAIR": 5},
        history_cap_rate=0.333333,
        model_distribution={"qwen38-27b": 5, "qwen36": 4},
        recent_records=[
            {
                "session_id": "gw-secret-1",
                "model": "qwen38-27b",
                "intent": "SEARCH",
                "status": "ok",
                "completed_at": "2026-07-01T00:00:00+00:00",
            },
        ],
    )
    client = _client(model_router=None, settings=_settings())
    with patch_quality_history([]):
        with patch(
            "apps.gateway.api.runtime_context.build_session_log_summary",
            return_value=summary,
        ):
            with patch(
                "apps.gateway.api.runtime_context.get_settings",
                return_value=_settings(),
            ):
                response = client.get("/debug/runtime-context")
    assert response.status_code == 200
    body = response.json()
    # Counts, timing, distributions and the history-cap rate are reflected.
    assert body["gateway_session_summary"] == {
        "available": True,
        "total_records": 9,
        "success_rate": 0.222222,
        "failure_count": 7,
        "avg_total_ms": 200.0,
        "avg_provider_wait_ms": 40.0,
        "history_cap_rate": 0.333333,
        "intent_distribution": {"SEARCH": 2, "DEBUG": 2, "REPAIR": 5},
        "model_distribution": {"qwen38-27b": 5, "qwen36": 4},
        # Capped to 5, sorted by count desc, ties broken by prefix asc; the
        # sixth error ("Provider 502 error") is dropped.
        "recent_errors": [
            {"error": "Connection timeout: backend", "count": 3},
            {"error": "Rate limit exceeded", "count": 2},
            {"error": "Bad gateway downstream", "count": 1},
            {"error": "Invalid API key", "count": 1},
            {"error": "Provider 500 error", "count": 1},
        ],
    }
    # Raw session-log records (recent_records) are never exposed.
    assert "gw-secret-1" not in response.text


def test_gateway_session_empty_history_unavailable() -> None:
    """A zero-record summary yields available=false with 200."""
    client = _client(model_router=None, settings=_settings())
    with patch_quality_history([]):
        with patch(
            "apps.gateway.api.runtime_context.build_session_log_summary",
            return_value=SessionLogSummary(),
        ):
            with patch(
                "apps.gateway.api.runtime_context.get_settings",
                return_value=_settings(),
            ):
                response = client.get("/debug/runtime-context")
    assert response.status_code == 200
    assert response.json()["gateway_session_summary"] == UNAVAILABLE_GATEWAY_SESSION_SUMMARY


def test_gateway_session_loader_exception_unavailable() -> None:
    """A memory loader exception yields available=false and still returns 200."""

    class _ExplodingMemory:
        def __init__(self, storage_path: str | None = None, in_memory_only: bool = False) -> None:
            raise RuntimeError("memory storage unavailable")

    client = _client(model_router=None, settings=_settings())
    with patch("apps.gateway.api.runtime_context.EngineeringMemory", _ExplodingMemory):
        with patch(
            "apps.gateway.api.runtime_context.build_session_log_summary",
            side_effect=AssertionError("summarizer must not run when memory fails"),
        ):
            with patch(
                "apps.gateway.api.runtime_context.get_settings",
                return_value=_settings(),
            ):
                response = client.get("/debug/runtime-context")
    assert response.status_code == 200
    assert response.json()["gateway_session_summary"] == UNAVAILABLE_GATEWAY_SESSION_SUMMARY


def test_gateway_session_summarizer_exception_unavailable() -> None:
    """A build_session_log_summary exception yields available=false and 200."""
    client = _client(model_router=None, settings=_settings())
    with patch_quality_history([]):
        with patch(
            "apps.gateway.api.runtime_context.build_session_log_summary",
            side_effect=ValueError("malformed session history"),
        ):
            with patch(
                "apps.gateway.api.runtime_context.get_settings",
                return_value=_settings(),
            ):
                response = client.get("/debug/runtime-context")
    assert response.status_code == 200
    assert response.json()["gateway_session_summary"] == UNAVAILABLE_GATEWAY_SESSION_SUMMARY
