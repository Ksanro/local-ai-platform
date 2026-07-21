"""Immutable session model definitions.

Defines all data structures used by the Engineering Session Framework. These are
the stable contracts between the session manager and its consumers.

Architecture
------------

EngineeringRequest
       |
       v
EngineeringSession
       |
       ├── WorkflowPlan
       ├── ExecutionPlan
       ├── EvaluationReport
       ├── PatchSet
       ├── WorkspaceChanges
       ├── VerificationReport
       ├── Telemetry
       └── FinalEngineeringReport

Everything belongs to one Session.

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No file system operations.
- No platform logic fields.
- No provider fields.
- No repository analysis fields.

Public API
----------

.. code-block:: python

    from packages.session.models import (
        EngineeringSession,
        SessionArtifact,
        SessionSnapshot,
        SessionStatistics,
        SessionStatus,
    )

    session = EngineeringSession(
        session_id="sess-001",
        request_id="req-001",
        status=SessionStatus.CREATED,
        workflow_name="bug-investigation",
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

__all__ = [
    "EngineeringSession",
    "SessionArtifact",
    "SessionSnapshot",
    "SessionStatistics",
    "SessionStatus",
]


# ---------------------------------------------------------------------------
# SessionStatus
# ---------------------------------------------------------------------------


class SessionStatus(str, Enum):
    """Status of an engineering session.

    Attributes:
        CREATED: Session has been created but not yet started.
        PLANNING: Session is in the planning phase.
        EXECUTING: Session is actively executing.
        VERIFYING: Session is in the verification phase.
        COMPLETED: Session has completed successfully.
        FAILED: Session failed due to an error.
        CANCELLED: Session was cancelled.
    """

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# EngineeringSession
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EngineeringSession:
    """Immutable engineering session definition.

    The Session owns every artifact produced during execution.
    It is the root object for future UI, CLI, IDE integration
    and long-running engineering work.

    It NEVER performs engineering work.
    It NEVER invokes providers.
    It NEVER performs repository analysis.
    It ONLY coordinates lifecycle.

    Attributes:
        session_id: Unique session identifier.
        request_id: Associated request identifier.
        status: Current session status.
        created_at: ISO format timestamp when the session was created.
        updated_at: ISO format timestamp of the last update.
        workflow_name: Name of the workflow associated with this session.
        execution_id: Associated execution identifier.
        evaluation_id: Associated evaluation identifier.
        verification_id: Associated verification identifier.
        metadata: Additional metadata about the session.
    """

    session_id: str
    request_id: str
    status: SessionStatus
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    workflow_name: str = ""
    execution_id: str = ""
    evaluation_id: str = ""
    verification_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SessionArtifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SessionArtifact:
    """Immutable record of a session artifact.

    Attributes:
        artifact_type: Type of artifact (e.g. "WorkflowPlan", "PatchSet").
        artifact_id: Unique artifact identifier.
        created_at: ISO format timestamp when the artifact was created.
        metadata: Additional artifact-specific metadata.
    """

    artifact_type: str
    artifact_id: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SessionStatistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SessionStatistics:
    """Aggregate statistics for a session.

    Attributes:
        workflows: Total number of workflows executed.
        executions: Total number of executions.
        evaluations: Total number of evaluations.
        patches: Total number of patches generated.
        modifications: Total number of code modifications.
        verifications: Total number of verifications.
        duration_ms: Total session duration in milliseconds.
    """

    workflows: int = 0
    executions: int = 0
    evaluations: int = 0
    patches: int = 0
    modifications: int = 0
    verifications: int = 0
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# SessionSnapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Immutable snapshot of a session at a point in time.

    A deterministic, point-in-time view of the session state.

    Attributes:
        session: The engineering session.
        artifacts: Tuple of all session artifacts.
        statistics: Session execution statistics.
    """

    session: EngineeringSession
    artifacts: tuple[SessionArtifact, ...] = field(default_factory=tuple)
    statistics: SessionStatistics = field(default_factory=SessionStatistics)