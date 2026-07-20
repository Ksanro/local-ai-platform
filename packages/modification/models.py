"""Immutable modification model definitions.

Defines the output structures of the Code Modification Engine. These are the
stable contracts between the engine and its consumers.

Architecture
------------

PatchSet --> CodeModificationEngine --> WorkspaceChanges

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No file system operations.
- No repository analysis fields.
- No provider fields.
- No patch generation.

Public API
----------

.. code-block:: python

    from packages.modification.models import (
        ModifiedFile,
        ModificationStatus,
        ModificationStatistics,
        WorkspaceChanges,
    )

    changes = WorkspaceChanges(
        workflow_name="implement_feature",
        execution_id="exec-123",
        applied_files=(modified_file,),
        statistics=stats,
        success=True,
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "ModifiedFile",
    "ModificationStatistics",
    "ModificationStatus",
    "WorkspaceChanges",
]


# ---------------------------------------------------------------------------
# ModificationStatus
# ---------------------------------------------------------------------------


class ModificationStatus(str, Enum):
    """Status of a single file modification operation.

    Attributes:
        PENDING: Modification has not been attempted yet.
        APPLIED: Modification was successfully applied.
        FAILED: Modification failed and could not be recovered.
        ROLLED_BACK: Modification was rolled back due to a later failure.
    """

    PENDING = "PENDING"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


# ---------------------------------------------------------------------------
# ModifiedFile
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModifiedFile:
    """An immutable record of a single file modification.

    Attributes:
        path: File path relative to workspace root.
        operation: Operation type (ADD, MODIFY, DELETE, RENAME).
        original_hash: SHA-256 hash of the original file content.
        resulting_hash: SHA-256 hash of the resulting file content after modification.
        changed_lines: Tuple of 1-based line numbers that were changed.
        status: Current modification status.
    """

    path: str
    operation: str  # PatchOperation value string to avoid circular import
    original_hash: str
    resulting_hash: str
    changed_lines: tuple[int, ...] = ()
    status: ModificationStatus = ModificationStatus.PENDING


# ---------------------------------------------------------------------------
# ModificationStatistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModificationStatistics:
    """Aggregate statistics for a set of file modifications.

    Attributes:
        files_modified: Number of existing files that were modified.
        files_created: Number of new files created.
        files_deleted: Number of files deleted.
        lines_added: Total number of lines added across all files.
        lines_removed: Total number of lines removed across all files.
        total_operations: Total number of modification operations performed.
    """

    files_modified: int = 0
    files_created: int = 0
    files_deleted: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    total_operations: int = 0


# ---------------------------------------------------------------------------
# WorkspaceChanges
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkspaceChanges:
    """Complete record of all changes applied to a workspace.

    This is the canonical output artifact of the Code Modification Engine.
    It becomes the stable contract consumed by downstream components.

    Attributes:
        workflow_name: The workflow name that triggered this modification.
        execution_id: Unique execution identifier.
        applied_files: Tuple of all modified file records in deterministic order.
        statistics: Aggregate modification statistics.
        warnings: Tuple of warning messages generated during modification.
        success: Whether all modifications were applied successfully.
    """

    workflow_name: str
    execution_id: str
    applied_files: tuple[ModifiedFile, ...] = ()
    statistics: ModificationStatistics = field(default_factory=ModificationStatistics)
    warnings: tuple[str, ...] = ()
    success: bool = True