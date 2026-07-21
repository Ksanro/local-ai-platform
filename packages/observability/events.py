"""Event model and categorization for the observability framework.

Defines the event categories and types that correspond to platform lifecycle
events. This module provides deterministic event classification.

Architecture
------------

EventCategory --> EventType --> TelemetryEvent

Constraints
-----------

- No mutable state.
- No file system operations.
- No platform logic.

Public API
----------

.. code-block:: python

    from packages.observability.events import (
        EventCategory,
        EventType,
        validate_event,
        create_event,
    )

    event = create_event(
        category=EventCategory.WORKFLOW,
        event_type=EventType.WORKFLOW_PLAN_GENERATED,
        correlation_id="req-001",
        metadata={"workflow_name": "bug-investigation"},
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "EventCategory",
    "EventType",
    "create_event",
    "validate_event",
]


# ---------------------------------------------------------------------------
# EventCategory
# ---------------------------------------------------------------------------


class EventCategory:
    """Event categories matching the platform lifecycle.

    Categories are ordered to support deterministic processing.

    Attributes:
        GATEWAY: Gateway-level events.
        PIPELINE: Pipeline processing events.
        WORKFLOW: Workflow engine events.
        EXECUTION: Execution engine events.
        PROVIDER: Provider interaction events.
        EVALUATION: Evaluation framework events.
        PATCH: Patch generator events.
        MODIFICATION: Code modification engine events.
        VERIFICATION: Self verification events.
        AUTONOMOUS: Autonomous engineering events.
        SYSTEM: System-level events.
    """

    GATEWAY = "gateway"
    PIPELINE = "pipeline"
    WORKFLOW = "workflow"
    EXECUTION = "execution"
    PROVIDER = "provider"
    EVALUATION = "evaluation"
    PATCH = "patch"
    MODIFICATION = "modification"
    VERIFICATION = "verification"
    AUTONOMOUS = "autonomous"
    SYSTEM = "system"

    ALL: tuple[str, ...] = (
        GATEWAY,
        PIPELINE,
        WORKFLOW,
        EXECUTION,
        PROVIDER,
        EVALUATION,
        PATCH,
        MODIFICATION,
        VERIFICATION,
        AUTONOMOUS,
        SYSTEM,
    )


# ---------------------------------------------------------------------------
# EventType
# ---------------------------------------------------------------------------


class EventType:
    """Event types for each category.

    Event types are deterministic strings that map to specific platform
    lifecycle events.

    Gateway Events
    ----------------
    GATEWAY_REQUEST: Incoming request received.
    GATEWAY_RESPONSE: Response sent.

    Pipeline Events
    ---------------
    PIPELINE_STAGE_START: Stage execution started.
    PIPELINE_STAGE_COMPLETE: Stage execution completed.
    PIPELINE_STAGE_FAILED: Stage execution failed.
    PIPELINE_COMPLETE: Pipeline execution completed.

    Workflow Events
    ---------------
    WORKFLOW_PLAN_GENERATED: Workflow plan generated.
    WORKFLOW_PLAN_EXECUTED: Workflow plan execution started.
    WORKFLOW_STEP_STARTED: Workflow step started.
    WORKFLOW_STEP_COMPLETED: Workflow step completed.
    WORKFLOW_COMPLETE: Workflow execution completed.

    Execution Events
    ----------------
    EXECUTION_STEP_START: Execution step started.
    EXECUTION_STEP_COMPLETE: Execution step completed.
    EXECUTION_COMPLETE: Execution completed.

    Provider Events
    ---------------
    PROVIDER_CALL: Provider API call made.
    PROVIDER_RESPONSE: Provider response received.
    PROVIDER_ERROR: Provider error occurred.

    Evaluation Events
    -----------------
    EVALUATION_STARTED: Evaluation started.
    EVALUATION_COMPLETED: Evaluation completed.

    Patch Events
    ------------
    PATCH_GENERATED: Patch set generated.
    PATCH_APPLIED: Patch set applied.

    Modification Events
    -------------------
    MODIFICATION_STARTED: Code modification started.
    MODIFICATION_COMPLETE: Code modification completed.

    Verification Events
    -------------------
    VERIFICATION_STARTED: Verification started.
    VERIFICATION_COMPLETED: Verification completed.

    Autonomous Events
    -----------------
    AUTONOMOUS_ITERATION_STARTED: Autonomous iteration started.
    AUTONOMOUS_ITERATION_COMPLETED: Autonomous iteration completed.
    AUTONOMOUS_GOAL_ACHIEVED: Engineering goal achieved.
    AUTONOMOUS_STOPPING_CONDITION: Stopping condition reached.

    System Events
    -------------
    SYSTEM_SNAPSHOT: System snapshot taken.
    SYSTEM_TELEMETY_RECORD: Telemetry recorded.
    """

    # Gateway
    GATEWAY_REQUEST = "gateway.request"
    GATEWAY_RESPONSE = "gateway.response"

    # Pipeline
    PIPELINE_STAGE_START = "pipeline.stage_start"
    PIPELINE_STAGE_COMPLETE = "pipeline.stage_complete"
    PIPELINE_STAGE_FAILED = "pipeline.stage_failed"
    PIPELINE_COMPLETE = "pipeline.complete"

    # Workflow
    WORKFLOW_PLAN_GENERATED = "workflow.plan_generated"
    WORKFLOW_PLAN_EXECUTED = "workflow.plan_executed"
    WORKFLOW_STEP_STARTED = "workflow.step_started"
    WORKFLOW_STEP_COMPLETED = "workflow.step_completed"
    WORKFLOW_COMPLETE = "workflow.complete"

    # Execution
    EXECUTION_STEP_START = "execution.step_start"
    EXECUTION_STEP_COMPLETE = "execution.step_complete"
    EXECUTION_COMPLETE = "execution.complete"

    # Provider
    PROVIDER_CALL = "provider.call"
    PROVIDER_RESPONSE = "provider.response"
    PROVIDER_ERROR = "provider.error"

    # Evaluation
    EVALUATION_STARTED = "evaluation.started"
    EVALUATION_COMPLETED = "evaluation.completed"

    # Patch
    PATCH_GENERATED = "patch.generated"
    PATCH_APPLIED = "patch.applied"

    # Modification
    MODIFICATION_STARTED = "modification.started"
    MODIFICATION_COMPLETE = "modification.complete"

    # Verification
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_COMPLETED = "verification.completed"

    # Autonomous
    AUTONOMOUS_ITERATION_STARTED = "autonomous.iteration_started"
    AUTONOMOUS_ITERATION_COMPLETED = "autonomous.iteration_completed"
    AUTONOMOUS_GOAL_ACHIEVED = "autonomous.goal_achieved"
    AUTONOMOUS_STOPPING_CONDITION = "autonomous.stopping_condition"

    # System
    SYSTEM_SNAPSHOT = "system.snapshot"
    SYSTEM_TELEMETRY_RECORD = "system.telemetry_record"

    # Category mapping
    CATEGORY_MAP: dict[str, str] = {
        GATEWAY_REQUEST: EventCategory.GATEWAY,
        GATEWAY_RESPONSE: EventCategory.GATEWAY,
        PIPELINE_STAGE_START: EventCategory.PIPELINE,
        PIPELINE_STAGE_COMPLETE: EventCategory.PIPELINE,
        PIPELINE_STAGE_FAILED: EventCategory.PIPELINE,
        PIPELINE_COMPLETE: EventCategory.PIPELINE,
        WORKFLOW_PLAN_GENERATED: EventCategory.WORKFLOW,
        WORKFLOW_PLAN_EXECUTED: EventCategory.WORKFLOW,
        WORKFLOW_STEP_STARTED: EventCategory.WORKFLOW,
        WORKFLOW_STEP_COMPLETED: EventCategory.WORKFLOW,
        WORKFLOW_COMPLETE: EventCategory.WORKFLOW,
        EXECUTION_STEP_START: EventCategory.EXECUTION,
        EXECUTION_STEP_COMPLETE: EventCategory.EXECUTION,
        EXECUTION_COMPLETE: EventCategory.EXECUTION,
        PROVIDER_CALL: EventCategory.PROVIDER,
        PROVIDER_RESPONSE: EventCategory.PROVIDER,
        PROVIDER_ERROR: EventCategory.PROVIDER,
        EVALUATION_STARTED: EventCategory.EVALUATION,
        EVALUATION_COMPLETED: EventCategory.EVALUATION,
        PATCH_GENERATED: EventCategory.PATCH,
        PATCH_APPLIED: EventCategory.PATCH,
        MODIFICATION_STARTED: EventCategory.MODIFICATION,
        MODIFICATION_COMPLETE: EventCategory.MODIFICATION,
        VERIFICATION_STARTED: EventCategory.VERIFICATION,
        VERIFICATION_COMPLETED: EventCategory.VERIFICATION,
        AUTONOMOUS_ITERATION_STARTED: EventCategory.AUTONOMOUS,
        AUTONOMOUS_ITERATION_COMPLETED: EventCategory.AUTONOMOUS,
        AUTONOMOUS_GOAL_ACHIEVED: EventCategory.AUTONOMOUS,
        AUTONOMOUS_STOPPING_CONDITION: EventCategory.AUTONOMOUS,
        SYSTEM_SNAPSHOT: EventCategory.SYSTEM,
        SYSTEM_TELEMETRY_RECORD: EventCategory.SYSTEM,
    }


# ---------------------------------------------------------------------------
# Event Creation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _EventContext:
    """Internal context for event creation.

    Attributes:
        event_id: Unique event identifier.
        timestamp: ISO format timestamp.
        category: Event category.
        type: Event type.
        correlation_id: Correlation ID.
        request_id: Request ID.
        metadata: Additional metadata.
    """

    event_id: str
    timestamp: str
    category: str
    type: str
    correlation_id: str
    request_id: str
    metadata: dict[str, Any]


def create_event(
    category: str,
    event_type: str,
    correlation_id: str = "",
    request_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Create a new event and return (event_id, timestamp).

    This is a factory function that generates deterministic event IDs
    and timestamps. It does NOT record events — that is the
    responsibility of the EngineeringTelemetry collector.

    Args:
        category: Event category (e.g. "workflow").
        event_type: Event type (e.g. "plan_generated").
        correlation_id: Correlation ID for linking events.
        request_id: Request ID from the gateway.
        metadata: Additional event metadata.

    Returns:
        Tuple of (event_id, timestamp).

    Raises:
        ValueError: If category or event_type is invalid.
    """
    # Validate category
    if category not in EventCategory.ALL:
        raise ValueError(
            f"Invalid event category: {category}. "
            f"Must be one of: {EventCategory.ALL}"
        )

    # Validate event_type against category mapping
    if event_type not in EventType.CATEGORY_MAP:
        raise ValueError(
            f"Invalid event type: {event_type}. "
            f"Must be a valid {category} event type."
        )

    # Generate deterministic event ID
    event_id = f"evt-{category}-{event_type}-{len(metadata or {})}"

    # Generate timestamp
    timestamp = datetime.now(timezone.utc).isoformat()

    return event_id, timestamp


def validate_event(
    category: str,
    event_type: str,
) -> bool:
    """Validate an event category and type combination.

    Args:
        category: Event category to validate.
        event_type: Event type to validate.

    Returns:
        True if valid, False otherwise.
    """
    if category not in EventCategory.ALL:
        return False

    if event_type not in EventType.CATEGORY_MAP:
        return False

    return EventType.CATEGORY_MAP[event_type] == category