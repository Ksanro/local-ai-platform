"""Deterministic lifecycle validation for engineering sessions.

Implements a strict state machine for session lifecycle transitions.
Invalid transitions are rejected with explicit errors.

Architecture
------------

CREATED --> PLANNING --> EXECUTING --> VERIFYING --> COMPLETED
   |           |            |            |
   v           v            v            v
 FAILED       FAILED       FAILED       FAILED
   |
 CANCELLED (terminal)

Constraints
-----------

- Invalid transitions raise LifecycleError.
- FAILED and CANCELLED are terminal states.
- Updated timestamp is refreshed on every transition.

Public API
----------

.. code-block:: python

    from packages.session.lifecycle import (
        LifecycleError,
        validate_transition,
        transition,
    )

    session = EngineeringSession(...)
    session = transition(session, SessionStatus.PLANNING)

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from packages.session.models import EngineeringSession, SessionStatus

if TYPE_CHECKING:
    from typing import Set

__all__ = [
    "LifecycleError",
    "validate_transition",
    "transition",
]


# ---------------------------------------------------------------------------
# LifecycleError
# ---------------------------------------------------------------------------


class LifecycleError(Exception):
    """Raised when an invalid lifecycle transition is attempted.

    Attributes:
        current: The current session status.
        target: The attempted target status.
    """

    def __init__(self, current: SessionStatus, target: SessionStatus) -> None:
        message = (
            f"Invalid lifecycle transition: {current.value} -> {target.value}. "
            f"Current status '{current.value}' does not allow transition to '{target.value}'."
        )
        super().__init__(message)
        self.current = current
        self.target = target


# ---------------------------------------------------------------------------
# Allowed Transitions
# ---------------------------------------------------------------------------

# Type annotation for the transitions dict.
# _ALLOWED_TRANSITIONS maps each current status to the set of allowed
# target statuses. Terminal states (FAILED, CANCELLED) map to empty sets.

_ALLOWED_TRANSITIONS: dict[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.CREATED: frozenset({
        SessionStatus.PLANNING,
        SessionStatus.FAILED,
        SessionStatus.CANCELLED,
    }),
    SessionStatus.PLANNING: frozenset({
        SessionStatus.EXECUTING,
        SessionStatus.FAILED,
        SessionStatus.CANCELLED,
    }),
    SessionStatus.EXECUTING: frozenset({
        SessionStatus.VERIFYING,
        SessionStatus.FAILED,
        SessionStatus.CANCELLED,
    }),
    SessionStatus.VERIFYING: frozenset({
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
        SessionStatus.CANCELLED,
    }),
    SessionStatus.COMPLETED: frozenset(),
    SessionStatus.FAILED: frozenset(),
    SessionStatus.CANCELLED: frozenset(),
}


# ---------------------------------------------------------------------------
# validate_transition
# ---------------------------------------------------------------------------


def validate_transition(current: SessionStatus, target: SessionStatus) -> bool:
    """Validate whether a lifecycle transition is allowed.

    Checks if transitioning from `current` status to `target` status
    is permitted by the state machine.

    Args:
        current: The current session status.
        target: The desired target status.

    Returns:
        True if the transition is allowed.

    Raises:
        LifecycleError: If the transition is not allowed.
    """
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise LifecycleError(current, target)
    return True


# ---------------------------------------------------------------------------
# transition
# ---------------------------------------------------------------------------


def transition(
    session: EngineeringSession,
    new_status: SessionStatus,
) -> EngineeringSession:
    """Transition a session to a new status with validation.

    Validates the lifecycle transition and returns a new EngineeringSession
    with the updated status and refreshed updated_at timestamp.

    Args:
        session: The current session state.
        new_status: The desired target status.

    Returns:
        A new EngineeringSession with the updated status.

    Raises:
        LifecycleError: If the transition is not allowed.
    """
    validate_transition(session.status, new_status)

    return EngineeringSession(
        session_id=session.session_id,
        request_id=session.request_id,
        status=new_status,
        created_at=session.created_at,
        updated_at=datetime.now(timezone.utc).isoformat(),
        workflow_name=session.workflow_name,
        execution_id=session.execution_id,
        evaluation_id=session.evaluation_id,
        verification_id=session.verification_id,
        metadata=dict(session.metadata),
    )