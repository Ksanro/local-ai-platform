"""Tests for autonomous models.

Tests cover:
- Immutable models
- Default values
- Frozen state
- Type correctness
"""

from __future__ import annotations

import pytest

from packages.autonomous.models import (
    AutonomousIteration,
    AutonomousState,
    AutonomousStatistics,
    EngineeringGoal,
    FinalEngineeringReport,
    IterationStatus,
)


# ---------------------------------------------------------------------------
# IterationStatus
# ---------------------------------------------------------------------------


class TestIterationStatus:
    """Tests for IterationStatus."""

    def test_completed_value(self) -> None:
        assert IterationStatus.COMPLETED == "COMPLETED"

    def test_failed_value(self) -> None:
        assert IterationStatus.FAILED == "FAILED"

    def test_skipped_value(self) -> None:
        assert IterationStatus.SKIPPED == "SKIPPED"

    def test_stopped_value(self) -> None:
        assert IterationStatus.STOPPED == "STOPPED"


# ---------------------------------------------------------------------------
# EngineeringGoal
# ---------------------------------------------------------------------------


class TestEngineeringGoal:
    """Tests for EngineeringGoal."""

    def test_basic_creation(self) -> None:
        goal = EngineeringGoal(
            id="goal-001",
            objective="Implement feature X",
        )
        assert goal.id == "goal-001"
        assert goal.objective == "Implement feature X"
        assert goal.constraints == ()
        assert goal.success_criteria == ()
        assert goal.max_iterations == 10
        assert goal.metadata == {}

    def test_full_creation(self) -> None:
        goal = EngineeringGoal(
            id="goal-002",
            objective="Fix bug Y",
            constraints=("no-breaking-changes",),
            success_criteria=("tests-pass",),
            max_iterations=5,
            metadata={"priority": "high"},
        )
        assert goal.id == "goal-002"
        assert goal.objective == "Fix bug Y"
        assert goal.constraints == ("no-breaking-changes",)
        assert goal.success_criteria == ("tests-pass",)
        assert goal.max_iterations == 5
        assert goal.metadata == {"priority": "high"}

    def test_immutability(self) -> None:
        goal = EngineeringGoal(
            id="goal-003",
            objective="Test",
        )
        with pytest.raises(TypeError):
            goal.id = "modified"

    def test_equality(self) -> None:
        goal1 = EngineeringGoal(
            id="goal-004",
            objective="Test",
        )
        goal2 = EngineeringGoal(
            id="goal-004",
            objective="Test",
        )
        assert goal1 == goal2

    def test_hash(self) -> None:
        goal = EngineeringGoal(
            id="goal-005",
            objective="Test",
        )
        # Frozen dataclasses are hashable
        hash(goal)


# ---------------------------------------------------------------------------
# AutonomousIteration
# ---------------------------------------------------------------------------


class TestAutonomousIteration:
    """Tests for AutonomousIteration."""

    def test_basic_creation(self) -> None:
        iteration = AutonomousIteration(
            iteration=1,
            workflow_name="test-workflow",
            evaluation_score=0.85,
            verification_status="PASSED",
            duration_ms=1000,
            result_summary="Test completed",
        )
        assert iteration.iteration == 1
        assert iteration.workflow_name == "test-workflow"
        assert iteration.evaluation_score == 0.85
        assert iteration.verification_status == "PASSED"
        assert iteration.duration_ms == 1000
        assert iteration.result_summary == "Test completed"
        assert iteration.status == IterationStatus.COMPLETED
        assert iteration.metadata == {}

    def test_failed_status(self) -> None:
        iteration = AutonomousIteration(
            iteration=2,
            workflow_name="test-workflow",
            evaluation_score=0.1,
            verification_status="FAILED",
            duration_ms=500,
            result_summary="Test failed",
            status=IterationStatus.FAILED,
        )
        assert iteration.status == IterationStatus.FAILED

    def test_immutability(self) -> None:
        iteration = AutonomousIteration(
            iteration=3,
            workflow_name="test-workflow",
            evaluation_score=0.5,
            verification_status="UNKNOWN",
            duration_ms=100,
            result_summary="Test",
        )
        with pytest.raises(TypeError):
            iteration.iteration = 4

    def test_default_status(self) -> None:
        iteration = AutonomousIteration(
            iteration=4,
            workflow_name="test-workflow",
            evaluation_score=0.5,
            verification_status="UNKNOWN",
            duration_ms=100,
            result_summary="Test",
        )
        assert iteration.status == IterationStatus.COMPLETED


# ---------------------------------------------------------------------------
# AutonomousState
# ---------------------------------------------------------------------------


