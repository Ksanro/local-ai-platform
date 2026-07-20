"""Tests for Patch model definitions.

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

from packages.patches.models import (
    PatchFile,
    PatchHunk,
    PatchOperation,
    PatchSet,
    PatchStatistics,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Test: PatchOperation
# ---------------------------------------------------------------------------


class TestPatchOperation:
    """Tests for PatchOperation enum."""

    def test_all_operations_exist(self) -> None:
        """All PatchOperation values must exist."""
        assert PatchOperation.ADD == "ADD"
        assert PatchOperation.DELETE == "DELETE"
        assert PatchOperation.MODIFY == "MODIFY"
        assert PatchOperation.RENAME == "RENAME"

    def test_operation_values_are_uppercase(self) -> None:
        """All PatchOperation values must be uppercase."""
        for op in PatchOperation:
            assert op.value.isupper()

    def test_operation_from_string(self) -> None:
        """PatchOperation must be constructible from string."""
        assert PatchOperation("ADD") == PatchOperation.ADD
        assert PatchOperation("DELETE") == PatchOperation.DELETE
        assert PatchOperation("MODIFY") == PatchOperation.MODIFY
        assert PatchOperation("RENAME") == PatchOperation.RENAME

    def test_operation_iteration(self) -> None:
        """PatchOperation must be iterable."""
        ops = list(PatchOperation)
        assert len(ops) == 4


# ---------------------------------------------------------------------------
# Test: PatchHunk Immutability
# ---------------------------------------------------------------------------


class TestPatchHunkImmutability:
    """Tests for PatchHunk immutability."""

    def test_model_is_frozen(self) -> None:
        """PatchHunk should be immutable."""
        hunk = PatchHunk(
            file_path="src/main.py",
            old_start=1,
            old_count=5,
            new_start=1,
            new_count=5,
            diff_lines=("+ line\n",),
        )
        with pytest.raises(FrozenInstanceError):
            hunk.file_path = "modified"  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """PatchHunk should use slots."""
        hunk = PatchHunk(
            file_path="src/main.py",
            old_start=1,
            old_count=5,
            new_start=1,
            new_count=5,
            diff_lines=("+ line\n",),
        )
        assert not hasattr(hunk, "__dict__")

    def test_model_cannot_add_arbitrary_attributes(self) -> None:
        """PatchHunk should not allow arbitrary attribute addition."""
        hunk = PatchHunk(
            file_path="src/main.py",
            old_start=1,
            old_count=5,
            new_start=1,
            new_count=5,
            diff_lines=("+ line\n",),
        )
        with pytest.raises(FrozenInstanceError):
            hunk.extra_field = "extra"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test: PatchHunk Construction
# ---------------------------------------------------------------------------


class TestPatchHunkConstruction:
    """Tests for PatchHunk construction."""

    def test_minimal_construction(self) -> None:
        """PatchHunk should accept required fields only."""
        hunk = PatchHunk(
            file_path="src/main.py",
            old_start=1,
            old_count=0,
            new_start=1,
            new_count=0,
        )
        assert hunk.file_path == "src/main.py"
        assert hunk.old_start == 1
        assert hunk.old_count == 0
        assert hunk.new_start == 1
        assert hunk.new_count == 0
        assert hunk.diff_lines == ()

    def test_full_construction(self) -> None:
        """PatchHunk should accept all fields."""
        hunk = PatchHunk(
            file_path="src/main.py",
            old_start=10,
            old_count=5,
            new_start=10,
            new_count=7,
            diff_lines=("@@ -10,5 +10,7 @@\n", "- old\n", "+ new\n", "+ new2\n"),
        )
        assert hunk.file_path == "src/main.py"
        assert hunk.old_start == 10
        assert hunk.old_count == 5
        assert hunk.new_start == 10
        assert hunk.new_count == 7
        assert len(hunk.diff_lines) == 4

    def test_diff_lines_defaults_to_empty_tuple(self) -> None:
        """diff_lines should default to empty tuple."""
        hunk = PatchHunk(
            file_path="test",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
        )
        assert hunk.diff_lines == ()
        assert isinstance(hunk.diff_lines, tuple)


# ---------------------------------------------------------------------------
# Test: PatchFile Immutability
# ---------------------------------------------------------------------------


class TestPatchFileImmutability:
    """Tests for PatchFile immutability."""

    def test_model_is_frozen(self) -> None:
        """PatchFile should be immutable."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
        )
        with pytest.raises(FrozenInstanceError):
            patch_file.path = "modified"  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """PatchFile should use slots."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
        )
        assert not hasattr(patch_file, "__dict__")


# ---------------------------------------------------------------------------
# Test: PatchFile Construction
# ---------------------------------------------------------------------------


class TestPatchFileConstruction:
    """Tests for PatchFile construction."""

    def test_minimal_construction(self) -> None:
        """PatchFile should accept required fields only."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
        )
        assert patch_file.path == "src/main.py"
        assert patch_file.operation == PatchOperation.MODIFY
        assert patch_file.hunks == ()
        assert patch_file.estimated_changed_lines == 0
        assert patch_file.metadata == {}

    def test_full_construction(self) -> None:
        """PatchFile should accept all fields."""
        hunk = PatchHunk(
            file_path="src/main.py",
            old_start=1,
            old_count=5,
            new_start=1,
            new_count=5,
            diff_lines=("+ line\n",),
        )
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(hunk,),
            estimated_changed_lines=10,
            metadata={"author": "system"},
        )
        assert patch_file.path == "src/main.py"
        assert patch_file.operation == PatchOperation.MODIFY
        assert len(patch_file.hunks) == 1
        assert patch_file.estimated_changed_lines == 10
        assert patch_file.metadata == {"author": "system"}

    def test_hunks_defaults_to_empty_tuple(self) -> None:
        """hunks should default to empty tuple."""
        patch_file = PatchFile(
            path="test",
            operation=PatchOperation.ADD,
        )
        assert patch_file.hunks == ()
        assert isinstance(patch_file.hunks, tuple)

    def test_metadata_defaults_to_empty_dict(self) -> None:
        """metadata should default to empty dict."""
        patch_file = PatchFile(
            path="test",
            operation=PatchOperation.ADD,
        )
        assert patch_file.metadata == {}
        assert isinstance(patch_file.metadata, dict)

    def test_metadata_is_independent(self) -> None:
        """Each PatchFile should have independent metadata."""
        f1 = PatchFile(
            path="f1",
            operation=PatchOperation.ADD,
            metadata={"key": "value1"},
        )
        f2 = PatchFile(
            path="f2",
            operation=PatchOperation.ADD,
            metadata={"key": "value2"},
        )
        assert f1.metadata is not f2.metadata
        assert f1.metadata["key"] == "value1"
        assert f2.metadata["key"] == "value2"


