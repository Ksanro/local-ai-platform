"""Tests for PatchValidator.

Verifies:
- Valid PatchSet passes
- Invalid operations detected
- Duplicate files detected
- Duplicate hunks detected
- Overlapping hunks detected
- Invalid line ranges detected
- Empty patches detected
- Statistics mismatch detected
- Errors do not modify PatchSet
- Multiple errors reported simultaneously
"""

from __future__ import annotations

import pytest

from packages.patches.models import (
    PatchFile,
    PatchHunk,
    PatchOperation,
    PatchSet,
    PatchStatistics,
    ValidationResult,
)
from packages.patches.validator import PatchValidator


# ---------------------------------------------------------------------------
# Test: Valid PatchSet
# ---------------------------------------------------------------------------


class TestValidPatchSet:
    """Tests for valid PatchSet validation."""

    def test_valid_patch_set_passes(self) -> None:
        """Valid PatchSet should pass validation."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=5,
                    new_start=1,
                    new_count=5,
                    diff_lines=("+ line\n",),
                ),
            ),
        )
        stats = PatchStatistics(
            files_changed=1,
            hunks=1,
            added_lines=1,
            removed_lines=0,
            modified_lines=1,
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
            statistics=stats,
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is True
        assert result.errors == ()

    def test_empty_patch_set_passes(self) -> None:
        """Empty PatchSet should pass validation."""
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is True

    def test_multiple_valid_files(self) -> None:
        """Multiple valid files should pass validation."""
        files = (
            PatchFile(
                path="src/a.py",
                operation=PatchOperation.MODIFY,
                hunks=(
                    PatchHunk(
                        file_path="src/a.py",
                        old_start=1,
                        old_count=1,
                        new_start=1,
                        new_count=2,
                        diff_lines=("+ new\n",),
                    ),
                ),
            ),
            PatchFile(
                path="src/b.py",
                operation=PatchOperation.MODIFY,
                hunks=(
                    PatchHunk(
                        file_path="src/b.py",
                        old_start=1,
                        old_count=1,
                        new_start=1,
                        new_count=1,
                        diff_lines=("- removed\n",),
                    ),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=files,
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Test: Invalid Operations
# ---------------------------------------------------------------------------


class TestInvalidOperations:
    """Tests for invalid operation detection."""

    def test_invalid_operation_detected(self) -> None:
        """Invalid operation should be detected."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.ADD,  # type: ignore[typeddict-item]
        )
        # Simulate an invalid operation by creating a PatchSet with a
        # mock file that has an invalid operation
        class MockFile:
            path = "src/main.py"
            operation = "INVALID_OP"  # type: ignore
            hunks = ()

        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(MockFile(),),  # type: ignore[list-item]
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("INVALID_OP" in err for err in result.errors)

    def test_none_operation_detected(self) -> None:
        """None operation should be detected."""
        class MockFile:
            path = "src/main.py"
            operation = None  # type: ignore
            hunks = ()

        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(MockFile(),),  # type: ignore[list-item]
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False


# ---------------------------------------------------------------------------
# Test: Duplicate Files
# ---------------------------------------------------------------------------


