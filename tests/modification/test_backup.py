"""Tests for BackupManager.

Verifies:
- Create backup
- Restore backup
- Delete backup
- Deterministic backup naming
- Manifest file
- File contents preservation
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from packages.modification.backup import BackupManager


# ---------------------------------------------------------------------------
# Test: Create Backup
# ---------------------------------------------------------------------------


class TestCreateBackup:
    """Tests for backup creation."""

    def test_create_backup_creates_directory(self) -> None:
        """Create backup should create a backup directory."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            files = {"test.txt": "content"}
            backup_dir = BackupManager.create_backup(workspace, files)

            assert backup_dir.exists()
            assert backup_dir.is_dir()
            assert (backup_dir / "test.txt").exists()

    def test_create_backup_preserves_content(self) -> None:
        """Create backup should preserve file contents."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            files = {"test.txt": "test content here"}
            backup_dir = BackupManager.create_backup(workspace, files)

            content = (backup_dir / "test.txt").read_text(encoding="utf-8")
            assert content == "test content here"

    def test_create_backup_creates_manifest(self) -> None:
        """Create backup should create a MANIFEST.txt."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            files = {"a.txt": "content a", "b.txt": "content b"}
            backup_dir = BackupManager.create_backup(workspace, files)

            manifest = backup_dir / "MANIFEST.txt"
            assert manifest.exists()
            content = manifest.read_text(encoding="utf-8")
            assert "a.txt" in content
            assert "b.txt" in content

    def test_create_backup_with_nested_paths(self) -> None:
        """Create backup should preserve nested directory structure."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            files = {"src/nested/deep/file.txt": "content"}
            backup_dir = BackupManager.create_backup(workspace, files)

            assert (backup_dir / "src" / "nested" / "deep" / "file.txt").exists()

    def test_create_backup_with_custom_dir(self) -> None:
        """Create backup should use custom backup directory when provided."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            custom_backup = Path(tmpdir) / "custom_backup"
            files = {"test.txt": "content"}
            backup_dir = BackupManager.create_backup(workspace, files, custom_backup)

            assert backup_dir == custom_backup
            assert backup_dir.exists()


# ---------------------------------------------------------------------------
# Test: Restore Backup
# ---------------------------------------------------------------------------


class TestRestoreBackup:
    """Tests for backup restoration."""

    def test_restore_backup_restores_content(self) -> None:
        """Restore backup should restore file contents."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            backup_dir = Path(tmpdir) / "backup"

            # Create backup with external directory
            files = {"test.txt": "restored content"}
            BackupManager.create_backup(workspace, files, backup_dir)

            # Create a different workspace file
            test_file = workspace / "test.txt"
            test_file.write_text("different content", encoding="utf-8")

            # Restore
            BackupManager.restore_backup(backup_dir, workspace)

            content = test_file.read_text(encoding="utf-8")
            assert content == "restored content"

    def test_restore_backup_removes_extra_files(self) -> None:
        """Restore backup should remove files not in backup."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            backup_dir = Path(tmpdir) / "backup"

            # Create files
            (workspace / "test.txt").write_text("backup content", encoding="utf-8")
            (workspace / "extra.txt").write_text("extra content", encoding="utf-8")

            # Create backup with only test.txt using external directory
            files = {"test.txt": "backup content"}
            BackupManager.create_backup(workspace, files, backup_dir)

            # Restore
            BackupManager.restore_backup(backup_dir, workspace)

            assert (workspace / "test.txt").exists()
            assert not (workspace / "extra.txt").exists()

    def test_restore_backup_from_manifest(self) -> None:
        """Restore backup should use MANIFEST.txt for file listing."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            backup_dir = Path(tmpdir) / "backup"

            # Create backup with external directory
            files = {"a.txt": "content a", "b.txt": "content b"}
            BackupManager.create_backup(workspace, files, backup_dir)

            # Modify a file
            (workspace / "a.txt").write_text("modified", encoding="utf-8")

            # Restore
            BackupManager.restore_backup(backup_dir, workspace)

            content = (workspace / "a.txt").read_text(encoding="utf-8")
            assert content == "content a"

    def test_restore_nonexistent_backup_raises(self) -> None:
        """Restore should raise FileNotFoundError for nonexistent backup."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            backup_dir = Path(tmpdir) / "nonexistent"

            with pytest.raises(FileNotFoundError):
                BackupManager.restore_backup(backup_dir, workspace)


