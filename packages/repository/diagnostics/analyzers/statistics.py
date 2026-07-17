"""Module statistics analyzer.

Calculates aggregate module-level statistics from the RepositoryIndex
— no filesystem metadata, no AST parsing.

Algorithm: O(M + S + R) where M is modules, S is symbols, R is
relationships.  Single pass over each collection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.models import (
    ModuleStatistics,
    RepositoryDiagnostics,
)
from packages.repository.index.models import RepositoryIndex

if TYPE_CHECKING:
    pass


class ModuleStatisticsAnalyzer(DiagnosticsAnalyzer):
    """Calculates module-level aggregate statistics.

    Computes:
    - module_count
    - average_symbols
    - largest_module
    - largest_call_graph
    - average_relationships
    - relationship_density

    Complexity: O(M + S + R) — single pass over modules, symbols, and
    relationships.
    """

    @property
    def name(self) -> str:
        """Analyzer name."""
        return "module_statistics"

    def analyze(
        self,
        repository_index: RepositoryIndex,
    ) -> RepositoryDiagnostics:
        """Run module statistics analysis.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A ``RepositoryDiagnostics`` with module statistics.
        """
        modules = repository_index.modules_list()
        module_count = len(modules)

        if module_count == 0:
            return RepositoryDiagnostics(
                module_statistics=ModuleStatistics(
                    module_count=0,
                    average_symbols=0.0,
                    largest_module="",
                    largest_module_symbol_count=0,
                    largest_call_graph="",
                    largest_call_graph_size=0,
                    average_relationships=0.0,
                    relationship_density=0.0,
                ),
            )

        # Count symbols per module.
        symbol_counts: dict[str, int] = {}
        for mod in modules:
            symbol_counts[mod.path] = len(mod.symbols)

        # Find largest module by symbol count.
        largest_module = ""
        largest_symbol_count = 0
        for mod in modules:
            count = symbol_counts.get(mod.path, 0)
            if count > largest_symbol_count:
                largest_symbol_count = count
                largest_module = mod.path

        # Count relationships per module (both source and target).
        relationship_counts: dict[str, int] = {}
        total_relationships = 0

        for rel in repository_index.relationships():
            total_relationships += 1

            # Count for source module
            src_count = relationship_counts.get(rel.source, 0)
            relationship_counts[rel.source] = src_count + 1

            # Count for target module
            tgt_count = relationship_counts.get(rel.target, 0)
            relationship_counts[rel.target] = tgt_count + 1

        # Find module with most relationships (call graph size).
        largest_call_graph = ""
        largest_call_graph_size = 0
        for mod in modules:
            count = relationship_counts.get(mod.path, 0)
            if count > largest_call_graph_size:
                largest_call_graph_size = count
                largest_call_graph = mod.path

        # Calculate averages.
        total_symbols = sum(symbol_counts.values())
        average_symbols = total_symbols / module_count if module_count > 0 else 0.0
        average_relationships = (
            total_relationships / module_count if module_count > 0 else 0.0
        )

        # Calculate relationship density.
        # Density = actual_relationships / possible_pairs
        # For a directed graph: possible_pairs = M * (M - 1)
        possible_pairs = module_count * (module_count - 1) if module_count > 1 else 1
        relationship_density = (
            total_relationships / possible_pairs if possible_pairs > 0 else 0.0
        )
        # Clamp to [0, 1]
        relationship_density = min(relationship_density, 1.0)

        return RepositoryDiagnostics(
            module_statistics=ModuleStatistics(
                module_count=module_count,
                average_symbols=round(average_symbols, 4),
                largest_module=largest_module,
                largest_module_symbol_count=largest_symbol_count,
                largest_call_graph=largest_call_graph,
                largest_call_graph_size=largest_call_graph_size,
                average_relationships=round(average_relationships, 4),
                relationship_density=round(relationship_density, 6),
            ),
        )
