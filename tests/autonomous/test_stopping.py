"""Tests for stopping conditions.

Tests cover:
- Stopping rules
- All stopping conditions
- Edge cases
- Combined conditions
"""

from __future__ import annotations

import pytest

from packages.autonomous.models import (
    AutonomousIteration,
    AutonomousState,
    EngineeringGoal,
    IterationStatus,
)
from packages.autonomous.stopping import (
    check_goal_achieved,
    check_max_iterations_reached,
    check_policy_request_stop,
    check_repeated_failure,
    check_verification_successful,
    check_all_stopping_conditions,
    DEFAULT_REPEATED_FAILURE_THRESHOLD,
)


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


def _make_state(
    current_iteration: int = 0,
    completed_iterations=(),
    goal: EngineeringGoal | None = None,
) -> AutonomousState:
    if goal is None:
        goal = _make_goal()
    return AutonomousState(
        current_iteration=current_iteration,
        current_goal=goal,
        completed_iterations=completed_iterations,
    )


def _make_iteration(
    iteration: int = 1,
    status: IterationStatus = IterationStatus.COMPLETED,
    evaluation_score: float = 0.85,
    verification_status: str = "PASSED",
) -> AutonomousIteration:
    return AutonomousIteration(
        iteration=iteration,
        workflow_name="test-workflow",
        evaluation_score=evaluation_score,
        verification_status=verification_status,
        duration_ms=1000,
        result_summary="Test",
        status=status,
    )


# ---------------------------------------------------------------------------
# check_goal_achieved
# ---------------------------------------------------------------------------


class TestCheckGoalAchieved:
    """Tests for check_goal_achieved."""

    def test_empty_iterations(self) -> None:
        state = _make_state()
        assert check_goal_achieved(state) is False

    def test_high_score(self) -> None:
        iteration = _make_iteration(evaluation_score=0.85)
        state = _make_state(completed_iterations=(iteration,))
        assert check_goal_achieved(state) is True

    def test_low_score(self) -> None:
        iteration = _make_iteration(evaluation_score=0.3)
        state = _make_state(completed_iterations=(iteration,))
        assert check_goal_achieved(state) is False

    def test_boundary_score(self) -> None:
        iteration = _make_iteration(evaluation_score=0.8)
        state = _make_state(completed_iterations=(iteration,))
        assert check_goal_achieved(state) is True

    def test_multiple_iterations_one_high(self) -> None:
        iter1 = _make_iteration(iteration=1, evaluation_score=0.3)
        iter2 = _make_iteration(iteration=2, evaluation_score=0.9)
        state = _make_state(completed_iterations=(iter1, iter2))
        assert check_goal_achieved(state) is True

    def test_all_low_scores(self) -> None:
        iter1 = _make_iteration(iteration=1, evaluation_score=0.3)
        iter2 = _make_iteration(iteration=2, evaluation_score=0.4)
        state = _make_state(completed_iterations=(iter1, iter2))
        assert check_goal_achieved(state) is False

    def test_zero_score(self) -> None:
        iteration = _make_iteration(evaluation_score=0.0)
        state = _make_state(completed_iterations=(iteration,))
        assert check_goal_achieved(state) is False


# ---------------------------------------------------------------------------
# check_verification_successful
# ---------------------------------------------------------------------------


class TestCheckVerificationSuccessful:
    """Tests for check_verification_successful."""

    def test_empty_iterations(self) -> None:
        state = _make_state()
        assert check_verification_successful(state) is False

    def test_passed_status(self) -> None:
        iteration = _make_iteration(verification_status="PASSED")
        state = _make_state(completed_iterations=(iteration,))
        assert check_verification_successful(state) is True

    def test_completed_status(self) -> None:
        iteration = _make_iteration(verification_status="COMPLETED")
        state = _make_state(completed_iterations=(iteration,))
        assert check_verification_successful(state) is True

    def test_success_status(self) -> None:
        iteration = _make_iteration(verification_status="SUCCESS")
        state = _make_state(completed_iterations=(iteration,))
        assert check_verification_successful(state) is True

    def test_failed_status(self) -> None:
        iteration = _make_iteration(verification_status="FAILED")
        state = _make_state(completed_iterations=(iteration,))
        assert check_verification_successful(state) is False

    def test_unknown_status(self) -> None:
        iteration = _make_iteration(verification_status="UNKNOWN")
        state = _make_state(completed_iterations=(iteration,))
        assert check_verification_successful(state) is False

    def test_empty_status(self) -> None:
        iteration = _make_iteration(verification_status="")
        state = _make_state(completed_iterations=(iteration,))
        assert check_verification_successful(state) is False


