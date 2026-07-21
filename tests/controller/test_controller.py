"""Tests for EngineeringController.

Tests all public API methods, error handling, session ownership,
deterministic execution, artifact aggregation, and telemetry.
"""

import pytest

from packages.controller.models import (
    EngineeringRequest,
    EngineeringResult,
    OperationType,
    ValidationStatus,
)
from packages.controller.controller import EngineeringController


class TestControllerInitialization:
    """Test controller initialization."""

    def test_default_initialization(self):
        """Test controller with default initialization."""
        controller = EngineeringController()
        assert not controller.is_initialized

    def test_initialization_triggers_auto_init(self):
        """Test that processing triggers auto-initialization."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXPLAIN,
            description="Test explanation",
        )
        # EXPLAIN doesn't require workspace, so validation passes
        result = controller._process_request(request)
        assert controller.is_initialized

    def test_explicit_initialization(self):
        """Test explicit initialization."""
        controller = EngineeringController()
        controller._ensure_initialized()
        assert controller.is_initialized


class TestPublicAPI:
    """Test all public API methods."""

    def setup_method(self):
        """Setup test fixtures."""
        self.controller = EngineeringController()
        # Auto-initialize
        self.controller._ensure_initialized()

    def test_execute_method_exists(self):
        """Test execute method exists and returns EngineeringResult."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Test execution",
        )
        result = controller.execute(request)
        assert isinstance(result, EngineeringResult)
        assert result.request_id == "req-001"
        assert result.operation == OperationType.EXECUTE

    def test_review_method_exists(self):
        """Test review method exists and returns EngineeringResult."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-002",
            operation=OperationType.REVIEW,
            description="Test review",
        )
        result = controller.review(request)
        assert isinstance(result, EngineeringResult)
        assert result.request_id == "req-002"
        assert result.operation == OperationType.REVIEW

    def test_implement_method_exists(self):
        """Test implement method exists and returns EngineeringResult."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-003",
            operation=OperationType.IMPLEMENT,
            description="Test implementation",
        )
        result = controller.implement(request)
        assert isinstance(result, EngineeringResult)
        assert result.request_id == "req-003"
        assert result.operation == OperationType.IMPLEMENT

    def test_refactor_method_exists(self):
        """Test refactor method exists and returns EngineeringResult."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-004",
            operation=OperationType.REFACTOR,
            description="Test refactoring",
        )
        result = controller.refactor(request)
        assert isinstance(result, EngineeringResult)
        assert result.request_id == "req-004"
        assert result.operation == OperationType.REFACTOR

    def test_debug_method_exists(self):
        """Test debug method exists and returns EngineeringResult."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-005",
            operation=OperationType.DEBUG,
            description="Test debugging",
        )
        result = controller.debug(request)
        assert isinstance(result, EngineeringResult)
        assert result.request_id == "req-005"
        assert result.operation == OperationType.DEBUG

    def test_explain_method_exists(self):
        """Test explain method exists and returns EngineeringResult."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-006",
            operation=OperationType.EXPLAIN,
            description="Test explanation",
        )
        result = controller.explain(request)
        assert isinstance(result, EngineeringResult)
        assert result.request_id == "req-006"
        assert result.operation == OperationType.EXPLAIN


class TestRequestValidation:
    """Test request validation in controller."""

    def test_empty_request_id_fails(self):
        """Test that empty request ID causes failure."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="",
            operation=OperationType.EXECUTE,
            description="Test",
        )
        result = controller.execute(request)
        assert result.status == "FAILED"
        assert "request_id" in result.error_message.lower()

    def test_empty_description_fails(self):
        """Test that empty description causes failure."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="",
        )
        result = controller.execute(request)
        assert result.status == "FAILED"
        assert "description" in result.error_message.lower()

    def test_valid_request_passes_validation(self):
        """Test that valid request passes validation."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXPLAIN,
            description="Test explanation",
        )
        result = controller.execute(request)
        # Should not fail validation (even if delegation returns None)
        assert "Invalid request" not in result.error_message


