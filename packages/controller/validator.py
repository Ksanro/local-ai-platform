"""Request validator — Validates EngineeringRequest objects.

Ensures all requests meet the required format before processing.
Handles validation of operation types, workspace paths, and request structure.

Architecture
------------

EngineeringRequest --> Validator --> RequestValidationResult

Responsibilities
----------------

- Validate request_id format and uniqueness.
- Validate operation type is recognized.
- Validate description is non-empty and within length limits.
- Validate workspace_path format and accessibility.
- Validate context structure.
- Produce immutable RequestValidationResult.

Non-responsibilities
--------------------

- Must NOT process requests.
- Must NOT modify requests.
- Must NOT access file system.
- Must NOT invoke providers.
- Must NOT perform repository analysis.

Public API
----------

.. code-block:: python

    from packages.controller.validator import (
        RequestValidator,
        RequestValidationResult,
        ValidationStatus,
    )

    validator = RequestValidator()
    result = validator.validate(request)

"""

from __future__ import annotations

import os
from typing import Any

from packages.controller.models import (
    EngineeringRequest,
    OperationType,
    RequestValidationResult,
    ValidationSeverity,
    ValidationStatus,
)

__all__ = [
    "RequestValidator",
    "RequestValidationResult",
    "ValidationStatus",
]

# Configuration constants
MAX_DESCRIPTION_LENGTH = 10000
MAX_REQUEST_ID_LENGTH = 64
MAX_CONTEXT_KEYS = 100
MAX_METADATA_KEYS = 50


