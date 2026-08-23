"""Runtime-context introspection endpoint.

Provides ``GET /debug/runtime-context`` - a read-only, non-liveness debug
endpoint so agents can see the live gateway/backend/context configuration
without manually reading ``.env`` or the docs.

Security:
- Read-only; never mutates settings, state, or storage.
- ``models`` entries expose only a public whitelist of fields; ``api_key``
  and other provider-config secrets are never serialized.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from apps.gateway.core.config import get_settings
from packages.engineering_memory.memory import EngineeringMemory
from packages.engineering_memory.quality_harness_records import WORKFLOW_NAME
from packages.observability.quality_history import summarize_quality_history
from packages.providers.models import ModelDefinition
from packages.providers.router import ModelRouter

router = APIRouter(prefix="/debug", tags=["debug"])

# Whitelist of ModelDefinition fields that are safe to expose. Everything
# else (api_key, timeout, tokenizer, capability flags) is deliberately
# omitted.
_MODEL_FIELDS = (
    "model",
    "backend_model",
    "provider",
    "base_url",
    "context_window",
    "max_output_tokens",
)

def _model_entries(definitions: list[ModelDefinition]) -> list[dict[str, Any]]:
    """Serialize model definitions to a public, secret-free payload.

    Args:
        definitions: The registry model definitions.

    Returns:
        A list of dicts with only the whitelisted public fields.
    """
    return [
        {field: getattr(definition, field) for field in _MODEL_FIELDS}
        for definition in definitions
    ]


def _unavailable_quality_baseline() -> dict[str, Any]:
    """Return the empty quality-baseline shape used when no history is usable."""
    return {
        "available": False,
        "latest_score": None,
        "best_score": None,
        "latest_session_id": None,
        "latest_model": None,
        "recent_missing_facts": [],
    }


def _quality_baseline() -> dict[str, Any]:
    """Build a read-only quality-baseline summary from persisted history.

    Reads persisted quality-harness runs from Engineering Memory and uses the
    observability summarizer to aggregate them. Reports, for the primary
    quality-harness workflow: the latest and best score ratio, the model and
    session id of the most recent run, and the recent missing-fact rows.

    This is strictly read-only and never raises. A missing, empty, unreadable,
    or malformed history file yields the empty baseline (``available=False``)
    so the endpoint still returns 200.

    Returns:
        A dict with the keys ``available``, ``latest_score``, ``best_score``,
        ``latest_session_id``, ``latest_model`` and ``recent_missing_facts``.
    """
    try:
        memory = EngineeringMemory()
        memory.reload()
        records = list(memory.list_sessions())

        summary = summarize_quality_history(records)

        if summary.quality_harness_runs <= 0:
            return _unavailable_quality_baseline()

        primary = next(
            (
                workflow
                for workflow in summary.workflows
                if workflow.workflow_name == WORKFLOW_NAME
            ),
            None,
        )
        if primary is None:
            return _unavailable_quality_baseline()

        latest = next(
            (
                record
                for record in records
                if record.session_id == primary.latest_session_id
            ),
            None,
        )

        latest_score: float | None = None
        latest_model: str | None = None
        if latest is not None:
            report = latest.evaluation_report
            report = report if isinstance(report, dict) else {}
            maximum = int(report.get("total_maximum", 0) or 0)
            if maximum > 0:
                latest_score = int(report.get("total_score", 0) or 0) / maximum
            else:
                latest_score = 0.0
            model = latest.metadata.get("model")
            latest_model = model if isinstance(model, str) and model else None

        recent_missing_facts = [
            {
                "session_id": row.session_id,
                "probe_id": row.probe_id,
                "missing_facts": ", ".join(row.missing_facts),
            }
            for row in summary.recent_missing_facts
            if row.workflow_name == WORKFLOW_NAME
        ]

        return {
            "available": True,
            "latest_score": latest_score,
            "best_score": primary.best_score_ratio,
            "latest_session_id": primary.latest_session_id,
            "latest_model": latest_model,
            "recent_missing_facts": recent_missing_facts,
        }
    except Exception:
        return _unavailable_quality_baseline()


@router.get("/runtime-context")
async def runtime_context(request: Request) -> dict[str, Any]:
    """Return the live runtime-context configuration.

    Args:
        request: The incoming request, used to reach ``app.state``.

    Returns:
        A dict with the settings-driven context flags, the routing mode,
        and the configured model aliases. When the model router is not
        available (pre-lifespan or no usable config), ``routing_mode`` is
        ``"none"`` and ``models`` is empty rather than raising. Also includes
        a read-only ``quality_baseline`` summary derived from persisted
        quality-harness history.
    """
    settings = get_settings()
    model_router = getattr(request.app.state, "model_router", None)

    if model_router is None:
        routing_mode = "none"
        models: list[dict[str, Any]] = []
    elif isinstance(model_router, ModelRouter):
        routing_mode = "models_config"
        models = _model_entries(model_router.registry.definitions)
    else:
        routing_mode = "fallback"
        models = [
            {
                "model": name,
                "backend_model": None,
                "provider": settings.default_provider,
                "base_url": None,
                "context_window": None,
                "max_output_tokens": None,
            }
            for name in model_router.available_models()
        ]

    return {
        "repository_context_enabled": settings.repository_context_enabled,
        "repository_context_max_tokens": settings.repository_context_max_tokens,
        "repository_context_intent_budget_map": (
            settings.repository_context_intent_budget_map
        ),
        "context_delta_injection": settings.context_delta_injection,
        "session_log_enabled": settings.session_log_enabled,
        "session_log_path": settings.session_log_path,
        "default_model": settings.default_model,
        "default_provider": settings.default_provider,
        "history_cap_enabled": settings.history_cap_enabled,
        "history_cap_tokens": settings.history_cap_tokens,
        "routing_mode": routing_mode,
        "models": models,
        "quality_baseline": _quality_baseline(),
    }
