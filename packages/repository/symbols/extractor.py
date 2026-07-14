"""Abstract extractor interface for symbol graphs.

Language-specific extractors (Python AST, Tree-sitter, etc.) implement
this interface so that consumers can work with any language without
knowing the underlying implementation details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from packages.repository.symbols.models import Language, SymbolGraph


class SymbolExtractor(ABC):
    """Abstract base class for symbol extractors.

    Subclasses implement language-specific extraction logic.  The
    ``extract`` method accepts either a single source file or a
    directory — directory extraction is handled by iterating over files
    and merging per-file ``SymbolGraph`` instances.

    Attributes:
        language: The programming language this extractor handles.
    """

    @property
    @abstractmethod
    def language(self) -> Language:
        """The programming language this extractor handles."""
        ...

    @abstractmethod
    def extract(self, path: Path) -> SymbolGraph:
        """Extract symbols from a single file or directory.

        Args:
            path: Path to a Python source file or a directory of files.

        Returns:
            A ``SymbolGraph`` containing all discovered symbols and
            relationships.  When ``path`` is a directory, the result
            merges per-file graphs — modules remain isolated and
            relationships never cross module boundaries except
            ``IMPORTS``.
        """
        ...
