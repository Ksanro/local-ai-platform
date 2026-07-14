"""Directory and file filtering logic for the repository scanner.

Provides two mechanisms for excluding paths from scan results:
1. A hardcoded set of directory basenames that are always ignored.
2. Parsing of a ``.gitignore`` file at the repository root for
   additional exclusion patterns.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

# Hardcoded directory basenames that are always skipped.
_DEFAULT_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "target",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "__pycache__",
    }
)


def parse_gitignore(root: Path) -> list[str]:
    """Parse a ``.gitignore`` file and return a list of patterns.

    Only top-level patterns are extracted (no nested gitignore files).
    Blank lines and comment lines (starting with ``#``) are skipped.

    Args:
        root: Repository root directory.

    Returns:
        A list of gitignore pattern strings.
    """
    gitignore_path = root / ".gitignore"
    if not gitignore_path.is_file():
        return []

    patterns: list[str] = []
    with open(gitignore_path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            patterns.append(stripped)
    return patterns


def should_ignore_path(
    relative_path: Path,
    is_dir: bool,
    ignored_patterns: list[str],
) -> bool:
    """Determine whether a path should be excluded from scan results.

    Checks both the hardcoded ignored directory set and any
    ``.gitignore`` patterns.

    Args:
        relative_path: Path relative to the repository root.
        is_dir: Whether the path refers to a directory.
        ignored_patterns: Parsed gitignore patterns.

    Returns:
        ``True`` if the path should be ignored, ``False`` otherwise.
    """
    # Hardcoded directory check — only directories are ignored.
    if is_dir and relative_path.name in _DEFAULT_IGNORED_DIRS:
        return True

    # Check gitignore patterns against the relative path.
    for pattern in ignored_patterns:
        if _matches_pattern(relative_path, pattern, is_dir):
            return True

    return False


def _matches_pattern(path: Path, pattern: str, is_dir: bool) -> bool:
    """Check whether a path matches a single gitignore-style pattern.

    Supports:
    - Simple glob patterns (``*.pyc``, ``*.egg-info``).
    - Directory-only patterns (trailing ``/``).
    - Prefix patterns (``dir/`` matches anything under ``dir/``).
    - Basename patterns (no leading ``/`` or ``**`` — matches anywhere).

    Args:
        path: The relative path to test.
        pattern: A gitignore pattern string.
        is_dir: Whether the path is a directory.

    Returns:
        ``True`` if the path matches the pattern.
    """
    # Directory-only patterns (trailing slash).
    if pattern.endswith("/"):
        prefix = pattern.rstrip("/")
        # Match the directory itself (if it's a directory).
        if is_dir and path.name == prefix:
            return True
        # For files, check if they are nested under the directory.
        if not is_dir:
            prefix_parts = prefix.split(os.sep)
            if len(path.parts) > len(prefix_parts):
                if path.parts[: len(prefix_parts)] == tuple(prefix_parts):
                    return True
            return False
        return False

    # Directory-only patterns with leading slash (anchored).
    if pattern.startswith("/"):
        pattern = pattern.lstrip("/")
        return path.match(pattern) and (not is_dir or path == Path(pattern))

    # Directory-only patterns with ** prefix.
    if pattern.startswith("**/"):
        pattern = pattern.lstrip("*").lstrip("/")
        if is_dir:
            return path.match(f"{pattern}/**") or path.name == pattern
        return path.match(f"**/{pattern}") or path.name == pattern

    # Basename match — pattern without a slash matches any file/dir
    # with that name at any depth.
    if "/" not in pattern:
        if is_dir:
            return path.name == pattern or path.match(f"**/{pattern}")
        return fnmatch.fnmatch(path.name, pattern)

    # Path-level match.
    return path.match(pattern) or fnmatch.fnmatch(str(path), pattern)
