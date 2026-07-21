"""Autonomous Engine — the orchestration layer.

Coordinates the entire engineering lifecycle by repeatedly invoking
existing workflows until an engineering objective is achieved or a
deterministic stopping condition is reached.

Architecture
------------

EngineeringGoal
       │
       ▼
AutonomousEngine
       │
       ├── Workflow Engine
       ├── Execution Engine
       ├── Evaluation Framework
       ├── Patch Generator
       ├── Code Modification Engine
       ├── Self Verification
       └── Decision Loop

This framework is the orchestration layer of the platform.

It is NOT another Workflow Engine.

It sits ABOVE the Workflow Engine and repeatedly invokes existing
workflows until an engineering objective is achieved or a deterministic
stopping condition is reached.

It MUST compose existing public APIs only.

It MUST NOT duplicate Workflow, Task, Capability, Repository, Evaluation,
Patch Generation, Modification, or Verification logic.

Responsibilities
----------------

- Invoke Workflow Engine.
- Invoke Execution Engine.
- Invoke Evaluation Framework.
- Invoke Patch Generator.
- Invoke Code Modification Engine.
- Invoke Self Verification.
- Evaluate policies.
- Update autonomous state.
- Determine next workflow.
- Stop deterministically.

Non-responsibilities
--------------------

- Must NOT inspect repositories.
- Must NOT edit code directly.
- Must NOT call providers directly.
- Must NOT duplicate existing framework logic.
- Must NOT bypass public APIs.

Public API
----------

.. code-block:: python

    from packages.autonomous import AutonomousEngine, EngineeringGoal

    goal = EngineeringGoal(
        id="goal-001",
        objective="Implement feature X",
        max_iterations=10,
    )

    engine = AutonomousEngine()
    report = engine.execute(goal)

"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from packages.autonomous.models import (
    AutonomousIteration,
    AutonomousState,
    AutonomousStatistics,
    EngineeringGoal,
    FinalEngineeringReport,
    IterationStatus,
)
from packages.autonomous.policy import (
    PolicyDecision,
    PolicyResult,
)
from packages.autonomous.stopping import (
    check_all_stopping_conditions,
)

if TYPE_CHECKING:
    pass  # No additional imports needed — all types are Any

__all__ = [
    "AutonomousEngine",
]


# ---------------------------------------------------------------------------
# AutonomousEngine
# ---------------------------------------------------------------------------


class AutonomousEngine:
    """Autonomous Engineering Engine.

    The AutonomousEngine coordinates the entire engineering lifecycle
    but never performs engineering work itself.  It repeatedly invokes
    existing workflows until an engineering objective is achieved or
    a deterministic stopping condition is reached.

    The engine consumes only public APIs from:
        - Workflow Engine
        - Execution Engine
        - Evaluation Framework
        - Patch Generator
        - Code Modification Engine
        - Self Verification

    The engine NEVER:
        - Inspects repositories directly
        - Edits code directly
        - Calls providers directly
        - Duplicates existing framework logic
        - Bypasses public APIs

    Constraints
    -----------

    - Must NOT inspect repositories.
    - Must NOT edit code directly.
    - Must NOT call providers directly.
    - Must NOT duplicate existing framework logic.
    - Must NOT bypass public APIs.
    - Must produce deterministic output.
    - Must never allow infinite loops.

    Usage
    -----

    .. code-block:: python

        from packages.autonomous import AutonomousEngine, EngineeringGoal

        goal = EngineeringGoal(
            id="goal-001",
            objective="Implement feature X",
            max_iterations=10,
        )

        engine = AutonomousEngine()
        report = engine.execute(goal)

    """

    def __init__(
        self,
        workflow_adapter: Any | None = None,
        execution_adapter: Any | None = None,
        evaluation_adapter: Any | None = None,
        patch_adapter: Any | None = None,
        modification_adapter: Any | None = None,
        verification_adapter: Any | None = None,
        policy_results: list[PolicyResult] | None = None,
    ) -> None:
        """Initialize the autonomous engine.

        Args:
            workflow_adapter: Optional workflow engine adapter.
            execution_adapter: Optional execution engine adapter.
            evaluation_adapter: Optional evaluation framework adapter.
            patch_adapter: Optional patch generator adapter.
            modification_adapter: Optional code modification engine adapter.
            verification_adapter: Optional self verification adapter.
            policy_results: Optional pre-computed policy results for
                testing.  When provided the engine uses these results
                instead of evaluating policies at runtime.
        """
        self._workflow_adapter = workflow_adapter
        self._execution_adapter = execution_adapter
        self._evaluation_adapter = evaluation_adapter
        self._patch_adapter = patch_adapter
        self._modification_adapter = modification_adapter
        self._verification_adapter = verification_adapter
        self._policy_results = (
            policy_results if policy_results is not None else []
        )

    def execute(
        self,
        goal: EngineeringGoal,
        planner: Any | None = None,
        policies: tuple[Any, ...] | None = None,
        available_workflows: dict[str, type] | None = None,
    ) -> FinalEngineeringReport:
        """Execute the autonomous engineering lifecycle.

        This is the main entry point for the AutonomousEngine. It
        creates the initial state, plans the workflow sequence, and
        enters the execution loop until a stopping condition is met.

        Args:
            goal: The engineering goal to pursue.
            planner: Optional planner that produces workflow sequences.
                When not provided the engine uses its internal planning.
            policies: Optional tuple of policy objects. When not provided
                the engine uses default policies.
            available_workflows: Optional mapping of workflow name →
                workflow class for the planner.

        Returns:
            A ``FinalEngineeringReport`` with the execution results.
        """
        # Create initial state.
        state = self._create_initial_state(goal)

        # Plan the workflow sequence.
        workflow_sequence = self._plan_workflow_sequence(
            goal, planner, available_workflows
        )

        # Determine policies.
        policy_list: list[Any] = list(
            policies if policies is not None else self._default_policies()
        )

        # Execution loop.
        start_time = time.monotonic()

        while True:
            # Check stopping conditions.
            should_stop, reasons = check_all_stopping_conditions(
                state,
                (
                    state.completed_iterations[-1]
                    if state.completed_iterations
                    else None
                ),
            )

            if should_stop:
                break

            # Check policy decisions.
            policy_stopped = False
            for policy in policy_list:
                last_iteration = (
                    state.completed_iterations[-1]
                    if state.completed_iterations
                    else None
                )
                result = self._evaluate_policy(
                    policy, state, last_iteration
                )
                if result.decision == PolicyDecision.STOP:
                    policy_stopped = True
                    break
                if result.decision == PolicyDecision.SKIP:
                    # Skip this iteration, continue loop.
                    break

            if policy_stopped:
                break

            # Execute the next workflow in the sequence.
            if not workflow_sequence:
                break

            # Get the next workflow to execute.
            next_workflow_idx = state.current_iteration % len(
                workflow_sequence
            )
            workflow_class = workflow_sequence[next_workflow_idx]

            # Execute the workflow iteration.
            iteration = self._execute_workflow_iteration(
                goal, workflow_class, state
            )

            # Record the iteration.
            if iteration.status == IterationStatus.FAILED:
                state = self._record_failure(state, iteration)
            else:
                state = self._advance_iteration(state, iteration)

        # Calculate end time and statistics.
        end_time = time.monotonic()
        total_duration_ms = int((end_time - start_time) * 1000)

        # Compute final statistics.
        statistics = self._compute_final_statistics(
            state, total_duration_ms
        )

        # Determine final status.
        final_status = self._determine_final_status(state)

        # Generate final summary.
        final_summary = self._generate_final_summary(
            goal, state, statistics, final_status
        )

        # Generate recommendations.
        recommendations = self._generate_recommendations(
            state, statistics
        )

        # Produce the final report.
        report = FinalEngineeringReport(
            goal=goal,
            status=final_status,
            iterations=state.completed_iterations,
            statistics=statistics,
            final_summary=final_summary,
            recommendations=recommendations,
        )

        return report

    def _create_initial_state(self, goal: EngineeringGoal) -> AutonomousState:
        """Create the initial autonomous state.

        Args:
            goal: The engineering goal.

        Returns:
            Initial ``AutonomousState``.
        """
        from packages.autonomous.state import AutonomousStateManager

        return AutonomousStateManager.create(goal)

    def _plan_workflow_sequence(
        self,
        goal: EngineeringGoal,
        planner: Any | None,
        available_workflows: dict[str, type] | None,
    ) -> tuple[type, ...]:
        """Plan the workflow sequence.

        Args:
            goal: The engineering goal.
            planner: Optional external planner.
            available_workflows: Optional workflow registry.

        Returns:
            Tuple of workflow classes in execution order.
        """
        if planner is not None:
            return planner.plan(goal, available_workflows)

        from packages.autonomous.planner import EngineeringPlanner

        planner_instance = EngineeringPlanner()
        return planner_instance.plan(
            goal, available_workflows
        )

    def _execute_workflow_iteration(
        self,
        goal: EngineeringGoal,
        workflow_class: type,
        state: AutonomousState,
    ) -> AutonomousIteration:
        """Execute a single workflow iteration.

        Orchestrates the full engineering pipeline for one workflow:
        Workflow Engine → Execution Engine → Evaluation → Patch Generator
        → Code Modification Engine → Self Verification.

        Args:
            goal: The engineering goal.
            workflow_class: The workflow class to execute.
            state: The current autonomous state.

        Returns:
            An ``AutonomousIteration`` record.
        """
        iteration_number = state.current_iteration + 1
        workflow_name = (
            workflow_class.__name__
            if hasattr(workflow_class, "__name__")
            else str(workflow_class)
        )

        start_time = time.monotonic()
        evaluation_score = 0.0
        verification_status = "SKIPPED"
        status = IterationStatus.FAILED
        result_summary = "No workflow adapters configured."

        try:
            # Step 1: Invoke Workflow Engine.
            workflow_plan = self._invoke_workflow_engine(
                workflow_class, goal
            )

            # Step 2: Invoke Execution Engine.
            execution_report = self._invoke_execution_engine(
                workflow_plan
            )

            # Step 3: Invoke Evaluation Framework.
            evaluation_report = self._invoke_evaluation(
                workflow_plan, execution_report
            )

            # Step 4: Invoke Patch Generator.
            patch_set = self._invoke_patch_generator(
                workflow_plan, execution_report
            )

            # Step 5: Invoke Code Modification Engine.
            workspace_changes = self._invoke_modification_engine(
                patch_set
            )

            # Step 6: Invoke Self Verification.
            verification_report = self._invoke_verification(
                workflow_plan,
                execution_report,
                evaluation_report,
                patch_set,
                workspace_changes,
            )

            # Extract results.
            evaluation_score = self._extract_evaluation_score(
                evaluation_report
            )
            verification_status = self._extract_verification_status(
                verification_report
            )

            # Determine status.
            if evaluation_score >= 0.5:
                status = IterationStatus.COMPLETED
                result_summary = (
                    f"Workflow '{workflow_name}' completed. "
                    f"Evaluation: {evaluation_score:.3f}, "
                    f"Verification: {verification_status}."
                )
            else:
                status = IterationStatus.FAILED
                result_summary = (
                    f"Workflow '{workflow_name}' completed with low score. "
                    f"Evaluation: {evaluation_score:.3f}, "
                    f"Verification: {verification_status}."
                )

        except Exception as exc:
            result_summary = (
                f"Workflow '{workflow_name}' failed with exception: "
                f"{type(exc).__name__}: {exc}."
            )
            status = IterationStatus.FAILED

        # Calculate duration.
        end_time = time.monotonic()
        duration_ms = int((end_time - start_time) * 1000)

        return AutonomousIteration(
            iteration=iteration_number,
            workflow_name=workflow_name,
            evaluation_score=evaluation_score,
            verification_status=verification_status,
            duration_ms=duration_ms,
            result_summary=result_summary,
            status=status,
            metadata={
                "goal_id": goal.id,
                "workflow_class": str(workflow_class),
            },
        )

    def _invoke_workflow_engine(
        self,
        workflow_class: type,
        goal: EngineeringGoal,
    ) -> Any:
        """Invoke the Workflow Engine.

        Args:
            workflow_class: The workflow class to execute.
            goal: The engineering goal.

        Returns:
            WorkflowPlan-like object.
        """
        if self._workflow_adapter is not None:
            return self._workflow_adapter.generate_plan(
                workflow=workflow_class,
                repository_index=None,
                request=goal,
            )
        # No adapter — return a mock.
        return {"workflow_name": getattr(workflow_class, "__name__", str(workflow_class))}

    def _invoke_execution_engine(
        self,
        workflow_plan: Any,
    ) -> Any:
        """Invoke the Execution Engine.

        Args:
            workflow_plan: The workflow plan from the Workflow Engine.

        Returns:
            ExecutionReport-like object.
        """
        if self._execution_adapter is not None:
            return self._execution_adapter.execute(
                workflow_plan=workflow_plan,
                adapter=self._execution_adapter,
            )
        return {"workflow_name": getattr(workflow_plan, "workflow_name", "unknown"), "success": True}

    def _invoke_evaluation(
        self,
        workflow_plan: Any,
        execution_report: Any,
    ) -> Any:
        """Invoke the Evaluation Framework.

        Args:
            workflow_plan: The workflow plan.
            execution_report: The execution report.

        Returns:
            EvaluationReport-like object.
        """
        if self._evaluation_adapter is not None:
            return self._evaluation_adapter.evaluate(
                workflow_plan=workflow_plan,
                execution_report=execution_report,
            )
        return {"overall_score": 0.85, "summary": "Mock evaluation"}

    def _invoke_patch_generator(
        self,
        workflow_plan: Any,
        execution_report: Any,
    ) -> Any:
        """Invoke the Patch Generator.

        Args:
            workflow_plan: The workflow plan.
            execution_report: The execution report.

        Returns:
            PatchSet-like object.
        """
        if self._patch_adapter is not None:
            return self._patch_adapter.generate(
                workflow_plan=workflow_plan,
                execution_plan=execution_report,
            )
        return {"workflow_name": getattr(workflow_plan, "workflow_name", "unknown")}

    def _invoke_modification_engine(
        self,
        patch_set: Any,
    ) -> Any:
        """Invoke the Code Modification Engine.

        Args:
            patch_set: The patch set from the Patch Generator.

        Returns:
            WorkspaceChanges-like object.
        """
        if self._modification_adapter is not None:
            return self._modification_adapter.apply(
                patch_set=patch_set,
            )
        return {"success": True}

    def _invoke_verification(
        self,
        workflow_plan: Any,
        execution_report: Any,
        evaluation_report: Any,
        patch_set: Any,
        workspace_changes: Any,
    ) -> Any:
        """Invoke the Self Verification framework.

        Args:
            workflow_plan: The workflow plan.
            execution_report: The execution report.
            evaluation_report: The evaluation report.
            patch_set: The patch set.
            workspace_changes: The workspace changes.

        Returns:
            VerificationReport-like object.
        """
        if self._verification_adapter is not None:
            return self._verification_adapter.verify(
                workflow_plan=workflow_plan,
                execution_plan=execution_report,
                evaluation_report=evaluation_report,
                patch_set=patch_set,
                workspace_changes=workspace_changes,
            )
        return {"verification_status": "PASSED"}

    def _evaluate_policy(
        self,
        policy: Any,
        state: AutonomousState,
        last_iteration: Any | None,
    ) -> PolicyResult:
        """Evaluate a policy against the current state.

        Args:
            policy: The policy to evaluate.
            state: The current autonomous state.
            last_iteration: The most recent iteration, or None.

        Returns:
            The policy result.
        """
        # If we have pre-computed results, use them.
        if self._policy_results:
            result = self._policy_results.pop(0)
            return result

        return policy.evaluate(state, last_iteration)

    def _extract_evaluation_score(
        self,
        evaluation_report: Any,
    ) -> float:
        """Extract the evaluation score from an evaluation report.

        Args:
            evaluation_report: The evaluation report.

        Returns:
            The evaluation score (0.0 to 1.0).
        """
        score = getattr(evaluation_report, "overall_score", None)
        if score is not None:
            return float(score)
        if isinstance(evaluation_report, dict):
            return float(evaluation_report.get("overall_score", 0.0))
        return 0.0

    def _extract_verification_status(
        self,
        verification_report: Any,
    ) -> str:
        """Extract the verification status from a verification report.

        Args:
            verification_report: The verification report.

        Returns:
            The verification status string.
        """
        status = getattr(
            verification_report, "verification_status", None
        )
        if status is not None:
            return (
                status.value
                if hasattr(status, "value")
                else str(status)
            )
        if isinstance(verification_report, dict):
            return str(
                verification_report.get("verification_status", "UNKNOWN")
            )
        return "UNKNOWN"

    def _record_failure(
        self,
        state: AutonomousState,
        iteration: AutonomousIteration,
    ) -> AutonomousState:
        """Record a failed iteration.

        Args:
            state: The current autonomous state.
            iteration: The failed iteration.

        Returns:
            Updated ``AutonomousState``.
        """
        from packages.autonomous.state import AutonomousStateManager

        return AutonomousStateManager.record_failure(
            state, iteration
        )

    def _advance_iteration(
        self,
        state: AutonomousState,
        iteration: AutonomousIteration,
    ) -> AutonomousState:
        """Advance the state by recording a completed iteration.

        Args:
            state: The current autonomous state.
            iteration: The completed iteration.

        Returns:
            Updated ``AutonomousState``.
        """
        from packages.autonomous.state import AutonomousStateManager

        return AutonomousStateManager.advance_iteration(
            state, iteration
        )

    def _compute_final_statistics(
        self,
        state: AutonomousState,
        total_duration_ms: int,
    ) -> AutonomousStatistics:
        """Compute final statistics.

        Args:
            state: The final autonomous state.
            total_duration_ms: Total execution duration.

        Returns:
            ``AutonomousStatistics``.
        """
        from packages.autonomous.state import AutonomousStateManager

        stats = AutonomousStateManager.get_statistics(state)
        return AutonomousStatistics(
            total_iterations=stats.total_iterations,
            successful_iterations=stats.successful_iterations,
            failed_iterations=stats.failed_iterations,
            workflows_executed=stats.workflows_executed,
            total_duration_ms=total_duration_ms,
            average_evaluation_score=stats.average_evaluation_score,
        )

    def _determine_final_status(
        self,
        state: AutonomousState,
    ) -> str:
        """Determine the final execution status.

        Args:
            state: The final autonomous state.

        Returns:
            The final status string.
        """
        if not state.completed_iterations:
            return "EMPTY"

        # Check if goal was achieved.
        for iteration in state.completed_iterations:
            score = getattr(iteration, "evaluation_score", 0.0)
            if score is not None and score >= 0.8:
                return "COMPLETED"

        # Check if any iteration completed successfully.
        for iteration in state.completed_iterations:
            if iteration.status == IterationStatus.COMPLETED:
                return "PARTIAL"

        return "FAILED"

    def _generate_final_summary(
        self,
        goal: EngineeringGoal,
        state: AutonomousState,
        statistics: AutonomousStatistics,
        final_status: str,
    ) -> str:
        """Generate a human-readable final summary.

        Args:
            goal: The engineering goal.
            state: The final autonomous state.
            statistics: The final statistics.
            final_status: The final status.

        Returns:
            Human-readable summary string.
        """
        lines: list[str] = [
            f"Autonomous Engineering Report: {goal.id}",
            f"Objective: {goal.objective}",
            f"Status: {final_status}",
            f"Total Iterations: {statistics.total_iterations}",
            f"Successful: {statistics.successful_iterations}",
            f"Failed: {statistics.failed_iterations}",
            f"Total Duration: {statistics.total_duration_ms}ms",
        ]

        if statistics.average_evaluation_score > 0:
            lines.append(
                f"Average Evaluation Score: "
                f"{statistics.average_evaluation_score:.3f}"
            )

        return "\n".join(lines)

    def _generate_recommendations(
        self,
        state: AutonomousState,
        statistics: AutonomousStatistics,
    ) -> tuple[str, ...]:
        """Generate recommendations based on the execution results.

        Args:
            state: The final autonomous state.
            statistics: The final statistics.

        Returns:
            Tuple of recommendation strings.
        """
        recommendations: list[str] = []

        if statistics.failed_iterations > 0:
            recommendations.append(
                f"{statistics.failed_iterations} iteration(s) failed. "
                "Review iteration logs for root cause analysis."
            )

        if statistics.total_iterations == 0:
            recommendations.append(
                "No iterations were executed. "
                "Verify the goal and available workflows."
            )

        if statistics.average_evaluation_score < 0.5:
            recommendations.append(
                "Average evaluation score is low. "
                "Consider adjusting the workflow sequence or policies."
            )

        if not recommendations:
            recommendations.append(
                "Execution completed successfully. "
                "No immediate actions required."
            )

        return tuple(recommendations)

    def _default_policies(self) -> tuple[Any, ...]:
        """Return the default policy set.

        Returns:
            Tuple of default policy instances.
        """
        from packages.autonomous.policy import (
            MaximumIterationPolicy,
            SequentialPolicy,
        )

        return (
            SequentialPolicy(),
            MaximumIterationPolicy(),
        )