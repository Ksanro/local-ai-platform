"""Pipeline stages.

Contains concrete stage implementations. The built-in stages are:

- ``ProviderStage`` — resolves a provider and calls its ``chat()`` method.
- ``RepositoryContextStage`` — assembles repository context before
  provider execution.

Future stages will include authentication, memory, prompt optimization,
and metrics.
"""

from __future__ import annotations

from packages.pipeline.stages.planning_stage import PlanningStage
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.pipeline.stages.stages import ProviderStage

__all__ = ["PlanningStage", "ProviderStage", "RepositoryContextStage"]