# ---------------------------------------------------------------------------
# Test: PatchStatistics Immutability
# ---------------------------------------------------------------------------


class TestPatchStatisticsImmutability:
    """Tests for PatchStatistics immutability."""

    def test_model_is_frozen(self) -> None:
        """PatchStatistics should be immutable."""
        stats = PatchStatistics(
            files_changed=1,
            hunks=1,
            added_lines=5,
            removed_lines=3,
            modified_lines=1,
        )
        with pytest.raises(FrozenInstanceError):
            stats.files_changed = 2  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """PatchStatistics should use slots."""
        stats = PatchStatistics(
            files_changed=1,
            hunks=1,
            added_lines=5,
            removed_lines=3,
            modified_lines=1,
        )
        assert not hasattr(stats, "__dict__")


# ---------------------------------------------------------------------------
# Test: PatchStatistics Construction
# ---------------------------------------------------------------------------


class TestPatchStatisticsConstruction:
    """Tests for PatchStatistics construction."""

    def test_default_values(self) -> None:
        """PatchStatistics should have correct default values."""
        stats = PatchStatistics()
        assert stats.files_changed == 0
        assert stats.hunks == 0
        assert stats.added_lines == 0
        assert stats.removed_lines == 0
        assert stats.modified_lines == 0

    def test_full_construction(self) -> None:
        """PatchStatistics should accept all fields."""
        stats = PatchStatistics(
            files_changed=3,
            hunks=10,
            added_lines=50,
            removed_lines=30,
            modified_lines=2,
        )
        assert stats.files_changed == 3
        assert stats.hunks == 10
        assert stats.added_lines == 50
        assert stats.removed_lines == 30
        assert stats.modified_lines == 2


