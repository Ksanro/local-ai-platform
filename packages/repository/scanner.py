"""Repository scanning logic.

Walks a directory tree, collects file and directory metadata,
classifies files by language, and produces a :class:`RepositoryIndex`.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from packages.repository.filters import parse_gitignore, should_ignore_path
from packages.repository.languages import detect_language
from packages.repository.models import (
    Directory,
    LanguageSummary,
    RepositoryIndex,
    SourceFile,
    Statistics,
)


def scan(path: Path) -> RepositoryIndex:
    """Scan a directory tree and produce a :class:`RepositoryIndex`.

    Walks the directory starting at ``path``, collects metadata for every
    file and subdirectory, classifies files by language, and computes
    aggregate statistics.

    Args:
        path: Root directory to scan. Must exist and be a directory.

    Returns:
        A :class:`RepositoryIndex` containing all discovered metadata.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        NotADirectoryError: If ``path`` is not a directory.
    """
    root = path.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root}")

    ignored_patterns = parse_gitignore(root)

    all_directories: list[Directory] = []
    all_files: list[SourceFile] = []

    _walk_directory(root, root, ignored_patterns, all_directories, all_files)

    statistics = _compute_statistics(all_files)

    return RepositoryIndex(
        root=root,
        directories=all_directories,
        files=all_files,
        statistics=statistics,
    )


def _walk_directory(
    absolute_path: Path,
    root: Path,
    ignored_patterns: list[str],
    directories: list[Directory],
    files: list[SourceFile],
) -> None:
    """Recursively walk a directory tree, collecting metadata.

    Args:
        absolute_path: Current directory being scanned.
        root: Repository root directory.
        ignored_patterns: Parsed gitignore patterns.
        directories: Accumulator list for discovered directories.
        files: Accumulator list for discovered files.
    """
    relative_path = absolute_path.relative_to(root)

    # Skip ignored directories at the top level.
    if relative_path.name and should_ignore_path(relative_path, True, ignored_patterns):
        return

    dir_entry = Directory(
        path=absolute_path,
        relative_path=relative_path,
    )

    try:
        entries = sorted(os.scandir(absolute_path), key=lambda e: e.name)
    except PermissionError:
        return

    file_count = 0
    for entry in entries:
        entry_path = Path(entry.path)
        entry_relative = entry_path.relative_to(root)

        if entry.is_dir(follow_symlinks=False):
            if should_ignore_path(entry_relative, True, ignored_patterns):
                continue
            _walk_directory(
                entry_path,
                root,
                ignored_patterns,
                directories,
                files,
            )
        elif entry.is_file(follow_symlinks=False):
            if should_ignore_path(entry_relative, False, ignored_patterns):
                continue
            _collect_file(entry_path, root, ignored_patterns, files)
            file_count += 1

    dir_entry = replace(dir_entry, file_count=file_count)
    directories.append(dir_entry)


def _collect_file(
    absolute_path: Path,
    root: Path,
    ignored_patterns: list[str],
    files: list[SourceFile],
) -> None:
    """Collect metadata for a single file and append to the files list.

    Args:
        absolute_path: Absolute path to the file.
        root: Repository root directory.
        ignored_patterns: Parsed gitignore patterns (for safety check).
        files: Accumulator list for discovered files.
    """
    relative_path = absolute_path.relative_to(root)

    if should_ignore_path(relative_path, False, ignored_patterns):
        return

    stat_result = absolute_path.stat()
    extension = absolute_path.suffix
    language = detect_language(extension)

    files.append(
        SourceFile(
            path=absolute_path,
            relative_path=relative_path,
            extension=extension,
            language=language,
            size_bytes=stat_result.st_size,
            modified_time=stat_result.st_mtime,
        )
    )


def _compute_statistics(files: list[SourceFile]) -> Statistics:
    """Compute aggregate statistics from a list of source files.

    Args:
        files: All discovered files.

    Returns:
        A :class:`Statistics` dataclass with computed values.
    """
    total_files = len(files)
    source_files = [f for f in files if f.language != "Unknown"]
    source_count = len(source_files)

    # Group by language.
    language_map: dict[str, dict[str, Any]] = {}
    for f in source_files:
        if f.language not in language_map:
            language_map[f.language] = {"file_count": 0, "total_size_bytes": 0}
        language_map[f.language]["file_count"] += 1
        language_map[f.language]["total_size_bytes"] += f.size_bytes

    languages = [
        LanguageSummary(
            language=lang,
            file_count=data["file_count"],
            total_size_bytes=data["total_size_bytes"],
        )
        for lang, data in sorted(
            language_map.items(),
            key=lambda x: x[1]["file_count"],
            reverse=True,
        )
    ]

    # Top 10 largest files.
    sorted_files = sorted(files, key=lambda f: f.size_bytes, reverse=True)
    largest_files = sorted_files[:10]

    total_size = sum(f.size_bytes for f in files)

    return Statistics(
        total_files=total_files,
        source_files=source_count,
        languages=languages,
        largest_files=largest_files,
        total_size_bytes=total_size,
    )
