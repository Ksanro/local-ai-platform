"""Immutable Patch model definitions.

Defines the output structures of the Patch Generator framework. These are
the stable contracts between the Patch Generator and its consumers.

Architecture
------------

PatchOperation --> PatchHunk --> PatchFile --> PatchSet --> PatchStatistics

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No file system operations.
- No repository analysis fields.
- No provider fields.

Public API
----------

.. code-block:: python

    from packages.patches.models import (
        PatchFile,
        PatchHunk,
        PatchOperation,
        PatchSet,
        PatchStatistics,
        ValidationResult,
    )

    hunk = PatchHunk(
        file_path="src/main.py",
        old_start=1,
        old_count=5,
        new_start=1,
        new_count=5,
        diff_lines=("+ new line\\n",),
    )

    patch_set = PatchSet(
        workflow_name="implement_feature",
        execution_id="exec-123",
        generated_from=("workflow-plan-1",),
        files=(patch_file,),
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "PatchFile",
    "PatchHunk",
    "PatchOperation",
    "PatchSet",
    "PatchStatistics",
    "ValidationResult",
]


# ---------------------------------------------------------------------------
# PatchOperation
# ---------------------------------------------------------------------------


class PatchOperation(str, Enum):
    """Operation type for a patch file.

    Attributes:
        ADD: New file being added.
        DELETE: Existing file being deleted.
        MODIFY: Existing file being modified.
        RENAME: File being renamed (delete old + add new).
    """

    ADD = "ADD"
    DELETE = "DELETE"
    MODIFY = "MODIFY"
    RENAME = "RENAME"


# ---------------------------------------------------------------------------
# PatchHunk
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PatchHunk:
    """An immutable diff hunk within a patch file.

    Attributes:
        file_path: Path to the file this hunk belongs to.
        old_start: Starting line number in the old file (1-based).
        old_count: Number of lines in the old file covered by this hunk.
        new_start: Starting line number in the new file (1-based).
        new_count: Number of lines in the new file covered by this hunk.
        diff_lines: Tuple of diff content lines (unified diff format).
    """

    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    diff_lines: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# PatchFile
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PatchFile:
    """An immutable patch file containing one or more hunks.

    Attributes:
        path: File path relative to repository root.
        operation: Operation type (ADD, DELETE, MODIFY, RENAME).
        hunks: Tuple of hunks for this file.
        estimated_changed_lines: Estimated total changed lines.
        metadata: Additional metadata about this patch file.
    """

    path: str
    operation: PatchOperation
    hunks: tuple[PatchHunk, ...] = ()
    estimated_changed_lines: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PatchStatistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PatchStatistics:
    """Aggregate statistics for a complete PatchSet.

    Attributes:
        files_changed: Number of files with patches.
        hunks: Total number of hunks across all files.
        added_lines: Total number of added lines.
        removed_lines: Total number of removed lines.
        modified_lines: Total number of modified files.
    """

    files_changed: int = 0
    hunks: int = 0
    added_lines: int = 0
    removed_lines: int = 0
    modified_lines: int = 0


# ---------------------------------------------------------------------------
# PatchSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PatchSet:
    """Complete patch set for a workflow execution.

    This is the canonical output artifact of the Patch Generator.
    It becomes the ONLY contract consumed by the Code Modification Engine.

    Attributes:
        workflow_name: The workflow name that generated this patch set.
        execution_id: Unique execution identifier.
        generated_from: Tuple of originating engineering artifact references.
        files: Tuple of all patch files in deterministic order.
        statistics: Aggregate statistics for the patch set.
        warnings: Tuple of warning messages for this patch set.
    """

    workflow_name: str
    execution_id: str
    generated_from: tuple[str, ...] = ()
    files: tuple[PatchFile, ...] = ()
    statistics: PatchStatistics = field(default_factory=PatchStatistics)
    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of validating a PatchSet.

    Attributes:
        is_valid: Whether the PatchSet passed all validation checks.
        errors: Tuple of validation error messages.
        warnings: Tuple of validation warning messages.
    """

    is_valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()