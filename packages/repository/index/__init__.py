"""Repository Index package.

Provides an immutable, deterministic structural index for a repository
or directory.  The index is built once and queried read-only — no
parsing, ranking, or inference is performed.

Usage
-----

Build an index:

    from packages.repository.index import RepositoryIndexBuilder

    builder = RepositoryIndexBuilder()
    index = builder.build(path)

Query the index:

    symbols = index.symbols()
    modules = index.modules_list()
    stats = index.statistics()
    found = index.find("App")
    module = index.find_module("main.py")
"""

from packages.repository.index.builder import RepositoryIndexBuilder
from packages.repository.index.helpers import (
    find_extension,
    find_language,
    get_file,
    summary,
)
from packages.repository.index.models import RepositoryIndex, RepositoryStatistics

__all__ = [
    "find_extension",
    "find_language",
    "get_file",
    "RepositoryIndex",
    "RepositoryIndexBuilder",
    "RepositoryStatistics",
    "summary",
]
