"""Data models for the repository scanner.

Defines strongly typed dataclasses that represent the structured
output of a repository scan — directories, files, language summaries,
and aggregate statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# File-level models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceFile:
    """Metadata for a single source file discovered during scanning.

    Attributes:
        path: Absolute path to the file.
        relative_path: Path relative to the repository root.
        extension: File extension including the dot (e.g. ``".py"``).
        language: Detected programming language name.
        size_bytes: File size in bytes.
        modified_time: Last modification timestamp (seconds since epoch).
    """

    path: Path
    relative_path: Path
    extension: str
    language: str
    size_bytes: int
    modified_time: float


@dataclass(frozen=True, slots=True)
class Directory:
    """Metadata for a directory discovered during scanning.

    Attributes:
        path: Absolute path to the directory.
        relative_path: Path relative to the repository root.
        file_count: Number of files directly inside this directory.
        subdirectories: Child directories (recursively discovered).
    """

    path: Path
    relative_path: Path
    file_count: int = 0
    subdirectories: list[Directory] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Aggregate models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LanguageSummary:
    """Summary of files grouped by detected language.

    Attributes:
        language: The language name (e.g. ``"Python"``).
        file_count: Number of files in this language.
        total_size_bytes: Combined size of all files in this language.
    """

    language: str
    file_count: int
    total_size_bytes: int


@dataclass(frozen=True, slots=True)
class Statistics:
    """Aggregate statistics for a scanned repository.

    Attributes:
        total_files: Total number of files (including non-source).
        source_files: Number of files with a known language.
        languages: Per-language breakdown.
        largest_files: Top 10 largest files by size.
        total_size_bytes: Total size of all scanned files.
    """

    total_files: int
    source_files: int
    languages: list[LanguageSummary]
    largest_files: list[SourceFile]
    total_size_bytes: int


@dataclass(frozen=True, slots=True)
class RepositoryIndex:
    """Complete index produced by a repository scan.

    Attributes:
        root: The repository root directory that was scanned.
        directories: All discovered directories.
        files: All discovered files.
        statistics: Computed aggregate statistics.
    """

    root: Path
    directories: list[Directory]
    files: list[SourceFile]
    statistics: Statistics
