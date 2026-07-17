"""Diagnostics engine.

Orchestrates all registered diagnostics analyzers and produces a
complete ``RepositoryDiagnostics`` result.

The engine never modifies the ``RepositoryIndex`` — it only reads from
it and composes the results of all analyzers.

Usage::

    from packages.repository.diagnostics.engine import DiagnosticsEngine
    from packages.repository.index.models import RepositoryIndex

    diagnostics = DiagnosticsEngine().analyze(repository_index)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.models import RepositoryDiagnostics
from packages.repository.index.models import RepositoryIndex

if TYPE_CHECKING:
    from collections.abc import Sequence


class DiagnosticsEngine:
    """Orchestrates all registered diagnostics analyzers.

    Maintains an ordered list of analyzers.  When ``analyze()`` is
    called, each registered analyzer is invoked and the results are
    composed into a single ``RepositoryDiagnostics``.

    Attributes:
        _analyzers: Ordered list of registered analyzers.
    """

    def __init__(self) -> None:
        """Initialise the engine with no analyzers."""
        self._analyzers: list[DiagnosticsAnalyzer] = []

    def register(self, analyzer: DiagnosticsAnalyzer) -> None:
        """Register a diagnostics analyzer.

        Analyzers are stored in registration order.  Duplicate
        registrations (same analyzer instance) are ignored.

        Args:
            analyzer: The analyzer to register.
        """
        if analyzer not in self._analyzers:
            self._analyzers.append(analyzer)

    def analyze(
        self,
        repository_index: RepositoryIndex,
    ) -> RepositoryDiagnostics:
        """Run all registered analyzers and compose the results.

        Each analyzer is invoked in registration order.  Results are
        composed — dead symbols are merged, orphans are merged, etc.
        The final result has all collections sorted deterministically.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A composed ``RepositoryDiagnostics`` with all findings.
        """
        # Start with empty diagnostics.
        result: RepositoryDiagnostics = RepositoryDiagnostics()

        # Run each analyzer and merge results.
        for analyzer in self._analyzers:
            analyzer_result = analyzer.analyze(repository_index)

            # Merge each field by concatenating tuples.
            result = RepositoryDiagnostics(
                dead_symbols=result.dead_symbols + analyzer_result.dead_symbols,
                dependency_cycles=result.dependency_cycles
                + analyzer_result.dependency_cycles,
                orphan_modules=result.orphan_modules
                + analyzer_result.orphan_modules,
                large_modules=result.large_modules
                + analyzer_result.large_modules,
                module_statistics=analyzer_result.module_statistics
                if analyzer_result.module_statistics.module_count > 0
                else result.module_statistics,
                graph_statistics=analyzer_result.graph_statistics
                if analyzer_result.graph_statistics.connected_components > 0
                else result.graph_statistics,
                warnings=result.warnings + analyzer_result.warnings,
            )

        return result

    @property
    def analyzers(self) -> Sequence[DiagnosticsAnalyzer]:
        """Return all registered analyzers.

        Returns:
            Ordered list of registered analyzers.
        """
        return tuple(self._analyzers)

    def get_analyzer_by_name(self, name: str) -> DiagnosticsAnalyzer | None:
        """Return the analyzer with the given name.

        Args:
            name: The analyzer name (``DiagnosticsAnalyzer.name``).

        Returns:
            The analyzer instance, or ``None`` if not found.
        """
        for analyzer in self._analyzers:
            if analyzer.name == name:
                return analyzer
        return None
