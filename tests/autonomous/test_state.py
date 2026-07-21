"""Tests for autonomous state management.

Tests cover:
- State creation
- State snapshots
- Iteration advancement
- Failure recording
- Statistics computation
"""

from __future__ import annotations

import pytest

from packages.autonomous.models import (
    AutonomousIteration,
    AutonomousState,
    AutonomousStatistics,
    EngineeringGoal,
    IterationStatus,
)
from packages.autonomous.state import AutonomousStateManager


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _make_goal(
    max_iterations: int = 10,
) -> EngineeringGoal:
    return EngineeringGoal(
        id="goal-001",
        objective="Test",
        max_iterations=max_iterations,
    )


def _make_iteration(
    iteration: int = 1,
    status: IterationStatus = IterationStatus.COMPLETED,
    workflow_name: str = "test-workflow",
    evaluation_score: float = 0.85,
    verification_status: str = "PASSED",
) -> AutonomousIteration:
    return AutonomousIteration(
        iteration=iteration,
        workflow_name=workflow_name,
        evaluation_score=evaluation_score,
        verification_status=verification_status,
        duration_ms=1000,
        result_summary="Test",
        status=status,
    )


# ---------------------------------------------------------------------------
# AutonomousStateManager
# ---------------------------------------------------------------------------