# ---------------------------------------------------------------------------
# Test: PatchSet Immutability
# ---------------------------------------------------------------------------


class TestPatchSetImmutability:
    """Tests for PatchSet immutability."""

    def test_model_is_frozen(self) -> None:
        """PatchSet should be immutable."""
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-123",
        )
        with pytest.raises(FrozenInstanceError):
            patch_set.workflow_name = "modified"  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """PatchSet should use slots."""
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-123",
        )
        assert not hasattr(patch_set, "__dict__")


# ---------------------------------------------------------------------------
# Test: PatchSet Construction
# ---------------------------------------------------------------------------


class TestPatchSetConstruction:
    """Tests for PatchSet construction."""

    def test_minimal_construction(self) -> None:
        """PatchSet should accept required fields only."""
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-123",
        )
        assert patch_set.workflow_name == "test"
        assert patch_set.execution_id == "exec-123"
        assert patch_set.generated_from == ()
        assert patch_set.files == ()
        assert patch_set.statistics.files_changed == 0
        assert patch_set.warnings == ()

    def test_full_construction(self) -> None:
        """PatchSet should accept all fields."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
        )
        stats = PatchStatistics(
            files_changed=1,
            hunks=1,
            added_lines=5,
            removed_lines=3,
            modified_lines=1,
        )
        patch_set = PatchSet(
            workflow_name="implement_feature",
            execution_id="exec-456",
            generated_from=("workflow:implement_feature", "execution:exec-456"),
            files=(patch_file,),
            statistics=stats,
            warnings=("Warning 1", "Warning 2"),
        )
        assert patch_set.workflow_name == "implement_feature"
        assert patch_set.execution_id == "exec-456"
        assert len(patch_set.generated_from) == 2
        assert len(patch_set.files) == 1
        assert patch_set.statistics.files_changed == 1
        assert len(patch_set.warnings) == 2

    def test_generated_from_defaults_to_empty_tuple(self) -> None:
        """generated_from should default to empty tuple."""
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="test",
        )
        assert patch_set.generated_from == ()
        assert isinstance(patch_set.generated_from, tuple)

    def test_files_defaults_to_empty_tuple(self) -> None:
        """files should default to empty tuple."""
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="test",
        )
        assert patch_set.files == ()
        assert isinstance(patch_set.files, tuple)

    def test_warnings_defaults_to_empty_tuple(self) -> None:
        """warnings should default to empty tuple."""
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="test",
        )
        assert patch_set.warnings == ()
        assert isinstance(patch_set.warnings, tuple)


# ---------------------------------------------------------------------------
# Test: ValidationResult Immutability
# ---------------------------------------------------------------------------


class TestValidationResultImmutability:
    """Tests for ValidationResult immutability."""

    def test_model_is_frozen(self) -> None:
        """ValidationResult should be immutable."""
        result = ValidationResult(is_valid=True)
        with pytest.raises(FrozenInstanceError):
            result.is_valid = False  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """ValidationResult should use slots."""
        result = ValidationResult(is_valid=True)
        assert not hasattr(result, "__dict__")


# ---------------------------------------------------------------------------
# Test: ValidationResult Construction
# ---------------------------------------------------------------------------


class TestValidationResultConstruction:
    """Tests for ValidationResult construction."""

    def test_minimal_construction(self) -> None:
        """ValidationResult should accept required fields only."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == ()
        assert result.warnings == ()

    def test_full_construction(self) -> None:
        """ValidationResult should accept all fields."""
        result = ValidationResult(
            is_valid=False,
            errors=("Error 1", "Error 2"),
            warnings=("Warning 1",),
        )
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1

    def test_errors_defaults_to_empty_tuple(self) -> None:
        """errors should default to empty tuple."""
        result = ValidationResult(is_valid=True)
        assert result.errors == ()
        assert isinstance(result.errors, tuple)

    def test_warnings_defaults_to_empty_tuple(self) -> None:
        """warnings should default to empty tuple."""
        result = ValidationResult(is_valid=True)
        assert result.warnings == ()
        assert isinstance(result.warnings, tuple)


