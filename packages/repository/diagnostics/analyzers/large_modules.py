"""Large module analyzer.

Detects modules with an excessive number of symbols — a proxy for
complexity and potential maintenance risk.

A module is considered large when its symbol count exceeds the
configured threshold (default: 10).

Algorithm: O(S) where S is the total number of symbols.
Single pass over all modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.models import (
    LargeModule,
    RepositoryDiagnostics,
)
from packages.repository.index.models import RepositoryIndex

if TYPE_CHECKING:
    pass


class LargeModuleAnalyzer(DiagnosticsAnalyzer):
    """Detects modules with excessive symbol count.

    A module is considered large when its symbol count exceeds the
    configured threshold (default: 10).

    Complexity: O(S) — single pass over all modules.
    """

    def __init__(self, threshold: int = 10) -> None:
        """Initialise the analyzer.

        Args:
            threshold: Minimum symbol count to consider a module large.
        """
        self._threshold = threshold

    @property
    def name(self) -> str:
        """Analyzer name."""
        return "large_modules"

    def analyze(
        self,
        repository_index: RepositoryIndex,
    ) -> RepositoryDiagnostics:
        """Run large module detection.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A ``RepositoryDiagnostics`` with large module findings.
        """
        large: list[LargeModule] = []
        seen: set[str] = set()

        for mod in repository_index.modules_list():
            path = mod.path

            # Dedup by path.
            if path in seen:
                continue
            seen.add(path)

            symbol_count = len(mod.symbols)
            if symbol_count >= self._threshold:
                large.append(LargeModule(
                    path=path,
                    symbol_count=symbol_count,
                ))

        # Sort by path for deterministic output.
        large.sort(key=lambda m: m.path)

        return RepositoryDiagnostics(
            large_modules=tuple(large),
        )
