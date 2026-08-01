"""Pipeline stages.

Contains concrete stage implementations.

Live gateway stages registered by ``apps.gateway.main``:

- ``ModelResolutionStage`` - resolves model and provider before context
  assembly, because ``context_window`` is needed for token budgeting.
- ``PlanningStage`` - runs context planning and intent detection.
- ``RepositoryContextStage`` - assembles repository context before provider
  execution.
- ``ProviderStage`` - resolves a provider and calls its ``chat()`` method.

Dormant/future stages:

- ``WorkflowStage`` - selects and executes a workflow, producing a
  ``WorkflowPlan``.
- ``ExecutionStage`` - executes a ``WorkflowPlan`` through the
  ``ExecutionEngine``, producing an ``ExecutionReport``.
- ``VerificationStage`` - performs self-verification after execution,
  producing a ``VerificationReport``.
- ``EvaluationStage`` - evaluates execution results after verification,
  producing an ``EvaluationReport``.

Live gateway execution order:

    Request
      -> ModelResolutionStage
      -> PlanningStage
      -> RepositoryContextStage
      -> ProviderStage

The dormant stages remain importable for tests and future work, but they are
not part of the live gateway path until explicitly registered.
"""

from __future__ import annotations

from packages.pipeline.stages.evaluation_stage import EvaluationStage
from packages.pipeline.stages.execution_stage import ExecutionStage
from packages.pipeline.stages.planning_stage import PlanningStage
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.pipeline.stages.stages import ProviderStage
from packages.pipeline.stages.verification_stage import VerificationStage
from packages.pipeline.stages.workflow_stage import WorkflowStage


# Lazy import ModelResolutionStage to avoid circular imports at module load.
# It is registered in lifespan after the router is built.
def __getattr__(name: str):
    """Lazy-load ModelResolutionStage to avoid circular imports."""
    if name == "ModelResolutionStage":
        from packages.pipeline.stages.model_resolution import (
            ModelResolutionStage as _ModelResolutionStage,
        )

        return _ModelResolutionStage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Live gateway stages
    "ModelResolutionStage",
    "PlanningStage",
    "ProviderStage",
    "RepositoryContextStage",
    # Dormant/future stages
    "WorkflowStage",
    "ExecutionStage",
    "VerificationStage",
    "EvaluationStage",
]
