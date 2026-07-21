"""Pipeline stages.

Contains concrete stage implementations. The built-in stages are:

**Existing stages:**

- ``PlanningStage`` — runs context planning (intent detection, rule matching).
- ``RepositoryContextStage`` — assembles repository context before
  provider execution.
- ``ProviderStage`` — resolves a provider and calls its ``chat()`` method.

**Integration Milestone v1 stages:**

- ``WorkflowStage`` — selects and executes a workflow, producing a
  ``WorkflowPlan``.
- ``ExecutionStage`` — executes a ``WorkflowPlan`` through the
  ``ExecutionEngine``, producing an ``ExecutionReport``.
- ``VerificationStage`` — performs self-verification after execution,
  producing a ``VerificationReport``.
- ``EvaluationStage`` — evaluates execution results after verification,
  producing an ``EvaluationReport``.

**Model routing stages:**

- ``ModelResolutionStage`` — resolves model → provider before context
  assembly, because ``context_window`` is needed for token-budgeting.

**Execution pipeline order:**

    Request
      → ModelResolutionStage
      → PlanningStage
      → RepositoryContextStage
      → WorkflowStage
      → ExecutionStage
      → VerificationStage
      → EvaluationStage
      → ProviderStage

Future stages will include authentication, memory, prompt optimization,
and metrics.
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
    # Existing stages
    "PlanningStage",
    "ProviderStage",
    "RepositoryContextStage",
    # Integration Milestone v1 stages
    "WorkflowStage",
    "ExecutionStage",
    "VerificationStage",
    "EvaluationStage",
    # Model routing
    "ModelResolutionStage",
]
