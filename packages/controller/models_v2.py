"""Controller v2 models — Request, Result, and Session definitions.

Defines all data structures used by the Engineering Controller v2. These are
the stable contracts for the autonomous engineering session control loop.

Architecture
------------

EngineeringRequest
       │
       ▼
EngineeringControllerV2
       │
       ├── WorkflowEngine   (public API)
       ├── ExecutionEngine  (public API)
       ├── Verification     (public API)
       ├── Evaluation       (public API)
       │
       ▼
EngineeringResultV2

Everything belongs to one EngineeringSessionV2.

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

    from packages.controller.models_v2 import (
        ControllerConfig,
        ControllerDecision,
        ControllerReport,
        EngineeringRequestV2,
        EngineeringResultV2,
        EngineeringSessionV2,
        SessionHistoryEntry,
    )

    config = ControllerConfig()
    session = EngineeringSessionV2.create(session_id="sess-001", request_id="req-001")

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

__all__ = [
    # Enums
    "ControllerDecision",
    "SessionStatusV2",
    # Config
    "ControllerConfig",
    # Reports
    "ControllerReport",
    # Requests
    "EngineeringRequestV2",
    # Results
    "EngineeringResultV2",
    # Session
    "EngineeringSessionV2",
    "SessionHistoryEntry",
]


# ---------------------------------------------------------------------------
# SessionStatusV2
# ---------------------------------------------------------------------------


class SessionStatusV2(str, Enum):
    """Status of an engineering session v2.

    Attributes:
        ACTIVE: Session is actively running.
        COMPLETED: Session completed successfully.
        REVIEW_REQUIRED: Session requires human review.
        FAILED: Session failed unrecoverably.
        CANCELLED: Session was cancelled.
    """

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# ControllerDecision
# ---------------------------------------------------------------------------


class ControllerDecision(str, Enum):
    """Deterministic controller decision outcomes.

    Attributes:
        COMPLETE: All checks passed, session is complete.
        RETRY: Retry the workflow execution loop.
        REQUEST_REVIEW: Human review is required.
        FAIL: Unrecoverable failure, terminate session.
    """

    COMPLETE = "COMPLETE"
    RETRY = "RETRY"
    REQUEST_REVIEW = "REQUEST_REVIEW"
    FAIL = "FAIL"


# ---------------------------------------------------------------------------
# ControllerConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ControllerConfig:
    """Configurable thresholds and policies for the controller loop.

    Attributes:
        evaluation_threshold: Minimum evaluation score for COMPLETE decision.
        max_retries: Maximum number of retry attempts.
        max_iterations: Maximum total iterations (planning + retries).
        verification_required: Whether verification must pass for COMPLETE.
        auto_review_threshold: Evaluation score below this triggers REQUEST_REVIEW.
    """

    evaluation_threshold: float = 0.7
    max_retries: int = 3
    max_iterations: int = 10
    verification_required: bool = True
    auto_review_threshold: float = 0.5


# ---------------------------------------------------------------------------
# ControllerReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ControllerReport:
    """Record of a single controller decision.

    Attributes:
        decision: The decision made by the controller.
        reason: Human-readable explanation of the decision.
        iteration: Current iteration number (1-based).
        retry_count: Current retry count.
        evaluation_score: Evaluation score used for decision (None if not available).
        verification_score: Verification score used for decision (None if not available).
        created_at: ISO format timestamp when the decision was made.
    """

    decision: ControllerDecision
    reason: str
    iteration: int
    retry_count: int
    evaluation_score: float | None = None
    verification_score: float | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# EngineeringRequestV2
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EngineeringRequestV2:
    """Engineering request for the v2 controller.

    This is the input to the EngineeringControllerV2. It carries the
    operation type, description, and optional configuration.

    Attributes:
        request_id: Unique request identifier.
        operation: Type of operation to perform.
        description: Human-readable description of the engineering task.
        workspace_path: Target workspace path (empty for read-only operations).
        workflow_name: Optional specific workflow to use (empty for auto-select).
        context: Additional context (files, code snippets, constraints).
        metadata: Free-form metadata for extensibility.
        config: Optional controller configuration override.
    """

    request_id: str
    operation: Any  # OperationType from packages.controller.models
    description: str
    workspace_path: str = ""
    workflow_name: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    config: ControllerConfig | None = None


# ---------------------------------------------------------------------------
# SessionHistoryEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SessionHistoryEntry:
    """Record of a single iteration in the session history.

    Attributes:
        iteration: Iteration number (1-based).
        workflow_name: Name of the workflow executed.
        workflow_plan: Generated workflow plan (if applicable).
        execution_report: Execution report (if applicable).
        verification_report: Verification report (if applicable).
        evaluation_report: Evaluation report (if applicable).
        controller_report: Controller decision report.
        created_at: ISO format timestamp when the iteration completed.
    """

    iteration: int
    workflow_name: str
    workflow_plan: Any = None
    execution_report: Any = None
    verification_report: Any = None
    evaluation_report: Any = None
    controller_report: ControllerReport | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# EngineeringSessionV2
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EngineeringSessionV2:
    """Immutable engineering session with full history tracking.

    The session owns every artifact produced during execution.
    It is the root object for session lifecycle and history.

    It NEVER performs engineering work.
    It NEVER invokes providers.
    It NEVER performs repository analysis.
    It ONLY tracks state and history.

    Attributes:
        session_id: Unique session identifier.
        request_id: Associated request identifier.
        status: Current session status.
        iteration: Current iteration number (1-based, includes retries).
        max_iterations: Maximum allowed iterations.
        retry_count: Current retry count.
        max_retries: Maximum allowed retries.
        history: Tuple of completed iteration history entries.
        created_at: ISO format timestamp when the session was created.
        updated_at: ISO format timestamp of the last update.
        metadata: Additional metadata about the session.
    """

    session_id: str
    request_id: str
    status: SessionStatusV2
    iteration: int = 0
    max_iterations: int = 10
    retry_count: int = 0
    max_retries: int = 3
    history: tuple[SessionHistoryEntry, ...] = field(default_factory=tuple)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    # -----------------------------------------------------------------------
    # Factory
    # -----------------------------------------------------------------------

    @staticmethod
    def create(
        session_id: str,
        request_id: str,
        config: ControllerConfig | None = None,
    ) -> EngineeringSessionV2:
        """Create a new engineering session.

        Args:
            session_id: Unique session identifier.
            request_id: Associated request identifier.
            config: Optional controller configuration.

        Returns:
            A new EngineeringSessionV2 in ACTIVE status.
        """
        cfg = config or ControllerConfig()
        return EngineeringSessionV2(
            session_id=session_id,
            request_id=request_id,
            status=SessionStatusV2.ACTIVE,
            iteration=0,
            max_iterations=cfg.max_iterations,
            retry_count=0,
            max_retries=cfg.max_retries,
            history=(),
            metadata={},
        )

    # -----------------------------------------------------------------------
    # Immutable state transitions
    # -----------------------------------------------------------------------

    def with_iteration(self, iteration: int) -> EngineeringSessionV2:
        """Return a new session with updated iteration.

        Args:
            iteration: New iteration number.

        Returns:
            A new EngineeringSessionV2 with updated iteration.
        """
        return EngineeringSessionV2(
            session_id=self.session_id,
            request_id=self.request_id,
            status=self.status,
            iteration=iteration,
            max_iterations=self.max_iterations,
            retry_count=self.retry_count,
            max_retries=self.max_retries,
            history=self.history,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(self.metadata),
        )

    def with_retry_count(self, retry_count: int) -> EngineeringSessionV2:
        """Return a new session with updated retry count.

        Args:
            retry_count: New retry count.

        Returns:
            A new EngineeringSessionV2 with updated retry count.
        """
        return EngineeringSessionV2(
            session_id=self.session_id,
            request_id=self.request_id,
            status=self.status,
            iteration=self.iteration,
            max_iterations=self.max_iterations,
            retry_count=retry_count,
            max_retries=self.max_retries,
            history=self.history,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(self.metadata),
        )

    def with_status(self, status: SessionStatusV2) -> EngineeringSessionV2:
        """Return a new session with updated status.

        Args:
            status: New session status.

        Returns:
            A new EngineeringSessionV2 with updated status.
        """
        return EngineeringSessionV2(
            session_id=self.session_id,
            request_id=self.request_id,
            status=status,
            iteration=self.iteration,
            max_iterations=self.max_iterations,
            retry_count=self.retry_count,
            max_retries=self.max_retries,
            history=self.history,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(self.metadata),
        )

    def append_history(self, entry: SessionHistoryEntry) -> EngineeringSessionV2:
        """Return a new session with an appended history entry.

        Args:
            entry: History entry to append.

        Returns:
            A new EngineeringSessionV2 with updated history.
        """
        return EngineeringSessionV2(
            session_id=self.session_id,
            request_id=self.request_id,
            status=self.status,
            iteration=self.iteration,
            max_iterations=self.max_iterations,
            retry_count=self.retry_count,
            max_retries=self.max_retries,
            history=self.history + (entry,),
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(self.metadata),
        )

    # -----------------------------------------------------------------------
    # Query methods
    # -----------------------------------------------------------------------

    @property
    def workflow_history(self) -> tuple[str, ...]:
        """Tuple of workflow names executed in order."""
        return tuple(entry.workflow_name for entry in self.history)

    @property
    def execution_reports(self) -> tuple[Any, ...]:
        """Tuple of all execution reports."""
        return tuple(entry.execution_report for entry in self.history if entry.execution_report is not None)

    @property
    def verification_reports(self) -> tuple[Any, ...]:
        """Tuple of all verification reports."""
        return tuple(entry.verification_report for entry in self.history if entry.verification_report is not None)

    @property
    def evaluation_reports(self) -> tuple[Any, ...]:
        """Tuple of all evaluation reports."""
        return tuple(entry.evaluation_report for entry in self.history if entry.evaluation_report is not None)

    @property
    def controller_decisions(self) -> tuple[ControllerReport, ...]:
        """Tuple of all controller reports."""
        return tuple(
            entry.controller_report for entry in self.history
            if entry.controller_report is not None
        )

    def snapshot(self) -> EngineeringSessionV2:
        """Return a point-in-time snapshot (self, since immutable).

        Returns:
            The same EngineeringSessionV2 instance.
        """
        return self


# ---------------------------------------------------------------------------
# EngineeringResultV2
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EngineeringResultV2:
    """Canonical result returned by the EngineeringControllerV2.

    Contains all artifacts produced during an engineering session.
    This becomes the single source of truth for consumers.

    Attributes:
        request_id: Associated request identifier.
        session_id: Associated session identifier.
        decision: Final controller decision.
        status: Final session status.
        workflow_plan: Generated workflow plan (from last iteration).
        execution_report: Execution report (from last iteration).
        verification_report: Verification report (from last iteration).
        evaluation_report: Evaluation report (from last iteration).
        session: The complete engineering session with full history.
        telemetry: Telemetry data collected during execution.
        error_message: Error message if operation failed.
        created_at: ISO format timestamp when the result was created.
    """

    request_id: str
    session_id: str
    decision: ControllerDecision
    status: SessionStatusV2
    session: EngineeringSessionV2
    workflow_plan: Any = None
    execution_report: Any = None
    verification_report: Any = None
    evaluation_report: Any = None
    telemetry: Any = None
    error_message: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )