"""Execution Engine.

Orchestrates the execution of immutable WorkflowPlan objects through
ExecutionAdapters.  The engine is responsible only for orchestration.

Architecture
------------

WorkflowPlan  -->  ExecutionEngine  -->  ExecutionAdapter  -->  ExecutionReport
       |                    |
       |                    v
       |             ExecutionSession (internal)
       |                    |
       |                    v
       |             ExecutionStepResult (collected)
       |                    |
       |                    v
       |             ExecutionReport (output)

Responsibilities
----------------

- Validate WorkflowPlan.
- Create ExecutionSession.
- Execute WorkflowSteps sequentially.
- Collect ExecutionStepResults.
- Stop on first failure.
- Produce immutable ExecutionReport.

Non-responsibilities
--------------------

- No retries.
- No scheduling.
- No parallelism.
- No checkpoints.
- No recovery.
- No repository inspection.
- No AST parsing.
- No ranking.
- No context building.
- No invocation of planners.

Version 1 is intentionally simple.

Public API
----------

.. code-block:: python

    from packages.execution.engine import ExecutionEngine
    from packages.execution.adapter import ProviderExecutionAdapter
    from packages.workflows.models import WorkflowPlan

    adapter = ProviderExecutionAdapter()
    report = ExecutionEngine.execute(workflow_plan, adapter)

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.execution.runtime_models import (
    ExecutionReport,
    ExecutionStatus,
    ExecutionStepResult,
)

if TYPE_CHECKING:
    from packages.execution.adapter import ExecutionAdapter  # noqa: F401
    from packages.tasks.models import TaskPlan  # noqa: F401
    from packages.workflows.models import WorkflowPlan, WorkflowStep  # noqa: F401

__all__ = [
    "ExecutionEngine",
]


# ---------------------------------------------------------------------------
# ExecutionEngine
# ---------------------------------------------------------------------------


class ExecutionEngine:
    """Orchestrates execution of WorkflowPlan through ExecutionAdapter.

    ExecutionEngine consumes only public interfaces.  It never knows
    which implementation is behind the adapter.

    The engine validates the WorkflowPlan, creates an ExecutionSession,
    executes WorkflowSteps sequentially, collects ExecutionStepResults,
    stops on first failure, and produces an immutable ExecutionReport.

    Constraints
    -----------

    - Must NOT inspect repositories.
    - Must NOT parse AST.
    - Must NOT rank symbols.
    - Must NOT build context.
    - Must NOT invoke planners.
    - Must NOT modify WorkflowPlan.
    - Must NOT modify TaskPlan.
    - Must NOT know provider implementations.
    - Must consume only public interfaces.

    Usage
    -----

    .. code-block:: python

        from packages.execution.engine import ExecutionEngine
        from packages.execution.adapter import ProviderExecutionAdapter

        adapter = ProviderExecutionAdapter()
        report = ExecutionEngine.execute(workflow_plan, adapter)
    """

    @staticmethod
    def execute(
        workflow_plan: WorkflowPlan,
        adapter: ExecutionAdapter,
    ) -> ExecutionReport:
        """Execute a WorkflowPlan using the given ExecutionAdapter.

        This is the main entry point for the ExecutionEngine.  It
        validates the WorkflowPlan, creates an ExecutionSession,
        executes each WorkflowStep sequentially, collects results,
        and returns an immutable ExecutionReport.

        Execution is sequential — one step at a time.
        On first failure, execution stops immediately.

        Args:
            workflow_plan: The immutable WorkflowPlan to execute.
            adapter: The ExecutionAdapter to use for step execution.

        Returns:
            An immutable ExecutionReport with execution results.

        Raises:
            ValueError: If workflow_plan is invalid (empty steps).
            Exception: If an adapter raises an exception during
                execution, it propagates to the caller.
        """
        # Validate WorkflowPlan
        ExecutionEngine._validate_workflow_plan(workflow_plan)

        # Execute steps sequentially
        step_results: list[ExecutionStepResult] = []
        execution_status = ExecutionStatus.COMPLETED
        failures: list[str] = []

        for workflow_step in workflow_plan.workflow_steps:
            # Find the corresponding task plan
            task_plan = ExecutionEngine._find_task_plan(
                workflow_plan,
                workflow_step,
            )

            if task_plan is None:
                # No task plan for this step — skip
                continue

            # Execute the step
            step_result = adapter.execute_step(workflow_step, task_plan)

            # Track failures
            if step_result.status == ExecutionStatus.FAILED:
                execution_status = ExecutionStatus.FAILED
                failures.append(
                    f"Step '{workflow_step.step_id}' failed: "
                    f"{step_result.output_summary}"
                )
                step_results.append(step_result)
                break  # Stop on first failure

            step_results.append(step_result)

        # Calculate total duration
        total_duration_ms = 0
        for result in step_results:
            total_duration_ms += result.duration_ms

        # Determine success
        success = execution_status == ExecutionStatus.COMPLETED

        report = ExecutionReport(
            workflow_name=workflow_plan.workflow_name,
            execution_status=execution_status,
            total_duration_ms=total_duration_ms,
            step_results=tuple(step_results),
            adapter_name=adapter.name,
            success=success,
            failures=tuple(failures),
        )

        return report

    @staticmethod
    def _validate_workflow_plan(workflow_plan: WorkflowPlan) -> None:
        """Validate a WorkflowPlan before execution.

        Args:
            workflow_plan: The WorkflowPlan to validate.

        Raises:
            ValueError: If the plan is invalid.
        """
        if not workflow_plan.workflow_name:
            raise ValueError("WorkflowPlan must have a non-empty workflow_name")

        if not workflow_plan.workflow_steps:
            raise ValueError(
                f"WorkflowPlan '{workflow_plan.workflow_name}' has no workflow steps"
            )

    @staticmethod
    def _find_task_plan(
        workflow_plan: WorkflowPlan,
        workflow_step: WorkflowStep,
    ) -> TaskPlan | None:
        """Find the TaskPlan corresponding to a workflow step.

        Args:
            workflow_plan: The workflow plan.
            workflow_step: The workflow step to find a task plan for.

        Returns:
            The matching TaskPlan or None.
        """
        for task_plan in workflow_plan.task_plans:
            if task_plan.task_name == workflow_step.task_name:
                return task_plan  # type: ignore[no-any-return]

        return None