# ---------------------------------------------------------------------------
# check_max_iterations_reached
# ---------------------------------------------------------------------------


class TestCheckMaxIterationsReached:
    """Tests for check_max_iterations_reached."""

    def test_below_max(self) -> None:
        state = _make_state(current_iteration=5, goal=_make_goal(max_iterations=10))
        assert check_max_iterations_reached(state) is False

    def test_at_max(self) -> None:
        state = _make_state(current_iteration=10, goal=_make_goal(max_iterations=10))
        assert check_max_iterations_reached(state) is True

    def test_above_max(self) -> None:
        state = _make_state(current_iteration=15, goal=_make_goal(max_iterations=10))
        assert check_max_iterations_reached(state) is True

    def test_zero_max(self) -> None:
        state = _make_state(current_iteration=0, goal=_make_goal(max_iterations=0))
        assert check_max_iterations_reached(state) is True

    def test_zero_iteration_zero_max(self) -> None:
        state = _make_state(current_iteration=0, goal=_make_goal(max_iterations=0))
        assert check_max_iterations_reached(state) is True

    def test_single_iteration_single_max(self) -> None:
        state = _make_state(current_iteration=1, goal=_make_goal(max_iterations=1))
        assert check_max_iterations_reached(state) is True


# ---------------------------------------------------------------------------
# check_repeated_failure
# ---------------------------------------------------------------------------


class TestCheckRepeatedFailure:
    """Tests for check_repeated_failure."""

    def test_empty_iterations(self) -> None:
        state = _make_state()
        assert check_repeated_failure(state) is False

    def test_fewer_than_threshold(self) -> None:
        iter1 = _make_iteration(status=IterationStatus.FAILED)
        state = _make_state(completed_iterations=(iter1,))
        assert check_repeated_failure(state) is False

    def test_exactly_threshold_failures(self) -> None:
        iterations = tuple(
            _make_iteration(iteration=i, status=IterationStatus.FAILED)
            for i in range(1, DEFAULT_REPEATED_FAILURE_THRESHOLD + 1)
        )
        state = _make_state(completed_iterations=iterations)
        assert check_repeated_failure(state) is True

    def test_more_than_threshold_failures(self) -> None:
        iterations = tuple(
            _make_iteration(iteration=i, status=IterationStatus.FAILED)
            for i in range(1, DEFAULT_REPEATED_FAILURE_THRESHOLD + 4)
        )
        state = _make_state(completed_iterations=iterations)
        assert check_repeated_failure(state) is True

    def test_mixed_statuses(self) -> None:
        iterations = (
            _make_iteration(iteration=1, status=IterationStatus.FAILED),
            _make_iteration(iteration=2, status=IterationStatus.COMPLETED),
            _make_iteration(iteration=3, status=IterationStatus.FAILED),
        )
        state = _make_state(completed_iterations=iterations)
        assert check_repeated_failure(state) is False

    def test_all_completed(self) -> None:
        iterations = (
            _make_iteration(iteration=1, status=IterationStatus.COMPLETED),
            _make_iteration(iteration=2, status=IterationStatus.COMPLETED),
            _make_iteration(iteration=3, status=IterationStatus.COMPLETED),
        )
        state = _make_state(completed_iterations=iterations)
        assert check_repeated_failure(state) is False

    def test_custom_threshold(self) -> None:
        iterations = tuple(
            _make_iteration(iteration=i, status=IterationStatus.FAILED)
            for i in range(1, 6)
        )
        state = _make_state(completed_iterations=iterations)
        assert check_repeated_failure(state, threshold=5) is True
        assert check_repeated_failure(state, threshold=6) is False


# ---------------------------------------------------------------------------
# check_policy_request_stop
# ---------------------------------------------------------------------------


