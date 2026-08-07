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

from importlib import import_module

from packages.pipeline.stages.planning_stage import PlanningStage
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.pipeline.stages.stages import ProviderStage

_LAZY_STAGE_EXPORTS = {
    "ModelResolutionStage": (
        "packages.pipeline.stages.model_resolution",
        "ModelResolutionStage",
    ),
    "WorkflowStage": ("packages.pipeline.stages.workflow_stage", "WorkflowStage"),
    "ExecutionStage": ("packages.pipeline.stages.execution_stage", "ExecutionStage"),
    "VerificationStage": (
        "packages.pipeline.stages.verification_stage",
        "VerificationStage",
    ),
    "EvaluationStage": ("packages.pipeline.stages.evaluation_stage", "EvaluationStage"),
}


# Lazy import stages that either have circular dependencies or belong to
# dormant/future workflow stacks. Live gateway startup imports only the active
# stages eagerly above.
def __getattr__(name: str) -> object:
    """Lazy-load stage exports that are not eagerly imported."""
    export = _LAZY_STAGE_EXPORTS.get(name)
    if export is not None:
        module_name, attribute = export
        return getattr(import_module(module_name), attribute)
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