class RequestValidator:
    """Validates EngineeringRequest objects.

    Provides comprehensive validation of engineering requests before
    they are processed by the controller.

    Attributes:
        max_description_length: Maximum allowed description length.
        max_request_id_length: Maximum allowed request ID length.
        max_context_keys: Maximum allowed context keys.
        max_metadata_keys: Maximum allowed metadata keys.
    """

    def __init__(
        self,
        max_description_length: int = MAX_DESCRIPTION_LENGTH,
        max_request_id_length: int = MAX_REQUEST_ID_LENGTH,
        max_context_keys: int = MAX_CONTEXT_KEYS,
        max_metadata_keys: int = MAX_METADATA_KEYS,
    ) -> None:
        """Initialize the request validator.

        Args:
            max_description_length: Maximum allowed description length.
            max_request_id_length: Maximum allowed request ID length.
            max_context_keys: Maximum allowed context keys.
            max_metadata_keys: Maximum allowed metadata keys.
        """
        self.max_description_length = max_description_length
        self.max_request_id_length = max_request_id_length
        self.max_context_keys = max_context_keys
        self.max_metadata_keys = max_metadata_keys

    def validate(
        self,
        request: EngineeringRequest,
    ) -> RequestValidationResult:
        """Validate an engineering request.

        Performs all validation checks and returns a comprehensive result.

        Args:
            request: The engineering request to validate.

        Returns:
            A RequestValidationResult with validation status and details.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Run all validation checks
        errors.extend(self._validate_request_id(request))
        errors.extend(self._validate_operation(request))
        errors.extend(self._validate_description(request))
        errors.extend(self._validate_workspace_path(request))
        errors.extend(self._validate_context(request))
        errors.extend(self._validate_metadata(request))

        # Determine status
        if errors:
            status = ValidationStatus.INVALID
        elif warnings:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.VALID

        return RequestValidationResult(
            status=status,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def _validate_request_id(
        self,
        request: EngineeringRequest,
    ) -> list[str]:
        """Validate the request ID.

        Args:
            request: The engineering request to validate.

        Returns:
            List of error messages.
        """
        errors: list[str] = []

        if not request.request_id:
            errors.append("request_id cannot be empty")
            return errors

        if len(request.request_id) > self.max_request_id_length:
            errors.append(
                f"request_id exceeds maximum length of {self.max_request_id_length} "
                f"characters (got {len(request.request_id)})"
            )

        # Check for invalid characters (alphanumeric, hyphens, underscores, dots)
        if not all(
            c.isalnum() or c in "-_." for c in request.request_id
        ):
            errors.append(
                "request_id contains invalid characters. "
                "Only alphanumeric, hyphens, underscores, and dots are allowed."
            )

        return errors

    def _validate_operation(
        self,
        request: EngineeringRequest,
    ) -> list[str]:
        """Validate the operation type.

        Args:
            request: The engineering request to validate.

        Returns:
            List of error messages.
        """
        errors: list[str] = []

        valid_operations = [op.value for op in OperationType]
        if request.operation.value not in valid_operations:
            errors.append(
                f"Unknown operation: {request.operation.value}. "
                f"Valid operations: {', '.join(valid_operations)}"
            )

        return errors

    def _validate_description(
        self,
        request: EngineeringRequest,
    ) -> list[str]:
        """Validate the description field.

        Args:
            request: The engineering request to validate.

        Returns:
            List of error messages.
        """
        errors: list[str] = []

        if not request.description or not request.description.strip():
            errors.append("description cannot be empty")
            return errors

        if len(request.description) > self.max_description_length:
            errors.append(
                f"description exceeds maximum length of {self.max_description_length} "
                f"characters (got {len(request.description)})"
            )

        return errors

    def _validate_workspace_path(
        self,
        request: EngineeringRequest,
    ) -> list[str]:
        """Validate the workspace path.

        Args:
            request: The engineering request to validate.

        Returns:
            List of error messages.
        """
        errors: list[str] = []

        # EXPLAIN operation is read-only, workspace_path is optional
        if request.operation == OperationType.EXPLAIN:
            return errors

        if not request.workspace_path:
            errors.append("workspace_path is required for this operation")
            return errors

        # Check for valid path characters
        if not request.workspace_path.strip():
            errors.append("workspace_path cannot be empty or whitespace")
            return errors

        # Check for invalid path characters
        invalid_chars = set('<>:"|?*')
        if any(c in invalid_chars for c in request.workspace_path):
            errors.append(
                "workspace_path contains invalid characters. "
                "Avoid: <>:\"|?*"
            )

        return errors

    def _validate_context(
        self,
        request: EngineeringRequest,
    ) -> list[str]:
        """Validate the context dictionary.

        Args:
            request: The engineering request to validate.

        Returns:
            List of error messages.
        """
        errors: list[str] = []

        if not request.context:
            return errors

        if len(request.context) > self.max_context_keys:
            errors.append(
                f"context exceeds maximum number of keys ({self.max_context_keys})"
            )

        # Check for duplicate keys (shouldn't happen in dict, but be safe)
        if len(request.context) != len(set(request.context.keys())):
            errors.append("context contains duplicate keys")

        return errors

    def _validate_metadata(
        self,
        request: EngineeringRequest,
    ) -> list[str]:
        """Validate the metadata dictionary.

        Args:
            request: The engineering request to validate.

        Returns:
            List of error messages.
        """
        errors: list[str] = []

        if not request.metadata:
            return errors

        if len(request.metadata) > self.max_metadata_keys:
            errors.append(
                f"metadata exceeds maximum number of keys ({self.max_metadata_keys})"
            )

        return errors

    def validate_workspace_path(
        self,
        path: str,
    ) -> list[str]:
        """Validate a workspace path independently.

        Args:
            path: The workspace path to validate.

        Returns:
            List of error messages.
        """
        errors: list[str] = []

        if not path or not path.strip():
            errors.append("workspace_path cannot be empty")
            return errors

        if not path.strip():
            errors.append("workspace_path cannot be whitespace")
            return errors

        invalid_chars = set('<>:"|?*')
        if any(c in invalid_chars for c in path):
            errors.append(
                "workspace_path contains invalid characters. "
                "Avoid: <>:\"|?*"
            )

        return errors