class TestCheckPolicyRequestStop:
    """Tests for check_policy_request_stop."""

    def test_no_last_iteration(self) -> None:
        state = _make_state()
        assert check_policy_request_stop(state, None) is False

    def test_no_metadata(self) -> None:
        iteration = _make_iteration()
        state = _make_state()
        assert check_policy_request_stop(state, iteration) is False

    def test_no_policy_stop_in_metadata(self) -> None:
        iteration = _make_iteration()
        iteration = AutonomousIteration(
            iteration=iteration.iteration,
            workflow_name=iteration.workflow_name,
            evaluation_score=iteration.evaluation_score,
            verification_status=iteration.verification_status,
            duration_ms=iteration.duration_ms,
            result_summary=iteration.result_summary,
            status=iteration.status,
            metadata={"other_key": "value"},
        )
        state = _make_state()
        assert check_policy_request_stop(state, iteration) is False

    def test_policy_stop_false(self) -> None:
        iteration = _make_iteration()
        iteration = AutonomousIteration(
            iteration=iteration.iteration,
            workflow_name=iteration.workflow_name,
            evaluation_score=iteration.evaluation_score,
            verification_status=iteration.verification_status,
            duration_ms=iteration.duration_ms,
            result_summary=iteration.result_summary,
            status=iteration.status,
            metadata={"policy_stop": False},
        )
        state = _make_state()
        assert check_policy_request_stop(state, iteration) is False

    def test_policy_stop_true(self) -> None:
        iteration = _make_iteration()
        iteration = AutonomousIteration(
            iteration=iteration.iteration,
            workflow_name=iteration.workflow_name,
            evaluation_score=iteration.evaluation_score,
            verification_status=iteration.verification_status,
            duration_ms=iteration.duration_ms,
            result_summary=iteration.result_summary,
            status=iteration.status,
            metadata={"policy_stop": True},
        )
        state = _make_state()
        assert check_policy_request_stop(state, iteration) is True


# ---------------------------------------------------------------------------
# check_all_stopping_conditions
# ---------------------------------------------------------------------------


class TestCheckAllStoppingConditions:
    """Tests for check_all_stopping_conditions."""

    def test_no_conditions_met(self) -> None:
        state = _make_state()
        should_stop, reasons = check_all_stopping_conditions(state)
        assert should_stop is False
        assert len(reasons) == 0

    def test_max_iterations_met(self) -> None:
        state = _make_state(current_iteration=10, goal=_make_goal(max_iterations=10))
        should_stop, reasons = check_all_stopping_conditions(state)
        assert should_stop is True
        assert any("Maximum iterations" in r for r in reasons)

    def test_goal_achieved(self) -> None:
        iteration = _make_iteration(evaluation_score=0.9)
        state = _make_state(completed_iterations=(iteration,))
        should_stop, reasons = check_all_stopping_conditions(state)
        assert should_stop is True
        assert any("Goal achieved" in r for r in reasons)

    def test_verification_successful(self) -> None:
        iteration = _make_iteration(verification_status="PASSED")
        state = _make_state(completed_iterations=(iteration,))
        should_stop, reasons = check_all_stopping_conditions(state)
        assert should_stop is True
        assert any("Verification successful" in r for r in reasons)

    def test_multiple_conditions(self) -> None:
        iteration = _make_iteration(evaluation_score=0.9, verification_status="PASSED")
        state = _make_state(
            current_iteration=10,
            completed_iterations=(iteration,),
            goal=_make_goal(max_iterations=10),
        )
        should_stop, reasons = check_all_stopping_conditions(state)
        assert should_stop is True
        assert len(reasons) >= 2

    def test_policy_stop(self) -> None:
        iteration = _make_iteration()
        iteration = AutonomousIteration(
            iteration=iteration.iteration,
            workflow_name=iteration.workflow_name,
            evaluation_score=iteration.evaluation_score,
            verification_status=iteration.verification_status,
            duration_ms=iteration.duration_ms,
            result_summary=iteration.result_summary,
            status=iteration.status,
            metadata={"policy_stop": True},
        )
        state = _make_state(completed_iterations=(iteration,))
        should_stop, reasons = check_all_stopping_conditions(state, iteration)
        assert should_stop is True
        assert any("Policy requested stop" in r for r in reasons)