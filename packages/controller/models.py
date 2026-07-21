"""Controller models — Request and Result definitions.

Defines all data structures used by the Engineering Controller. These are
the stable contracts between external consumers and the platform.

Architecture
------------

EngineeringRequest
       │
       ▼
EngineeringController
       │
       ▼
EngineeringResult

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

    from packages.controller import (
        EngineeringRequest,
        EngineeringResult,
        OperationType,
        RequestValidationResult,
    )

    request = EngineeringRequest(
        request_id="req-001",
        operation=OperationType.EXECUTE,
        description="Fix the bug in module X",
    )

    result = controller.execute(request)

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

__all__ = [
    # Models
    "EngineeringRequest",
    "EngineeringResult",
    "OperationType",
    "RequestValidationResult",
    "ValidationSeverity",
    "ValidationStatus",
]


# ---------------------------------------------------------------------------
# ValidationStatus
# ---------------------------------------------------------------------------


class ValidationStatus(str, Enum):
    """Status of a request validation.

    Attributes:
        VALID: Request is valid and can be processed.
        INVALID: Request has errors and cannot be processed.
        WARNING: Request has warnings but can still be processed.
    """

    VALID = "VALID"
    INVALID = "INVALID"
    WARNING = "WARNING"


# ---------------------------------------------------------------------------
# ValidationSeverity
# ---------------------------------------------------------------------------


class ValidationSeverity(str, Enum):
    """Severity level of a validation issue.

    Attributes:
        ERROR: Critical issue that prevents processing.
        WARNING: Non-critical issue that should be noted.
        INFO: Informational message.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


# ---------------------------------------------------------------------------
# RequestValidationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RequestValidationResult:
    """Validation result for an engineering request.

    Attributes:
        status: Validation status (VALID, INVALID, WARNING).
        errors: List of error messages.
        warnings: List of warning messages.
        metadata: Additional validation metadata.
    """

    status: ValidationStatus = ValidationStatus.VALID
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# OperationType
# ---------------------------------------------------------------------------


class OperationType(str, Enum):
    """Type of engineering operation.

    Attributes:
        EXECUTE: General engineering execution.
        REVIEW: Code review operation.
        IMPLEMENT: Feature implementation.
        REFACTOR: Code refactoring.
        DEBUG: Bug investigation and debugging.
        EXPLAIN: Code explanation (read-only).
    """

    EXECUTE = "execute"
    REVIEW = "review"
    IMPLEMENT = "implement"
    REFACTOR = "refactor"
    DEBUG = "debug"
    EXPLAIN = "explain"


# ---------------------------------------------------------------------------
# EngineeringRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EngineeringRequest:
    """Canonical engineering request that flows through the controller.

    This is the ONLY input structure that external consumers interact with.
    All operations (execute, review, implement, refactor, debug, explain)
    accept this same request structure.

    The controller maps operation types to appropriate workflows internally.

    Attributes:
        request_id: Unique request identifier.
        operation: Type of operation to perform.
        description: Human-readable description of the engineering task.
        workspace_path: Target workspace path (empty for read-only operations).
        workflow_name: Optional specific workflow to use (empty for auto-select).
        context: Additional context (files, code snippets, constraints).
        metadata: Free-form metadata for extensibility.
    """

    request_id: str
    operation: OperationType
    description: str
    workspace_path: str = ""
    workflow_name: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# EngineeringResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EngineeringResult:
    """Canonical result returned by every controller operation.

    Contains all artifacts produced during an engineering operation.
    This becomes the single source of truth for consumers.

    Attributes:
        request_id: Associated request identifier.
        session_id: Associated session identifier.
        operation: Operation that was performed.
        status: Final operation status (SUCCESS, FAILED, PARTIAL).
        workflow_plan: Generated workflow plan (if applicable).
        execution_report: Execution report (if applicable).
        evaluation_report: Evaluation report (if applicable).
        patch_set: Generated patch set (if applicable).
        workspace_changes: Applied workspace changes (if applicable).
        verification_report: Self-verification report (if applicable).
        final_report: Final engineering report (if applicable).
        telemetry: Telemetry data collected during execution (if applicable).
        error_message: Error message if operation failed.
        created_at: ISO format timestamp when the result was created.
    """

    request_id: str
    session_id: str
    operation: OperationType
    status: str = "SUCCESS"
    workflow_plan: Any = None
    execution_report: Any = None
    evaluation_report: Any = None
    patch_set: Any = None
    workspace_changes: Any = None
    verification_report: Any = None
    final_report: Any = None
    telemetry: Any = None
    error_message: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )