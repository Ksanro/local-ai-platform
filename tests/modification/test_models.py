"""Tests for modification model definitions.

Verifies:
- Immutability (frozen=True, slots=True)
- Default values
- Construction with all fields
- Deterministic output
- Coverage >95%
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from packages.modification.models import (
    ModifiedFile,
    ModificationStatistics,
    ModificationStatus,
    WorkspaceChanges,
)


# ---------------------------------------------------------------------------
# Test: ModificationStatus
# ---------------------------------------------------------------------------


class TestModificationStatus:
    """Tests for ModificationStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """All ModificationStatus values must exist."""
        assert ModificationStatus.PENDING == "PENDING"
        assert ModificationStatus.APPLIED == "APPLIED"
        assert ModificationStatus.FAILED == "FAILED"
        assert ModificationStatus.ROLLED_BACK == "ROLLED_BACK"

    def test_status_values_are_uppercase(self) -> None:
        """All ModificationStatus values must be uppercase."""
        for status in ModificationStatus:
            assert status.value.isupper()

    def test_status_from_string(self) -> None:
        """ModificationStatus must be constructible from string."""
        assert ModificationStatus("PENDING") == ModificationStatus.PENDING
        assert ModificationStatus("APPLIED") == ModificationStatus.APPLIED
        assert ModificationStatus("FAILED") == ModificationStatus.FAILED
        assert ModificationStatus("ROLLED_BACK") == ModificationStatus.ROLLED_BACK

    def test_status_iteration(self) -> None:
        """ModificationStatus must be iterable."""
        statuses = list(ModificationStatus)
        assert len(statuses) == 4


# ---------------------------------------------------------------------------
# Test: ModifiedFile Immutability
# ---------------------------------------------------------------------------


class TestModifiedFileImmutability:
    """Tests for ModifiedFile immutability."""

    def test_model_is_frozen(self) -> None:
        """ModifiedFile should be immutable."""
        mf = ModifiedFile(
            path="src/main.py",
            operation="MODIFY",
            original_hash="abc123",
            resulting_hash="def456",
        )
        with pytest.raises(FrozenInstanceError):
            mf.path = "modified"  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """ModifiedFile should use slots."""
        mf = ModifiedFile(
            path="src/main.py",
            operation="MODIFY",
            original_hash="abc123",
            resulting_hash="def456",
        )
        assert not hasattr(mf, "__dict__")

    def test_model_cannot_add_arbitrary_attributes(self) -> None:
        """ModifiedFile should not allow arbitrary attribute addition."""
        mf = ModifiedFile(
            path="src/main.py",
            operation="MODIFY",
            original_hash="abc123",
            resulting_hash="def456",
        )
        with pytest.raises(FrozenInstanceError):
            mf.extra_field = "extra"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test: ModifiedFile Construction
# ---------------------------------------------------------------------------


class TestModifiedFileConstruction:
    """Tests for ModifiedFile construction."""

    def test_minimal_construction(self) -> None:
        """ModifiedFile should accept required fields only."""
        mf = ModifiedFile(
            path="src/main.py",
            operation="MODIFY",
            original_hash="abc123",
            resulting_hash="def456",
        )
        assert mf.path == "src/main.py"
        assert mf.operation == "MODIFY"
        assert mf.original_hash == "abc123"
        assert mf.resulting_hash == "def456"
        assert mf.changed_lines == ()
        assert mf.status == ModificationStatus.PENDING

    def test_full_construction(self) -> None:
        """ModifiedFile should accept all fields."""
        mf = ModifiedFile(
            path="src/main.py",
            operation="MODIFY",
            original_hash="abc123",
            resulting_hash="def456",
            changed_lines=(1, 2, 3),
            status=ModificationStatus.APPLIED,
        )
        assert mf.path == "src/main.py"
        assert mf.operation == "MODIFY"
        assert mf.original_hash == "abc123"
        assert mf.resulting_hash == "def456"
        assert mf.changed_lines == (1, 2, 3)
        assert mf.status == ModificationStatus.APPLIED

    def test_changed_lines_defaults_to_empty_tuple(self) -> None:
        """changed_lines should default to empty tuple."""
        mf = ModifiedFile(
            path="test",
            operation="ADD",
            original_hash="none",
            resulting_hash="hash",
        )
        assert mf.changed_lines == ()
        assert isinstance(mf.changed_lines, tuple)

    def test_status_defaults_to_pending(self) -> None:
        """status should default to PENDING."""
        mf = ModifiedFile(
            path="test",
            operation="ADD",
            original_hash="none",
            resulting_hash="hash",
        )
        assert mf.status == ModificationStatus.PENDING
        assert isinstance(mf.status, ModificationStatus)


