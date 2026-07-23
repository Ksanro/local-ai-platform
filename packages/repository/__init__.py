"""Repository package.

Provides repository scanning, symbol extraction, and structural indexing.

The package owns all repository analysis — no other package may scan
source files directly.

Architecture
------------

Repository

    |

    v

Repository Index

    |

    |-- Symbol Graph

    |-- Module Metadata

    |-- Relationships

    +-- Statistics

            |

            v

    Context Builder

Usage
-----

Scan for file metadata:

    from packages.repository import scan

    index = scan(path)

Build a structural index:

    from packages.repository import index

    struct_index = index(path)
"""

from __future__ import annotations

from pathlib import Path

from packages.repository.filters import parse_gitignore, should_ignore_path
from packages.repository.index import find_extension, find_language, get_file, summary
from packages.repository.index.builder import RepositoryIndexBuilder
from packages.repository.index.models import (
    RepositoryIndex as StructIndex,
)
from packages.repository.index.models import (
    RepositoryStatistics,
)
from packages.repository.models import (
    Directory,
    LanguageSummary,
    RepositoryIndex,
    SourceFile,
    Statistics,
)
from packages.repository.scanner import scan

__all__ = [
    "Directory",
    "LanguageSummary",
    "RepositoryIndex",
    "SourceFile",
    "Statistics",
    "StructIndex",
    "RepositoryStatistics",
    "RepositoryIndexBuilder",
    "find_extension",
    "find_language",
    "get_file",
    "build_index",
    "parse_gitignore",
    "should_ignore_path",
    "scan",
    "summary",
]


def build_index(path: Path, exclude_tests: bool = False) -> StructIndex:
    """Build a structural :class:`StructIndex` from the given path.

    Delegates symbol extraction to the existing :class:`PythonAstExtractor`
    and returns an immutable, deterministic :class:`StructIndex` containing
    all modules, symbols, relationships, and statistics.

    Args:
        path: Path to a Python source file or directory.
        exclude_tests: When ``True``, test files are excluded from
            the index.

    Returns:
        A :class:`StructIndex` with complete structural analysis.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        NotADirectoryError: If ``path`` is not a directory.
    """
    return RepositoryIndexBuilder(exclude_tests=exclude_tests).build(path)
