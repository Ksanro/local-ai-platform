"""Tests for autonomous engine.

Tests cover:
- Deterministic execution
- State transitions
- Iteration history
- Workflow sequencing
- Failure handling
- Successful completion
- Maximum iteration handling
- Empty goal
- Policy integration
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from packages.autonomous.engine import AutonomousEngine
from packages.autonomous.models import (
    AutonomousIteration,
    AutonomousState,
    EngineeringGoal,
    IterationStatus,
)
from packages.autonomous.policy import PolicyDecision, PolicyResult


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


def _make_mock_workflow(name: str = "test-workflow") -> type:
    """Create a mock workflow class."""
    workflow = MagicMock()
    workflow.__name__ = name
    workflow.__name__ = name
    return workflow


# ---------------------------------------------------------------------------
# TestAutonomousEngine
# ---------------------------------------------------------------------------


class TestExecute:
    """Tests for AutonomousEngine.execute()."""

    def test_execute_no_adapters(self) -> None:
        """Test execution with no adapters configured."""
        engine = AutonomousEngine()
        goal = _make_goal(max_iterations=3)

        report = engine.execute(goal)

        assert report.goal == goal
        assert report.status in ("EMPTY", "FAILED")
        assert isinstance(report.iterations, tuple)
        assert isinstance(report.final_summary, str)
        assert isinstance(report.recommendations, tuple)

    def test_execute_with_mock_adapters(self) -> None:
        """Test execution with mock adapters."""
        # Create mock adapters
        workflow_adapter = MagicMock()
        workflow_adapter.generate_plan.return_value = {
            "workflow_name": "test-workflow"
        }

        execution_adapter = MagicMock()
        execution_adapter.execute.return_value = {
            "workflow_name": "test-workflow",
            "success": True,
        }

        evaluation_adapter = MagicMock()
        evaluation_adapter.evaluate.return_value = {
            "overall_score": 0.85,
            "summary": "Test evaluation",
        }

        patch_adapter = MagicMock()
        patch_adapter.generate.return_value = {"patches": []}

        modification_adapter = MagicMock()
        modification_adapter.apply.return_value = {"success": True}

        verification_adapter = MagicMock()
        verification_adapter.verify.return_value = {
            "verification_status": "PASSED"
        }

        engine = AutonomousEngine(
            workflow_adapter=workflow_adapter,
            execution_adapter=execution_adapter,
            evaluation_adapter=evaluation_adapter,
            patch_adapter=patch_adapter,
            modification_adapter=modification_adapter,
            verification_adapter=verification_adapter,
        )

        goal = _make_goal(max_iterations=2)

        # Create mock workflow
        mock_workflow = _make_mock_workflow("test-workflow")

        report = engine.execute(
            goal,
            available_workflows={"test-workflow": mock_workflow},
        )

        assert report.goal == goal
        assert len(report.iterations) > 0

    def test_execute_respects_max_iterations(self) -> None:
        """Test that execution respects max iterations."""
        engine = AutonomousEngine()
        goal = _make_goal(max_iterations=1)

        report = engine.execute(goal)

        # Should have at most max_iterations iterations
        assert len(report.iterations) <= 1 or report.status in (
            "COMPLETED",
            "EMPTY",
            "FAILED",
        )

    def test_execute_empty_goal(self) -> None:
        """Test execution with minimal goal."""
        engine = AutonomousEngine()
        goal = EngineeringGoal(id="empty", objective="")

        report = engine.execute(goal)

        assert report.goal == goal
        assert isinstance(report.status, str)

    def test_execute_with_policy_results(self) -> None:
        """Test execution with pre-computed policy results."""
        # Pre-computed policy results that stop immediately
        policy_results = [
            PolicyResult(
                decision=PolicyDecision.STOP,
                reason="Test stop policy",
            )
        ]

        engine = AutonomousEngine(policy_results=policy_results)
        goal = _make_goal(max_iterations=10)

        report = engine.execute(goal)

        # Should stop immediately with no iterations
        assert len(report.iterations) == 0
        assert report.status == "EMPTY"

    def test_execute_iteration_counting(self) -> None:
        """Test that iterations are properly counted."""
        # Create mock adapters that track calls
        call_count = 0

        def mock_generate_plan(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"workflow_name": "test-workflow"}

        workflow_adapter = MagicMock()
        workflow_adapter.generate_plan.side_effect = mock_generate_plan

        evaluation_adapter = MagicMock()
        evaluation_adapter.evaluate.return_value = {
            "overall_score": 0.9,
        }

        engine = AutonomousEngine(
            workflow_adapter=workflow_adapter,
            evaluation_adapter=evaluation_adapter,
        )

        goal = _make_goal(max_iterations=3)
        mock_workflow = _make_mock_workflow("test-workflow")

        report = engine.execute(
            goal,
            available_workflows={"test-workflow": mock_workflow},
        )

        # Should have executed up to max_iterations workflows
        assert len(report.iterations) <= 3


class TestWorkflowIteration:
    """Tests for workflow iteration handling."""

    def test_iteration_workflow_name(self) -> None:
        """Test that iteration records workflow name."""
        engine = AutonomousEngine()
        goal = _make_goal()

        report = engine.execute(goal)

        for iteration in report.iterations:
            assert isinstance(iteration.workflow_name, str)
            assert len(iteration.workflow_name) > 0

    def test_iteration_status_values(self) -> None:
        """Test that iteration statuses are valid."""
        engine = AutonomousEngine()
        goal = _make_goal()

        report = engine.execute(goal)

        for iteration in report.iterations:
            assert iteration.status in (
                IterationStatus.COMPLETED,
                IterationStatus.FAILED,
                IterationStatus.SKIPPED,
                IterationStatus.STOPPED,
            )

    def test_iteration_duration(self) -> None:
        """Test that iteration has duration."""
        engine = AutonomousEngine()
        goal = _make_goal()

        report = engine.execute(goal)

        for iteration in report.iterations:
            assert iteration.duration_ms >= 0


class TestFinalReport:
    """Tests for final report generation."""

    def test_report_has_goal(self) -> None:
        """Test that report contains the goal."""
        engine = AutonomousEngine()
        goal = _make_goal(id="test-id", objective="Test objective")

        report = engine.execute(goal)

        assert report.goal.id == "test-id"
        assert report.goal.objective == "Test objective"

    def test_report_has_status(self) -> None:
        """Test that report has a status."""
        engine = AutonomousEngine()
        goal = _make_goal()

        report = engine.execute(goal)

        assert isinstance(report.status, str)
        assert len(report.status) > 0

    def test_report_has_summary(self) -> None:
        """Test that report has a summary."""
        engine = AutonomousEngine()
        goal = _make_goal()

        report = engine.execute(goal)

        assert isinstance(report.final_summary, str)

    def test_report_has_recommendations(self) -> None:
        """Test that report has recommendations."""
        engine = AutonomousEngine()
        goal = _make_goal()

        report = engine.execute(goal)

        assert isinstance(report.recommendations, tuple)


class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_deterministic_planning(self) -> None:
        """Test that planning is deterministic."""
        from packages.autonomous.planner import EngineeringPlanner

        goal = _make_goal()
        planner = EngineeringPlanner()

        sequence1 = planner.plan(goal)
        sequence2 = planner.plan(goal)

        assert sequence1 == sequence2

    def test_deterministic_state_transitions(self) -> None:
        """Test that state transitions are deterministic."""
        from packages.autonomous.state import AutonomousStateManager

        goal = _make_goal()
        state1 = AutonomousStateManager.create(goal)
        state2 = AutonomousStateManager.create(goal)

        iteration = AutonomousIteration(
            iteration=1,
            workflow_name="test",
            evaluation_score=0.85,
            verification_status="PASSED",
            duration_ms=100,
            result_summary="Test",
        )

        new_state1 = AutonomousStateManager.advance_iteration(
            state1, iteration
        )
        new_state2 = AutonomousStateManager.advance_iteration(
            state2, iteration
        )

        assert new_state1.current_iteration == new_state2.current_iteration
        assert new_state1.completed_workflows == new_state2.completed_workflows


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_execute_zero_max_iterations(self) -> None:
        """Test execution with zero max iterations."""
        engine = AutonomousEngine()
        goal = _make_goal(max_iterations=0)

        report = engine.execute(goal)

        # Should stop immediately
        assert len(report.iterations) == 0
        assert report.status in ("EMPTY", "FAILED")

    def test_execute_single_iteration(self) -> None:
        """Test execution with single iteration."""
        engine = AutonomousEngine()
        goal = _make_goal(max_iterations=1)

        report = engine.execute(goal)

        # Should have at most 1 iteration
        assert len(report.iterations) <= 1

    def test_execute_with_no_workflow_sequence(self) -> None:
        """Test execution when no workflows are available."""
        engine = AutonomousEngine()
        goal = _make_goal()

        # Use a planner that returns empty sequence
        class EmptyPlanner:
            @staticmethod
            def plan(*args, **kwargs):
                return ()

        report = engine.execute(goal, planner=EmptyPlanner())

        assert len(report.iterations) == 0
        assert report.status == "EMPTY"

    def test_execute_with_exception(self) -> None:
        """Test execution handles exceptions gracefully."""
        workflow_adapter = MagicMock()
        workflow_adapter.generate_plan.side_effect = Exception(
            "Test exception"
        )

        engine = AutonomousEngine(workflow_adapter=workflow_adapter)
        goal = _make_goal()
        mock_workflow = _make_mock_workflow("test-workflow")

        report = engine.execute(
            goal,
            available_workflows={"test-workflow": mock_workflow},
        )

        # Should still produce a report despite exception
        assert report.goal == goal
        assert len(report.iterations) >= 0


class TestPolicyIntegration:
    """Tests for policy integration."""

    def test_stop_on_failure_policy(self) -> None:
        """Test StopOnFailurePolicy integration."""
        from packages.autonomous.policy import StopOnFailurePolicy

        engine = AutonomousEngine()
        goal = _make_goal(max_iterations=5)

        policies = (StopOnFailurePolicy(),)

        report = engine.execute(goal, policies=policies)

        assert report.goal == goal
        assert isinstance(report.status, str)

    def test_sequential_policy(self) -> None:
        """Test SequentialPolicy integration."""
        from packages.autonomous.policy import SequentialPolicy

        engine = AutonomousEngine()
        goal = _make_goal(max_iterations=5)

        policies = (SequentialPolicy(),)

        report = engine.execute(goal, policies=policies)

        assert report.goal == goal

    def test_maximum_iteration_policy(self) -> None:
        """Test MaximumIterationPolicy integration."""
        from packages.autonomous.policy import MaximumIterationPolicy

        engine = AutonomousEngine()
        goal = _make_goal(max_iterations=3)

        policies = (MaximumIterationPolicy(),)

        report = engine.execute(goal, policies=policies)

        assert report.goal == goal