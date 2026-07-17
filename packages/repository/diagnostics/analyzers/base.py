"""Abstract base class for diagnostics analyzers.

Defines the interface that all diagnostics analyzers must implement.
Each analyzer operates on the existing RepositoryIndex and produces
a DiagnosticResult — it never modifies the index or performs side effects.

No analyzer may:

- modify the RepositoryIndex
- modify the SymbolGraph
- call providers
- access filesystem
- parse AST
- perform inference
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from packages.repository.index.models import RepositoryIndex

if TYPE_CHECKING:
    from packages.repository.diagnostics.models import (
        RepositoryDiagnostics,
    )


class DiagnosticsAnalyzer(ABC):
    """Abstract base class for diagnostics analyzers.

    Subclasses implement specific diagnostic analyses.  The ``analyze``
    method receives a ``RepositoryIndex`` and returns a ``RepositoryDiagnostics``
    with the diagnostic findings.

    Analyzers must be deterministic — repeated analysis on the same
    repository must produce identical results, sorted by the appropriate
    keys for each result type.

    Attributes:
        _name: Human-readable name of this analyzer.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this analyzer.

        Returns:
            The analyzer name (e.g. ``"dead_code"``).
        """
        ...

    @abstractmethod
    def analyze(
        self,
        repository_index: RepositoryIndex,
    ) -> RepositoryDiagnostics:
        """Run the diagnostic analysis on the given repository index.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A ``RepositoryDiagnostics`` with diagnostic findings.
        """
        ...
