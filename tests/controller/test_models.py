"""Tests for controller models.

Tests EngineeringRequest, EngineeringResult, OperationType,
and RequestValidationResult data structures.
"""

import pytest
from datetime import datetime

from packages.controller.models import (
    EngineeringRequest,
    EngineeringResult,
    OperationType,
    RequestValidationResult,
    ValidationSeverity,
    ValidationStatus,
)


class TestOperationType:
    """Test OperationType enum."""

    def test_all_operations_exist(self):
        """Test all operation types are defined."""
        assert hasattr(OperationType, "EXECUTE")
        assert hasattr(OperationType, "REVIEW")
        assert hasattr(OperationType, "IMPLEMENT")
        assert hasattr(OperationType, "REFACTOR")
        assert hasattr(OperationType, "DEBUG")
        assert hasattr(OperationType, "EXPLAIN")

    def test_operation_values(self):
        """Test operation type values."""
        assert OperationType.EXECUTE.value == "execute"
        assert OperationType.REVIEW.value == "review"
        assert OperationType.IMPLEMENT.value == "implement"
        assert OperationType.REFACTOR.value == "refactor"
        assert OperationType.DEBUG.value == "debug"
        assert OperationType.EXPLAIN.value == "explain"

    def test_iteration_over_operations(self):
        """Test iterating over all operations."""
        operations = list(OperationType)
        assert len(operations) == 6


class TestValidationStatus:
    """Test ValidationStatus enum."""

    def test_all_statuses_exist(self):
        """Test all validation statuses are defined."""
        assert hasattr(ValidationStatus, "VALID")
        assert hasattr(ValidationStatus, "INVALID")
        assert hasattr(ValidationStatus, "WARNING")

    def test_status_values(self):
        """Test validation status values."""
        assert ValidationStatus.VALID.value == "VALID"
        assert ValidationStatus.INVALID.value == "INVALID"
        assert ValidationStatus.WARNING.value == "WARNING"


class TestValidationSeverity:
    """Test ValidationSeverity enum."""

    def test_all_severities_exist(self):
        """Test all validation severities are defined."""
        assert hasattr(ValidationSeverity, "ERROR")
        assert hasattr(ValidationSeverity, "WARNING")
        assert hasattr(ValidationSeverity, "INFO")

    def test_severity_values(self):
        """Test validation severity values."""
        assert ValidationSeverity.ERROR.value == "ERROR"
        assert ValidationSeverity.WARNING.value == "WARNING"
        assert ValidationSeverity.INFO.value == "INFO"


class TestRequestValidationResult:
    """Test RequestValidationResult model."""

    def test_default_values(self):
        """Test default values for RequestValidationResult."""
        result = RequestValidationResult()
        assert result.status == ValidationStatus.VALID
        assert result.errors == ()
        assert result.warnings == ()
        assert result.metadata == {}

    def test_custom_values(self):
        """Test custom values for RequestValidationResult."""
        result = RequestValidationResult(
            status=ValidationStatus.INVALID,
            errors=("error1", "error2"),
            warnings=("warning1",),
            metadata={"key": "value"},
        )
        assert result.status == ValidationStatus.INVALID
        assert result.errors == ("error1", "error2")
        assert result.warnings == ("warning1",)
        assert result.metadata == {"key": "value"}

    def test_is_frozen(self):
        """Test that RequestValidationResult is immutable."""
        result = RequestValidationResult()
        with pytest.raises(AttributeError):
            result.status = ValidationStatus.INVALID


class TestEngineeringRequest:
    """Test EngineeringRequest model."""

    def test_required_fields_only(self):
        """Test creating request with only required fields."""
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Test description",
        )
        assert request.request_id == "req-001"
        assert request.operation == OperationType.EXECUTE
        assert request.description == "Test description"
        assert request.workspace_path == ""
        assert request.workflow_name == ""
        assert request.context == {}
        assert request.metadata == {}

    def test_all_fields(self):
        """Test creating request with all fields."""
        request = EngineeringRequest(
            request_id="req-002",
            operation=OperationType.REVIEW,
            description="Review code changes",
            workspace_path="/path/to/workspace",
            workflow_name="code-review",
            context={"files": ["file1.py", "file2.py"]},
            metadata={"author": "test"},
        )
        assert request.request_id == "req-002"
        assert request.operation == OperationType.REVIEW
        assert request.description == "Review code changes"
        assert request.workspace_path == "/path/to/workspace"
        assert request.workflow_name == "code-review"
        assert request.context == {"files": ["file1.py", "file2.py"]}
        assert request.metadata == {"author": "test"}

    def test_is_frozen(self):
        """Test that EngineeringRequest is immutable."""
        request = EngineeringRequest(
            request_id="req-003",
            operation=OperationType.EXECUTE,
            description="Test",
        )
        with pytest.raises(AttributeError):
            request.request_id = "new-id"

    def test_different_operations(self):
        """Test creating requests with different operations."""
        for op in OperationType:
            request = EngineeringRequest(
                request_id=f"req-{op.value}",
                operation=op,
                description=f"Test {op.value}",
            )
            assert request.operation == op


class TestEngineeringResult:
    """Test EngineeringResult model."""

    def test_minimal_result(self):
        """Test creating minimal result."""
        result = EngineeringResult(
            request_id="req-001",
            session_id="sess-001",
            operation=OperationType.EXECUTE,
        )
        assert result.request_id == "req-001"
        assert result.session_id == "sess-001"
        assert result.operation == OperationType.EXECUTE
        assert result.status == "SUCCESS"
        assert result.error_message == ""
        assert result.created_at is not None

    def test_full_result(self):
        """Test creating result with all fields."""
        result = EngineeringResult(
            request_id="req-002",
            session_id="sess-002",
            operation=OperationType.IMPLEMENT,
            status="FAILED",
            error_message="Something went wrong",
        )
        assert result.request_id == "req-002"
        assert result.session_id == "sess-002"
        assert result.operation == OperationType.IMPLEMENT
        assert result.status == "FAILED"
        assert result.error_message == "Something went wrong"

    def test_result_with_all_artifacts(self):
        """Test result with all artifact types."""
        mock_plan = {"steps": []}
        mock_report = {"details": []}
        mock_patch = {"files": []}
        mock_changes = {"modified": []}
        mock_verification = {"findings": []}
        mock_telemetry = {"events": []}

        result = EngineeringResult(
            request_id="req-003",
            session_id="sess-003",
            operation=OperationType.EXECUTE,
            workflow_plan=mock_plan,
            execution_report=mock_report,
            evaluation_report=mock_report,
            patch_set=mock_patch,
            workspace_changes=mock_changes,
            verification_report=mock_verification,
            telemetry=mock_telemetry,
        )
        assert result.workflow_plan == mock_plan
        assert result.execution_report == mock_report
        assert result.evaluation_report == mock_report
        assert result.patch_set == mock_patch
        assert result.workspace_changes == mock_changes
        assert result.verification_report == mock_verification
        assert result.telemetry == mock_telemetry

    def test_is_frozen(self):
        """Test that EngineeringResult is immutable."""
        result = EngineeringResult(
            request_id="req-004",
            session_id="sess-004",
            operation=OperationType.EXECUTE,
        )
        with pytest.raises(AttributeError):
            result.status = "FAILED"

    def test_created_at_timestamp(self):
        """Test that created_at is a valid timestamp."""
        result = EngineeringResult(
            request_id="req-005",
            session_id="sess-005",
            operation=OperationType.EXECUTE,
        )
        # Should be parseable as ISO format
        datetime.fromisoformat(result.created_at)