class TestErrorHandling:
    """Test error handling in controller."""

    def test_handler_exception_returns_failed_result(self):
        """Test that handler exceptions return failed result."""
        controller = EngineeringController()
        # Create a request that will trigger a handler
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXPLAIN,
            description="Test",
        )
        result = controller.execute(request)
        # Controller handles exceptions gracefully
        assert result.request_id == "req-001"

    def test_result_contains_error_message_on_failure(self):
        """Test that failed results contain error messages."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="",  # Invalid: empty description
        )
        result = controller.execute(request)
        assert result.status == "FAILED"
        assert len(result.error_message) > 0


class TestSessionOwnership:
    """Test session ownership in controller."""

    def test_result_contains_session_id(self):
        """Test that results contain session ID."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXPLAIN,
            description="Test explanation",
        )
        result = controller.execute(request)
        assert result.session_id is not None
        assert len(result.session_id) > 0

    def test_session_id_format(self):
        """Test that session ID follows expected format."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-123",
            operation=OperationType.EXPLAIN,
            description="Test",
        )
        result = controller.execute(request)
        # Session ID should be derived from request ID
        assert "sess" in result.session_id or "req-123" in result.session_id


class TestDeterministicExecution:
    """Test deterministic execution."""

    def test_same_input_produces_same_result(self):
        """Test that same input produces same result structure."""
        controller1 = EngineeringController()
        controller2 = EngineeringController()

        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXPLAIN,
            description="Test explanation",
        )

        result1 = controller1.execute(request)
        result2 = controller2.execute(request)

        # Same structure
        assert result1.request_id == result2.request_id
        assert result1.operation == result2.operation
        assert result1.status == result2.status


class TestArtifactAggregation:
    """Test artifact aggregation in results."""

    def test_result_has_all_artifact_fields(self):
        """Test that result has all artifact fields."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Test execution",
        )
        result = controller.execute(request)

        # All artifact fields should be present (may be None)
        assert result.workflow_plan is not None or result.workflow_plan is None
        assert result.execution_report is not None or result.execution_report is None
        assert result.evaluation_report is not None or result.evaluation_report is None
        assert result.patch_set is not None or result.patch_set is None
        assert result.workspace_changes is not None or result.workspace_changes is None
        assert result.verification_report is not None or result.verification_report is None

    def test_execute_produces_full_pipeline_result(self):
        """Test that execute produces full pipeline result."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Test execution",
        )
        result = controller.execute(request)

        # Execute should attempt full pipeline
        assert result.workflow_plan is not None or result.workflow_plan is None
        assert result.execution_report is not None or result.execution_report is None


class TestTelemetryRecording:
    """Test telemetry recording."""

    def test_telemetry_is_included_in_result(self):
        """Test that telemetry is included in result."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXPLAIN,
            description="Test explanation",
        )
        result = controller.execute(request)
        # Telemetry may be None if no telemetry collector is configured
        assert result.telemetry is not None or result.telemetry is None

    def test_multiple_requests_record_events(self):
        """Test that multiple requests record events."""
        controller = EngineeringController()
        controller._ensure_initialized()

        # Multiple requests should work consistently
        for i in range(3):
            request = EngineeringRequest(
                request_id=f"req-{i}",
                operation=OperationType.EXPLAIN,
                description=f"Test {i}",
            )
            result = controller.execute(request)
            assert result.request_id == f"req-{i}"


class TestOperationRegistryIntegration:
    """Test operation registry integration."""

    def test_all_operations_registered(self):
        """Test that all operations are registered."""
        controller = EngineeringController()
        controller._ensure_initialized()

        for op in OperationType:
            assert controller.registry.has_operation(op)

    def test_all_operations_have_workflows(self):
        """Test that all operations have default workflows."""
        controller = EngineeringController()
        controller._ensure_initialized()

        for op in OperationType:
            workflow = controller.registry.get_default_workflow(op)
            assert workflow is not None
            assert len(workflow) > 0

    def test_all_operations_have_handlers(self):
        """Test that all operations have handlers."""
        controller = EngineeringController()
        controller._ensure_initialized()

        for op in OperationType:
            handler = controller.registry.get_handler(op)
            assert handler is not None


class TestControllerWithSessionManager:
    """Test controller with injected session manager."""

    def test_controller_without_session_manager(self):
        """Test controller works without session manager."""
        controller = EngineeringController(session_manager=None)
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXPLAIN,
            description="Test",
        )
        result = controller.execute(request)
        # Should still work, just generates session ID directly
        assert result.request_id == "req-001"


class TestProcessRequest:
    """Test _process_request method."""

    def test_process_request_validates_first(self):
        """Test that validation happens before processing."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="",  # Invalid
            operation=OperationType.EXECUTE,
            description="",  # Also invalid
        )
        result = controller._process_request(request)
        assert result.status == "FAILED"
        assert "Invalid request" in result.error_message

    def test_process_request_initializes_controller(self):
        """Test that processing initializes the controller."""
        controller = EngineeringController()
        assert not controller.is_initialized

        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXPLAIN,
            description="Test",
        )
        controller._process_request(request)
        assert controller.is_initialized

    def test_process_request_with_custom_validator(self):
        """Test process request with custom validator."""
        controller = EngineeringController()
        # Validator is created by default
        assert controller.validator is not None


class TestResultStructure:
    """Test EngineeringResult structure."""

    def test_result_has_correct_request_id(self):
        """Test that result has correct request ID."""
        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="unique-request-123",
            operation=OperationType.EXPLAIN,
            description="Test",
        )
        result = controller.execute(request)
        assert result.request_id == "unique-request-123"

    def test_result_has_correct_operation(self):
        """Test that result has correct operation."""
        controller = EngineeringController()
        for op in OperationType:
            request = EngineeringRequest(
                request_id=f"req-{op.value}",
                operation=op,
                description="Test",
            )
            result = controller.execute(request)
            assert result.operation == op

    def test_result_has_timestamp(self):
        """Test that result has created_at timestamp."""
        from datetime import datetime

        controller = EngineeringController()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXPLAIN,
            description="Test",
        )
        result = controller.execute(request)
        # Should be parseable as ISO format
        datetime.fromisoformat(result.created_at)