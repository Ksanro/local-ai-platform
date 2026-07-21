"""Tests for request validator.

Tests RequestValidator class and all validation rules.
"""

import pytest

from packages.controller.models import (
    EngineeringRequest,
    OperationType,
    RequestValidationResult,
    ValidationStatus,
)
from packages.controller.validator import RequestValidator


class TestRequestValidator:
    """Test RequestValidator class."""

    def test_valid_request(self):
        """Test validation of a valid request."""
        validator = RequestValidator()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Test description",
            workspace_path="/path/to/workspace",
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.VALID
        assert result.errors == ()

    def test_empty_request_id(self):
        """Test validation fails with empty request ID."""
        validator = RequestValidator()
        request = EngineeringRequest(
            request_id="",
            operation=OperationType.EXECUTE,
            description="Test description",
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID
        assert len(result.errors) > 0

    def test_request_id_too_long(self):
        """Test validation fails when request ID exceeds max length."""
        validator = RequestValidator(max_request_id_length=10)
        request = EngineeringRequest(
            request_id="a" * 20,
            operation=OperationType.EXECUTE,
            description="Test description",
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID
        assert any("maximum length" in e for e in result.errors)

    def test_invalid_request_id_characters(self):
        """Test validation fails with invalid characters in request ID."""
        validator = RequestValidator()
        request = EngineeringRequest(
            request_id="req@001!invalid",
            operation=OperationType.EXECUTE,
            description="Test description",
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID
        assert any("invalid characters" in e for e in result.errors)

    def test_empty_description(self):
        """Test validation fails with empty description."""
        validator = RequestValidator()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="",
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID
        assert any("description" in e.lower() for e in result.errors)

    def test_whitespace_only_description(self):
        """Test validation fails with whitespace-only description."""
        validator = RequestValidator()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="   ",
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID

    def test_description_too_long(self):
        """Test validation fails when description exceeds max length."""
        validator = RequestValidator(max_description_length=10)
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="a" * 20,
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID
        assert any("maximum length" in e for e in result.errors)

    def test_missing_workspace_path(self):
        """Test validation fails when workspace path is missing."""
        validator = RequestValidator()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Test description",
            workspace_path="",
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID
        assert any("workspace_path" in e for e in result.errors)

    def test_explain_no_workspace_required(self):
        """Test EXPLAIN operation does not require workspace path."""
        validator = RequestValidator()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXPLAIN,
            description="Explain this code",
        )
        result = validator.validate(request)
        # Should be valid - EXPLAIN is read-only
        assert result.status != ValidationStatus.INVALID or not any(
            "workspace" in e for e in result.errors
        )

    def test_invalid_workspace_path_characters(self):
        """Test validation fails with invalid characters in workspace path."""
        validator = RequestValidator()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.IMPLEMENT,
            description="Implement feature",
            workspace_path="/path/with<>invalid",
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID
        assert any("invalid characters" in e for e in result.errors)

    def test_empty_context(self):
        """Test validation passes with empty context."""
        validator = RequestValidator()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Test description",
            workspace_path="/path",
            context={},
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.VALID

    def test_max_context_keys_exceeded(self):
        """Test validation fails when context exceeds max keys."""
        validator = RequestValidator(max_context_keys=2)
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Test description",
            workspace_path="/path",
            context={"a": 1, "b": 2, "c": 3},
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID
        assert any("context exceeds" in e for e in result.errors)

    def test_max_metadata_keys_exceeded(self):
        """Test validation fails when metadata exceeds max keys."""
        validator = RequestValidator(max_metadata_keys=2)
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Test description",
            workspace_path="/path",
            metadata={"a": 1, "b": 2, "c": 3},
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID
        assert any("metadata exceeds" in e for e in result.errors)

    def test_valid_context_and_metadata(self):
        """Test validation passes with valid context and metadata."""
        validator = RequestValidator()
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Test description",
            workspace_path="/path",
            context={"key1": "value1"},
            metadata={"author": "test"},
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.VALID


class TestValidateWorkspacePath:
    """Test standalone workspace path validation."""

    def test_valid_path(self):
        """Test valid workspace path."""
        validator = RequestValidator()
        errors = validator.validate_workspace_path("/path/to/workspace")
        assert errors == []

    def test_empty_path(self):
        """Test empty workspace path."""
        validator = RequestValidator()
        errors = validator.validate_workspace_path("")
        assert len(errors) > 0

    def test_whitespace_path(self):
        """Test whitespace-only workspace path."""
        validator = RequestValidator()
        errors = validator.validate_workspace_path("   ")
        assert len(errors) > 0

    def test_invalid_characters(self):
        """Test workspace path with invalid characters."""
        validator = RequestValidator()
        errors = validator.validate_workspace_path("/path/with<>invalid")
        assert len(errors) > 0
        assert any("invalid characters" in e for e in errors)


class TestValidatorConfiguration:
    """Test validator with custom configuration."""

    def test_custom_max_description_length(self):
        """Test custom max description length."""
        validator = RequestValidator(max_description_length=5)
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="This is longer than 5 chars",
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID

    def test_custom_max_request_id_length(self):
        """Test custom max request ID length."""
        validator = RequestValidator(max_request_id_length=3)
        request = EngineeringRequest(
            request_id="req-001",
            operation=OperationType.EXECUTE,
            description="Test",
        )
        result = validator.validate(request)
        assert result.status == ValidationStatus.INVALID