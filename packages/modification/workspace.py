"""Workspace file system operations manager.

Responsible only for filesystem operations. No business logic, no repository
analysis, no AST parsing, no provider invocation.

Architecture
------------

WorkspaceChanges --> WorkspaceFileSystem --> filesystem operations

Constraints
-----------

- Filesystem operations only.
- No business logic.
- No repository analysis.
- No AST parsing.
- No provider invocation.
- No patch generation.

Public API
----------

.. code-block:: python

    from packages.modification.workspace import WorkspaceFileSystem

    content = WorkspaceFileSystem.read_file("src/main.py")
    WorkspaceFileSystem.write_file("src/main.py", content)
    WorkspaceFileSystem.delete_file("src/old.py")
    WorkspaceFileSystem.rename_file("src/old.py", "src/new.py")
    WorkspaceFileSystem.exists("src/main.py")
    WorkspaceFileSystem.compute_hash("src/main.py")

"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

__all__ = [
    "WorkspaceFileSystem",
]


# ---------------------------------------------------------------------------
# WorkspaceFileSystem
# ---------------------------------------------------------------------------


class WorkspaceFileSystem:
    """Manages filesystem operations for workspace modifications.

    This class provides only raw filesystem operations. It contains no
    business logic, no repository analysis, and no patch generation.

    Constraints
    -----------

    - Filesystem operations only.
    - Must NOT contain business logic.
    - Must NOT perform repository analysis.
    - Must NOT parse AST.
    - Must NOT invoke providers.
    - Must NOT generate patches.
    - Must be deterministic.

    Usage
    -----

    .. code-block:: python

        from packages.modification.workspace import WorkspaceFileSystem

        content = WorkspaceFileSystem.read_file("src/main.py")
        WorkspaceFileSystem.write_file("src/main.py", content)
        WorkspaceFileSystem.delete_file("src/old.py")
        WorkspaceFileSystem.rename_file("src/old.py", "src/new.py")
        WorkspaceFileSystem.exists("src/main.py")
        WorkspaceFileSystem.compute_hash("src/main.py")
    """

    @staticmethod
    def read_file(path: str) -> str:
        """Read the contents of a file.

        Args:
            path: Relative or absolute file path.

        Returns:
            File contents as a string.

        Raises:
            FileNotFoundError: If the file does not exist.
            PermissionError: If the file cannot be read due to permissions.
            UnicodeDecodeError: If the file cannot be decoded as UTF-8.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return file_path.read_text(encoding="utf-8")

    @staticmethod
    def write_file(path: str, content: str) -> None:
        """Write content to a file, creating directories as needed.

        Args:
            path: Relative or absolute file path.
            content: Content to write to the file.

        Raises:
            PermissionError: If the file cannot be written due to permissions.
        """
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    @staticmethod
    def delete_file(path: str) -> None:
        """Delete a file from the workspace.

        Args:
            path: Relative or absolute file path.

        Raises:
            FileNotFoundError: If the file does not exist.
            PermissionError: If the file cannot be deleted due to permissions.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        file_path.unlink()

    @staticmethod
    def rename_file(old_path: str, new_path: str) -> None:
        """Rename or move a file in the workspace.

        Creates parent directories for the new path if needed.

        Args:
            old_path: Current file path.
            new_path: New file path.

        Raises:
            FileNotFoundError: If the old file does not exist.
            FileExistsError: If a file already exists at the new path.
        """
        old_file = Path(old_path)
        new_file = Path(new_path)
        if not old_file.exists():
            raise FileNotFoundError(f"File not found: {old_path}")
        new_file.parent.mkdir(parents=True, exist_ok=True)
        old_file.rename(new_file)

    @staticmethod
    def exists(path: str) -> bool:
        """Check if a file exists in the workspace.

        Args:
            path: Relative or absolute file path.

        Returns:
            True if the file exists, False otherwise.
        """
        return Path(path).is_file()

    @staticmethod
    def compute_hash(path: str) -> str:
        """Compute SHA-256 hash of a file's contents.

        Args:
            path: Relative or absolute file path.

        Returns:
            Hex digest of the SHA-256 hash.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        content = Path(path).read_bytes()
        return sha256(content).hexdigest()

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute SHA-256 hash of a string content.

        Args:
            content: String content to hash.

        Returns:
            Hex digest of the SHA-256 hash.
        """
        return sha256(content.encode("utf-8")).hexdigest()