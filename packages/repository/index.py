"""RepositoryIndex helper methods.

Provides lookup and query methods on top of the raw scan results
produced by :func:`scan`.
"""

from __future__ import annotations

from pathlib import Path

from packages.repository.models import RepositoryIndex, SourceFile


def get_file(index: RepositoryIndex, relative_path: Path) -> SourceFile | None:
    """Look up a file by its relative path.

    Args:
        index: A :class:`RepositoryIndex` from a completed scan.
        relative_path: Relative path to look up (e.g. ``Path("README.md")``).

    Returns:
        The :class:`SourceFile` if found, or ``None``.
    """
    for f in index.files:
        if f.relative_path == relative_path:
            return f
    return None


def find_extension(index: RepositoryIndex, extension: str) -> list[SourceFile]:
    """Find all files with a given extension.

    Args:
        index: A :class:`RepositoryIndex` from a completed scan.
        extension: File extension to search for (with or without leading dot).

    Returns:
        List of matching :class:`SourceFile` objects.
    """
    ext = extension.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    return [f for f in index.files if f.extension.lower() == ext]


def find_language(index: RepositoryIndex, language: str) -> list[SourceFile]:
    """Find all files matching a detected language.

    Args:
        index: A :class:`RepositoryIndex` from a completed scan.
        language: Language name to search for (e.g. ``"Python"``).

    Returns:
        List of matching :class:`SourceFile` objects.
    """
    return [f for f in index.files if f.language == language]


def summary(index: RepositoryIndex) -> dict[str, object]:
    """Produce a human-readable summary of the index.

    Args:
        index: A :class:`RepositoryIndex` from a completed scan.

    Returns:
        Dict with keys ``total_files``, ``source_files``, ``languages``,
        ``total_size_bytes``, and ``largest_files``.
    """
    stats = index.statistics
    return {
        "total_files": stats.total_files,
        "source_files": stats.source_files,
        "languages": [
            {
                "language": ls.language,
                "file_count": ls.file_count,
                "total_size_bytes": ls.total_size_bytes,
            }
            for ls in stats.languages
        ],
        "total_size_bytes": stats.total_size_bytes,
        "largest_files": [
            {
                "path": str(f.relative_path),
                "size_bytes": f.size_bytes,
                "language": f.language,
            }
            for f in stats.largest_files
        ],
    }
