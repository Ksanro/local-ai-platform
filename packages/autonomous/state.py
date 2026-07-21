"""Autonomous state management.

Provides deterministic state creation, snapshots, and iteration advancement
for the Autonomous Engineering Framework.

Architecture
------------

State Creation --> AutonomousStateManager --> AutonomousState
State Snapshot --> Immutable View
State Advance --> New State with Updated Iteration

Constraints
-----------

- No global mutable state.
- No singleton pattern.
- Immutable state objects.
- Deterministic state transitions.

Public API
----------

.. code-block:: python

    from packages.autonomous.state import AutonomousStateManager

    state = AutonomousStateManager.create(goal)
    snapshot = AutonomousStateManager.snapshot(state)
    new_state = AutonomousStateManager.advance_iteration(state, iteration)

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from packages.autonomous.models import (
    AutonomousIteration,
    AutonomousState,
    AutonomousStatistics,
    EngineeringGoal,
)

if TYPE_CHECKING:
    pass  # No additional imports needed

__all__ = [
    "AutonomousStateManager",
]


# ---------------------------------------------------------------------------
# AutonomousStateManager
# ---------------------------------------------------------------------------


class AutonomousStateManager:
    """Deterministic autonomous state manager.

    Provides state creation, snapshots, and iteration advancement.
    All state objects are immutable — operations return new instances.

    The manager is stateless and deterministic — given the same inputs
    it always produces the same outputs.

    Constraints
    -----------

    - Must NOT modify existing state objects.
    - Must NOT use global mutable state.
    - Must NOT use singleton pattern.
    - Must produce deterministic output.
    - Must consume only public API objects.

    Usage
    -----

    .. code-block:: python

        from packages.autonomous.state import AutonomousStateManager
        from packages.autonomous.models import EngineeringGoal

        goal = EngineeringGoal(id="goal-001", objective="Test")
        state = AutonomousStateManager.create(goal)
        new_state = AutonomousStateManager.advance_iteration(state, iteration)

    """

    @staticmethod
    def create(
        goal: EngineeringGoal,
        metadata: dict[str, Any] | None = None,
    ) -> AutonomousState:
        """Create a new autonomous state for the given goal.

        This is the main entry point for state creation. It produces
        a fresh ``AutonomousState`` with iteration zero and empty history.

        Args:
            goal: The engineering goal to create state for.
            metadata: Optional additional metadata.

        Returns:
            A new ``AutonomousState`` with iteration zero.
        """
        meta: dict[str, Any] = metadata if metadata is not None else {}

        return AutonomousState(
            current_iteration=0,
            completed_workflows=(),
            completed_iterations=(),
            current_goal=goal,
            metadata=meta,
        )

    @staticmethod
    def snapshot(state: AutonomousState) -> dict[str, Any]:
        """Create an immutable snapshot of the current state.

        Returns a dictionary containing all state fields. This is a
        read-only view — the original state is never modified.

        Args:
            state: The autonomous state to snapshot.

        Returns:
            Dictionary with all state fields.
        """
        return {
            "current_iteration": state.current_iteration,
            "completed_workflows": state.completed_workflows,
            "completed_iterations": state.completed_iterations,
            "current_goal": state.current_goal,
            "metadata": dict(state.metadata),
        }

    @staticmethod
    def advance_iteration(
        state: AutonomousState,
        iteration: AutonomousIteration,
    ) -> AutonomousState:
        """Advance the state by recording a completed iteration.

        Returns a new ``AutonomousState`` with the iteration number
        incremented and the iteration record appended to history.

        Args:
            state: The current autonomous state.
            iteration: The completed iteration record.

        Returns:
            A new ``AutonomousState`` with updated iteration count
            and appended iteration record.
        """
        new_iteration = state.current_iteration + 1
        new_iterations = state.completed_iterations + (iteration,)
        new_workflows = state.completed_workflows + (
            iteration.workflow_name,
        )

        return AutonomousState(
            current_iteration=new_iteration,
            completed_workflows=new_workflows,
            completed_iterations=new_iterations,
            current_goal=state.current_goal,
            metadata=dict(state.metadata),
        )

    @staticmethod
    def record_failure(
        state: AutonomousState,
        iteration: AutonomousIteration,
    ) -> AutonomousState:
        """Record a failed iteration in the state.

        Returns a new ``AutonomousState`` with the failed iteration
        appended to history.

        Args:
            state: The current autonomous state.
            iteration: The failed iteration record.

        Returns:
            A new ``AutonomousState`` with the failed iteration recorded.
        """
        new_iterations = state.completed_iterations + (iteration,)
        new_workflows = state.completed_workflows + (
            iteration.workflow_name,
        )

        return AutonomousState(
            current_iteration=state.current_iteration,
            completed_workflows=new_workflows,
            completed_iterations=new_iterations,
            current_goal=state.current_goal,
            metadata=dict(state.metadata),
        )

    @staticmethod
    def get_statistics(state: AutonomousState) -> AutonomousStatistics:
        """Compute statistics from the current state.

        Args:
            state: The autonomous state.

        Returns:
            ``AutonomousStatistics`` computed from the state.
        """
        total = len(state.completed_iterations)
        successful = 0
        failed = 0
        total_duration = 0
        scores: list[float] = []

        for iteration in state.completed_iterations:
            status = getattr(iteration, "status", None)
            if status is not None:
                status_str = (
                    status.value
                    if hasattr(status, "value")
                    else str(status)
                )
                if status_str == "COMPLETED":
                    successful += 1
                elif status_str == "FAILED":
                    failed += 1

            duration = getattr(iteration, "duration_ms", 0)
            if duration is not None:
                total_duration += duration

            score = getattr(iteration, "evaluation_score", 0.0)
            if score is not None:
                scores.append(float(score))

        avg_score = 0.0
        if scores:
            avg_score = sum(scores) / len(scores)

        return AutonomousStatistics(
            total_iterations=total,
            successful_iterations=successful,
            failed_iterations=failed,
            workflows_executed=len(state.completed_workflows),
            total_duration_ms=total_duration,
            average_evaluation_score=avg_score,
        )