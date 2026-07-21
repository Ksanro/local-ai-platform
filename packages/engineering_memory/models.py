"""Engineering Memory models — Session record and statistics definitions.

Defines all data structures used by the Engineering Memory subsystem.
These are the stable contracts for storing and querying engineering session
facts without using embeddings, vector databases, or semantic search.

Architecture
------------

EngineeringSessionRecord
       │
       ▼
EngineeringMemory
       │
       ├── store(record)
       ├── find_session(session_id)
       ├── find_by_workflow(workflow_name)
       ├── find_successful()
       ├── find_failed()
       ├── find_by_module(module_name)
       ├── recent(limit)
       ├── statistics()
       └── list_sessions()

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No file system operations.
- No provider fields.
- No repository analysis fields.
- No embeddings.
- No semantic search.
- No vector database.

Public API
----------

.. code-block:: python

    from packages.engineering_memory.models import (
        EngineeringSessionRecord,
        MemoryStatistics,
    )

    record = EngineeringSessionRecord(
        session_id="sess-001",
        workflow_name="bug-fix",
        request_summary="Fix null pointer in ModuleX",
        transaction_id="txn-001",
        execution_report={"status": "COMPLETED"},
        verification_report={"status": "PASSED"},
        evaluation_report={"overall_score": 0.9},
        controller_decision="COMPLETE",
        completed_at="2026-07-21T14:55:00+00:00",
        metadata={},
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    # Models
    "EngineeringSessionRecord",
    "MemoryStatistics",
]


# ---------------------------------------------------------------------------
# EngineeringSessionRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EngineeringSessionRecord:
    """Immutable record of a completed engineering session.

    This is the canonical fact stored in Engineering Memory. It contains
    only deterministic, serializable data from a completed session.

    Attributes:
        session_id: Unique session identifier.
        workflow_name: Name of the workflow executed.
        request_summary: Human-readable description of the engineering task.
        transaction_id: Associated transaction identifier.
        execution_report: Serialized execution report (dict, not mutable object).
        verification_report: Serialized verification report (dict, not mutable object).
        evaluation_report: Serialized evaluation report (dict, not mutable object).
        controller_decision: Final controller decision (COMPLETE, RETRY, REQUEST_REVIEW, FAIL).
        completed_at: ISO format timestamp when the session completed.
        metadata: Free-form metadata for extensibility.
    """

    session_id: str
    workflow_name: str
    request_summary: str
    transaction_id: str
    execution_report: dict[str, Any] = field(default_factory=dict)
    verification_report: dict[str, Any] = field(default_factory=dict)
    evaluation_report: dict[str, Any] = field(default_factory=dict)
    controller_decision: str = "COMPLETE"
    completed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    # -------------------------------------------------------------------
    # Module extraction
    # -------------------------------------------------------------------

    @property
    def modified_modules(self) -> tuple[str, ...]:
        """Extract modified module names from metadata.

        Returns:
            Tuple of module names sorted alphabetically.
        """
        modules = self.metadata.get("modified_modules", [])
        if isinstance(modules, list):
            return tuple(sorted(set(str(m) for m in modules)))
        if isinstance(modules, tuple):
            return tuple(sorted(set(str(m) for m in modules)))
        if isinstance(modules, str):
            return tuple(sorted({modules}))
        return ()

    @property
    def evaluation_score(self) -> float | None:
        """Extract the overall evaluation score if available.

        Returns:
            The overall_score field from evaluation_report, or None if not present.
        """
        score = self.evaluation_report.get("overall_score")
        if score is not None:
            try:
                return float(score)
            except (TypeError, ValueError):
                return None
        return None

    @property
    def iteration_count(self) -> int:
        """Extract the iteration count from metadata.

        Returns:
            The iteration count, or 0 if not present.
        """
        count = self.metadata.get("iteration_count", 0)
        try:
            return int(count)
        except (TypeError, ValueError):
            return 0

    # -------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the record to a dictionary.

        Returns:
            Dictionary representation of the record.
        """
        return {
            "session_id": self.session_id,
            "workflow_name": self.workflow_name,
            "request_summary": self.request_summary,
            "transaction_id": self.transaction_id,
            "execution_report": self.execution_report,
            "verification_report": self.verification_report,
            "evaluation_report": self.evaluation_report,
            "controller_decision": self.controller_decision,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EngineeringSessionRecord:
        """Create a record from a dictionary.

        Args:
            data: Dictionary containing record fields.

        Returns:
            A new EngineeringSessionRecord.

        Raises:
            ValueError: If required fields are missing.
        """
        required_fields = [
            "session_id",
            "workflow_name",
            "request_summary",
            "transaction_id",
            "controller_decision",
            "completed_at",
        ]
        for field_name in required_fields:
            if field_name not in data:
                raise ValueError(
                    f"Missing required field: {field_name}"
                )

        return cls(
            session_id=data["session_id"],
            workflow_name=data["workflow_name"],
            request_summary=data["request_summary"],
            transaction_id=data["transaction_id"],
            execution_report=data.get("execution_report", {}),
            verification_report=data.get("verification_report", {}),
            evaluation_report=data.get("evaluation_report", {}),
            controller_decision=data.get("controller_decision", "COMPLETE"),
            completed_at=data.get("completed_at", datetime.now(timezone.utc).isoformat()),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# MemoryStatistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MemoryStatistics:
    """Statistics about stored engineering sessions.

    Attributes:
        total_sessions: Total number of stored sessions.
        successful_sessions: Number of sessions with COMPLETE decision.
        failed_sessions: Number of sessions with non-COMPLETE decision.
        average_evaluation_score: Average evaluation score across all sessions.
        average_iterations: Average iteration count across all sessions.
        workflow_usage: Mapping of workflow names to session counts.
    """

    total_sessions: int = 0
    successful_sessions: int = 0
    failed_sessions: int = 0
    average_evaluation_score: float = 0.0
    average_iterations: float = 0.0
    workflow_usage: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Calculate the success rate.

        Returns:
            Ratio of successful sessions to total (0.0 to 1.0).
            Returns 0.0 if no sessions exist.
        """
        if self.total_sessions == 0:
            return 0.0
        return self.successful_sessions / self.total_sessions