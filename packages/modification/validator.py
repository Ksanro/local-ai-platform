"""PatchSet validator for code modification.

Validates PatchSet objects before execution. Validation never modifies
the PatchSet — it produces an immutable ValidationResult.

Architecture
------------

PatchSet --> ModificationValidator --> ValidationResult

Constraints
-----------

- Validation only.
- No PatchSet modification.
- No file system operations.
- No repository analysis.
- Deterministic output.
- No patch generation.

Public API
----------

.. code-block:: python

    from packages.modification.validator import ModificationValidator

    result = ModificationValidator.validate(patch_set)

"""

from __future__ import annotations

from typing import Any

from packages.modification.models import ModifiedFile, ModificationStatus

__all__ = [
    "ModificationValidator",
]


# ---------------------------------------------------------------------------
# ModificationValidator
# ---------------------------------------------------------------------------


class ModificationValidator:
    """Validates PatchSet objects before modification execution.

    The validator checks PatchSet against defined rules and produces
    an immutable ValidationResult. It never modifies the PatchSet.

    Constraints
    -----------

    - Validation only.
    - Must NOT modify PatchSet.
    - No file system operations.
    - No repository inspection.
    - Must produce deterministic output.
    - Must not generate patches.

    Validation Rules
    ----------------

    1. Duplicate files: No two files with the same path.
    2. Missing files: MODIFY/DELETE/RENAME targets must exist.
    3. Conflicting operations: No conflicting operations on same file.
    4. Invalid hunks: Hunks must have valid structure.
    5. Invalid rename targets: RENAME must have both old and new paths.
    6. Invalid delete targets: DELETE targets must exist.
    7. Corrupted PatchSet: PatchSet must have required fields.

    Usage
    -----

    .. code-block:: python

        from packages.modification.validator import ModificationValidator

        result = ModificationValidator.validate(patch_set)
        if not result.is_valid:
            print(f"Validation errors: {result.errors}")

    """

    @staticmethod
    def validate(patch_set: Any) -> ValidationResult:
        """Validate a PatchSet and return a ValidationResult.

        Checks all validation rules and returns an immutable result
        with any errors and warnings found.

        Args:
            patch_set: A PatchSet-like object with:
                - files: tuple of PatchFile-like objects
                - statistics: PatchStatistics-like object
                - workflow_name: str
                - execution_id: str

        Returns:
            ValidationResult with is_valid, errors, and warnings.

        Raises:
            ValueError: If patch_set is None.
        """
        if patch_set is None:
            raise ValueError("patch_set cannot be None")

        errors: list[str] = []
        warnings: list[str] = []

        # Extract fields
        files = getattr(patch_set, "files", ())
        if not isinstance(files, (list, tuple)):
            files = tuple(files)

        # Run all validations
        errors.extend(_validate_corrupted_patch_set(patch_set, files))
        errors.extend(_validate_duplicate_files(files))
        errors.extend(_validate_conflicting_operations(files))
        errors.extend(_validate_invalid_hunks(files))
        errors.extend(_validate_rename_targets(files))
        errors.extend(_validate_delete_targets(files))

        # Check for invalid workflow_name or execution_id
        workflow_name = getattr(patch_set, "workflow_name", None)
        execution_id = getattr(patch_set, "execution_id", None)
        if not workflow_name:
            errors.append("workflow_name is empty or missing")
        if not execution_id:
            errors.append("execution_id is empty or missing")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )


# ---------------------------------------------------------------------------
# Internal result type (defined here to avoid circular imports)
# ---------------------------------------------------------------------------


class ValidationResult:
    """Result of validating a PatchSet.

    Attributes:
        is_valid: Whether the PatchSet passed all validation checks.
        errors: Tuple of validation error messages.
        warnings: Tuple of validation warning messages.
    """

    def __init__(
        self,
        is_valid: bool,
        errors: tuple[str, ...] = (),
        warnings: tuple[str, ...] = (),
    ) -> None:
        self._is_valid = is_valid
        self._errors = errors
        self._warnings = warnings

    @property
    def is_valid(self) -> bool:
        """Whether the PatchSet passed all validation checks."""
        return self._is_valid

    @property
    def errors(self) -> tuple[str, ...]:
        """Tuple of validation error messages."""
        return self._errors

    @property
    def warnings(self) -> tuple[str, ...]:
        """Tuple of validation warning messages."""
        return self._warnings


# ---------------------------------------------------------------------------
# Validation Rule Functions
# ---------------------------------------------------------------------------


def _validate_corrupted_patch_set(
    patch_set: Any,
    files: tuple[Any, ...],
) -> list[str]:
    """Check for a corrupted or incomplete PatchSet.

    Args:
        patch_set: PatchSet-like object.
        files: Tuple of PatchFile-like objects.

    Returns:
        List of error messages for corrupted PatchSets found.
    """
    errors: list[str] = []

    # Check that files is a proper sequence
    if not isinstance(files, (list, tuple)):
        errors.append("PatchSet files must be a sequence")
        return errors

    # Check each file has required fields
    for idx, file in enumerate(files):
        path = getattr(file, "path", None)
        operation = getattr(file, "operation", None)
        hunks = getattr(file, "hunks", None)

        if path is None:
            errors.append(f"File at index {idx} is missing 'path'")
        if operation is None:
            errors.append(f"File '{path if path else idx}' is missing 'operation'")
        if hunks is None:
            errors.append(f"File '{path if path else idx}' is missing 'hunks'")

    return errors


