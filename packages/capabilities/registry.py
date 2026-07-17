"""Capability Registry.

Manages registration, lookup, and discovery of capabilities.

Architecture
------------

The registry is the single source of truth for capability registration.
It maintains deterministic ordering using an ordered ``dict``.

Public API
----------

.. code-block:: python

    from packages.capabilities.registry import CapabilityRegistry

    registry = CapabilityRegistry()
    registry.register("explain", ExplainCapability)
    capability_cls = registry.get("explain")
    names = registry.all()
"""

from __future__ import annotations

from typing import Any, Type


class CapabilityRegistry:
    """Registry for capability classes.

    Responsibilities:
        - Register capabilities by name.
        - Prevent duplicate registration.
        - Lookup by name.
        - List registered capabilities in deterministic order.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._registry: dict[str, Type[Any]] = {}

    def register(self, name: str, capability_class: Type[Any]) -> None:
        """Register a capability class under the given name.

        Args:
            name: Unique identifier for the capability.
            capability_class: The capability class to register.

        Raises:
            ValueError: If a capability with the same name is already
                registered.
        """
        if name in self._registry:
            raise ValueError(
                f"Capability '{name}' is already registered. "
                f"Duplicate registration is not allowed."
            )
        self._registry[name] = capability_class

    def get(self, name: str) -> Type[Any] | None:
        """Lookup a capability class by name.

        Args:
            name: The capability name.

        Returns:
            The capability class, or ``None`` if not found.
        """
        return self._registry.get(name)

    def has(self, name: str) -> bool:
        """Check whether a capability is registered.

        Args:
            name: The capability name.

        Returns:
            ``True`` if registered, ``False`` otherwise.
        """
        return name in self._registry

    def all(self) -> list[str]:
        """Return all registered capability names in deterministic order.

        Returns:
            Sorted list of capability names.
        """
        return sorted(self._registry.keys())

    def unregister(self, name: str) -> None:
        """Remove a capability from the registry.

        Args:
            name: The capability name to remove.

        Raises:
            KeyError: If the name is not registered.
        """
        if name not in self._registry:
            raise KeyError(
                f"Capability '{name}' is not registered. "
                f"Cannot unregister a non-existent capability."
            )
        del self._registry[name]
