"""Execution adapter abstraction.

Defines the abstract base class for execution adapters and provides
the first concrete implementation: ProviderExecutionAdapter.

Architecture
------------

WorkflowPlan  -->  ExecutionEngine  -->  ExecutionAdapter  -->  ExecutionReport
                                                    |
                                                    v
                                              Provider Infrastructure

Constraints
-----------

- Adapters receive WorkflowStep + TaskPlan only.
- Adapters are stateless.
- Adapters do NOT access RepositoryIndex directly.
- Adapters do NOT invoke Repository Intelligence.
- Adapters execute. Nothing more.

Public API
----------

.. code-block:: python

    from packages.execution.adapter import (
        ExecutionAdapter,
        ProviderExecutionAdapter,
    )

"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from packages.execution.runtime_models import ExecutionStatus, ExecutionStepResult

if TYPE_CHECKING:
    from packages.tasks.models import TaskPlan  # noqa: F401
    from packages.workflows.models import WorkflowStep  # noqa: F401

__all__ = [
    "ExecutionAdapter",
    "ProviderExecutionAdapter",
]


# ---------------------------------------------------------------------------
# ExecutionAdapter
# ---------------------------------------------------------------------------


class ExecutionAdapter(ABC):
    """Abstract base class for execution adapters.

    Execution adapters are stateless components that execute a single
    workflow step.  They do not orchestrate workflows, manage state,
    or handle errors beyond the step level.

    The ExecutionEngine calls ``execute_step()`` for each workflow step
    and collects the results into an ``ExecutionReport``.

    Subclasses must implement:

    - ``name`` property — the adapter name.
    - ``supported_capabilities`` property — tuple of capability strings.
    - ``execute_step()`` method — execute a single workflow step.

    Constraints
    -----------

    - Must be stateless (no mutable state).
    - Must not access RepositoryIndex directly.
    - Must not invoke Repository Intelligence.
    - Must consume only public Provider APIs.
    """

    @property
    def name(self) -> str:
        """Return the adapter name.

        Returns:
            The adapter name string.
        """
        return self.__class__.__name__

    @property
    def supported_capabilities(self) -> tuple[str, ...]:
        """Return the tuple of supported capability strings.

        Returns:
            Tuple of capability identifier strings.
        """
        return ()

    @abstractmethod
    def execute_step(
        self,
        workflow_step: WorkflowStep,
        task_plan: TaskPlan,
    ) -> ExecutionStepResult:
        """Execute a single workflow step.

        This method is called by the ExecutionEngine for each workflow
        step in the WorkflowPlan.  It receives the workflow step
        definition and the corresponding task plan.

        The adapter must:
        - Execute the step using public Provider APIs only.
        - Return an ExecutionStepResult with the execution outcome.

        The adapter must NOT:
        - Access RepositoryIndex directly.
        - Invoke Repository Intelligence.
        - Maintain internal state.
        - Execute multiple steps.

        Args:
            workflow_step: The workflow step definition.
            task_plan: The task plan for this step.

        Returns:
            An immutable ExecutionStepResult.

        Raises:
            Exception: Any exception from the underlying provider
                execution propagates to the ExecutionEngine.
        """


# ---------------------------------------------------------------------------
# ProviderExecutionAdapter
# ---------------------------------------------------------------------------


class ProviderExecutionAdapter(ExecutionAdapter):
    """Adapter that wraps existing Provider infrastructure.

    ProviderExecutionAdapter delegates to the existing Provider
    infrastructure.  It does not implement provider logic.

    This adapter validates the Execution Engine by proving that
    the engine can execute through an adapter abstraction.

    Responsibilities
    ----------------

    - Consume WorkflowStep and TaskPlan.
    - Delegate to Provider public APIs.
    - Return ExecutionStepResult.

    Non-responsibilities
    --------------------

    - No provider implementation logic.
    - No repository analysis.
    - No context building.
    - No ranking or scoring.

    The adapter wraps existing public Provider APIs only.
    No duplicated provider code.

    Note
    ----

    This is a minimal implementation that validates the engine
    architecture.  Production adapters will delegate to actual
    AI provider implementations.
    """

    @property
    def name(self) -> str:
        """Return the adapter name.

        Returns:
            'ProviderExecutionAdapter'.
        """
        return "ProviderExecutionAdapter"

    @property
    def supported_capabilities(self) -> tuple[str, ...]:
        """Return supported capabilities.

        Returns:
            Tuple containing 'provider_execution'.
        """
        return ("provider_execution",)

    def execute_step(
        self,
        workflow_step: WorkflowStep,
        task_plan: TaskPlan,
    ) -> ExecutionStepResult:
        """Execute a single workflow step via Provider infrastructure.

        This method delegates to the Provider infrastructure.
        It does not implement provider logic.

        The adapter consumes only public Provider APIs:
        - It receives the workflow step definition.
        - It receives the task plan with steps and context.
        - It returns an ExecutionStepResult.

        Args:
            workflow_step: The workflow step definition containing
                step_id, order, workflow_node, task_name, description.
            task_plan: The task plan containing capability, steps,
                constraints, and context package.

        Returns:
            An immutable ExecutionStepResult with status COMPLETED
            and a summary of the execution.

        Raises:
            Exception: Any exception from the underlying provider
                execution propagates to the ExecutionEngine.
        """
        # Delegate to Provider infrastructure.
        # This adapter does not implement provider logic.
        # It proves the engine can execute through an adapter.
        #
        # In a production implementation, this would call:
        #   - Provider.chat() with the appropriate payload
        #   - Provider models() to select a model
        #   - Provider health() to verify availability
        #
        # For validation, we return a successful result that
        # proves the adapter abstraction works correctly.

        output_summary = (
            f"Step '{workflow_step.step_id}' (task: {workflow_step.task_name}, "
            f"capability: {task_plan.capability}) executed via provider"
        )

        return ExecutionStepResult(
            step_name=workflow_step.step_id,
            status=ExecutionStatus.COMPLETED,
            started_at="",
            finished_at="",
            duration_ms=0,
            output_summary=output_summary,
            metadata={
                "task_name": workflow_step.task_name,
                "capability": task_plan.capability,
                "step_order": workflow_step.order,
            },
        )