# ---------------------------------------------------------------------------
# Test: ModificationStatistics Immutability
# ---------------------------------------------------------------------------


class TestModificationStatisticsImmutability:
    """Tests for ModificationStatistics immutability."""

    def test_model_is_frozen(self) -> None:
        """ModificationStatistics should be immutable."""
        stats = ModificationStatistics(
            files_modified=1,
            files_created=2,
            files_deleted=3,
            lines_added=10,
            lines_removed=5,
            total_operations=6,
        )
        with pytest.raises(FrozenInstanceError):
            stats.files_modified = 2  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """ModificationStatistics should use slots."""
        stats = ModificationStatistics(
            files_modified=1,
            files_created=2,
            files_deleted=3,
            lines_added=10,
            lines_removed=5,
            total_operations=6,
        )
        assert not hasattr(stats, "__dict__")


# ---------------------------------------------------------------------------
# Test: ModificationStatistics Construction
# ---------------------------------------------------------------------------


class TestModificationStatisticsConstruction:
    """Tests for ModificationStatistics construction."""

    def test_default_values(self) -> None:
        """ModificationStatistics should have correct default values."""
        stats = ModificationStatistics()
        assert stats.files_modified == 0
        assert stats.files_created == 0
        assert stats.files_deleted == 0
        assert stats.lines_added == 0
        assert stats.lines_removed == 0
        assert stats.total_operations == 0

    def test_full_construction(self) -> None:
        """ModificationStatistics should accept all fields."""
        stats = ModificationStatistics(
            files_modified=3,
            files_created=2,
            files_deleted=1,
            lines_added=50,
            lines_removed=30,
            total_operations=6,
        )
        assert stats.files_modified == 3
        assert stats.files_created == 2
        assert stats.files_deleted == 1
        assert stats.lines_added == 50
        assert stats.lines_removed == 30
        assert stats.total_operations == 6


# ---------------------------------------------------------------------------
# Test: WorkspaceChanges Immutability
# ---------------------------------------------------------------------------


class TestWorkspaceChangesImmutability:
    """Tests for WorkspaceChanges immutability."""

    def test_model_is_frozen(self) -> None:
        """WorkspaceChanges should be immutable."""
        wc = WorkspaceChanges(
            workflow_name="test",
            execution_id="exec-123",
        )
        with pytest.raises(FrozenInstanceError):
            wc.workflow_name = "modified"  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """WorkspaceChanges should use slots."""
        wc = WorkspaceChanges(
            workflow_name="test",
            execution_id="exec-123",
        )
        assert not hasattr(wc, "__dict__")


# ---------------------------------------------------------------------------
# Test: WorkspaceChanges Construction
# ---------------------------------------------------------------------------


class TestWorkspaceChangesConstruction:
    """Tests for WorkspaceChanges construction."""

    def test_minimal_construction(self) -> None:
        """WorkspaceChanges should accept required fields only."""
        wc = WorkspaceChanges(
            workflow_name="test",
            execution_id="exec-123",
        )
        assert wc.workflow_name == "test"
        assert wc.execution_id == "exec-123"
        assert wc.applied_files == ()
        assert wc.statistics.files_modified == 0
        assert wc.warnings == ()
        assert wc.success is True

    def test_full_construction(self) -> None:
        """WorkspaceChanges should accept all fields."""
        mf = ModifiedFile(
            path="src/main.py",
            operation="MODIFY",
            original_hash="abc123",
            resulting_hash="def456",
            status=ModificationStatus.APPLIED,
        )
        stats = ModificationStatistics(
            files_modified=1,
            files_created=0,
            files_deleted=0,
            lines_added=5,
            lines_removed=3,
            total_operations=1,
        )
        wc = WorkspaceChanges(
            workflow_name="implement_feature",
            execution_id="exec-456",
            applied_files=(mf,),
            statistics=stats,
            warnings=("Warning 1", "Warning 2"),
            success=True,
        )
        assert wc.workflow_name == "implement_feature"
        assert wc.execution_id == "exec-456"
        assert len(wc.applied_files) == 1
        assert wc.statistics.files_modified == 1
        assert len(wc.warnings) == 2
        assert wc.success is True

    def test_applied_files_defaults_to_empty_tuple(self) -> None:
        """applied_files should default to empty tuple."""
        wc = WorkspaceChanges(
            workflow_name="test",
            execution_id="test",
        )
        assert wc.applied_files == ()
        assert isinstance(wc.applied_files, tuple)

    def test_warnings_defaults_to_empty_tuple(self) -> None:
        """warnings should default to empty tuple."""
        wc = WorkspaceChanges(
            workflow_name="test",
            execution_id="test",
        )
        assert wc.warnings == ()
        assert isinstance(wc.warnings, tuple)

    def test_success_defaults_to_true(self) -> None:
        """success should default to True."""
        wc = WorkspaceChanges(
            workflow_name="test",
            execution_id="test",
        )
        assert wc.success is True


