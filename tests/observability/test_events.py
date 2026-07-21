"""Tests for the event model and categorization.

Tests event categories, event types, validation, and creation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from packages.observability import events
from packages.observability.events import EventCategory, EventType


class TestEventCategory:
    """Tests for EventCategory."""

    def test_all_categories_exist(self) -> None:
        """Test that all expected categories exist."""
        assert EventCategory.GATEWAY == "gateway"
        assert EventCategory.PIPELINE == "pipeline"
        assert EventCategory.WORKFLOW == "workflow"
        assert EventCategory.EXECUTION == "execution"
        assert EventCategory.PROVIDER == "provider"
        assert EventCategory.EVALUATION == "evaluation"
        assert EventCategory.PATCH == "patch"
        assert EventCategory.MODIFICATION == "modification"
        assert EventCategory.VERIFICATION == "verification"
        assert EventCategory.AUTONOMOUS == "autonomous"
        assert EventCategory.SYSTEM == "system"

    def test_all_tuple(self) -> None:
        """Test that ALL tuple contains all categories."""
        assert len(EventCategory.ALL) == 11
        assert "gateway" in EventCategory.ALL
        assert "system" in EventCategory.ALL

    def test_all_is_tuple(self) -> None:
        """Test that ALL is a tuple."""
        assert isinstance(EventCategory.ALL, tuple)


class TestEventType:
    """Tests for EventType."""

    def test_gateway_events(self) -> None:
        """Test gateway event types."""
        assert EventType.GATEWAY_REQUEST == "gateway.request"
        assert EventType.GATEWAY_RESPONSE == "gateway.response"

    def test_pipeline_events(self) -> None:
        """Test pipeline event types."""
        assert EventType.PIPELINE_STAGE_START == "pipeline.stage_start"
        assert EventType.PIPELINE_STAGE_COMPLETE == "pipeline.stage_complete"
        assert EventType.PIPELINE_STAGE_FAILED == "pipeline.stage_failed"
        assert EventType.PIPELINE_COMPLETE == "pipeline.complete"

    def test_workflow_events(self) -> None:
        """Test workflow event types."""
        assert EventType.WORKFLOW_PLAN_GENERATED == "workflow.plan_generated"
        assert EventType.WORKFLOW_PLAN_EXECUTED == "workflow.plan_executed"
        assert EventType.WORKFLOW_STEP_STARTED == "workflow.step_started"
        assert EventType.WORKFLOW_STEP_COMPLETED == "workflow.step_completed"
        assert EventType.WORKFLOW_COMPLETE == "workflow.complete"

    def test_execution_events(self) -> None:
        """Test execution event types."""
        assert EventType.EXECUTION_STEP_START == "execution.step_start"
        assert EventType.EXECUTION_STEP_COMPLETE == "execution.step_complete"
        assert EventType.EXECUTION_COMPLETE == "execution.complete"

    def test_provider_events(self) -> None:
        """Test provider event types."""
        assert EventType.PROVIDER_CALL == "provider.call"
        assert EventType.PROVIDER_RESPONSE == "provider.response"
        assert EventType.PROVIDER_ERROR == "provider.error"

    def test_evaluation_events(self) -> None:
        """Test evaluation event types."""
        assert EventType.EVALUATION_STARTED == "evaluation.started"
        assert EventType.EVALUATION_COMPLETED == "evaluation.completed"

    def test_patch_events(self) -> None:
        """Test patch event types."""
        assert EventType.PATCH_GENERATED == "patch.generated"
        assert EventType.PATCH_APPLIED == "patch.applied"

    def test_modification_events(self) -> None:
        """Test modification event types."""
        assert EventType.MODIFICATION_STARTED == "modification.started"
        assert EventType.MODIFICATION_COMPLETE == "modification.complete"

    def test_verification_events(self) -> None:
        """Test verification event types."""
        assert EventType.VERIFICATION_STARTED == "verification.started"
        assert EventType.VERIFICATION_COMPLETED == "verification.completed"

    def test_autonomous_events(self) -> None:
        """Test autonomous event types."""
        assert EventType.AUTONOMOUS_ITERATION_STARTED == "autonomous.iteration_started"
        assert EventType.AUTONOMOUS_ITERATION_COMPLETED == "autonomous.iteration_completed"
        assert EventType.AUTONOMOUS_GOAL_ACHIEVED == "autonomous.goal_achieved"
        assert EventType.AUTONOMOUS_STOPPING_CONDITION == "autonomous.stopping_condition"

    def test_system_events(self) -> None:
        """Test system event types."""
        assert EventType.SYSTEM_SNAPSHOT == "system.snapshot"
        assert EventType.SYSTEM_TELEMETRY_RECORD == "system.telemetry_record"


class TestEventTypeCategoryMap:
    """Tests for EventType.CATEGORY_MAP."""

    def test_all_types_have_mappings(self) -> None:
        """Test that all event types have category mappings."""
        assert len(EventType.CATEGORY_MAP) == 30

    def test_gateway_mappings(self) -> None:
        """Test gateway event category mappings."""
        assert EventType.CATEGORY_MAP["gateway.request"] == "gateway"
        assert EventType.CATEGORY_MAP["gateway.response"] == "gateway"

    def test_workflow_mappings(self) -> None:
        """Test workflow event category mappings."""
        assert EventType.CATEGORY_MAP["workflow.plan_generated"] == "workflow"
        assert EventType.CATEGORY_MAP["workflow.complete"] == "workflow"

    def test_execution_mappings(self) -> None:
        """Test execution event category mappings."""
        assert EventType.CATEGORY_MAP["execution.step_start"] == "execution"
        assert EventType.CATEGORY_MAP["execution.complete"] == "execution"

    def test_provider_mappings(self) -> None:
        """Test provider event category mappings."""
        assert EventType.CATEGORY_MAP["provider.call"] == "provider"
        assert EventType.CATEGORY_MAP["provider.error"] == "provider"

    def test_autonomous_mappings(self) -> None:
        """Test autonomous event category mappings."""
        assert EventType.CATEGORY_MAP["autonomous.iteration_started"] == "autonomous"
        assert EventType.CATEGORY_MAP["autonomous.goal_achieved"] == "autonomous"


class TestCreateEvent:
    """Tests for create_event function."""

    def test_valid_creation(self) -> None:
        """Test creating a valid event."""
        event_id, timestamp = events.create_event(
            category="workflow",
            event_type="workflow.plan_generated",
            correlation_id="req-001",
            request_id="req-001",
            metadata={"workflow_name": "test"},
        )

        assert event_id.startswith("evt-workflow-workflow.plan_generated-")
        assert isinstance(timestamp, str)
        # Validate timestamp format
        datetime.fromisoformat(timestamp)  # Should not raise

    def test_invalid_category_raises(self) -> None:
        """Test that invalid category raises ValueError."""
        with pytest.raises(ValueError, match="Invalid event category"):
            events.create_event(
                category="invalid",
                event_type="some.type",
            )

    def test_invalid_event_type_raises(self) -> None:
        """Test that invalid event type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid event type"):
            events.create_event(
                category="workflow",
                event_type="invalid.event.type",
            )

    def test_no_metadata(self) -> None:
        """Test creating event with no metadata."""
        event_id, timestamp = events.create_event(
            category="system",
            event_type="system.snapshot",
        )

        assert event_id.endswith("-0")  # No metadata = len({}) = 0

    def test_empty_metadata(self) -> None:
        """Test creating event with empty metadata."""
        event_id, timestamp = events.create_event(
            category="system",
            event_type="system.snapshot",
            metadata=None,
        )

        assert event_id.endswith("-0")


