"""Tests for autonomous policies.

Tests cover:
- Policy execution
- Policy decisions
- Policy evaluation
- Policy results
"""

from __future__ import annotations

import pytest

from packages.autonomous.models import (
    AutonomousIteration,
    AutonomousState,
    EngineeringGoal,
    IterationStatus,
)
from packages.autonomous.policy import (
    MaximumIterationPolicy,
    PolicyDecision,
    PolicyResult,
    SequentialPolicy,
    StopOnFailurePolicy,
    VerificationGatePolicy,
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
# SequentialPolicy
# ---------------------------------------------------------------------------


class TestSequentialPolicy:
    """Tests for SequentialPolicy."""

    def test_always_continues(self) -> None:
        policy = SequentialPolicy()
        state = _make_state()
        result = policy.evaluate(state)
        assert result.decision == PolicyDecision.CONTINUE
        assert "always allow" in result.reason.lower()

    def test_with_last_iteration(self) -> None:
        policy = SequentialPolicy()
        state = _make_state()
        iteration = _make_iteration()
        result = policy.evaluate(state, iteration)
        assert result.decision == PolicyDecision.CONTINUE

    def test_with_failed_iteration(self) -> None:
        policy = SequentialPolicy()
        state = _make_state()
        iteration = _make_iteration(status=IterationStatus.FAILED)
        result = policy.evaluate(state, iteration)
        # SequentialPolicy always continues regardless of failure
        assert result.decision == PolicyDecision.CONTINUE


# ---------------------------------------------------------------------------
# StopOnFailurePolicy
# ---------------------------------------------------------------------------


class TestStopOnFailurePolicy:
    """Tests for StopOnFailurePolicy."""

    def test_no_last_iteration(self) -> None:
        policy = StopOnFailurePolicy()
        state = _make_state()
        result = policy.evaluate(state, None)
        assert result.decision == PolicyDecision.CONTINUE

    def test_completed_iteration(self) -> None:
        policy = StopOnFailurePolicy()
        state = _make_state()
        iteration = _make_iteration(status=IterationStatus.COMPLETED)
        result = policy.evaluate(state, iteration)
        assert result.decision == PolicyDecision.CONTINUE

    def test_failed_iteration(self) -> None:
        policy = StopOnFailurePolicy()
        state = _make_state()
        iteration = _make_iteration(status=IterationStatus.FAILED)
        result = policy.evaluate(state, iteration)
        assert result.decision == PolicyDecision.STOP
        assert "failed" in result.reason.lower()

    def test_skipped_iteration(self) -> None:
        policy = StopOnFailurePolicy()
        state = _make_state()
        iteration = _make_iteration(status=IterationStatus.SKIPPED)
        result = policy.evaluate(state, iteration)
        assert result.decision == PolicyDecision.CONTINUE

    def test_stopped_iteration(self) -> None:
        policy = StopOnFailurePolicy()
        state = _make_state()
        iteration = _make_iteration(status=IterationStatus.STOPPED)
        result = policy.evaluate(state, iteration)
        assert result.decision == PolicyDecision.CONTINUE


# ---------------------------------------------------------------------------
# VerificationGatePolicy
# ---------------------------------------------------------------------------


class TestVerificationGatePolicy:
    """Tests for VerificationGatePolicy."""

    def test_no_last_iteration(self) -> None:
        policy = VerificationGatePolicy()
        state = _make_state()
        result = policy.evaluate(state, None)
        assert result.decision == PolicyDecision.CONTINUE

    def test_empty_verification_status(self) -> None:
        policy = VerificationGatePolicy()
        state = _make_state()
        iteration = _make_iteration(verification_status="")
        result = policy.evaluate(state, iteration)
        assert result.decision == PolicyDecision.STOP

    def test_passed_status(self) -> None:
        policy = VerificationGatePolicy()
        state = _make_state()
        iteration = _make_iteration(verification_status="PASSED")
        result = policy.evaluate(state, iteration)
        assert result.decision == PolicyDecision.CONTINUE

    def test_completed_status(self) -> None:
        policy = VerificationGatePolicy()
        state = _make_state()
        iteration = _make_iteration(verification_status="COMPLETED")
        result = policy.evaluate(state, iteration)
        assert result.decision == PolicyDecision.CONTINUE

    def test_success_status(self) -> None:
        policy = VerificationGatePolicy()
        state = _make_state()
        iteration = _make_iteration(verification_status="SUCCESS")
        result = policy.evaluate(state, iteration)
        assert result.decision == PolicyDecision.CONTINUE

    def test_failed_status(self) -> None:
        policy = VerificationGatePolicy()
        state = _make_state()
        iteration = _make_iteration(verification_status="FAILED")
        result = policy.evaluate(state, iteration)
        assert result.decision == PolicyDecision.STOP

    def test_unknown_status(self) -> None:
        policy = VerificationGatePolicy()
        state = _make_state()
        iteration = _make_iteration(verification_status="UNKNOWN")
        result = policy.evaluate(state, iteration)
        assert result.decision == PolicyDecision.STOP


# ---------------------------------------------------------------------------
# MaximumIterationPolicy
# ---------------------------------------------------------------------------


class TestMaximumIterationPolicy:
    """Tests for MaximumIterationPolicy."""

    def test_below_max(self) -> None:
        policy = MaximumIterationPolicy()
        state = _make_state(current_iteration=5, goal=_make_goal(max_iterations=10))
        result = policy.evaluate(state)
        assert result.decision == PolicyDecision.CONTINUE

    def test_at_max(self) -> None:
        policy = MaximumIterationPolicy()
        state = _make_state(current_iteration=10, goal=_make_goal(max_iterations=10))
        result = policy.evaluate(state)
        assert result.decision == PolicyDecision.STOP
        assert "max iterations" in result.reason.lower()

    def test_above_max(self) -> None:
        policy = MaximumIterationPolicy()
        state = _make_state(current_iteration=15, goal=_make_goal(max_iterations=10))
        result = policy.evaluate(state)
        assert result.decision == PolicyDecision.STOP

    def test_zero_max(self) -> None:
        policy = MaximumIterationPolicy()
        state = _make_state(current_iteration=0, goal=_make_goal(max_iterations=0))
        result = policy.evaluate(state)
        assert result.decision == PolicyDecision.STOP


# ---------------------------------------------------------------------------
# PolicyResult
# ---------------------------------------------------------------------------


class TestPolicyResult:
    """Tests for PolicyResult."""

    def test_creation(self) -> None:
        result = PolicyResult(
            decision=PolicyDecision.CONTINUE,
            reason="Test reason",
        )
        assert result.decision == PolicyDecision.CONTINUE
        assert result.reason == "Test reason"
        assert result.metadata == {}

    def test_with_metadata(self) -> None:
        result = PolicyResult(
            decision=PolicyDecision.STOP,
            reason="Test reason",
            metadata={"key": "value"},
        )
        assert result.metadata == {"key": "value"}

    def test_immutability(self) -> None:
        result = PolicyResult(
            decision=PolicyDecision.CONTINUE,
            reason="Test reason",
        )
        with pytest.raises(TypeError):
            result.decision = PolicyDecision.STOP


# ---------------------------------------------------------------------------
# PolicyDecision
# ---------------------------------------------------------------------------


class TestPolicyDecision:
    """Tests for PolicyDecision."""

    def test_continue_value(self) -> None:
        assert PolicyDecision.CONTINUE == "CONTINUE"

    def test_stop_value(self) -> None:
        assert PolicyDecision.STOP == "STOP"

    def test_skip_value(self) -> None:
        assert PolicyDecision.SKIP == "SKIP"