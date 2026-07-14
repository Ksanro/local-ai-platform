"""Repository scanner package.

Walks a directory tree, collects file and directory metadata,
classifies files by language, and produces a structured index.
"""

from packages.repository.filters import parse_gitignore, should_ignore_path
from packages.repository.index import find_extension, find_language, get_file, summary
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
    "find_extension",
    "find_language",
    "get_file",
    "parse_gitignore",
    "scan",
    "should_ignore_path",
    "summary",
]