# ---------------------------------------------------------------------------
# Test: Deterministic Output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_deterministic_modified_file(self) -> None:
        """Same inputs should produce identical ModifiedFiles."""
        mf1 = ModifiedFile(
            path="test",
            operation="MODIFY",
            original_hash="abc",
            resulting_hash="def",
        )
        mf2 = ModifiedFile(
            path="test",
            operation="MODIFY",
            original_hash="abc",
            resulting_hash="def",
        )
        assert mf1.path == mf2.path
        assert mf1.operation == mf2.operation
        assert mf1.original_hash == mf2.original_hash

    def test_deterministic_workspace_changes(self) -> None:
        """Same inputs should produce identical WorkspaceChanges."""
        wc1 = WorkspaceChanges(
            workflow_name="test",
            execution_id="exec-1",
        )
        wc2 = WorkspaceChanges(
            workflow_name="test",
            execution_id="exec-1",
        )
        assert wc1.workflow_name == wc2.workflow_name
        assert wc1.execution_id == wc2.execution_id


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_file_path(self) -> None:
        """ModifiedFile should handle empty file path."""
        mf = ModifiedFile(
            path="",
            operation="ADD",
            original_hash="none",
            resulting_hash="hash",
        )
        assert mf.path == ""

    def test_unicode_file_path(self) -> None:
        """ModifiedFile should handle unicode in file path."""
        mf = ModifiedFile(
            path="src/\u4f60\u597d.py",
            operation="MODIFY",
            original_hash="abc",
            resulting_hash="def",
        )
        assert mf.path == "src/\u4f60\u597d.py"

    def test_empty_original_hash(self) -> None:
        """ModifiedFile should handle empty original hash."""
        mf = ModifiedFile(
            path="test",
            operation="ADD",
            original_hash="",
            resulting_hash="hash",
        )
        assert mf.original_hash == ""

    def test_deleted_resulting_hash(self) -> None:
        """ModifiedFile should handle 'deleted' resulting hash."""
        mf = ModifiedFile(
            path="test",
            operation="DELETE",
            original_hash="abc",
            resulting_hash="deleted",
        )
        assert mf.resulting_hash == "deleted"

    def test_all_operations(self) -> None:
        """ModifiedFile should handle all operation types."""
        for op in ("ADD", "MODIFY", "DELETE", "RENAME"):
            mf = ModifiedFile(
                path="test",
                operation=op,
                original_hash="hash",
                resulting_hash="hash",
            )
            assert mf.operation == op

    def test_all_statuses(self) -> None:
        """ModifiedFile should handle all status types."""
        for status in ModificationStatus:
            mf = ModifiedFile(
                path="test",
                operation="MODIFY",
                original_hash="hash",
                resulting_hash="hash",
                status=status,
            )
            assert mf.status == status

    def test_large_changed_lines(self) -> None:
        """ModifiedFile should handle large changed_lines tuple."""
        mf = ModifiedFile(
            path="test",
            operation="MODIFY",
            original_hash="abc",
            resulting_hash="def",
            changed_lines=tuple(range(1, 10001)),
        )
        assert len(mf.changed_lines) == 10000

    def test_empty_warnings(self) -> None:
        """WorkspaceChanges should handle empty warnings."""
        wc = WorkspaceChanges(
            workflow_name="test",
            execution_id="test",
            warnings=(),
        )
        assert wc.warnings == ()

    def test_failure_status(self) -> None:
        """WorkspaceChanges should handle success=False."""
        wc = WorkspaceChanges(
            workflow_name="test",
            execution_id="test",
            success=False,
        )
        assert wc.success is False