class TestCreate:
    """Tests for state creation."""

    def test_create_basic(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)

        assert state.current_iteration == 0
        assert state.completed_workflows == ()
        assert state.completed_iterations == ()
        assert state.current_goal == goal
        assert state.metadata == {}

    def test_create_with_metadata(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(
            goal, metadata={"key": "value"}
        )

        assert state.metadata == {"key": "value"}

    def test_create_preserves_goal(self) -> None:
        goal = _make_goal(max_iterations=5)
        state = AutonomousStateManager.create(goal)

        assert state.current_goal.max_iterations == 5
        assert state.current_goal.id == "goal-001"

    def test_create_returns_new_instance(self) -> None:
        goal = _make_goal()
        state1 = AutonomousStateManager.create(goal)
        state2 = AutonomousStateManager.create(goal)

        assert state1.current_iteration == state2.current_iteration
        assert state1 is not state2


class TestSnapshot:
    """Tests for state snapshots."""

    def test_snapshot_basic(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)
        snapshot = AutonomousStateManager.snapshot(state)

        assert snapshot["current_iteration"] == 0
        assert snapshot["completed_workflows"] == ()
        assert snapshot["completed_iterations"] == ()
        assert snapshot["current_goal"] == goal
        assert snapshot["metadata"] == {}

    def test_snapshot_with_iterations(self) -> None:
        goal = _make_goal()
        iteration = _make_iteration()
        state = AutonomousState(
            current_iteration=1,
            completed_workflows=("test-workflow",),
            completed_iterations=(iteration,),
            current_goal=goal,
        )
        snapshot = AutonomousStateManager.snapshot(state)

        assert snapshot["current_iteration"] == 1
        assert snapshot["completed_workflows"] == ("test-workflow",)
        assert snapshot["completed_iterations"] == (iteration,)

    def test_snapshot_is_copy(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)
        state.metadata["key"] = "value"
        snapshot = AutonomousStateManager.snapshot(state)

        # Modify snapshot metadata
        snapshot["metadata"]["new_key"] = "new_value"

        # Original state should not be affected
        assert "new_key" not in state.metadata


class TestAdvanceIteration:
    """Tests for iteration advancement."""

    def test_advance_basic(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)
        iteration = _make_iteration()

        new_state = AutonomousStateManager.advance_iteration(
            state, iteration
        )

        assert new_state.current_iteration == 1
        assert new_state.completed_iterations == (iteration,)
        assert new_state.completed_workflows == ("test-workflow",)
        # Original state unchanged
        assert state.current_iteration == 0

    def test_advance_multiple(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)

        iter1 = _make_iteration(iteration=1, workflow_name="workflow-1")
        iter2 = _make_iteration(iteration=2, workflow_name="workflow-2")

        state1 = AutonomousStateManager.advance_iteration(state, iter1)
        state2 = AutonomousStateManager.advance_iteration(state1, iter2)

        assert state2.current_iteration == 2
        assert len(state2.completed_iterations) == 2
        assert len(state2.completed_workflows) == 2
        assert state2.completed_workflows == ("workflow-1", "workflow-2")

    def test_advance_preserves_goal(self) -> None:
        goal = _make_goal(max_iterations=5)
        state = AutonomousStateManager.create(goal)
        iteration = _make_iteration()

        new_state = AutonomousStateManager.advance_iteration(
            state, iteration
        )

        assert new_state.current_goal.max_iterations == 5
        assert new_state.current_goal.id == "goal-001"

    def test_advance_returns_new_instance(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)
        iteration = _make_iteration()

        new_state = AutonomousStateManager.advance_iteration(
            state, iteration
        )

        assert new_state is not state


class TestRecordFailure:
    """Tests for failure recording."""

    def test_record_failure_basic(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)
        iteration = _make_iteration(status=IterationStatus.FAILED)

        new_state = AutonomousStateManager.record_failure(
            state, iteration
        )

        # Iteration count should NOT increase on failure
        assert new_state.current_iteration == 0
        assert new_state.completed_iterations == (iteration,)
        assert new_state.completed_workflows == ("test-workflow",)

    def test_record_failure_multiple(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)

        iter1 = _make_iteration(
            iteration=1,
            status=IterationStatus.FAILED,
            workflow_name="workflow-1",
        )
        iter2 = _make_iteration(
            iteration=2,
            status=IterationStatus.FAILED,
            workflow_name="workflow-2",
        )

        state1 = AutonomousStateManager.record_failure(state, iter1)
        state2 = AutonomousStateManager.record_failure(state1, iter2)

        assert state2.current_iteration == 0
        assert len(state2.completed_iterations) == 2
        assert state2.completed_workflows == ("workflow-1", "workflow-2")


class TestGetStatistics:
    """Tests for statistics computation."""

    def test_empty_state(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)

        stats = AutonomousStateManager.get_statistics(state)

        assert stats.total_iterations == 0
        assert stats.successful_iterations == 0
        assert stats.failed_iterations == 0
        assert stats.workflows_executed == 0
        assert stats.average_evaluation_score == 0.0

    def test_single_success(self) -> None:
        goal = _make_goal()
        iteration = _make_iteration(
            status=IterationStatus.COMPLETED,
            evaluation_score=0.85,
        )
        state = AutonomousState(
            current_iteration=1,
            completed_iterations=(iteration,),
            current_goal=goal,
        )

        stats = AutonomousStateManager.get_statistics(state)

        assert stats.total_iterations == 1
        assert stats.successful_iterations == 1
        assert stats.failed_iterations == 0
        assert stats.average_evaluation_score == 0.85

    def test_single_failure(self) -> None:
        goal = _make_goal()
        iteration = _make_iteration(
            status=IterationStatus.FAILED,
            evaluation_score=0.1,
        )
        state = AutonomousState(
            current_iteration=0,
            completed_iterations=(iteration,),
            current_goal=goal,
        )

        stats = AutonomousStateManager.get_statistics(state)

        assert stats.total_iterations == 1
        assert stats.successful_iterations == 0
        assert stats.failed_iterations == 1

    def test_mixed_iterations(self) -> None:
        goal = _make_goal()
        iter1 = _make_iteration(
            iteration=1,
            status=IterationStatus.COMPLETED,
            evaluation_score=0.9,
        )
        iter2 = _make_iteration(
            iteration=2,
            status=IterationStatus.FAILED,
            evaluation_score=0.2,
        )
        iter3 = _make_iteration(
            iteration=3,
            status=IterationStatus.COMPLETED,
            evaluation_score=0.8,
        )
        state = AutonomousState(
            current_iteration=3,
            completed_iterations=(iter1, iter2, iter3),
            current_goal=goal,
        )

        stats = AutonomousStateManager.get_statistics(state)

        assert stats.total_iterations == 3
        assert stats.successful_iterations == 2
        assert stats.failed_iterations == 1
        # Average of 0.9, 0.2, 0.8 = 1.9/3 ≈ 0.633
        assert abs(stats.average_evaluation_score - 1.9 / 3) < 0.001

    def test_duration_aggregation(self) -> None:
        goal = _make_goal()
        iteration = _make_iteration(duration_ms=5000)
        state = AutonomousState(
            current_iteration=1,
            completed_iterations=(iteration,),
            current_goal=goal,
        )

        stats = AutonomousStateManager.get_statistics(state)

        assert stats.total_duration_ms == 5000


class TestImmutability:
    """Tests for state immutability."""

    def test_create_state_is_immutable(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)

        with pytest.raises(TypeError):
            state.current_iteration = 1

    def test_advance_returns_new_state(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)
        iteration = _make_iteration()

        new_state = AutonomousStateManager.advance_iteration(
            state, iteration
        )

        # Original state should be unchanged
        assert state.current_iteration == 0
        assert new_state.current_iteration == 1

    def test_record_failure_returns_new_state(self) -> None:
        goal = _make_goal()
        state = AutonomousStateManager.create(goal)
        iteration = _make_iteration(status=IterationStatus.FAILED)

        new_state = AutonomousStateManager.record_failure(
            state, iteration
        )

        # Original state should be unchanged
        assert state.completed_iterations == ()
        assert len(new_state.completed_iterations) == 1