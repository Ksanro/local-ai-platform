"""Backup manager for workspace modifications.

Creates deterministic backups before any modification and supports
complete rollback. The backup system is purely mechanical — no business
logic, no repository analysis, no AST parsing.

Architecture
------------

WorkspaceChanges --> BackupManager --> backup directory

Constraints
-----------

- Backup operations only.
- No business logic.
- No repository analysis.
- No AST parsing.
- No provider invocation.
- No patch generation.
- Deterministic backup naming.

Public API
----------

.. code-block:: python

    from packages.modification.backup import BackupManager

    backup_dir = BackupManager.create_backup(workspace_path, files)
    BackupManager.restore_backup(backup_dir, workspace_path)
    BackupManager.delete_backup(backup_dir)

"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "BackupManager",
]


def _normalize_path(path_str: str) -> str:
    """Normalize path separators to forward slashes for consistency.

    This ensures path consistency across operating systems where
    Windows uses backslashes and Unix uses forward slashes.

    Args:
        path_str: Path string to normalize.

    Returns:
        Normalized path string with forward slashes.
    """
    return path_str.replace("\\", "/")


# ---------------------------------------------------------------------------
# BackupManager
# ---------------------------------------------------------------------------


class BackupManager:
    """Manages workspace backups for modification rollback.

    This class provides deterministic backup creation and restoration.
    It contains no business logic, no repository analysis, and no
    patch generation.

    Constraints
    -----------

    - Backup operations only.
    - Must NOT contain business logic.
    - Must NOT perform repository analysis.
    - Must NOT parse AST.
    - Must NOT invoke providers.
    - Must NOT generate patches.
    - Must produce deterministic backup directory names.

    Usage
    -----

    .. code-block:: python

        from packages.modification.backup import BackupManager

        backup_dir = BackupManager.create_backup(workspace_path, files)
        BackupManager.restore_backup(backup_dir, workspace_path)
        BackupManager.delete_backup(backup_dir)
    """

    @staticmethod
    def create_backup(
        workspace_path: Path,
        files: dict[str, str],
        backup_dir: Path | None = None,
    ) -> Path:
        """Create a deterministic backup of specified workspace files.

        Creates a timestamped backup directory containing copies of all
        specified files with their relative paths preserved.

        Args:
            workspace_path: Path to the workspace root directory.
            files: Dictionary mapping relative file paths to their contents.
            backup_dir: Optional backup directory. If None, creates a
                timestamped directory in the workspace.

        Returns:
            Path to the created backup directory.

        Raises:
            FileNotFoundError: If any source file does not exist.
            OSError: If the backup directory cannot be created.
        """
        # Create timestamped backup directory
        if backup_dir is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_dir = workspace_path / ".modification_backup" / timestamp

        backup_dir.mkdir(parents=True, exist_ok=True)

        # Copy each file to the backup directory
        for relative_path, content in files.items():
            # Normalize path separators for cross-platform consistency
            normalized_path = _normalize_path(relative_path)
            target_path = backup_dir / normalized_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")

        # Write a manifest file for verification
        manifest_path = backup_dir / "MANIFEST.txt"
        manifest_path.write_text(
            "\n".join(sorted(_normalize_path(k) for k in files.keys())),
            encoding="utf-8",
        )

        return backup_dir

    @staticmethod
    def restore_backup(backup_dir: Path, workspace_path: Path) -> None:
        """Restore workspace files from a backup directory.

        Removes the current workspace and restores all files from the
        backup directory, preserving relative paths.

        IMPORTANT: The backup directory must NOT be inside the workspace
        directory, as the workspace is completely removed before restore.

        Args:
            backup_dir: Path to the backup directory.
            workspace_path: Path to the workspace root directory.

        Raises:
            FileNotFoundError: If the backup directory does not exist.
            OSError: If the restoration fails.
        """
        if not backup_dir.exists():
            raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

        # Read all file contents BEFORE clearing workspace
        files_to_restore: dict[str, str] = {}
        manifest_path = backup_dir / "MANIFEST.txt"
        if manifest_path.exists():
            # Restore from manifest
            content = manifest_path.read_text(encoding="utf-8")
            for line in content.strip().split("\n"):
                normalized = _normalize_path(line.strip())
                if normalized:
                    backup_file = backup_dir / normalized
                    if backup_file.exists():
                        files_to_restore[normalized] = backup_file.read_text(encoding="utf-8")
        else:
            # Restore all files from backup directory
            for backup_file in backup_dir.rglob("*"):
                if backup_file.is_file() and backup_file.name != "MANIFEST.txt":
                    rel_path = _normalize_path(str(backup_file.relative_to(backup_dir)))
                    files_to_restore[rel_path] = backup_file.read_text(encoding="utf-8")

        # Clear workspace (including backup if it's inside workspace)
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Restore each file
        for relative_path, content in files_to_restore.items():
            normalized_path = _normalize_path(relative_path)
            target_path = workspace_path / normalized_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")

    @staticmethod
    def delete_backup(backup_dir: Path) -> None:
        """Delete a backup directory.

        Args:
            backup_dir: Path to the backup directory.

        Raises:
            FileNotFoundError: If the backup directory does not exist.
        """
        if not backup_dir.exists():
            raise FileNotFoundError(f"Backup directory not found: {backup_dir}")
        shutil.rmtree(backup_dir)

    @staticmethod
    def get_backup_files(backup_dir: Path) -> dict[str, str]:
        """Read all files from a backup directory.

        Args:
            backup_dir: Path to the backup directory.

        Returns:
            Dictionary mapping relative file paths to their contents.

        Raises:
            FileNotFoundError: If the backup directory does not exist.
        """
        if not backup_dir.exists():
            raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

        files: dict[str, str] = {}
        for backup_file in backup_dir.rglob("*"):
            if backup_file.is_file() and backup_file.name != "MANIFEST.txt":
                relative_path = _normalize_path(str(backup_file.relative_to(backup_dir)))
                files[relative_path] = backup_file.read_text(encoding="utf-8")
        return files