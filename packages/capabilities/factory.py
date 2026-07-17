"""Capability Factory.

Creates capability instances through the registry.

Architecture
------------

The factory delegates all lookup to the ``CapabilityRegistry``.  It never
hardcodes capability classes — the registry owns the mapping.

Public API
----------

.. code-block:: python

    from packages.capabilities.factory import CapabilityFactory
    from packages.capabilities.registry import CapabilityRegistry

    registry = CapabilityRegistry()
    registry.register("explain", ExplainCapability)

    factory = CapabilityFactory(registry)
    capability = factory.create("explain")
"""

from __future__ import annotations

from typing import Any

from packages.capabilities.registry import CapabilityRegistry


class CapabilityFactory:
    """Factory for creating capability instances.

    Responsibilities:
        - Create capability instances via the registry.
        - Validate registration before creation.
        - Raise deterministic exceptions for unregistered names.

    The factory never hardcodes capability classes.  All lookup goes
    through the registry.
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        """Initialize the factory with a registry.

        Args:
            registry: The capability registry to use for lookups.
        """
        self._registry = registry

    def create(self, name: str) -> Any:
        """Create a capability instance by name.

        Args:
            name: The capability name to create.

        Returns:
            An instance of the capability class.

        Raises:
            ValueError: If the capability name is not registered.
        """
        capability_class = self._registry.get(name)
        if capability_class is None:
            raise ValueError(
                f"Capability '{name}' is not registered. "
                f"Available capabilities: {self._registry.all()}"
            )
        return capability_class()
