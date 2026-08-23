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


@router.get("/runtime-context")
async def runtime_context(request: Request) -> dict[str, Any]:
    """Return the live runtime-context configuration.

    Args:
        request: The incoming request, used to reach ``app.state``.

    Returns:
        A dict with the settings-driven context flags, the routing mode,
        and the configured model aliases. When the model router is not
        available (pre-lifespan or no usable config), ``routing_mode`` is
        ``"none"`` and ``models`` is empty rather than raising.
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
    }
