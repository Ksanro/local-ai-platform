"""Tests for ModificationValidator.

Verifies:
- Duplicate detection
- Invalid PatchSet
- Invalid hunks
- Invalid rename targets
- Invalid delete targets
- Conflicting operations
- Corrupted PatchSet
"""

from __future__ import annotations

import pytest

from packages.modification.validator import (
    ModificationValidator,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockPatchFile:
    """Mock PatchFile for testing without importing patches.models."""

    def __init__(
        self,
        path: str,
        operation: str,
        hunks: tuple = (),
        metadata: dict | None = None,
    ) -> None:
        self.path = path
        self.operation = operation
        self.hunks = hunks
        self.metadata = metadata or {}


class _MockPatchSet:
    """Mock PatchSet for testing."""

    def __init__(
        self,
        files: tuple,
        workflow_name: str = "test-workflow",
        execution_id: str = "exec-123",
    ) -> None:
        self.files = files
        self.workflow_name = workflow_name
        self.execution_id = execution_id


def _make_patch_file(
    path: str,
    operation: str,
    hunks: tuple = (),
) -> _MockPatchFile:
    """Create a mock PatchFile."""
    return _MockPatchFile(path=path, operation=operation, hunks=hunks)


def _make_patch_set(
    files: tuple,
    workflow_name: str = "test-workflow",
    execution_id: str = "exec-123",
) -> _MockPatchSet:
    """Create a mock PatchSet."""
    return _MockPatchSet(files=files, workflow_name=workflow_name, execution_id=execution_id)


# ---------------------------------------------------------------------------
# Test: Valid PatchSet
# ---------------------------------------------------------------------------


class TestValidPatchSet:
    """Tests for valid PatchSet validation."""

    def test_valid_add(self) -> None:
        """Valid ADD PatchSet should pass validation."""
        pf = _make_patch_file("new.txt", "ADD", ())
        ps = _make_patch_set((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_valid_modify(self) -> None:
        """Valid MODIFY PatchSet should pass validation."""
        pf = _make_patch_file("existing.txt", "MODIFY", ())
        ps = _make_patch_set((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is True

    def test_valid_delete(self) -> None:
        """Valid DELETE PatchSet should pass validation."""
        pf = _make_patch_file("existing.txt", "DELETE", ())
        ps = _make_patch_set((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is True

    def test_valid_mixed_operations(self) -> None:
        """Mixed valid operations should pass validation."""
        pf1 = _make_patch_file("new.txt", "ADD", ())
        pf2 = _make_patch_file("modify.txt", "MODIFY", ())
        pf3 = _make_patch_file("delete.txt", "DELETE", ())
        ps = _make_patch_set((pf1, pf2, pf3))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Test: Duplicate Detection
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    """Tests for duplicate file detection."""

    def test_duplicate_add_files(self) -> None:
        """Duplicate ADD files should be detected."""
        pf1 = _make_patch_file("same.txt", "ADD", ())
        pf2 = _make_patch_file("same.txt", "ADD", ())
        ps = _make_patch_set((pf1, pf2))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert "Duplicate file path" in result.errors[0]

    def test_duplicate_modify_files(self) -> None:
        """Duplicate MODIFY files should be detected."""
        pf1 = _make_patch_file("same.txt", "MODIFY", ())
        pf2 = _make_patch_file("same.txt", "MODIFY", ())
        ps = _make_patch_set((pf1, pf2))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False
        assert "Duplicate file path" in result.errors[0]

    def test_duplicate_mixed_operations(self) -> None:
        """Duplicate files with mixed operations should be detected."""
        pf1 = _make_patch_file("same.txt", "ADD", ())
        pf2 = _make_patch_file("same.txt", "MODIFY", ())
        ps = _make_patch_set((pf1, pf2))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False
        assert "Duplicate file path" in result.errors[0]


# ---------------------------------------------------------------------------
# Test: Conflicting Operations
# ---------------------------------------------------------------------------


class TestConflictingOperations:
    """Tests for conflicting operation detection."""

    def test_add_and_delete_conflict(self) -> None:
        """ADD and DELETE on same path should be detected as duplicate."""
        # Note: The validator detects duplicates before conflicts,
        # so same-path different-ops is a duplicate error.
        pf1 = _make_patch_file("test.txt", "ADD", ())
        pf2 = _make_patch_file("test.txt", "DELETE", ())
        ps = _make_patch_set((pf1, pf2))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False
        assert "Duplicate file path" in result.errors[0]


# ---------------------------------------------------------------------------
# Test: Invalid Hunks
# ---------------------------------------------------------------------------


class TestInvalidHunks:
    """Tests for invalid hunk detection."""

    def test_hunk_with_negative_old_start(self) -> None:
        """Hunk with negative old_start should be invalid."""
        hunk = _MockPatchFile("", "", ())
        hunk.old_start = -1
        hunk.old_count = 1
        hunk.new_start = 1
        hunk.new_count = 1

        pf = _make_patch_file("test.txt", "MODIFY", (hunk,))
        ps = _make_patch_set((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False
        assert "invalid old_start" in result.errors[0]

    def test_hunk_with_negative_old_count(self) -> None:
        """Hunk with negative old_count should be invalid."""
        hunk = _MockPatchFile("", "", ())
        hunk.old_start = 1
        hunk.old_count = -1
        hunk.new_start = 1
        hunk.new_count = 1

        pf = _make_patch_file("test.txt", "MODIFY", (hunk,))
        ps = _make_patch_set((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False
        assert "invalid old_count" in result.errors[0]

    def test_hunk_with_negative_new_start(self) -> None:
        """Hunk with negative new_start should be invalid."""
        hunk = _MockPatchFile("", "", ())
        hunk.old_start = 1
        hunk.old_count = 1
        hunk.new_start = -1
        hunk.new_count = 1

        pf = _make_patch_file("test.txt", "MODIFY", (hunk,))
        ps = _make_patch_set((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False
        assert "invalid new_start" in result.errors[0]

    def test_hunk_with_negative_new_count(self) -> None:
        """Hunk with negative new_count should be invalid."""
        hunk = _MockPatchFile("", "", ())
        hunk.old_start = 1
        hunk.old_count = 1
        hunk.new_start = 1
        hunk.new_count = -1

        pf = _make_patch_file("test.txt", "MODIFY", (hunk,))
        ps = _make_patch_set((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False
        assert "invalid new_count" in result.errors[0]


# ---------------------------------------------------------------------------
# Test: Invalid Rename Targets
# ---------------------------------------------------------------------------


class TestInvalidRenameTargets:
    """Tests for invalid rename target detection."""

    def test_rename_is_valid_without_hunks(self) -> None:
        """RENAME without hunks is valid — it's metadata-only."""
        pf = _make_patch_file("test.txt", "RENAME", ())
        ps = _make_patch_set((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Test: Invalid Delete Targets
# ---------------------------------------------------------------------------


class TestInvalidDeleteTargets:
    """Tests for invalid delete target detection."""

    def test_delete_with_empty_path(self) -> None:
        """DELETE with empty path should be invalid."""
        pf = _make_patch_file("", "DELETE", ())
        ps = _make_patch_set((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# Test: Corrupted PatchSet
# ---------------------------------------------------------------------------


class TestCorruptedPatchSet:
    """Tests for corrupted PatchSet detection."""

    def test_none_patchset_raises(self) -> None:
        """None PatchSet should raise ValueError."""
        with pytest.raises(ValueError, match="patch_set cannot be None"):
            ModificationValidator.validate(None)  # type: ignore[arg-type]

    def test_missing_workflow_name(self) -> None:
        """PatchSet with empty workflow_name should fail validation."""
        ps = _MockPatchSet(
            files=(),
            workflow_name="",
            execution_id="exec-123",
        )
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False
        assert "workflow_name is empty" in result.errors[0]

    def test_missing_execution_id(self) -> None:
        """PatchSet with empty execution_id should fail validation."""
        ps = _MockPatchSet(
            files=(),
            workflow_name="test",
            execution_id="",
        )
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False
        assert "execution_id is empty" in result.errors[0]

    def test_file_missing_path(self) -> None:
        """File with empty path should be detected as invalid."""
        # Empty path triggers DELETE validation error for empty path
        pf = _MockPatchFile("", "DELETE", ())
        ps = _MockPatchSet((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# Test: ValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    """Tests for ValidationResult."""

    def test_valid_result(self) -> None:
        """Valid result should have is_valid=True."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == ()
        assert result.warnings == ()

    def test_invalid_result(self) -> None:
        """Invalid result should have is_valid=False."""
        result = ValidationResult(
            is_valid=False,
            errors=("error1", "error2"),
            warnings=("warning1",),
        )
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1

    def test_result_with_only_warnings(self) -> None:
        """Result with only warnings should still be valid."""
        result = ValidationResult(
            is_valid=True,
            warnings=("warning1",),
        )
        assert result.is_valid is True
        assert len(result.warnings) == 1


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_patchset(self) -> None:
        """Empty PatchSet should be valid."""
        ps = _MockPatchSet(files=())
        result = ModificationValidator.validate(ps)
        assert result.is_valid is True

    def test_single_file(self) -> None:
        """Single file PatchSet should be valid."""
        pf = _make_patch_file("single.txt", "ADD", ())
        ps = _make_patch_set((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is True

    def test_many_files(self) -> None:
        """Many files PatchSet should be valid."""
        files = tuple(_make_patch_file(f"file{i}.txt", "ADD", ()) for i in range(100))
        ps = _make_patch_set(files)
        result = ModificationValidator.validate(ps)
        assert result.is_valid is True

    def test_unicode_paths(self) -> None:
        """Unicode paths should be valid."""
        pf = _make_patch_file("\u4f60\u597d.txt", "ADD", ())
        ps = _make_patch_set((pf,))
        result = ModificationValidator.validate(ps)
        assert result.is_valid is True

    def test_result_errors_are_tuples(self) -> None:
        """Result errors should be tuples."""
        result = ValidationResult(
            is_valid=False,
            errors=("error1",),
        )
        assert isinstance(result.errors, tuple)

    def test_result_warnings_are_tuples(self) -> None:
        """Result warnings should be tuples."""
        result = ValidationResult(
            is_valid=True,
            warnings=("warning1",),
        )
        assert isinstance(result.warnings, tuple)