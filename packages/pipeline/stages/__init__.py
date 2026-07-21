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

**Execution pipeline order:**

    Request
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
]