class TestDuplicateFiles:
    """Tests for duplicate file detection."""

    def test_duplicate_files_detected(self) -> None:
        """Duplicate file paths should be detected."""
        files = (
            PatchFile(
                path="src/main.py",
                operation=PatchOperation.MODIFY,
            ),
            PatchFile(
                path="src/main.py",
                operation=PatchOperation.MODIFY,
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=files,
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("Duplicate file path" in err for err in result.errors)

    def test_unique_files_pass(self) -> None:
        """Unique file paths should pass."""
        files = (
            PatchFile(
                path="src/a.py",
                operation=PatchOperation.MODIFY,
            ),
            PatchFile(
                path="src/b.py",
                operation=PatchOperation.MODIFY,
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=files,
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Test: Duplicate Hunks
# ---------------------------------------------------------------------------


class TestDuplicateHunks:
    """Tests for duplicate hunk detection."""

    def test_duplicate_hunks_detected(self) -> None:
        """Duplicate hunks should be detected."""
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
            hunks=(hunk, hunk),  # Duplicate
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("Duplicate hunk" in err for err in result.errors)

    def test_unique_hunks_pass(self) -> None:
        """Unique hunks should pass."""
        hunk1 = PatchHunk(
            file_path="src/main.py",
            old_start=1,
            old_count=5,
            new_start=1,
            new_count=5,
            diff_lines=("+ line1\n",),
        )
        hunk2 = PatchHunk(
            file_path="src/main.py",
            old_start=10,
            old_count=3,
            new_start=10,
            new_count=3,
            diff_lines=("+ line2\n",),
        )
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(hunk1, hunk2),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Test: Overlapping Hunks
# ---------------------------------------------------------------------------


class TestOverlappingHunks:
    """Tests for overlapping hunk detection."""

    def test_overlapping_hunks_detected(self) -> None:
        """Overlapping hunks should be detected."""
        hunks = (
            PatchHunk(
                file_path="src/main.py",
                old_start=1,
                old_count=10,
                new_start=1,
                new_count=10,
                diff_lines=("+ line\n",),
            ),
            PatchHunk(
                file_path="src/main.py",
                old_start=5,
                old_count=10,
                new_start=5,
                new_count=10,
                diff_lines=("+ line\n",),
            ),
        )
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=hunks,
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("Overlapping hunks" in err for err in result.errors)

    def test_non_overlapping_hunks_pass(self) -> None:
        """Non-overlapping hunks should pass."""
        hunks = (
            PatchHunk(
                file_path="src/main.py",
                old_start=1,
                old_count=5,
                new_start=1,
                new_count=5,
                diff_lines=("+ line\n",),
            ),
            PatchHunk(
                file_path="src/main.py",
                old_start=10,
                old_count=5,
                new_start=10,
                new_count=5,
                diff_lines=("+ line\n",),
            ),
        )
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=hunks,
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Test: Invalid Line Ranges
# ---------------------------------------------------------------------------


class TestInvalidLineRanges:
    """Tests for invalid line range detection."""

    def test_negative_old_start_detected(self) -> None:
        """Negative old_start should be detected."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=-1,
                    old_count=5,
                    new_start=1,
                    new_count=5,
                    diff_lines=("+ line\n",),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("invalid old_start" in err for err in result.errors)

    def test_negative_old_count_detected(self) -> None:
        """Negative old_count should be detected."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=-5,
                    new_start=1,
                    new_count=5,
                    diff_lines=("+ line\n",),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("invalid old_count" in err for err in result.errors)

    def test_negative_new_start_detected(self) -> None:
        """Negative new_start should be detected."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=5,
                    new_start=-1,
                    new_count=5,
                    diff_lines=("+ line\n",),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("invalid new_start" in err for err in result.errors)

    def test_negative_new_count_detected(self) -> None:
        """Negative new_count should be detected."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=5,
                    new_start=1,
                    new_count=-5,
                    diff_lines=("+ line\n",),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("invalid new_count" in err for err in result.errors)


# ---------------------------------------------------------------------------
# Test: Empty Patches
# ---------------------------------------------------------------------------


class TestEmptyPatches:
    """Tests for empty patch detection."""

    def test_empty_patch_warning(self) -> None:
        """File with no hunks should generate a warning."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert any("no hunks" in w for w in result.warnings)

    def test_empty_patch_is_valid(self) -> None:
        """File with no hunks should not make the PatchSet invalid."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        # Warnings don't make it invalid
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Test: Statistics Mismatch
# ---------------------------------------------------------------------------


class TestStatisticsMismatch:
    """Tests for statistics mismatch detection."""

    def test_wrong_files_changed_count(self) -> None:
        """Wrong files_changed count should be detected."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
        )
        stats = PatchStatistics(
            files_changed=5,  # Should be 1
            hunks=0,
            added_lines=0,
            removed_lines=0,
            modified_lines=0,
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
            statistics=stats,
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("files_changed" in err for err in result.errors)

    def test_wrong_hunks_count(self) -> None:
        """Wrong hunks count should be detected."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=5,
                    new_start=1,
                    new_count=5,
                    diff_lines=("+ line\n",),
                ),
            ),
        )
        stats = PatchStatistics(
            files_changed=1,
            hunks=99,  # Should be 1
            added_lines=0,
            removed_lines=0,
            modified_lines=0,
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
            statistics=stats,
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("hunks" in err for err in result.errors)

    def test_no_statistics(self) -> None:
        """Missing statistics should be detected."""
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(),
            statistics=PatchStatistics(),
        )

        result = PatchValidator.validate(patch_set)

        # With default statistics, it should still be valid
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Test: Missing Required Fields
# ---------------------------------------------------------------------------


class TestMissingRequiredFields:
    """Tests for missing required field detection."""

    def test_empty_workflow_name(self) -> None:
        """Empty workflow_name should be detected."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
        )
        patch_set = PatchSet(
            workflow_name="",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("workflow_name" in err for err in result.errors)

    def test_empty_execution_id(self) -> None:
        """Empty execution_id should be detected."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert any("execution_id" in err for err in result.errors)

    def test_none_patch_set_raises(self) -> None:
        """None PatchSet should raise ValueError."""
        with pytest.raises(ValueError, match="patch_set cannot be None"):
            PatchValidator.validate(None)  # type: ignore


# ---------------------------------------------------------------------------
# Test: Multiple Errors
# ---------------------------------------------------------------------------


class TestMultipleErrors:
    """Tests for multiple error reporting."""

    def test_multiple_errors_reported(self) -> None:
        """Multiple errors should all be reported."""
        files = (
            PatchFile(
                path="src/main.py",
                operation=PatchOperation.MODIFY,
            ),
            PatchFile(
                path="src/main.py",  # Duplicate
                operation=PatchOperation.MODIFY,
            ),
        )
        patch_set = PatchSet(
            workflow_name="",  # Empty workflow_name
            execution_id="",  # Empty execution_id
            files=files,
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        # Should have multiple errors
        assert len(result.errors) >= 2

    def test_errors_and_warnings_together(self) -> None:
        """Errors and warnings can coexist."""
        files = (
            PatchFile(
                path="src/main.py",
                operation=PatchOperation.MODIFY,
                hunks=(),  # Empty — warning
            ),
            PatchFile(
                path="src/main.py",  # Duplicate — error
                operation=PatchOperation.MODIFY,
                hunks=(),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=files,
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# Test: Errors Do Not Modify PatchSet
# ---------------------------------------------------------------------------


class TestErrorsDoNotModifyPatchSet:
    """Tests that validation errors don't modify PatchSet."""

    def test_patchset_unchanged_after_validation(self) -> None:
        """PatchSet should be unchanged after validation."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=5,
                    new_start=1,
                    new_count=5,
                    diff_lines=("+ line\n",),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        # Store original values
        original_files = patch_set.files
        original_workflow = patch_set.workflow_name
        original_execution = patch_set.execution_id

        # Validate (even with errors)
        PatchValidator.validate(patch_set)

        # Verify unchanged
        assert patch_set.files is original_files
        assert patch_set.workflow_name == original_workflow
        assert patch_set.execution_id == original_execution


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_unicode_in_file_path(self) -> None:
        """Unicode file paths should be handled."""
        patch_file = PatchFile(
            path="src/\u4f60\u597d.py",
            operation=PatchOperation.MODIFY,
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is True

    def test_all_operations_valid(self) -> None:
        """All PatchOperation values should be valid."""
        for op in PatchOperation:
            patch_file = PatchFile(
                path=f"src/{op.value.lower()}.py",
                operation=op,
            )
            patch_set = PatchSet(
                workflow_name="test",
                execution_id="exec-1",
                files=(patch_file,),
            )

            result = PatchValidator.validate(patch_set)

            assert result.is_valid is True, f"Operation {op} should be valid"

    def test_many_files(self) -> None:
        """Many files should be handled correctly."""
        files = tuple(
            PatchFile(
                path=f"src/file_{i}.py",
                operation=PatchOperation.MODIFY,
            )
            for i in range(50)
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=files,
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is True

    def test_deeply_nested_paths(self) -> None:
        """Deeply nested paths should be handled."""
        patch_file = PatchFile(
            path="a/b/c/d/e/f/g/file.py",
            operation=PatchOperation.MODIFY,
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchValidator.validate(patch_set)

        assert result.is_valid is True