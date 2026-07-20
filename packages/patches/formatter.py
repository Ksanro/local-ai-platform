"""Patch Formatter.

Produces deterministic Git unified diff text from PatchSet objects.
Formatting only — no validation.

Architecture
------------

PatchSet --> PatchFormatter --> str (Git unified diff text)

Constraints
-----------

- Formatting only.
- No validation.
- No file system operations.
- No repository analysis.
- Deterministic output.

Public API
----------

.. code-block:: python

    from packages.patches.formatter import PatchFormatter

    diff_text = PatchFormatter.format(patch_set)

"""

from __future__ import annotations

from typing import Any

from packages.patches.models import (
    PatchFile,
    PatchHunk,
    PatchOperation,
    PatchSet,
)

__all__ = [
    "PatchFormatter",
]


# ---------------------------------------------------------------------------
# PatchFormatter
# ---------------------------------------------------------------------------


class PatchFormatter:
    """Formats PatchSet into Git unified diff text.

    The formatter produces deterministic output suitable for
    consumption by tools that accept Git unified diff format.

    Constraints
    -----------

    - Formatting only.
    - No validation.
    - No file system operations.
    - No repository inspection.
    - Must produce deterministic output.
    - Must not modify PatchSet.

    Usage
    -----

    .. code-block:: python

        from packages.patches.formatter import PatchFormatter

        diff_text = PatchFormatter.format(patch_set)

    """

    @staticmethod
    def format(patch_set: Any) -> str:
        """Format a PatchSet into Git unified diff text.

        Produces deterministic Git unified diff format text. The output
        follows the standard unified diff format with file headers,
        hunk headers, and diff content lines.

        Args:
            patch_set: A PatchSet-like object with:
                - files: tuple of PatchFile-like objects
                - workflow_name: str
                - execution_id: str

        Returns:
            Deterministic Git unified diff text string.

        Raises:
            ValueError: If patch_set is None.
        """
        if patch_set is None:
            raise ValueError("patch_set cannot be None")

        # Extract files
        files = getattr(patch_set, "files", ())
        if not isinstance(files, (list, tuple)):
            files = tuple(files)

        if len(files) == 0:
            return ""

        # Format each file's diff
        diff_sections: list[str] = []

        for file in files:
            diff_section = _format_patch_file(file)
            if diff_section:
                diff_sections.append(diff_section)

        return "\n".join(diff_sections)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _format_patch_file(file: Any) -> str:
    """Format a single PatchFile into unified diff text.

    Args:
        file: A PatchFile-like object with:
            - path: str
            - operation: PatchOperation
            - hunks: tuple of PatchHunk-like objects

    Returns:
        Unified diff text for this file, or empty string if no hunks.
    """
    path = getattr(file, "path", "")
    operation = getattr(file, "operation", None)
    hunks = getattr(file, "hunks", ())

    if not isinstance(hunks, (list, tuple)):
        hunks = tuple(hunks)

    # Handle ADD operation
    if operation == PatchOperation.ADD:
        lines: list[str] = []
        lines.append(f"diff --git a/{path} b/{path}")
        lines.append(f"new file mode 100644")
        lines.append(f"index 0000000..0000000")
        lines.append(f"--- /dev/null")
        lines.append(f"+++ b/{path}")

        for hunk in hunks:
            lines.append(_format_hunk_header(hunk, is_add=True))
            lines.extend(_format_diff_lines(hunk.diff_lines))

        return "\n".join(lines)

    # Handle DELETE operation
    if operation == PatchOperation.DELETE:
        lines: list[str] = []
        lines.append(f"diff --git a/{path} b/{path}")
        lines.append(f"deleted file mode 100644")
        lines.append(f"index 0000000..0000000")
        lines.append(f"--- a/{path}")
        lines.append(f"+++ /dev/null")

        for hunk in hunks:
            lines.append(_format_hunk_header(hunk, is_delete=True))
            lines.extend(_format_diff_lines(hunk.diff_lines))

        return "\n".join(lines)

    # Handle MODIFY or RENAME operations
    lines: list[str] = []
    lines.append(f"diff --git a/{path} b/{path}")
    lines.append(f"index 0000000..0000000 100644")
    lines.append(f"--- a/{path}")
    lines.append(f"+++ b/{path}")

    for hunk in hunks:
        lines.append(_format_hunk_header(hunk, is_add=False))
        lines.extend(_format_diff_lines(hunk.diff_lines))

    return "\n".join(lines)


def _format_hunk_header(
    hunk: Any,
    is_add: bool = False,
    is_delete: bool = False,
) -> str:
    """Format a hunk header for unified diff format.

    Args:
        hunk: A PatchHunk-like object with:
            - old_start: int
            - old_count: int
            - new_start: int
            - new_count: int
        is_add: Whether this is an ADD operation.
        is_delete: Whether this is a DELETE operation.

    Returns:
        Hunk header string (e.g., "@@ -1,5 +1,5 @@").
    """
    old_start = getattr(hunk, "old_start", 1)
    old_count = getattr(hunk, "old_count", 0)
    new_start = getattr(hunk, "new_start", 1)
    new_count = getattr(hunk, "new_count", 0)

    # Handle edge cases
    if old_count == 0:
        old_start = 0
    if new_count == 0:
        new_start = 0

    if is_add:
        old_count = 0
        old_start = 0
    elif is_delete:
        new_count = 0
        new_start = 0

    return f"@@ -{old_start},{old_count} +{new_start},{new_count} @@"


def _format_diff_lines(diff_lines: tuple[str, ...]) -> list[str]:
    """Format diff content lines.

    Ensures each line is properly formatted with the correct prefix.
    Lines without a prefix (context lines) are preserved as-is.

    Args:
        diff_lines: Tuple of diff content lines.

    Returns:
        List of formatted diff lines.
    """
    if not diff_lines:
        return []

    result: list[str] = []
    for line in diff_lines:
        if line.startswith("+") or line.startswith("-") or line.startswith("@@"):
            result.append(line)
        elif line.startswith("+++") or line.startswith("---"):
            result.append(line)
        elif line.startswith("index") or line.startswith("diff"):
            result.append(line)
        elif line.startswith("new file") or line.startswith("deleted file"):
            result.append(line)
        elif line.startswith("index "):
            result.append(line)
        elif line.startswith("mode "):
            result.append(line)
        else:
            # Context line — preserve as-is
            result.append(line)

    return result