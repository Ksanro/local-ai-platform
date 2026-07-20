"""Patch Validator.

Validates PatchSet objects against defined rules. Validation never modifies
the PatchSet — it produces an immutable ValidationResult.

Architecture
------------

PatchSet --> PatchValidator --> ValidationResult

Constraints
-----------

- Validation only.
- No PatchSet modification.
- No file system operations.
- No repository analysis.
- Deterministic output.

Public API
----------

.. code-block:: python

    from packages.patches.validator import PatchValidator

    result = PatchValidator.validate(patch_set)

"""

from __future__ import annotations

from typing import Any

from packages.patches.models import (
    PatchFile,
    PatchHunk,
    PatchOperation,
    PatchSet,
    PatchStatistics,
    ValidationResult,
)

__all__ = [
    "PatchValidator",
]


# ---------------------------------------------------------------------------
# PatchValidator
# ---------------------------------------------------------------------------


class PatchValidator:
    """Validates PatchSet objects.

    The validator checks PatchSet against defined rules and produces
    an immutable ValidationResult. It never modifies the PatchSet.

    Constraints
    -----------

    - Validation only.
    - Must NOT modify PatchSet.
    - No file system operations.
    - No repository inspection.
    - Must produce deterministic output.

    Validation Rules
    ----------------

    1. Duplicate files: No two files with the same path.
    2. Duplicate hunks: No two hunks with identical content in same file.
    3. Overlapping hunks: Hunks in same file must not overlap.
    4. Invalid operations: Operation must be a valid PatchOperation.
    5. Invalid line ranges: old_start, old_count, new_start, new_count >= 0.
    6. Empty patches: Files with no hunks are flagged as warnings.
    7. Invalid statistics: Statistics must match actual file counts.

    Usage
    -----

    .. code-block:: python

        from packages.patches.validator import PatchValidator

        result = PatchValidator.validate(patch_set)
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

        # Extract files
        files = getattr(patch_set, "files", ())
        if not isinstance(files, (list, tuple)):
            files = tuple(files)

        # Extract statistics
        statistics = getattr(patch_set, "statistics", None)

        # Run all validations
        errors.extend(_validate_duplicate_files(files))
        errors.extend(_validate_duplicate_hunks(files))
        errors.extend(_validate_overlapping_hunks(files))
        errors.extend(_validate_operations(files))
        errors.extend(_validate_line_ranges(files))
        warnings.extend(_validate_empty_patches(files))
        errors.extend(_validate_statistics(patch_set, files, statistics))

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
# Validation Rule Functions
# ---------------------------------------------------------------------------


def _validate_duplicate_files(files: tuple[PatchFile, ...]) -> list[str]:
    """Check for duplicate file paths.

    Args:
        files: Tuple of PatchFile objects.

    Returns:
        List of error messages for duplicate files found.
    """
    errors: list[str] = []
    seen_paths: set[str] = set()

    for file in files:
        path = getattr(file, "path", "")
        if path in seen_paths:
            errors.append(f"Duplicate file path: '{path}'")
        seen_paths.add(path)

    return errors


def _validate_duplicate_hunks(files: tuple[PatchFile, ...]) -> list[str]:
    """Check for duplicate hunks within each file.

    Args:
        files: Tuple of PatchFile objects.

    Returns:
        List of error messages for duplicate hunks found.
    """
    errors: list[str] = []

    for file in files:
        path = getattr(file, "path", "")
        hunks = getattr(file, "hunks", ())
        if not isinstance(hunks, (list, tuple)):
            continue

        seen_signatures: set[tuple] = set()

        for hunk in hunks:
            signature = (
                getattr(hunk, "file_path", ""),
                getattr(hunk, "old_start", 0),
                getattr(hunk, "old_count", 0),
                getattr(hunk, "new_start", 0),
                getattr(hunk, "new_count", 0),
                getattr(hunk, "diff_lines", ()),
            )

            if signature in seen_signatures:
                errors.append(
                    f"Duplicate hunk in '{path}' "
                    f"(old_start={signature[1]}, new_start={signature[3]})"
                )
            seen_signatures.add(signature)

    return errors


def _validate_overlapping_hunks(files: tuple[PatchFile, ...]) -> list[str]:
    """Check for overlapping hunks within each file.

    Two hunks overlap if their line ranges intersect.

    Args:
        files: Tuple of PatchFile objects.

    Returns:
        List of error messages for overlapping hunks found.
    """
    errors: list[str] = []

    for file in files:
        path = getattr(file, "path", "")
        hunks = getattr(file, "hunks", ())
        if not isinstance(hunks, (list, tuple)):
            continue

        for i in range(len(hunks)):
            for j in range(i + 1, len(hunks)):
                hunk_a = hunks[i]
                hunk_b = hunks[j]

                old_start_a = getattr(hunk_a, "old_start", 0)
                old_count_a = getattr(hunk_a, "old_count", 0)
                old_start_b = getattr(hunk_b, "old_start", 0)
                old_count_b = getattr(hunk_b, "old_count", 0)

                # Calculate ranges
                range_a_start = old_start_a
                range_a_end = old_start_a + old_count_a
                range_b_start = old_start_b
                range_b_end = old_start_b + old_count_b

                # Check overlap (ranges overlap if they intersect)
                if range_a_start < range_b_end and range_b_start < range_a_end:
                    errors.append(
                        f"Overlapping hunks in '{path}' "
                        f"(lines {range_a_start}-{range_a_end} and "
                        f"{range_b_start}-{range_b_end})"
                    )

    return errors


def _validate_operations(files: tuple[PatchFile, ...]) -> list[str]:
    """Check for invalid operation values.

    Args:
        files: Tuple of PatchFile objects.

    Returns:
        List of error messages for invalid operations found.
    """
    errors: list[str] = []
    valid_operations = {op.value for op in PatchOperation}

    for file in files:
        path = getattr(file, "path", "")
        operation = getattr(file, "operation", None)

        if operation is None:
            errors.append(f"File '{path}' has no operation")
            continue

        # Handle both enum and string values
        op_value = operation.value if isinstance(operation, PatchOperation) else operation
        if op_value not in valid_operations:
            errors.append(
                f"File '{path}' has invalid operation: '{op_value}'"
            )

    return errors


def _validate_line_ranges(files: tuple[PatchFile, ...]) -> list[str]:
    """Check for invalid line ranges in hunks.

    Validates that old_start, old_count, new_start, new_count are >= 0.

    Args:
        files: Tuple of PatchFile objects.

    Returns:
        List of error messages for invalid line ranges found.
    """
    errors: list[str] = []

    for file in files:
        path = getattr(file, "path", "")
        hunks = getattr(file, "hunks", ())
        if not isinstance(hunks, (list, tuple)):
            continue

        for idx, hunk in enumerate(hunks):
            old_start = getattr(hunk, "old_start", 0)
            old_count = getattr(hunk, "old_count", 0)
            new_start = getattr(hunk, "new_start", 0)
            new_count = getattr(hunk, "new_count", 0)

            if old_start < 0:
                errors.append(
                    f"File '{path}' hunk #{idx} has invalid old_start: {old_start}"
                )
            if old_count < 0:
                errors.append(
                    f"File '{path}' hunk #{idx} has invalid old_count: {old_count}"
                )
            if new_start < 0:
                errors.append(
                    f"File '{path}' hunk #{idx} has invalid new_start: {new_start}"
                )
            if new_count < 0:
                errors.append(
                    f"File '{path}' hunk #{idx} has invalid new_count: {new_count}"
                )

    return errors


def _validate_empty_patches(files: tuple[PatchFile, ...]) -> list[str]:
    """Check for files with no hunks (warning only).

    Args:
        files: Tuple of PatchFile objects.

    Returns:
        List of warning messages for empty patches found.
    """
    warnings: list[str] = []

    for file in files:
        path = getattr(file, "path", "")
        hunks = getattr(file, "hunks", ())
        if not isinstance(hunks, (list, tuple)):
            continue

        if len(hunks) == 0:
            warnings.append(f"File '{path}' has no hunks (empty patch)")

    return warnings


def _validate_statistics(
    patch_set: Any,
    files: tuple[PatchFile, ...],
    statistics: Any,
) -> list[str]:
    """Check that statistics match actual file counts.

    Statistics validation is skipped when statistics are at default values
    (i.e., not explicitly provided by the caller), since the PatchSet may
    have been created without explicit statistics.

    Args:
        patch_set: PatchSet-like object.
        files: Tuple of PatchFile objects.
        statistics: PatchStatistics-like object.

    Returns:
        List of error messages for statistics mismatches found.
    """
    errors: list[str] = []

    if statistics is None:
        errors.append("PatchSet has no statistics")
        return errors

    # Skip validation if statistics are all at default values.
    # This allows PatchSets created without explicit statistics to pass.
    default_stats = PatchStatistics()
    if (
        getattr(statistics, "files_changed", 0) == default_stats.files_changed
        and getattr(statistics, "hunks", 0) == default_stats.hunks
        and getattr(statistics, "added_lines", 0) == default_stats.added_lines
        and getattr(statistics, "removed_lines", 0) == default_stats.removed_lines
        and getattr(statistics, "modified_lines", 0) == default_stats.modified_lines
    ):
        return errors

    # Check files_changed count
    expected_files_changed = len(files)
    actual_files_changed = getattr(statistics, "files_changed", None)
    if actual_files_changed is not None and actual_files_changed != expected_files_changed:
        errors.append(
            f"Statistics files_changed ({actual_files_changed}) "
            f"does not match actual file count ({expected_files_changed})"
        )

    # Check hunks count
    expected_hunks = sum(len(getattr(f, "hunks", ()) or ()) for f in files)
    actual_hunks = getattr(statistics, "hunks", None)
    if actual_hunks is not None and actual_hunks != expected_hunks:
        errors.append(
            f"Statistics hunks ({actual_hunks}) does not match actual hunk count ({expected_hunks})"
        )

    return errors