# ---------------------------------------------------------------------------
# Test: Deterministic Output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_deterministic_hunk(self) -> None:
        """Same inputs should produce identical hunks."""
        h1 = PatchHunk(
            file_path="test",
            old_start=1,
            old_count=5,
            new_start=1,
            new_count=5,
            diff_lines=("+ line\n",),
        )
        h2 = PatchHunk(
            file_path="test",
            old_start=1,
            old_count=5,
            new_start=1,
            new_count=5,
            diff_lines=("+ line\n",),
        )
        assert h1.file_path == h2.file_path
        assert h1.old_start == h2.old_start
        assert h1.diff_lines == h2.diff_lines

    def test_deterministic_patch_set(self) -> None:
        """Same inputs should produce identical PatchSets."""
        ps1 = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
        )
        ps2 = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
        )
        assert ps1.workflow_name == ps2.workflow_name
        assert ps1.execution_id == ps2.execution_id


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_file_path(self) -> None:
        """PatchHunk should handle empty file path."""
        hunk = PatchHunk(
            file_path="",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
        )
        assert hunk.file_path == ""

    def test_negative_old_start(self) -> None:
        """PatchHunk should handle negative old_start."""
        hunk = PatchHunk(
            file_path="test",
            old_start=-1,
            old_count=1,
            new_start=1,
            new_count=1,
        )
        assert hunk.old_start == -1

    def test_large_line_numbers(self) -> None:
        """PatchHunk should handle large line numbers."""
        hunk = PatchHunk(
            file_path="test",
            old_start=1000000,
            old_count=500000,
            new_start=1000000,
            new_count=500000,
        )
        assert hunk.old_start == 1000000
        assert hunk.old_count == 500000

    def test_unicode_file_path(self) -> None:
        """PatchHunk should handle unicode in file path."""
        hunk = PatchHunk(
            file_path="src/\u4f60\u597d.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
        )
        assert hunk.file_path == "src/\u4f60\u597d.py"

    def test_empty_diff_lines(self) -> None:
        """PatchHunk should handle empty diff_lines."""
        hunk = PatchHunk(
            file_path="test",
            old_start=1,
            old_count=0,
            new_start=1,
            new_count=0,
            diff_lines=(),
        )
        assert hunk.diff_lines == ()

    def test_single_diff_line(self) -> None:
        """PatchHunk should handle single diff line."""
        hunk = PatchHunk(
            file_path="test",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            diff_lines=("+ new line\n",),
        )
        assert len(hunk.diff_lines) == 1

    def test_all_operations(self) -> None:
        """PatchFile should handle all operations."""
        for op in PatchOperation:
            patch_file = PatchFile(
                path="test",
                operation=op,
            )
            assert patch_file.operation == op

    def test_empty_metadata(self) -> None:
        """PatchFile should handle empty metadata."""
        patch_file = PatchFile(
            path="test",
            operation=PatchOperation.ADD,
            metadata={},
        )
        assert patch_file.metadata == {}

    def test_unicode_in_warnings(self) -> None:
        """PatchSet should handle unicode in warnings."""
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="test",
            warnings=("Warning: \u4f60\u597d",),
        )
        assert patch_set.warnings == ("Warning: \u4f60\u597d",)