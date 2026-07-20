"""Tests for WorkspaceFileSystem.

Verifies:
- read_file
- write_file
- delete_file
- rename_file
- exists
- compute_hash
- compute_content_hash
- error handling
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from packages.modification.workspace import WorkspaceFileSystem


# ---------------------------------------------------------------------------
# Test: Read File
# ---------------------------------------------------------------------------


class TestReadFile:
    """Tests for read_file."""

    def test_read_file_returns_content(self) -> None:
        """read_file should return file content."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "test.txt"
            test_file.write_text("hello world", encoding="utf-8")

            content = WorkspaceFileSystem.read_file(str(test_file))
            assert content == "hello world"

    def test_read_file_with_unicode(self) -> None:
        """read_file should handle unicode content."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "unicode.txt"
            test_file.write_text("\u4f60\u597d world", encoding="utf-8")

            content = WorkspaceFileSystem.read_file(str(test_file))
            assert content == "\u4f60\u597d world"

    def test_read_file_nonexistent_raises(self) -> None:
        """read_file should raise FileNotFoundError for nonexistent file."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            nonexistent = workspace / "nonexistent.txt"

            with pytest.raises(FileNotFoundError):
                WorkspaceFileSystem.read_file(str(nonexistent))

    def test_read_file_relative_path(self) -> None:
        """read_file should handle absolute paths."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "test.txt"
            test_file.write_text("relative path test", encoding="utf-8")

            # Use absolute path
            content = WorkspaceFileSystem.read_file(str(test_file.absolute()))
            assert content == "relative path test"


# ---------------------------------------------------------------------------
# Test: Write File
# ---------------------------------------------------------------------------


class TestWriteFile:
    """Tests for write_file."""

    def test_write_file_creates_file(self) -> None:
        """write_file should create a new file."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "new.txt"

            WorkspaceFileSystem.write_file(str(test_file), "content")

            assert test_file.exists()
            content = test_file.read_text(encoding="utf-8")
            assert content == "content"

    def test_write_file_creates_directories(self) -> None:
        """write_file should create parent directories."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "nested" / "deep" / "file.txt"

            WorkspaceFileSystem.write_file(str(test_file), "content")

            assert test_file.exists()
            content = test_file.read_text(encoding="utf-8")
            assert content == "content"

    def test_write_file_overwrites(self) -> None:
        """write_file should overwrite existing content."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "test.txt"
            test_file.write_text("old content", encoding="utf-8")

            WorkspaceFileSystem.write_file(str(test_file), "new content")

            content = test_file.read_text(encoding="utf-8")
            assert content == "new content"

    def test_write_file_with_unicode(self) -> None:
        """write_file should handle unicode content."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "unicode.txt"

            WorkspaceFileSystem.write_file(str(test_file), "\u4f60\u597d")

            content = test_file.read_text(encoding="utf-8")
            assert content == "\u4f60\u597d"


# ---------------------------------------------------------------------------
# Test: Delete File
# ---------------------------------------------------------------------------


class TestDeleteFile:
    """Tests for delete_file."""

    def test_delete_file_removes_file(self) -> None:
        """delete_file should remove the file."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "test.txt"
            test_file.write_text("content", encoding="utf-8")

            WorkspaceFileSystem.delete_file(str(test_file))

            assert not test_file.exists()

    def test_delete_file_nonexistent_raises(self) -> None:
        """delete_file should raise FileNotFoundError for nonexistent file."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            nonexistent = workspace / "nonexistent.txt"

            with pytest.raises(FileNotFoundError):
                WorkspaceFileSystem.delete_file(str(nonexistent))


# ---------------------------------------------------------------------------
# Test: Rename File
# ---------------------------------------------------------------------------


class TestRenameFile:
    """Tests for rename_file."""

    def test_rename_file_moves_file(self) -> None:
        """rename_file should move the file to new path."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            old_file = workspace / "old.txt"
            new_file = workspace / "new.txt"
            old_file.write_text("content", encoding="utf-8")

            WorkspaceFileSystem.rename_file(str(old_file), str(new_file))

            assert not old_file.exists()
            assert new_file.exists()
            content = new_file.read_text(encoding="utf-8")
            assert content == "content"

    def test_rename_file_creates_directories(self) -> None:
        """rename_file should create parent directories."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            old_file = workspace / "old.txt"
            new_file = workspace / "nested" / "deep" / "new.txt"
            old_file.write_text("content", encoding="utf-8")

            WorkspaceFileSystem.rename_file(str(old_file), str(new_file))

            assert new_file.exists()
            content = new_file.read_text(encoding="utf-8")
            assert content == "content"

    def test_rename_nonexistent_raises(self) -> None:
        """rename_file should raise FileNotFoundError for nonexistent file."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            nonexistent = workspace / "nonexistent.txt"

            with pytest.raises(FileNotFoundError):
                WorkspaceFileSystem.rename_file(
                    str(nonexistent),
                    str(workspace / "new.txt"),
                )


