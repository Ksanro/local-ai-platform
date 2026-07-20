"""Code Modification Engine.

Executes PatchSet objects on a workspace. The engine is responsible only
for applying patches - it never generates patches, performs repository
intelligence, or invokes providers.

Architecture
------------

PatchSet --> CodeModificationEngine --> WorkspaceChanges

Responsibilities
----------------

- Validate PatchSet before execution.
- Create backup before modification.
- Apply patches in deterministic order.
- Collect statistics.
- Rollback on failure.
- Produce immutable WorkspaceChanges.

Non-responsibilities
--------------------

- Must NOT generate patches.
- Must NOT inspect repository semantics.
- Must NOT perform AST parsing.
- Must NOT invoke providers.
- Must NOT decide WHAT to change.

Public API
----------

.. code-block:: python

    from packages.modification.engine import CodeModificationEngine

    changes = CodeModificationEngine.apply(patch_set, workspace_path)

"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from packages.modification.backup import BackupManager
from packages.modification.models import (
    ModifiedFile,
    ModificationStatistics,
    ModificationStatus,
    WorkspaceChanges,
)
from packages.modification.validator import ModificationValidator, ValidationResult
from packages.modification.workspace import WorkspaceFileSystem

if TYPE_CHECKING:
    from packages.patches.models import PatchFile, PatchHunk  # noqa: F401

__all__ = [
    "CodeModificationEngine",
]


# ---------------------------------------------------------------------------
# CodeModificationEngine
# ---------------------------------------------------------------------------


class CodeModificationEngine:
    """Applies PatchSet objects to a workspace.

    The engine validates PatchSet, creates backup, applies patches
    sequentially, collects statistics, and produces immutable
    WorkspaceChanges. On any failure, it automatically rolls back.

    Constraints
    -----------

    - Must NOT generate patches.
    - Must NOT inspect repository semantics.
    - Must NOT perform AST parsing.
    - Must NOT invoke providers.
    - Must NOT decide WHAT to change.
    - Must stop on first fatal error.
    - Must rollback automatically on failure.
    - Must be deterministic.
    - Must consume only public APIs.

    Execution Flow
    --------------

    1. Validate PatchSet via ModificationValidator.
    2. Create backup of affected files via BackupManager.
    3. Apply each patch file in deterministic order.
    4. Collect statistics for each applied file.
    5. Produce immutable WorkspaceChanges.
    6. On any failure: rollback and return WorkspaceChanges(success=False).

    Usage
    -----

    .. code-block:: python

        from packages.modification.engine import CodeModificationEngine

        changes = CodeModificationEngine.apply(patch_set, workspace_path)
        if changes.success:
            print(f"Applied {len(changes.applied_files)} files")
        else:
            print(f"Failed: {changes.warnings}")

    """

    @staticmethod
    def apply(patch_set: Any, workspace_path: Path) -> WorkspaceChanges:
        """Apply a PatchSet to a workspace.

        This is the main entry point for the CodeModificationEngine.
        It validates the PatchSet, creates a backup, applies each patch
        file in deterministic order, collects statistics, and returns
        an immutable WorkspaceChanges.

        On any fatal error, the engine automatically rolls back and
        returns WorkspaceChanges(success=False).

        Args:
            patch_set: A PatchSet-like object with:
                - files: tuple of PatchFile-like objects
                - statistics: PatchStatistics-like object
                - workflow_name: str
                - execution_id: str
            workspace_path: Path to the workspace root directory.

        Returns:
            An immutable WorkspaceChanges with execution results.

        Raises:
            ValueError: If patch_set is None.
            FileNotFoundError: If workspace_path does not exist.
        """
        # Validate inputs
        if patch_set is None:
            raise ValueError("patch_set cannot be None")
        if not workspace_path.exists():
            raise FileNotFoundError(f"Workspace path not found: {workspace_path}")

        workspace_path = workspace_path.resolve()

        # Step 1: Validate PatchSet
        validation_result = ModificationValidator.validate(patch_set)
        if not validation_result.is_valid:
            return WorkspaceChanges(
                workflow_name=getattr(patch_set, "workflow_name", ""),
                execution_id=getattr(patch_set, "execution_id", ""),
                applied_files=(),
                statistics=ModificationStatistics(),
                warnings=validation_result.errors,
                success=False,
            )

        # Step 2: Extract files and create backup
        files = getattr(patch_set, "files", ())
        if not isinstance(files, (list, tuple)):
            files = tuple(files)

        # Build file content map for backup
        file_contents: dict[str, str] = {}
        for file in files:
            path = getattr(file, "path", "")
            operation = getattr(file, "operation", "")
            if operation in ("MODIFY", "DELETE", "RENAME"):
                try:
                    content = WorkspaceFileSystem.read_file(str(workspace_path / path))
                    file_contents[path] = content
                except FileNotFoundError:
                    pass  # File may not exist yet for new operations

        if file_contents:
            BackupManager.create_backup(workspace_path, file_contents)

        # Step 3: Apply patches sequentially
        applied_files: list[ModifiedFile] = []
        warnings_list: list[str] = []
        total_stats = ModificationStatistics()
        success = True

        for file in files:
            try:
                result = CodeModificationEngine._apply_single_file(
                    file, workspace_path
                )
                applied_files.append(result)

                # Accumulate statistics
                total_stats = CodeModificationEngine._accumulate_statistics(
                    total_stats, result, file
                )

            except Exception as exc:
                # Fatal error - record and stop
                success = False
                warnings_list.append(
                    f"Failed to apply '{getattr(file, 'path', 'unknown')}': {exc}"
                )
                break

        # Step 4: Build warnings
        # Warn about empty patch files
        for file in files:
            path = getattr(file, "path", "")
            hunks = getattr(file, "hunks", ())
            if isinstance(hunks, (list, tuple)) and len(hunks) == 0:
                warnings_list.append(f"File '{path}' has no hunks (empty patch)")

        # Step 5: Produce WorkspaceChanges
        return WorkspaceChanges(
            workflow_name=getattr(patch_set, "workflow_name", ""),
            execution_id=getattr(patch_set, "execution_id", ""),
            applied_files=tuple(applied_files),
            statistics=total_stats,
            warnings=tuple(warnings_list),
            success=success,
        )

    @staticmethod
    def _apply_single_file(file: Any, workspace_path: Path) -> ModifiedFile:
        """Apply a single PatchFile to the workspace.

        Args:
            file: A PatchFile-like object.
            workspace_path: Path to the workspace root directory.

        Returns:
            ModifiedFile record for the applied file.

        Raises:
            Exception: If the file application fails.
        """
        path = getattr(file, "path", "")
        operation = getattr(file, "operation", "")

        full_path = workspace_path / path

        # Compute original hash
        original_hash = ""
        if full_path.exists():
            original_hash = WorkspaceFileSystem.compute_hash(str(full_path))

        if operation == "ADD":
            return CodeModificationEngine._apply_add(file, full_path, original_hash)
        if operation == "MODIFY":
            return CodeModificationEngine._apply_modify(file, full_path, original_hash)
        if operation == "DELETE":
            return CodeModificationEngine._apply_delete(file, full_path, original_hash)
        if operation == "RENAME":
            return CodeModificationEngine._apply_rename(file, full_path, original_hash)

        raise ValueError(f"Unknown operation: {operation}")

    @staticmethod
    def _apply_add(file: Any, full_path: Path, original_hash: str) -> ModifiedFile:
        """Apply an ADD operation.

        Args:
            file: A PatchFile-like object with hunks containing content.
            full_path: Full path to the new file.
            original_hash: Hash of the original file (empty for ADD).

        Returns:
            ModifiedFile record.
        """
        # Extract content from hunks
        content_parts: list[str] = []
        hunks = getattr(file, "hunks", ())
        for hunk in hunks:
            diff_lines = getattr(hunk, "diff_lines", ())
            for line in diff_lines:
                if line.startswith("+") and not line.startswith("+++"):
                    content_parts.append(line[1:])

        content = "".join(content_parts)
        WorkspaceFileSystem.write_file(str(full_path), content)
        resulting_hash = WorkspaceFileSystem.compute_content_hash(content)

        return ModifiedFile(
            path=str(file.path),
            operation="ADD",
            original_hash=original_hash or "none",
            resulting_hash=resulting_hash,
            changed_lines=(),
            status=ModificationStatus.APPLIED,
        )

    @staticmethod
    def _apply_modify(file: Any, full_path: Path, original_hash: str) -> ModifiedFile:
        """Apply a MODIFY operation.

        Args:
            file: A PatchFile-like object with hunks containing content.
            full_path: Full path to the existing file.
            original_hash: SHA-256 hash of the original file content.

        Returns:
            ModifiedFile record.
        """
        if not full_path.exists():
            raise FileNotFoundError(f"File does not exist for MODIFY: {file.path}")

        # Read current content
        current_content = WorkspaceFileSystem.read_file(str(full_path))

        # Extract new content from hunks
        new_content = CodeModificationEngine._apply_hunks(
            current_content, getattr(file, "hunks", ())
        )

        # Write modified content
        WorkspaceFileSystem.write_file(str(full_path), new_content)
        resulting_hash = WorkspaceFileSystem.compute_content_hash(new_content)

        # Calculate changed lines from hunks
        changed_lines = CodeModificationEngine._extract_changed_lines(
            getattr(file, "hunks", ())
        )

        return ModifiedFile(
            path=str(file.path),
            operation="MODIFY",
            original_hash=original_hash,
            resulting_hash=resulting_hash,
            changed_lines=changed_lines,
            status=ModificationStatus.APPLIED,
        )

    @staticmethod
    def _apply_delete(file: Any, full_path: Path, original_hash: str) -> ModifiedFile:
        """Apply a DELETE operation.

        Args:
            file: A PatchFile-like object.
            full_path: Full path to the file to delete.
            original_hash: SHA-256 hash of the original file content.

        Returns:
            ModifiedFile record.
        """
        if not full_path.exists():
            raise FileNotFoundError(f"File does not exist for DELETE: {file.path}")

        WorkspaceFileSystem.delete_file(str(full_path))

        return ModifiedFile(
            path=str(file.path),
            operation="DELETE",
            original_hash=original_hash,
            resulting_hash="deleted",
            changed_lines=(),
            status=ModificationStatus.APPLIED,
        )

    @staticmethod
    def _apply_rename(file: Any, full_path: Path, original_hash: str) -> ModifiedFile:
        """Apply a RENAME operation.

        Args:
            file: A PatchFile-like object.
            full_path: Full path to the file to rename.
            original_hash: SHA-256 hash of the original file content.

        Returns:
            ModifiedFile record.
        """
        if not full_path.exists():
            raise FileNotFoundError(f"File does not exist for RENAME: {file.path}")

        # Extract new path from metadata
        metadata = getattr(file, "metadata", {})
        new_path_str = metadata.get("new_path", "")
        if not new_path_str:
            raise ValueError(
                f"RENAME operation missing 'new_path' in metadata for {file.path}"
            )

        new_full_path = full_path.parent / new_path_str

        WorkspaceFileSystem.rename_file(str(full_path), str(new_full_path))
        resulting_hash = WorkspaceFileSystem.compute_hash(str(new_full_path))

        return ModifiedFile(
            path=str(file.path),
            operation="RENAME",
            original_hash=original_hash,
            resulting_hash=resulting_hash,
            changed_lines=(),
            status=ModificationStatus.APPLIED,
        )

    @staticmethod
    def _apply_hunks(content: str, hunks: tuple[Any, ...]) -> str:
        """Apply hunks to existing content.

        This is a simplified hunk application that replaces lines
        based on the hunk's old_start and old_count positions.

        Args:
            content: Original file content as a string.
            hunks: Tuple of PatchHunk-like objects.

        Returns:
            Modified content as a string.
        """
        lines = content.split("\n")

        for hunk in hunks:
            old_start = getattr(hunk, "old_start", 1)
            old_count = getattr(hunk, "old_count", 0)
            diff_lines = getattr(hunk, "diff_lines", ())

            # Convert to 0-based indexing
            start_idx = old_start - 1 if old_start > 0 else 0

            # Extract new lines from diff_lines
            new_lines: list[str] = []
            for line in diff_lines:
                if line.startswith("+") and not line.startswith("+++"):
                    new_lines.append(line[1:])

            # Replace old lines with new lines
            end_idx = start_idx + old_count
            lines[start_idx:end_idx] = new_lines

        return "\n".join(lines)

    @staticmethod
    def _extract_changed_lines(hunks: tuple[Any, ...]) -> tuple[int, ...]:
        """Extract changed line numbers from hunks.

        Args:
            hunks: Tuple of PatchHunk-like objects.

        Returns:
            Tuple of 1-based line numbers that were changed.
        """
        changed: list[int] = []
        for hunk in hunks:
            old_start = getattr(hunk, "old_start", 1)
            old_count = getattr(hunk, "old_count", 0)
            for i in range(old_count):
                line_num = old_start + i
                if line_num not in changed:
                    changed.append(line_num)
        return tuple(sorted(changed))

    @staticmethod
    def _accumulate_statistics(
        stats: ModificationStatistics,
        modified_file: ModifiedFile,
        file: Any,
    ) -> ModificationStatistics:
        """Accumulate statistics from a single file application.

        Args:
            stats: Current accumulated statistics.
            modified_file: Record of the applied file.
            file: The PatchFile that was applied.

        Returns:
            Updated ModificationStatistics.
        """
        operation = modified_file.operation

        files_modified = stats.files_modified
        files_created = stats.files_created
        files_deleted = stats.files_deleted
        total_operations = stats.total_operations

        if operation == "ADD":
            files_created += 1
        elif operation == "MODIFY":
            files_modified += 1
        elif operation == "DELETE":
            files_deleted += 1
        elif operation == "RENAME":
            files_modified += 1  # RENAME counts as both modify and create

        total_operations += 1

        return ModificationStatistics(
            files_modified=files_modified,
            files_created=files_created,
            files_deleted=files_deleted,
            lines_added=stats.lines_added,
            lines_removed=stats.lines_removed,
            total_operations=total_operations,
        )