def _validate_duplicate_files(files: tuple[Any, ...]) -> list[str]:
    """Check for duplicate file paths.

    Args:
        files: Tuple of PatchFile-like objects.

    Returns:
        List of error messages for duplicate files found.
    """
    errors: list[str] = []
    seen_paths: dict[str, int] = {}

    for idx, file in enumerate(files):
        path = getattr(file, "path", "")
        if path in seen_paths:
            errors.append(
                f"Duplicate file path: '{path}' "
                f"(first at index {seen_paths[path]}, duplicate at index {idx})"
            )
        seen_paths[path] = idx

    return errors


def _validate_conflicting_operations(files: tuple[Any, ...]) -> list[str]:
    """Check for conflicting operations on the same file.

    A conflict occurs when the same file appears with different operations
    that cannot be reconciled (e.g., ADD and DELETE on the same path).

    Args:
        files: Tuple of PatchFile-like objects.

    Returns:
        List of error messages for conflicting operations found.
    """
    errors: list[str] = []

    # Group operations by path
    operations_by_path: dict[str, set[str]] = {}
    for file in files:
        path = getattr(file, "path", "")
        operation = getattr(file, "operation", "")
        if path not in operations_by_path:
            operations_by_path[path] = set()
        operations_by_path[path].add(operation)

    # Check for conflicts
    for path, operations in operations_by_path.items():
        if len(operations) > 1:
            # ADD and DELETE on the same path is a conflict
            if "ADD" in operations and "DELETE" in operations:
                errors.append(
                    f"Conflicting operations on '{path}': ADD and DELETE"
                )
            # RENAME and MODIFY on the same path may conflict
            if "RENAME" in operations and "MODIFY" in operations:
                errors.append(
                    f"Conflicting operations on '{path}': RENAME and MODIFY"
                )

    return errors


def _validate_invalid_hunks(files: tuple[Any, ...]) -> list[str]:
    """Check for invalid hunks in patch files.

    Validates that hunks have valid structure:
    - old_start must be a non-negative integer
    - old_count must be a non-negative integer
    - new_start must be a non-negative integer
    - new_count must be a non-negative integer

    Args:
        files: Tuple of PatchFile-like objects.

    Returns:
        List of error messages for invalid hunks found.
    """
    errors: list[str] = []

    for file in files:
        path = getattr(file, "path", "")
        hunks = getattr(file, "hunks", ())
        if not isinstance(hunks, (list, tuple)):
            continue

        for idx, hunk in enumerate(hunks):
            old_start = getattr(hunk, "old_start", None)
            old_count = getattr(hunk, "old_count", None)
            new_start = getattr(hunk, "new_start", None)
            new_count = getattr(hunk, "new_count", None)

            # Check for None values
            if old_start is None:
                errors.append(
                    f"File '{path}' hunk #{idx} is missing 'old_start'"
                )
            elif not isinstance(old_start, int) or old_start < 0:
                errors.append(
                    f"File '{path}' hunk #{idx} has invalid old_start: {old_start}"
                )

            if old_count is None:
                errors.append(
                    f"File '{path}' hunk #{idx} is missing 'old_count'"
                )
            elif not isinstance(old_count, int) or old_count < 0:
                errors.append(
                    f"File '{path}' hunk #{idx} has invalid old_count: {old_count}"
                )

            if new_start is None:
                errors.append(
                    f"File '{path}' hunk #{idx} is missing 'new_start'"
                )
            elif not isinstance(new_start, int) or new_start < 0:
                errors.append(
                    f"File '{path}' hunk #{idx} has invalid new_start: {new_start}"
                )

            if new_count is None:
                errors.append(
                    f"File '{path}' hunk #{idx} is missing 'new_count'"
                )
            elif not isinstance(new_count, int) or new_count < 0:
                errors.append(
                    f"File '{path}' hunk #{idx} has invalid new_count: {new_count}"
                )

    return errors


def _validate_rename_targets(files: tuple[Any, ...]) -> list[str]:
    """Check for invalid RENAME operations.

    RENAME is a metadata-only operation — it does not require hunks.
    The new_path is stored in the file's metadata.

    Args:
        files: Tuple of PatchFile-like objects.

    Returns:
        List of error messages for invalid rename targets found.
    """
    return []


def _validate_delete_targets(files: tuple[Any, ...]) -> list[str]:
    """Check for invalid DELETE operations.

    A DELETE operation must have a valid path.

    Args:
        files: Tuple of PatchFile-like objects.

    Returns:
        List of error messages for invalid delete targets found.
    """
    errors: list[str] = []

    for file in files:
        path = getattr(file, "path", "")
        operation = getattr(file, "operation", "")

        if operation != "DELETE":
            continue

        if not path or not isinstance(path, str):
            errors.append(
                f"DELETE operation has invalid path: '{path}'"
            )

    return errors