# ---------------------------------------------------------------------------
# Test: Exists
# ---------------------------------------------------------------------------


class TestExists:
    """Tests for exists."""

    def test_exists_returns_true_for_existing_file(self) -> None:
        """exists should return True for existing file."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "test.txt"
            test_file.write_text("content", encoding="utf-8")

            assert WorkspaceFileSystem.exists(str(test_file)) is True

    def test_exists_returns_false_for_nonexistent(self) -> None:
        """exists should return False for nonexistent file."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            nonexistent = workspace / "nonexistent.txt"

            assert WorkspaceFileSystem.exists(str(nonexistent)) is False

    def test_exists_returns_false_for_directory(self) -> None:
        """exists should return False for directories."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_dir = workspace / "test_dir"
            test_dir.mkdir()

            assert WorkspaceFileSystem.exists(str(test_dir)) is False


# ---------------------------------------------------------------------------
# Test: Compute Hash
# ---------------------------------------------------------------------------


class TestComputeHash:
    """Tests for compute_hash and compute_content_hash."""

    def test_compute_hash_returns_hex_digest(self) -> None:
        """compute_hash should return hex digest string."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "test.txt"
            test_file.write_text("content", encoding="utf-8")

            hash_value = WorkspaceFileSystem.compute_hash(str(test_file))

            assert isinstance(hash_value, str)
            assert len(hash_value) == 64  # SHA-256 hex digest length
            # Verify it matches expected hash
            expected = sha256(b"content").hexdigest()
            assert hash_value == expected

    def test_compute_hash_different_content(self) -> None:
        """compute_hash should produce different hashes for different content."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            file1 = workspace / "file1.txt"
            file2 = workspace / "file2.txt"
            file1.write_text("content1", encoding="utf-8")
            file2.write_text("content2", encoding="utf-8")

            hash1 = WorkspaceFileSystem.compute_hash(str(file1))
            hash2 = WorkspaceFileSystem.compute_hash(str(file2))

            assert hash1 != hash2

    def test_compute_hash_deterministic(self) -> None:
        """compute_hash should be deterministic."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "test.txt"
            test_file.write_text("content", encoding="utf-8")

            hash1 = WorkspaceFileSystem.compute_hash(str(test_file))
            hash2 = WorkspaceFileSystem.compute_hash(str(test_file))

            assert hash1 == hash2

    def test_compute_content_hash(self) -> None:
        """compute_content_hash should hash string content."""
        hash1 = WorkspaceFileSystem.compute_content_hash("content1")
        hash2 = WorkspaceFileSystem.compute_content_hash("content2")

        assert hash1 != hash2
        assert hash1 == sha256(b"content1").hexdigest()

    def test_compute_content_hash_deterministic(self) -> None:
        """compute_content_hash should be deterministic."""
        hash1 = WorkspaceFileSystem.compute_content_hash("same content")
        hash2 = WorkspaceFileSystem.compute_content_hash("same content")

        assert hash1 == hash2

    def test_compute_hash_nonexistent_raises(self) -> None:
        """compute_hash should raise FileNotFoundError for nonexistent file."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            nonexistent = workspace / "nonexistent.txt"

            with pytest.raises(FileNotFoundError):
                WorkspaceFileSystem.compute_hash(str(nonexistent))


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_read_empty_file(self) -> None:
        """read_file should handle empty files."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "empty.txt"
            test_file.write_text("", encoding="utf-8")

            content = WorkspaceFileSystem.read_file(str(test_file))
            assert content == ""

    def test_write_empty_content(self) -> None:
        """write_file should handle empty content."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "empty.txt"

            WorkspaceFileSystem.write_file(str(test_file), "")

            content = test_file.read_text(encoding="utf-8")
            assert content == ""

    def test_rename_same_directory(self) -> None:
        """rename_file should handle same-directory renames."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            old_file = workspace / "old.txt"
            new_file = workspace / "new.txt"
            old_file.write_text("content", encoding="utf-8")

            WorkspaceFileSystem.rename_file(str(old_file), str(new_file))

            assert not old_file.exists()
            assert new_file.exists()

    def test_compute_hash_empty_content(self) -> None:
        """compute_hash should handle empty content."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "empty.txt"
            test_file.write_text("", encoding="utf-8")

            hash_value = WorkspaceFileSystem.compute_hash(str(test_file))
            expected = sha256(b"").hexdigest()
            assert hash_value == expected

    def test_large_file_content(self) -> None:
        """Operations should handle large file content."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "large.txt"
            large_content = "x" * 100000
            test_file.write_text(large_content, encoding="utf-8")

            content = WorkspaceFileSystem.read_file(str(test_file))
            assert content == large_content

            hash_value = WorkspaceFileSystem.compute_hash(str(test_file))
            assert isinstance(hash_value, str)
            assert len(hash_value) == 64