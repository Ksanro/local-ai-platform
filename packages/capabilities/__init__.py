"""Capabilities package.

Orchestrates platform components to solve developer tasks.

Architecture
------------

Capabilities are user-facing abstractions that compose existing platform
components (planner, repository, context builder, serializer) into
coherent workflows.

Each capability is orchestration only — no duplicated logic.

Public API
----------

.. code-block:: python

    from packages.capabilities.factory import CapabilityFactory
    from packages.capabilities.registry import CapabilityRegistry
    from packages.capabilities.explain import ExplainCapability

    registry = CapabilityRegistry()
    registry.register("explain", ExplainCapability)

    factory = CapabilityFactory(registry)
    capability = factory.create("explain")
    result = capability.execute(
        query="Explain ProviderFactory",
        repository_index=index,
    )

Capability Framework v1
-----------------------

- **Capability** – ABC that defines the interface for all capabilities.
- **CapabilityRegistry** – manages registration, lookup, and discovery.
- **CapabilityFactory** – creates capability instances through the registry.
- **PlannerIntent** – intent enum mapping capabilities to planner modes.

Future capabilities
-------------------

- Debug
- Implement Feature
- Refactor
- Review
- Generate Tests
"""

from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.debug import DebugCapability
from packages.capabilities.explain import ExplainCapability
from packages.capabilities.factory import CapabilityFactory
from packages.capabilities.registry import CapabilityRegistry

__all__ = [
    "Capability",
    "CapabilityFactory",
    "CapabilityRegistry",
    "DebugCapability",
    "ExplainCapability",
    "PlannerIntent",
]