class TestAutonomousState:
    """Tests for AutonomousState."""

    def test_basic_creation(self) -> None:
        goal = EngineeringGoal(
            id="goal-001",
            objective="Test",
        )
        state = AutonomousState(
            current_iteration=0,
            current_goal=goal,
        )
        assert state.current_iteration == 0
        assert state.completed_workflows == ()
        assert state.completed_iterations == ()
        assert state.current_goal == goal
        assert state.metadata == {}

    def test_with_iterations(self) -> None:
        goal = EngineeringGoal(
            id="goal-001",
            objective="Test",
        )
        iteration = AutonomousIteration(
            iteration=1,
            workflow_name="test-workflow",
            evaluation_score=0.85,
            verification_status="PASSED",
            duration_ms=1000,
            result_summary="Test completed",
        )
        state = AutonomousState(
            current_iteration=1,
            completed_workflows=("test-workflow",),
            completed_iterations=(iteration,),
            current_goal=goal,
        )
        assert state.current_iteration == 1
        assert state.completed_workflows == ("test-workflow",)
        assert state.completed_iterations == (iteration,)

    def test_immutability(self) -> None:
        goal = EngineeringGoal(
            id="goal-001",
            objective="Test",
        )
        state = AutonomousState(
            current_iteration=0,
            current_goal=goal,
        )
        with pytest.raises(TypeError):
            state.current_iteration = 1

    def test_none_goal_default(self) -> None:
        # When current_goal is None, it should be set to a default
        state = AutonomousState(
            current_iteration=0,
            current_goal=None,  # type: ignore
        )
        assert state.current_goal.id == "unknown"
        assert state.current_goal.objective == "Unknown"


# ---------------------------------------------------------------------------
# AutonomousStatistics
# ---------------------------------------------------------------------------


class TestAutonomousStatistics:
    """Tests for AutonomousStatistics."""

    def test_default_values(self) -> None:
        stats = AutonomousStatistics()
        assert stats.total_iterations == 0
        assert stats.successful_iterations == 0
        assert stats.failed_iterations == 0
        assert stats.workflows_executed == 0
        assert stats.total_duration_ms == 0
        assert stats.average_evaluation_score == 0.0

    def test_with_values(self) -> None:
        stats = AutonomousStatistics(
            total_iterations=5,
            successful_iterations=3,
            failed_iterations=2,
            workflows_executed=4,
            total_duration_ms=10000,
            average_evaluation_score=0.75,
        )
        assert stats.total_iterations == 5
        assert stats.successful_iterations == 3
        assert stats.failed_iterations == 2
        assert stats.workflows_executed == 4
        assert stats.total_duration_ms == 10000
        assert stats.average_evaluation_score == 0.75

    def test_immutability(self) -> None:
        stats = AutonomousStatistics()
        with pytest.raises(TypeError):
            stats.total_iterations = 10


# ---------------------------------------------------------------------------
# FinalEngineeringReport
# ---------------------------------------------------------------------------


class TestFinalEngineeringReport:
    """Tests for FinalEngineeringReport."""

    def test_basic_creation(self) -> None:
        goal = EngineeringGoal(
            id="goal-001",
            objective="Test",
        )
        report = FinalEngineeringReport(
            goal=goal,
            status="COMPLETED",
        )
        assert report.goal == goal
        assert report.status == "COMPLETED"
        assert report.iterations == ()
        assert report.statistics.total_iterations == 0
        assert report.final_summary == ""
        assert report.recommendations == ()

    def test_full_creation(self) -> None:
        goal = EngineeringGoal(
            id="goal-001",
            objective="Test",
        )
        iteration = AutonomousIteration(
            iteration=1,
            workflow_name="test-workflow",
            evaluation_score=0.85,
            verification_status="PASSED",
            duration_ms=1000,
            result_summary="Test completed",
        )
        stats = AutonomousStatistics(
            total_iterations=1,
            successful_iterations=1,
            failed_iterations=0,
            workflows_executed=1,
            total_duration_ms=1000,
            average_evaluation_score=0.85,
        )
        report = FinalEngineeringReport(
            goal=goal,
            status="COMPLETED",
            iterations=(iteration,),
            statistics=stats,
            final_summary="All tests passed",
            recommendations=("Keep going",),
        )
        assert report.goal == goal
        assert report.status == "COMPLETED"
        assert report.iterations == (iteration,)
        assert report.statistics == stats
        assert report.final_summary == "All tests passed"
        assert report.recommendations == ("Keep going",)

    def test_immutability(self) -> None:
        goal = EngineeringGoal(
            id="goal-001",
            objective="Test",
        )
        report = FinalEngineeringReport(
            goal=goal,
            status="COMPLETED",
        )
        with pytest.raises(TypeError):
            report.status = "MODIFIED"