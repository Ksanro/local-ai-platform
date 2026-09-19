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

Implemented capabilities
------------------------

- Explain
- Debug
- Refactor
- Implement Feature (dormant — exported for direct use, not wired into the
  live gateway pipeline)
- Generate Tests (dormant — exported for direct use, not wired into the live
  gateway pipeline)
- Review (dormant — exported for direct use, not wired into the live gateway
  pipeline; assembles review context, it does not author review findings)

Future capabilities
-------------------

Capabilities are additive: one class, one profile, one export. See
``docs/capabilities.md`` for the roster and the wiring rules.
"""

from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.debug import DebugCapability
from packages.capabilities.explain import ExplainCapability
from packages.capabilities.factory import CapabilityFactory
from packages.capabilities.generate_tests import GenerateTestsCapability
from packages.capabilities.implement_feature import ImplementFeatureCapability
from packages.capabilities.profiles import (
    ARCHITECTURE_REVIEW_PROFILE,
    DEBUG_PROFILE,
    EXPLAIN_PROFILE,
    GENERATE_TESTS_PROFILE,
    IMPLEMENT_PROFILE,
    REFACTOR_PROFILE,
    REVIEW_PROFILE,
    RetrievalProfile,
)
from packages.capabilities.refactor import RefactorCapability
from packages.capabilities.registry import CapabilityRegistry
from packages.capabilities.review import ReviewCapability

__all__ = [
    "Capability",
    "CapabilityFactory",
    "CapabilityRegistry",
    "DebugCapability",
    "ExplainCapability",
    "GenerateTestsCapability",
    "ImplementFeatureCapability",
    "PlannerIntent",
    "RefactorCapability",
    "ReviewCapability",
    "DEBUG_PROFILE",
    "EXPLAIN_PROFILE",
    "GENERATE_TESTS_PROFILE",
    "IMPLEMENT_PROFILE",
    "REFACTOR_PROFILE",
    "ARCHITECTURE_REVIEW_PROFILE",
    "REVIEW_PROFILE",
    "RetrievalProfile",
]
