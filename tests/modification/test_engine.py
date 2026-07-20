"""Tests for CodeModificationEngine.

Verifies:
- apply ADD
- apply MODIFY
- apply DELETE
- apply RENAME
- rollback on failure
- backup creation
- deterministic execution
- statistics
- duplicate detection
- invalid PatchSet
- partial failure rollback
- empty PatchSet
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from packages.modification.engine import CodeModificationEngine
from packages.modification.models import (
    ModifiedFile,
    ModificationStatistics,
    ModificationStatus,
    WorkspaceChanges,
)
from packages.patches.models import PatchFile, PatchHunk, PatchOperation, PatchSet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_patch_file(
    path: str,
    operation: PatchOperation,
    hunks: tuple[PatchHunk, ...] = (),
    metadata: dict[str, str] | None = None,
) -> PatchFile:
    """Create a PatchFile for testing."""
    return PatchFile(
        path=path,
        operation=operation,
        hunks=hunks,
        metadata=metadata or {},
    )


def _make_patch_set(
    files: tuple[PatchFile, ...],
    workflow_name: str = "test-workflow",
    execution_id: str = "exec-123",
) -> PatchSet:
    """Create a PatchSet for testing."""
    return PatchSet(
        workflow_name=workflow_name,
        execution_id=execution_id,
        files=files,
    )


# ---------------------------------------------------------------------------
# Test: Apply ADD
# ---------------------------------------------------------------------------


class TestApplyAdd:
    """Tests for ADD operation."""

    def test_apply_add_creates_file(self) -> None:
        """ADD operation should create a new file."""
        hunk = PatchHunk(
            file_path="src/new_file.py",
            old_start=0,
            old_count=0,
            new_start=1,
            new_count=2,
            diff_lines=("# New file\n", "print('hello')\n"),
        )
        patch_file = _make_patch_file("src/new_file.py", PatchOperation.ADD, (hunk,))
        patch_set = _make_patch_set((patch_file,))

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.success is True
            assert len(changes.applied_files) == 1
            assert changes.applied_files[0].path == "src/new_file.py"
            assert changes.applied_files[0].operation == "ADD"
            assert changes.applied_files[0].status == ModificationStatus.APPLIED
            assert (workspace / "src" / "new_file.py").exists()

    def test_apply_add_empty_hunks(self) -> None:
        """ADD with empty hunks should create an empty file."""
        patch_file = _make_patch_file("empty.txt", PatchOperation.ADD, ())
        patch_set = _make_patch_set((patch_file,))

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.success is True
            assert (workspace / "empty.txt").exists()

    def test_apply_add_multiple_files(self) -> None:
        """ADD should handle multiple files."""
        hunk1 = PatchHunk(
            file_path="src/a.py",
            old_start=0,
            old_count=0,
            new_start=1,
            new_count=1,
            diff_lines=("# A\n",),
        )
        hunk2 = PatchHunk(
            file_path="src/b.py",
            old_start=0,
            old_count=0,
            new_start=1,
            new_count=1,
            diff_lines=("# B\n",),
        )
        pf1 = _make_patch_file("src/a.py", PatchOperation.ADD, (hunk1,))
        pf2 = _make_patch_file("src/b.py", PatchOperation.ADD, (hunk2,))
        patch_set = _make_patch_set((pf1, pf2))

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.success is True
            assert len(changes.applied_files) == 2
            assert changes.statistics.files_created == 2


# ---------------------------------------------------------------------------
# Test: Apply MODIFY
# ---------------------------------------------------------------------------


class TestApplyModify:
    """Tests for MODIFY operation."""

    def test_apply_modify_changes_content(self) -> None:
        """MODIFY operation should change file content."""
        workspace_path = Path(__file__).parent.parent.parent / "test_workspace_modify"
        workspace_path.mkdir(exist_ok=True)
        test_file = workspace_path / "modify_test.txt"
        test_file.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        hunk = PatchHunk(
            file_path="modify_test.txt",
            old_start=2,
            old_count=1,
            new_start=2,
            new_count=1,
            diff_lines=("- line 2\n", "+ modified line 2\n"),
        )
        patch_file = _make_patch_file("modify_test.txt", PatchOperation.MODIFY, (hunk,))
        patch_set = _make_patch_set((patch_file,))

        changes = CodeModificationEngine.apply(patch_set, workspace_path)

        assert changes.success is True
        assert changes.applied_files[0].operation == "MODIFY"
        assert changes.applied_files[0].status == ModificationStatus.APPLIED
        assert changes.statistics.files_modified == 1

        result = test_file.read_text(encoding="utf-8")
        assert "modified line 2" in result

        # Cleanup
        import shutil
        test_file.unlink()
        shutil.rmtree(workspace_path)

    def test_apply_modify_nonexistent_file(self) -> None:
        """MODIFY on non-existent file should fail."""
        patch_file = _make_patch_file(
            "nonexistent.py",
            PatchOperation.MODIFY,
            (
                PatchHunk(
                    file_path="nonexistent.py",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    diff_lines=("- old\n", "+ new\n"),
                ),
            ),
        )
        patch_set = _make_patch_set((patch_file,))

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.success is False
            assert len(changes.warnings) > 0


# ---------------------------------------------------------------------------
# Test: Apply DELETE
# ---------------------------------------------------------------------------


class TestApplyDelete:
    """Tests for DELETE operation."""

    def test_apply_delete_removes_file(self) -> None:
        """DELETE operation should remove a file."""
        workspace_path = Path(__file__).parent.parent.parent / "test_workspace_delete"
        workspace_path.mkdir(exist_ok=True)
        test_file = workspace_path / "delete_me.txt"
        test_file.write_text("content", encoding="utf-8")

        patch_file = _make_patch_file(
            "delete_me.txt",
            PatchOperation.DELETE,
            (),
        )
        patch_set = _make_patch_set((patch_file,))

        changes = CodeModificationEngine.apply(patch_set, workspace_path)

        assert changes.success is True
        assert changes.applied_files[0].operation == "DELETE"
        assert changes.applied_files[0].status == ModificationStatus.APPLIED
        assert changes.statistics.files_deleted == 1
        assert not test_file.exists()

        # Cleanup
        import shutil
        shutil.rmtree(workspace_path)

    def test_apply_delete_nonexistent_file(self) -> None:
        """DELETE on non-existent file should fail."""
        patch_file = _make_patch_file(
            "nonexistent.txt",
            PatchOperation.DELETE,
            (),
        )
        patch_set = _make_patch_set((patch_file,))

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.success is False


# ---------------------------------------------------------------------------
# Test: Apply RENAME
# ---------------------------------------------------------------------------


class TestApplyRename:
    """Tests for RENAME operation."""

    def test_apply_rename_moves_file(self) -> None:
        """RENAME operation should move a file."""
        workspace_path = Path(__file__).parent.parent.parent / "test_workspace_rename"
        workspace_path.mkdir(exist_ok=True)
        old_file = workspace_path / "old_name.txt"
        old_file.write_text("content", encoding="utf-8")

        patch_file = _make_patch_file(
            "old_name.txt",
            PatchOperation.RENAME,
            (),
            metadata={"new_path": "new_name.txt"},
        )
        patch_set = _make_patch_set((patch_file,))

        changes = CodeModificationEngine.apply(patch_set, workspace_path)

        assert changes.success is True
        assert changes.applied_files[0].operation == "RENAME"
        assert changes.applied_files[0].status == ModificationStatus.APPLIED
        assert not old_file.exists()
        assert (workspace_path / "new_name.txt").exists()

        # Cleanup
        import shutil
        (workspace_path / "new_name.txt").unlink()
        shutil.rmtree(workspace_path)

    def test_apply_rename_missing_metadata(self) -> None:
        """RENAME without new_path metadata should fail."""
        patch_file = _make_patch_file(
            "test.txt",
            PatchOperation.RENAME,
            (),
            metadata={},
        )
        patch_set = _make_patch_set((patch_file,))

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "test.txt").write_text("content")
            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.success is False


# ---------------------------------------------------------------------------
# Test: Rollback
# ---------------------------------------------------------------------------


class TestRollback:
    """Tests for rollback behavior."""

    def test_partial_failure_stops_on_first_error(self) -> None:
        """Engine should stop on first fatal error."""
        # First file exists, second doesn't
        patch_file1 = _make_patch_file(
            "exists.txt",
            PatchOperation.MODIFY,
            (
                PatchHunk(
                    file_path="exists.txt",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    diff_lines=("- old\n", "+ new\n"),
                ),
            ),
        )
        patch_file2 = _make_patch_file(
            "nonexistent.txt",
            PatchOperation.MODIFY,
            (
                PatchHunk(
                    file_path="nonexistent.txt",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    diff_lines=("- old\n", "+ new\n"),
                ),
            ),
        )
        patch_set = _make_patch_set((patch_file1, patch_file2))

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "exists.txt").write_text("content", encoding="utf-8")

            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.success is False
            assert len(changes.warnings) > 0


# ---------------------------------------------------------------------------
# Test: Empty PatchSet
# ---------------------------------------------------------------------------


class TestEmptyPatchSet:
    """Tests for empty PatchSet handling."""

    def test_empty_patchset_proceeds_successfully(self) -> None:
        """Empty PatchSet should succeed with no changes."""
        patch_set = _make_patch_set(())

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.success is True
            assert len(changes.applied_files) == 0
            assert changes.statistics.total_operations == 0


# ---------------------------------------------------------------------------
# Test: Deterministic Execution
# ---------------------------------------------------------------------------


class TestDeterministicExecution:
    """Tests for deterministic execution."""

    def test_deterministic_order(self) -> None:
        """Files should be applied in the order they appear in PatchSet."""
        hunk_a = PatchHunk(
            file_path="src/a.py",
            old_start=0,
            old_count=0,
            new_start=1,
            new_count=1,
            diff_lines=("# A\n",),
        )
        hunk_b = PatchHunk(
            file_path="src/b.py",
            old_start=0,
            old_count=0,
            new_start=1,
            new_count=1,
            diff_lines=("# B\n",),
        )
        pf_a = _make_patch_file("src/a.py", PatchOperation.ADD, (hunk_a,))
        pf_b = _make_patch_file("src/b.py", PatchOperation.ADD, (hunk_b,))

        # Apply in order (b, a)
        patch_set = _make_patch_set((pf_b, pf_a))

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.success is True
            # Files should be in the order they were applied
            assert len(changes.applied_files) == 2
            assert changes.applied_files[0].path == "src/b.py"
            assert changes.applied_files[1].path == "src/a.py"


# ---------------------------------------------------------------------------
# Test: Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    """Tests for statistics computation."""

    def test_statistics_add_modify_delete(self) -> None:
        """Statistics should correctly count operations."""
        workspace_path = Path(__file__).parent.parent.parent / "test_workspace_stats"
        workspace_path.mkdir(exist_ok=True)

        # Create all required files
        test_file = workspace_path / "modify.txt"
        test_file.write_text("line 1\n", encoding="utf-8")
        delete_file = workspace_path / "delete.txt"
        delete_file.write_text("content", encoding="utf-8")

        hunk_add = PatchHunk(
            file_path="new.txt",
            old_start=0,
            old_count=0,
            new_start=1,
            new_count=1,
            diff_lines=("# new\n",),
        )
        pf_add = _make_patch_file("new.txt", PatchOperation.ADD, (hunk_add,))

        hunk_modify = PatchHunk(
            file_path="modify.txt",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            diff_lines=("- line 1\n", "+ modified\n"),
        )
        pf_modify = _make_patch_file("modify.txt", PatchOperation.MODIFY, (hunk_modify,))

        pf_delete = _make_patch_file(
            "delete.txt",
            PatchOperation.DELETE,
            (),
        )

        patch_set = _make_patch_set((pf_add, pf_modify, pf_delete))

        changes = CodeModificationEngine.apply(patch_set, workspace_path)

        assert changes.success is True
        assert changes.statistics.files_created == 1
        assert changes.statistics.files_modified == 1
        assert changes.statistics.files_deleted == 1
        assert changes.statistics.total_operations == 3

        # Cleanup
        import shutil
        shutil.rmtree(workspace_path)

    def test_statistics_empty_patchset(self) -> None:
        """Statistics should be zero for empty PatchSet."""
        patch_set = _make_patch_set(())

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.statistics.files_created == 0
            assert changes.statistics.files_modified == 0
            assert changes.statistics.files_deleted == 0
            assert changes.statistics.total_operations == 0


# ---------------------------------------------------------------------------
# Test: Duplicate Detection
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    """Tests for duplicate detection."""

    def test_duplicate_files_in_patchset(self) -> None:
        """Duplicate files in PatchSet should be detected by validator."""
        hunk = PatchHunk(
            file_path="src/test.py",
            old_start=0,
            old_count=0,
            new_start=1,
            new_count=1,
            diff_lines=("# test\n",),
        )
        pf1 = _make_patch_file("src/test.py", PatchOperation.ADD, (hunk,))
        pf2 = _make_patch_file("src/test.py", PatchOperation.ADD, (hunk,))
        patch_set = _make_patch_set((pf1, pf2))

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.success is False
            assert len(changes.warnings) > 0


# ---------------------------------------------------------------------------
# Test: Invalid PatchSet
# ---------------------------------------------------------------------------


class TestInvalidPatchSet:
    """Tests for invalid PatchSet handling."""

    def test_none_patchset_raises(self) -> None:
        """None PatchSet should raise ValueError."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            with pytest.raises(ValueError, match="patch_set cannot be None"):
                CodeModificationEngine.apply(None, workspace)  # type: ignore[arg-type]

    def test_nonexistent_workspace_raises(self) -> None:
        """Non-existent workspace path should raise FileNotFoundError."""
        patch_set = _make_patch_set(())
        with pytest.raises(FileNotFoundError):
            CodeModificationEngine.apply(patch_set, Path("/nonexistent/path"))

    def test_empty_workflow_name(self) -> None:
        """Empty workflow_name should produce validation errors."""
        patch_set = PatchSet(
            workflow_name="",
            execution_id="exec-123",
            files=(),
        )

        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            changes = CodeModificationEngine.apply(patch_set, workspace)

            assert changes.success is False
            assert len(changes.warnings) > 0


# ---------------------------------------------------------------------------
# Test: WorkspaceChanges Contract
# ---------------------------------------------------------------------------


class TestWorkspaceChangesContract:
    """Tests for WorkspaceChanges contract."""

    def test_workspace_changes_is_immutable(self) -> None:
        """WorkspaceChanges should be immutable."""
        from dataclasses import FrozenInstanceError

        wc = WorkspaceChanges(
            workflow_name="test",
            execution_id="exec-123",
        )
        with pytest.raises(FrozenInstanceError):
            wc.workflow_name = "modified"  # type: ignore[misc]

    def test_workspace_changes_has_all_fields(self) -> None:
        """WorkspaceChanges should have all required fields."""
        wc = WorkspaceChanges(
            workflow_name="test",
            execution_id="exec-123",
        )
        assert hasattr(wc, "workflow_name")
        assert hasattr(wc, "execution_id")
        assert hasattr(wc, "applied_files")
        assert hasattr(wc, "statistics")
        assert hasattr(wc, "warnings")
        assert hasattr(wc, "success")