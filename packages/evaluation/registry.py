"""Registry for evaluation metrics and categories.

Supports registration of custom metrics and categories.
Provides lookup and discovery functionality.
Eliminates duplicate registrations.

Architecture
------------

Registry  -->  Metric Registration  -->  Metric Lookup
Registry  -->  Category Registration  -->  Category Lookup

Public API
----------

.. code-block:: python

    from packages.evaluation.registry import (
        register_metric,
        register_category,
        get_metric,
        get_category,
        list_metrics,
        list_categories,
    )

"""

from __future__ import annotations

from typing import Any, Callable

__all__ = [
    "register_metric",
    "register_category",
    "get_metric",
    "get_category",
    "list_metrics",
    "list_categories",
    "reset_registry",
]

# Internal storage — private module-level dictionaries.
# These are the only mutable state in the evaluation package.

_metric_registry: dict[str, dict[str, Any]] = {}
_category_registry: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Metric Registration
# ---------------------------------------------------------------------------


def register_metric(
    name: str,
    computation: Callable[..., float],
    weight: float = 1.0,
    description: str = "",
) -> None:
    """Register a custom metric computation function.

    Metrics are identified by name. Duplicate names are silently
    ignored — the original registration is preserved.

    Args:
        name: Unique metric name.
        computation: Callable that computes the metric value.
            Must accept keyword arguments matching the metric's
            expected inputs and return a float.
        weight: Weight in the scoring formula (default 1.0).
        description: Human-readable description (default "").
    """
    if name in _metric_registry:
        return  # Duplicate — ignore silently

    _metric_registry[name] = {
        "computation": computation,
        "weight": weight,
        "description": description,
    }


def get_metric(name: str) -> dict[str, Any] | None:
    """Look up a registered metric by name.

    Args:
        name: Metric name to look up.

    Returns:
        Metric dict with 'computation', 'weight', and 'description'
        keys, or None if not found.
    """
    return _metric_registry.get(name)


def list_metrics() -> tuple[str, ...]:
    """List all registered metric names.

    Returns:
        Tuple of metric names in registration order.
    """
    return tuple(_metric_registry.keys())


# ---------------------------------------------------------------------------
# Category Registration
# ---------------------------------------------------------------------------


def register_category(
    name: str,
    weight: float,
    metric_names: list[str] | None = None,
    description: str = "",
) -> None:
    """Register a custom evaluation category.

    Categories group related metrics into a scored group.
    Duplicate names are silently ignored — the original registration
    is preserved.

    Args:
        name: Unique category name.
        weight: Weight in the overall score calculation.
        metric_names: List of metric names belonging to this category.
            If None, an empty list is used.
        description: Human-readable description (default "").
    """
    if name in _category_registry:
        return  # Duplicate — ignore silently

    _category_registry[name] = {
        "weight": weight,
        "metric_names": metric_names or [],
        "description": description,
    }


def get_category(name: str) -> dict[str, Any] | None:
    """Look up a registered category by name.

    Args:
        name: Category name to look up.

    Returns:
        Category dict with 'weight', 'metric_names', and 'description'
        keys, or None if not found.
    """
    return _category_registry.get(name)


def list_categories() -> tuple[str, ...]:
    """List all registered category names.

    Returns:
        Tuple of category names in registration order.
    """
    return tuple(_category_registry.keys())


# ---------------------------------------------------------------------------
# Registry Reset (for testing)
# ---------------------------------------------------------------------------


def reset_registry() -> None:
    """Reset all registries to empty state.

    This is primarily used in tests to ensure isolation between
    test cases. Do not call in production code.
    """
    _metric_registry.clear()
    _category_registry.clear()