"""Tests for PatchFormatter.

Verifies:
- Deterministic output
- Git unified diff format correctness
- All operations (ADD, DELETE, MODIFY, RENAME)
- Empty PatchSet
- Multiple files
- Formatting does not modify PatchSet
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from packages.patches.formatter import PatchFormatter
from packages.patches.models import (
    PatchFile,
    PatchHunk,
    PatchOperation,
    PatchSet,
    PatchStatistics,
)


# ---------------------------------------------------------------------------
# Test: Deterministic Output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_deterministic_format(self) -> None:
        """Same PatchSet should produce identical diff text."""
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
                    diff_lines=("@@ -1,5 +1,5 @@\n", "- old\n", "+ new\n"),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result1 = PatchFormatter.format(patch_set)
        result2 = PatchFormatter.format(patch_set)

        assert result1 == result2

    def test_deterministic_with_multiple_files(self) -> None:
        """Multiple files should produce deterministic output."""
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

        result1 = PatchFormatter.format(patch_set)
        result2 = PatchFormatter.format(patch_set)

        assert result1 == result2


# ---------------------------------------------------------------------------
# Test: MODIFY Operation
# ---------------------------------------------------------------------------


class TestModifyOperation:
    """Tests for MODIFY operation formatting."""

    def test_basic_modify_format(self) -> None:
        """MODIFY operation should produce standard diff format."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=10,
                    old_count=5,
                    new_start=10,
                    new_count=7,
                    diff_lines=("@@ -10,5 +10,7 @@\n", "- old line\n", "+ new line\n", "+ another\n"),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)

        assert "diff --git a/src/main.py b/src/main.py" in result
        assert "--- a/src/main.py" in result
        assert "+++ b/src/main.py" in result
        assert "@@ -10,5 +10,7 @@" in result
        assert "- old line" in result
        assert "+ new line" in result
        assert "+ another" in result

    def test_modify_with_multiple_hunks(self) -> None:
        """MODIFY with multiple hunks should format all hunks."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=3,
                    new_start=1,
                    new_count=3,
                    diff_lines=("@@ -1,3 +1,3 @@\n", "- old\n", "+ new\n"),
                ),
                PatchHunk(
                    file_path="src/main.py",
                    old_start=10,
                    old_count=2,
                    new_start=10,
                    new_count=4,
                    diff_lines=("@@ -10,2 +10,4 @@\n", "- old2\n", "+ new2\n", "+ new3\n"),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)

        assert "@@ -1,3 +1,3 @@" in result
        assert "@@ -10,2 +10,4 @@" in result


# ---------------------------------------------------------------------------
# Test: ADD Operation
# ---------------------------------------------------------------------------


class TestAddOperation:
    """Tests for ADD operation formatting."""

    def test_add_format(self) -> None:
        """ADD operation should produce new file diff format."""
        patch_file = PatchFile(
            path="src/new.py",
            operation=PatchOperation.ADD,
            hunks=(
                PatchHunk(
                    file_path="src/new.py",
                    old_start=0,
                    old_count=0,
                    new_start=1,
                    new_count=3,
                    diff_lines=("@@ -0,0 +1,3 @@\n", "+ line1\n", "+ line2\n", "+ line3\n"),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)

        assert "diff --git a/src/new.py b/src/new.py" in result
        assert "new file mode 100644" in result
        assert "--- /dev/null" in result
        assert "+++ b/src/new.py" in result
        assert "+ line1" in result


# ---------------------------------------------------------------------------
# Test: DELETE Operation
# ---------------------------------------------------------------------------


class TestDeleteOperation:
    """Tests for DELETE operation formatting."""

    def test_delete_format(self) -> None:
        """DELETE operation should produce deleted file diff format."""
        patch_file = PatchFile(
            path="src/old.py",
            operation=PatchOperation.DELETE,
            hunks=(
                PatchHunk(
                    file_path="src/old.py",
                    old_start=1,
                    old_count=5,
                    new_start=0,
                    new_count=0,
                    diff_lines=("@@ -1,5 +0,0 @@\n", "- line1\n", "- line2\n", "- line3\n"),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)

        assert "diff --git a/src/old.py b/src/old.py" in result
        assert "deleted file mode 100644" in result
        assert "--- a/src/old.py" in result
        assert "+++ /dev/null" in result
        assert "- line1" in result


# ---------------------------------------------------------------------------
# Test: RENAME Operation
# ---------------------------------------------------------------------------


class TestRenameOperation:
    """Tests for RENAME operation formatting."""
    def test_rename_format(self) -> None:
        """RENAME operation should produce standard diff format."""
        patch_file = PatchFile(
            path="src/renamed.py",
            operation=PatchOperation.RENAME,
            hunks=(
                PatchHunk(
                    file_path="src/renamed.py",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    diff_lines=("@@ -1 +1 @@\n", "- old\n", "+ new\n"),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)

        assert "diff --git a/src/renamed.py b/src/renamed.py" in result
        assert "--- a/src/renamed.py" in result
        assert "+++ b/src/renamed.py" in result


# ---------------------------------------------------------------------------
# Test: Empty PatchSet
# ---------------------------------------------------------------------------


class TestEmptyPatchSet:
    """Tests for empty PatchSet formatting."""

    def test_empty_files_produces_empty_string(self) -> None:
        """Empty PatchSet should produce empty string."""
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(),
        )

        result = PatchFormatter.format(patch_set)
        assert result == ""

    def test_none_raises_value_error(self) -> None:
        """None PatchSet should raise ValueError."""
        with pytest.raises(ValueError, match="patch_set cannot be None"):
            PatchFormatter.format(None)  # type: ignore


# ---------------------------------------------------------------------------
# Test: Multiple Files
# ---------------------------------------------------------------------------


class TestMultipleFiles:
    """Tests for multiple file formatting."""

    def test_multiple_files_separated(self) -> None:
        """Multiple files should be separated by newlines."""
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
                        new_count=2,
                        diff_lines=("+ new\n",),
                    ),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=files,
        )

        result = PatchFormatter.format(patch_set)

        # Both files should appear
        assert "src/a.py" in result
        assert "src/b.py" in result
        # Should be separated (not concatenated)
        assert result.count("diff --git") == 2


# ---------------------------------------------------------------------------
# Test: Does Not Modify PatchSet
# ---------------------------------------------------------------------------


class TestDoesNotModifyPatchSet:
    """Tests that formatting does not modify PatchSet."""

    def test_patchset_unchanged_after_format(self) -> None:
        """PatchSet should be unchanged after formatting."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=2,
                    diff_lines=("+ new\n",),
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

        # Format
        PatchFormatter.format(patch_set)

        # Verify unchanged
        assert patch_set.files is original_files
        assert patch_set.workflow_name == original_workflow
        assert patch_set.execution_id == original_execution


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_file_path(self) -> None:
        """Empty file path should be handled."""
        patch_file = PatchFile(
            path="",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=2,
                    diff_lines=("+ new\n",),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)
        # Empty file path produces diff header with empty paths
        assert "diff --git a/ b/" in result

    def test_unicode_file_path(self) -> None:
        """Unicode file path should be handled."""
        patch_file = PatchFile(
            path="src/\u4f60\u597d.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/\u4f60\u597d.py",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=2,
                    diff_lines=("+ new\n",),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)
        assert "\u4f60\u597d.py" in result

    def test_file_with_no_hunks(self) -> None:
        """File with no hunks should produce no diff section."""
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

        result = PatchFormatter.format(patch_set)
        # Should not contain diff content for file with no hunks
        assert "@@" not in result

    def test_context_lines_preserved(self) -> None:
        """Context lines (without + or - prefix) should be preserved."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=3,
                    diff_lines=(
                        "@@ -1 +1,3 @@\n",
                        " context line\n",
                        "- old\n",
                        "+ new1\n",
                        "+ new2\n",
                    ),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)
        assert " context line" in result

    def test_add_operation_with_new_file_marker(self) -> None:
        """ADD operation should include new file marker."""
        patch_file = PatchFile(
            path="src/new_file.py",
            operation=PatchOperation.ADD,
            hunks=(
                PatchHunk(
                    file_path="src/new_file.py",
                    old_start=0,
                    old_count=0,
                    new_start=1,
                    new_count=1,
                    diff_lines=("@@ -0,0 +1 @@\n", "+ new content\n"),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)
        assert "new file mode" in result

    def test_delete_operation_with_deleted_file_marker(self) -> None:
        """DELETE operation should include deleted file marker."""
        patch_file = PatchFile(
            path="src/old_file.py",
            operation=PatchOperation.DELETE,
            hunks=(
                PatchHunk(
                    file_path="src/old_file.py",
                    old_start=1,
                    old_count=1,
                    new_start=0,
                    new_count=0,
                    diff_lines=("@@ -1 +0,0 @@\n", "- old content\n"),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)
        assert "deleted file mode" in result

    def test_format_returns_string(self) -> None:
        """format() should return a string."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    diff_lines=("@@ -1 +1 @@\n", "- old\n", "+ new\n"),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)
        assert isinstance(result, str)

    def test_special_diff_line_prefixes(self) -> None:
        """Special diff line prefixes should be handled."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    diff_lines=(
                        "index abc1234..def5678 100644\n",
                        "new file mode 100644\n",
                        "deleted file mode 100644\n",
                        "mode 100644\n",
                        "index abc1234\n",
                        "+ content\n",
                    ),
                ),
            ),
        )
        patch_set = PatchSet(
            workflow_name="test",
            execution_id="exec-1",
            files=(patch_file,),
        )

        result = PatchFormatter.format(patch_set)
        assert "index abc1234..def5678 100644" in result
        assert "new file mode 100644" in result
        assert "deleted file mode 100644" in result
        assert "mode 100644" in result

    def test_files_as_list_converted(self) -> None:
        """Files passed as a list should be converted to tuple."""
        patch_file = PatchFile(
            path="src/main.py",
            operation=PatchOperation.MODIFY,
            hunks=(
                PatchHunk(
                    file_path="src/main.py",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    diff_lines=("+ new\n",),
                ),
            ),
        )
        # Create a PatchSet-like object with files as a list
        patch_set = MagicMock()
        patch_set.files = [patch_file]
        patch_set.workflow_name = "test"
        patch_set.execution_id = "exec-1"

        result = PatchFormatter.format(patch_set)
        assert "src/main.py" in result