class TestValidateEvent:
    """Tests for validate_event function."""

    def test_valid_workflow(self) -> None:
        """Test validating valid workflow event."""
        assert events.validate_event(
            "workflow",
            "workflow.plan_generated",
        ) is True

    def test_valid_execution(self) -> None:
        """Test validating valid execution event."""
        assert events.validate_event(
            "execution",
            "execution.step_complete",
        ) is True

    def test_valid_provider(self) -> None:
        """Test validating valid provider event."""
        assert events.validate_event(
            "provider",
            "provider.call",
        ) is True

    def test_invalid_category(self) -> None:
        """Test that invalid category returns False."""
        assert events.validate_event(
            "invalid",
            "some.type",
        ) is False

    def test_invalid_type(self) -> None:
        """Test that invalid type returns False."""
        assert events.validate_event(
            "workflow",
            "invalid.type",
        ) is False

    def test_mismatched_category(self) -> None:
        """Test that mismatched category and type returns False."""
        assert events.validate_event(
            "workflow",
            "execution.step_complete",
        ) is False

    def test_all_valid_combinations(self) -> None:
        """Test that all valid type combinations pass validation."""
        for event_type, expected_category in EventType.CATEGORY_MAP.items():
            assert events.validate_event(
                expected_category,
                event_type,
            ) is True


class TestEventContext:
    """Tests for _EventContext internal class."""

    def test_event_context_creation(self) -> None:
        """Test _EventContext creation."""
        ctx = events._EventContext(
            event_id="evt-001",
            timestamp="2024-01-01T00:00:00",
            category="workflow",
            type="plan_generated",
            correlation_id="req-001",
            request_id="req-001",
            metadata={"key": "value"},
        )

        assert ctx.event_id == "evt-001"
        assert ctx.category == "workflow"
        assert ctx.type == "plan_generated"


class TestEventOrdering:
    """Tests for deterministic event ordering."""

    def test_category_order(self) -> None:
        """Test that categories are in deterministic order."""
        all_categories = EventCategory.ALL
        assert all_categories[0] == "gateway"
        assert all_categories[1] == "pipeline"
        assert all_categories[2] == "workflow"
        assert all_categories[-1] == "system"

    def test_all_is_immutable(self) -> None:
        """Test that ALL tuple is immutable."""
        all_categories = EventCategory.ALL
        with pytest.raises(TypeError):
            all_categories[0] = "modified"  # type: ignore[assignment]


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_strings(self) -> None:
        """Test with empty strings."""
        event_id, timestamp = events.create_event(
            category="system",
            event_type="system.snapshot",
            correlation_id="",
            request_id="",
        )

        assert event_id.startswith("evt-system-system.snapshot-")

    def test_special_characters_in_metadata(self) -> None:
        """Test with special characters in metadata."""
        event_id, timestamp = events.create_event(
            category="workflow",
            event_type="workflow.plan_generated",
            metadata={"key_with_underscores": "value", "unicode": "\u00e9"},
        )

        assert event_id.startswith("evt-workflow-workflow.plan_generated-")

    def test_many_metadata_keys(self) -> None:
        """Test with many metadata keys."""
        metadata = {f"key_{i}": f"value_{i}" for i in range(100)}
        event_id, timestamp = events.create_event(
            category="system",
            event_type="system.snapshot",
            metadata=metadata,
        )

        # The event ID should include the count of metadata
        assert event_id.endswith("-100")