"""Deterministic execution policies.

Implements stateless deterministic execution policies that govern how the
AutonomousEngine iterates through workflows. Each policy is stateless and
deterministic.

Architecture
------------

Policy (ABC) --> Built-in Policies
                    |-- SequentialPolicy
                    |-- StopOnFailurePolicy
                    |-- VerificationGatePolicy
                    |-- MaximumIterationPolicy

Responsibilities
----------------

- Evaluate execution state deterministically.
- Return policy decisions without side effects.
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

    from packages.autonomous.policy import (
        SequentialPolicy,
        StopOnFailurePolicy,
        VerificationGatePolicy,
        MaximumIterationPolicy,
        PolicyDecision,
        PolicyResult,
    )

    decision = SequentialPolicy.evaluate(state, iteration)

"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from packages.autonomous.models import AutonomousState, IterationStatus

__all__ = [
    "MaximumIterationPolicy",
    "PolicyDecision",
    "PolicyResult",
    "SequentialPolicy",
    "StopOnFailurePolicy",
    "VerificationGatePolicy",
]


# ---------------------------------------------------------------------------
# PolicyDecision
# ---------------------------------------------------------------------------


class PolicyDecision(str):
    """Decision made by a policy evaluation.

    Attributes:
        CONTINUE: Continue execution normally.
        STOP: Stop execution immediately.
        SKIP: Skip the current iteration.
    """

    CONTINUE = "CONTINUE"
    STOP = "STOP"
    SKIP = "SKIP"


# ---------------------------------------------------------------------------
# PolicyResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PolicyResult:
    """Immutable result of a policy evaluation.

    Attributes:
        decision: The policy decision (CONTINUE, STOP, SKIP).
        reason: Human-readable reason for the decision.
        metadata: Additional metadata about the decision.
    """

    decision: PolicyDecision
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Policy (Abstract Base Class)
# ---------------------------------------------------------------------------


class Policy(ABC):
    """Abstract base class for all autonomous policies.

    Each policy is stateless and deterministic. Policies consume only
    public engineering artifacts and produce PolicyResult.

    Attributes:
        policy_id: Unique identifier for the policy.
    """

    @property
    def policy_id(self) -> str:
        """Unique identifier for the policy."""
        return self.__class__.__name__

    @abstractmethod
    def evaluate(
        self,
        state: AutonomousState,
        last_iteration: Any | None = None,
    ) -> PolicyResult:
        """Evaluate the current state and return a policy result.

        Args:
            state: The current autonomous state.
            last_iteration: The most recent iteration record, or None.

        Returns:
            A PolicyResult with the decision.
        """
        ...


# ---------------------------------------------------------------------------
# SequentialPolicy
# ---------------------------------------------------------------------------


class SequentialPolicy(Policy):
    """Sequential execution policy.

    Always allows execution to continue. This is the default policy
    that permits all iterations to proceed sequentially.

    Usage
    -----

    .. code-block:: python

        from packages.autonomous.policy import SequentialPolicy

        policy = SequentialPolicy()
        result = policy.evaluate(state)

    """

    def evaluate(
        self,
        state: AutonomousState,
        last_iteration: Any | None = None,
    ) -> PolicyResult:
        """Always allow execution to continue.

        Args:
            state: The current autonomous state.
            last_iteration: The most recent iteration record, or None.

        Returns:
            PolicyResult with CONTINUE decision.
        """
        return PolicyResult(
            decision=PolicyDecision.CONTINUE,
            reason="Sequential policy: always allow execution.",
        )


# ---------------------------------------------------------------------------
# StopOnFailurePolicy
# ---------------------------------------------------------------------------


class StopOnFailurePolicy(Policy):
    """Stop on failure policy.

    Stops execution when the last iteration failed. If the last iteration
    status is FAILED the policy returns STOP; otherwise CONTINUE.

    Usage
    -----

    .. code-block:: python

        from packages.autonomous.policy import StopOnFailurePolicy

        policy = StopOnFailurePolicy()
        result = policy.evaluate(state, last_iteration)

    """

    def evaluate(
        self,
        state: AutonomousState,
        last_iteration: Any | None = None,
    ) -> PolicyResult:
        """Check if the last iteration failed.

        Args:
            state: The current autonomous state.
            last_iteration: The most recent iteration record, or None.

        Returns:
            PolicyResult with STOP if last iteration failed, CONTINUE otherwise.
        """
        if last_iteration is None:
            return PolicyResult(
                decision=PolicyDecision.CONTINUE,
                reason="StopOnFailure: no last iteration to check.",
            )

        status = getattr(last_iteration, "status", None)
        if status is None:
            return PolicyResult(
                decision=PolicyDecision.CONTINUE,
                reason="StopOnFailure: last iteration status unknown.",
            )

        # Check for failed status.
        failed = False
        if isinstance(status, IterationStatus):
            failed = status == IterationStatus.FAILED
        elif isinstance(status, str):
            failed = status == IterationStatus.FAILED
        else:
            failed = str(status) == IterationStatus.FAILED

        if failed:
            return PolicyResult(
                decision=PolicyDecision.STOP,
                reason=(
                    "StopOnFailure: last iteration failed. "
                    f"Status: {status}. Summary: {getattr(last_iteration, 'result_summary', '')}."
                ),
            )

        return PolicyResult(
            decision=PolicyDecision.CONTINUE,
            reason="StopOnFailure: last iteration did not fail.",
        )


# ---------------------------------------------------------------------------
# VerificationGatePolicy
# ---------------------------------------------------------------------------


class VerificationGatePolicy(Policy):
    """Verification gate policy.

    Requires that the verification status indicates success before
    allowing the next iteration. If the verification status indicates
    failure the policy returns STOP.

    Usage
    -----

    .. code-block:: python

        from packages.autonomous.policy import VerificationGatePolicy

        policy = VerificationGatePolicy()
        result = policy.evaluate(state, last_iteration)

    """

    # Verification statuses that indicate success.
    _SUCCESS_STATUSES: tuple[str, ...] = (
        "PASSED",
        "COMPLETED",
        "SUCCESS",
    )

    def evaluate(
        self,
        state: AutonomousState,
        last_iteration: Any | None = None,
    ) -> PolicyResult:
        """Check if verification passed.

        Args:
            state: The current autonomous state.
            last_iteration: The most recent iteration record, or None.

        Returns:
            PolicyResult with STOP if verification failed, CONTINUE otherwise.
        """
        if last_iteration is None:
            return PolicyResult(
                decision=PolicyDecision.CONTINUE,
                reason="VerificationGate: no last iteration to check.",
            )

        verification_status = getattr(
            last_iteration, "verification_status", ""
        )

        if not verification_status:
            return PolicyResult(
                decision=PolicyDecision.STOP,
                reason=(
                    "VerificationGate: verification status is empty. "
                    "Cannot proceed without verification."
                ),
            )

        # Check if verification status indicates success.
        is_success = False
        for success_status in self._SUCCESS_STATUSES:
            if verification_status == success_status:
                is_success = True
                break

        if not is_success:
            return PolicyResult(
                decision=PolicyDecision.STOP,
                reason=(
                    f"VerificationGate: verification status is '{verification_status}'. "
                    f"Expected one of: {', '.join(self._SUCCESS_STATUSES)}."
                ),
            )

        return PolicyResult(
            decision=PolicyDecision.CONTINUE,
            reason=(
                f"VerificationGate: verification status is '{verification_status}'."
            ),
        )


# ---------------------------------------------------------------------------
# MaximumIterationPolicy
# ---------------------------------------------------------------------------


class MaximumIterationPolicy(Policy):
    """Maximum iteration policy.

    Stops execution when the current iteration count reaches or exceeds
    the goal's maximum iteration limit.

    Usage
    -----

    .. code-block:: python

        from packages.autonomous.policy import MaximumIterationPolicy

        policy = MaximumIterationPolicy()
        result = policy.evaluate(state, last_iteration)

    """

    def evaluate(
        self,
        state: AutonomousState,
        last_iteration: Any | None = None,
    ) -> PolicyResult:
        """Check if max iterations have been reached.

        Args:
            state: The current autonomous state.
            last_iteration: The most recent iteration record, or None.

        Returns:
            PolicyResult with STOP if max iterations reached, CONTINUE otherwise.
        """
        max_iterations = state.current_goal.max_iterations
        current = state.current_iteration

        if current >= max_iterations:
            return PolicyResult(
                decision=PolicyDecision.STOP,
                reason=(
                    f"MaximumIterationPolicy: reached max iterations "
                    f"({current}/{max_iterations})."
                ),
            )

        return PolicyResult(
            decision=PolicyDecision.CONTINUE,
            reason=(
                f"MaximumIterationPolicy: {current}/{max_iterations} iterations used."
            ),
        )