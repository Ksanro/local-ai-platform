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

    from packages.capabilities.explain import ExplainCapability

    engine = ExplainCapability()
    result = engine.execute(query="Explain ProviderFactory", repository_index=index)

Future capabilities
-------------------

- Debug
- Implement Feature
- Refactor
- Review
- Generate Tests
"""

from packages.capabilities.explain import ExplainCapability

__all__ = ["ExplainCapability"]
