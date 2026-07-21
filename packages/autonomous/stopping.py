"""Deterministic stopping conditions.

Implements deterministic stopping rules that determine when the
AutonomousEngine should halt execution. Stopping conditions prevent
infinite loops and ensure deterministic termination.

Architecture
------------

Stopping Conditions --> AutonomousEngine --> Execution Termination
       |
       |-- check_goal_achieved
       |-- check_verification_successful
       |-- check_max_iterations_reached
       |-- check_repeated_failure
       |-- check_policy_request_stop

Responsibilities
----------------

- Evaluate stopping conditions deterministically.
- Never allow infinite loops.
- Consume only public API objects.
- Never modify state.

Non-responsibilities
--------------------

- Must NOT modify AutonomousState.
- Must NOT inspect repositories.
- Must NOT invoke providers.
- Must NOT generate patches.
- Must NOT duplicate workflow logic.

Public API
----------

.. code-block:: python

    from packages.autonomous.stopping import (
        check_goal_achieved,
        check_verification_successful,
        check_max_iterations_reached,
        check_repeated_failure,
        check_policy_request_stop,
    )

    should_stop = check_max_iterations_reached(state)

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from packages.autonomous.models import AutonomousState, IterationStatus

if TYPE_CHECKING:
    pass  # No additional imports needed

__all__ = [
    "check_goal_achieved",
    "check_max_iterations_reached",
    "check_policy_request_stop",
    "check_repeated_failure",
    "check_verification_successful",
]

# ---------------------------------------------------------------------------
# Default constants
# ---------------------------------------------------------------------------

# Number of consecutive failed iterations that triggers the repeated
# failure stopping condition.  This is a constant — no hidden heuristics.
DEFAULT_REPEATED_FAILURE_THRESHOLD: int = 3


# ---------------------------------------------------------------------------
# Stopping condition functions
# ---------------------------------------------------------------------------


def check_goal_achieved(
    state: AutonomousState,
) -> bool:
    """Check if the engineering goal has been achieved.

    Evaluates whether the goal's success criteria have been met based
    on the completed iterations. For now this checks if any iteration
    has a high evaluation score (>= 0.8).

    Args:
        state: The current autonomous state.

    Returns:
        True if the goal is achieved, False otherwise.
    """
    if not state.completed_iterations:
        return False

    # Check if any iteration has a high evaluation score.
    for iteration in state.completed_iterations:
        score = getattr(iteration, "evaluation_score", 0.0)
        if score is not None and score >= 0.8:
            return True

    return False


def check_verification_successful(
    state: AutonomousState,
) -> bool:
    """Check if verification has been successful.

    Evaluates whether the most recent iteration has a successful
    verification status.

    Args:
        state: The current autonomous state.

    Returns:
        True if verification is successful, False otherwise.
    """
    if not state.completed_iterations:
        return False

    last = state.completed_iterations[-1]
    verification_status = getattr(last, "verification_status", "")

    if not verification_status:
        return False

    # Check if verification status indicates success.
    success_statuses = ("PASSED", "COMPLETED", "SUCCESS")
    return verification_status in success_statuses


def check_max_iterations_reached(
    state: AutonomousState,
) -> bool:
    """Check if the maximum number of iterations has been reached.

    Evaluates whether the current iteration count has reached or
    exceeded the goal's maximum iteration limit.

    Args:
        state: The current autonomous state.

    Returns:
        True if max iterations reached, False otherwise.
    """
    max_iterations = state.current_goal.max_iterations
    current = state.current_iteration

    return current >= max_iterations


def check_repeated_failure(
    state: AutonomousState,
    threshold: int = DEFAULT_REPEATED_FAILURE_THRESHOLD,
) -> bool:
    """Check if repeated failures have been detected.

    Evaluates whether the last N iterations have all failed. If so,
    execution should stop to avoid wasting resources.

    Args:
        state: The current autonomous state.
        threshold: Number of consecutive failures to trigger.

    Returns:
        True if repeated failures detected, False otherwise.
    """
    if not state.completed_iterations:
        return False

    if len(state.completed_iterations) < threshold:
        return False

    # Check the last N iterations for consecutive failures.
    recent = state.completed_iterations[-threshold:]

    for iteration in recent:
        status = getattr(iteration, "status", None)
        if status is None:
            return False

        status_str = (
            status.value
            if hasattr(status, "value")
            else str(status)
        )
        if status_str != IterationStatus.FAILED:
            return False

    return True


def check_policy_request_stop(
    state: AutonomousState,
    last_iteration: Any | None = None,
) -> bool:
    """Check if any policy has requested a stop.

    Evaluates whether the most recent iteration resulted in a policy
    decision to stop execution.

    Args:
        state: The current autonomous state.
        last_iteration: The most recent iteration record, or None.

    Returns:
        True if a policy requested stop, False otherwise.
    """
    if last_iteration is None:
        return False

    # Check if the iteration metadata contains a policy stop request.
    metadata = getattr(last_iteration, "metadata", {})
    if metadata:
        policy_stop = metadata.get("policy_stop", False)
        if policy_stop:
            return True

    return False


def check_all_stopping_conditions(
    state: AutonomousState,
    last_iteration: Any | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Check all stopping conditions and return results.

    This is the main entry point for stopping condition evaluation.
    It checks all conditions and returns whether execution should stop
    along with the reasons.

    Args:
        state: The current autonomous state.
        last_iteration: The most recent iteration record, or None.

    Returns:
        Tuple of (should_stop, tuple of reasons).
    """
    reasons: list[str] = []

    if check_goal_achieved(state):
        reasons.append("Goal achieved — success criteria met.")

    if check_verification_successful(state):
        reasons.append("Verification successful.")

    if check_max_iterations_reached(state):
        reasons.append(
            f"Maximum iterations reached ({state.current_iteration})."
        )

    if check_repeated_failure(state):
        reasons.append("Repeated failures detected.")

    if check_policy_request_stop(state, last_iteration):
        reasons.append("Policy requested stop.")

    should_stop = len(reasons) > 0
    return should_stop, tuple(reasons)