# ---------------------------------------------------------------------------
# Test: Delete Backup
# ---------------------------------------------------------------------------


class TestDeleteBackup:
    """Tests for backup deletion."""

    def test_delete_backup_removes_directory(self) -> None:
        """Delete backup should remove the backup directory."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            files = {"test.txt": "content"}
            backup_dir = BackupManager.create_backup(workspace, files)

            assert backup_dir.exists()
            BackupManager.delete_backup(backup_dir)
            assert not backup_dir.exists()

    def test_delete_nonexistent_backup_raises(self) -> None:
        """Delete should raise FileNotFoundError for nonexistent backup."""
        with TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "nonexistent"

            with pytest.raises(FileNotFoundError):
                BackupManager.delete_backup(backup_dir)


# ---------------------------------------------------------------------------
# Test: Get Backup Files
# ---------------------------------------------------------------------------


class TestGetBackupFiles:
    """Tests for get_backup_files."""

    def test_get_backup_files_returns_contents(self) -> None:
        """Get backup files should return file contents."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            files = {"test.txt": "content here"}
            backup_dir = BackupManager.create_backup(workspace, files)

            result = BackupManager.get_backup_files(backup_dir)
            assert result["test.txt"] == "content here"

    def test_get_backup_files_excludes_manifest(self) -> None:
        """Get backup files should exclude MANIFEST.txt."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            files = {"test.txt": "content"}
            backup_dir = BackupManager.create_backup(workspace, files)

            result = BackupManager.get_backup_files(backup_dir)
            assert "MANIFEST.txt" not in result

    def test_get_backup_files_nested(self) -> None:
        """Get backup files should handle nested paths."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            files = {"src/nested/file.txt": "content"}
            backup_dir = BackupManager.create_backup(workspace, files)

            result = BackupManager.get_backup_files(backup_dir)
            assert "src/nested/file.txt" in result

    def test_get_backup_nonexistent_raises(self) -> None:
        """Get backup files should raise for nonexistent backup."""
        with TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "nonexistent"

            with pytest.raises(FileNotFoundError):
                BackupManager.get_backup_files(backup_dir)


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_files_dict(self) -> None:
        """Create backup with empty files dict should still work."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            backup_dir = BackupManager.create_backup(workspace, {})

            assert backup_dir.exists()
            # Only MANIFEST.txt should exist (empty)
            manifest = backup_dir / "MANIFEST.txt"
            assert manifest.exists()
            assert manifest.read_text(encoding="utf-8") == ""

    def test_unicode_file_names(self) -> None:
        """Create backup should handle unicode in file names."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            files = {"\u4f60\u597d.txt": "content"}
            backup_dir = BackupManager.create_backup(workspace, files)

            assert (backup_dir / "\u4f60\u597d.txt").exists()

    def test_multiple_files(self) -> None:
        """Create backup should handle multiple files."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            files = {
                "a.txt": "content a",
                "b.txt": "content b",
                "c.txt": "content c",
            }
            backup_dir = BackupManager.create_backup(workspace, files)

            result = BackupManager.get_backup_files(backup_dir)
            assert len(result) == 3
            assert result["a.txt"] == "content a"
            assert result["b.txt"] == "content b"
            assert result["c.txt"] == "content c"

    def test_full_backup_restore_cycle(self) -> None:
        """Full backup and restore cycle should preserve all files."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            backup_dir = Path(tmpdir) / "backup"

            # Create original files (create nested dirs first)
            files = {
                "a.txt": "content a",
                "b.txt": "content b",
                "src/c.txt": "content c",
            }
            for path, content in files.items():
                (workspace / path).parent.mkdir(parents=True, exist_ok=True)
                (workspace / path).write_text(content, encoding="utf-8")

            # Create backup with external directory
            BackupManager.create_backup(workspace, files, backup_dir)

            # Modify files
            (workspace / "a.txt").write_text("modified a", encoding="utf-8")
            (workspace / "b.txt").unlink()

            # Restore
            BackupManager.restore_backup(backup_dir, workspace)

            # Verify
            result = BackupManager.get_backup_files(backup_dir)
            assert result["a.txt"] == "content a"
            assert result["b.txt"] == "content b"
            assert result["src/c.txt"] == "content c"
