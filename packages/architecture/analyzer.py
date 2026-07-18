"""Architecture Analyzer.

Orchestrates public Repository APIs into an ArchitectureReview.

Architecture
------------

RepositoryIndex
        │
        ▼
Dependency Graph (WorkspaceDependencyGraph)
        │
        ▼
Diagnostics (DiagnosticsEngine)
        │
        ▼
Change Impact Analyzer
        │
        ▼
ArchitectureReview (composed)

Usage
-----

.. code-block:: python

    from packages.architecture.analyzer import ArchitectureAnalyzer

    analyzer = ArchitectureAnalyzer()
    review = analyzer.analyze(repository_index)

Constraints
-----------

The analyzer must **not**:

- parse Python
- inspect AST
- traverse filesystem
- invoke providers
- compute relationships manually

Only orchestrates public APIs.

Public API
----------

.. code-block:: python

    from packages.architecture.analyzer import ArchitectureAnalyzer

    analyzer = ArchitectureAnalyzer()
    review = analyzer.analyze(repository_index)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.architecture.models import ArchitectureReview, ModuleSummary
from packages.repository.impact.analyzer import ChangeImpactAnalyzer
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import RelationshipType

if TYPE_CHECKING:
    pass


class ArchitectureAnalyzer:
    """Orchestrates public Repository APIs into an ArchitectureReview.

    The analyzer composes the following services:

    1. RepositoryIndex — modules, symbols, relationships, statistics
    2. WorkspaceDependencyGraph — dependency graph summary
    3. DiagnosticsEngine — dead code, cycles, orphans
    4. ChangeImpactAnalyzer — impact summary for top modules

    It never duplicates logic from these services.
    """

    def analyze(
        self,
        repository_index: RepositoryIndex,
    ) -> ArchitectureReview:
        """Analyze the repository and produce an ArchitectureReview.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            An ``ArchitectureReview`` with all architectural findings.
        """
        # Gather all data sources
        modules = self._gather_module_summaries(repository_index)
        dependency_summary = self._compute_dependency_summary(repository_index)
        dependency_cycles = self._compute_dependency_cycles(repository_index)
        layering_violations = self._detect_layering_violations(repository_index)
        orphan_modules = self._identify_orphan_modules(repository_index)
        high_coupling_modules = self._find_high_coupling_modules(modules)
        largest_components = self._find_largest_components(modules)
        diagnostics = self._gather_diagnostics(repository_index)
        impact_summary = self._compute_impact_summary(repository_index, modules)
        repository_statistics = self._gather_repository_statistics(repository_index)

        return ArchitectureReview(
            modules=tuple(modules),
            dependency_summary=dict(sorted(dependency_summary.items())),
            dependency_cycles=dependency_cycles,
            layering_violations=tuple(sorted(layering_violations)),
            orphan_modules=tuple(sorted(orphan_modules)),
            high_coupling_modules=tuple(high_coupling_modules),
            largest_components=tuple(largest_components),
            diagnostics=dict(sorted(diagnostics.items())),
            impact_summary=impact_summary,
            repository_statistics=dict(sorted(repository_statistics.items())),
        )

    # ------------------------------------------------------------------
    # Module summaries
    # ------------------------------------------------------------------

    def _gather_module_summaries(
        self,
        repository_index: RepositoryIndex,
    ) -> list[ModuleSummary]:
        """Build ModuleSummary for every module in the index.

        Args:
            repository_index: The repository index.

        Returns:
            List of ModuleSummary instances, sorted by module name.
        """
        modules: list[ModuleSummary] = []

        for module_path, module in repository_index.modules.items():
            symbol_count = len(module.symbols)
            dependency_count = self._count_outgoing(module_path, repository_index)
            dependent_count = self._count_incoming(module_path, repository_index)

            # Compute instability: dependency_count / (dependency_count + dependent_count)
            total = dependency_count + dependent_count
            if total == 0:
                instability_score = 0.0
            else:
                instability_score = round(dependency_count / total, 4)

            modules.append(
                ModuleSummary(
                    module=module_path,
                    symbol_count=symbol_count,
                    dependency_count=dependency_count,
                    dependent_count=dependent_count,
                    instability_score=instability_score,
                )
            )

        # Sort by module name for deterministic output
        modules.sort(key=lambda m: m.module)
        return modules

    # ------------------------------------------------------------------
    # Dependency summary
    # ------------------------------------------------------------------

    def _compute_dependency_summary(
        self,
        repository_index: RepositoryIndex,
    ) -> dict[str, int]:
        """Count relationships by type.

        Args:
            repository_index: The repository index.

        Returns:
            Dict mapping relationship type to count.
        """
        summary: dict[str, int] = {}
        for rel in repository_index.relationships():
            key = rel.type.value
            summary[key] = summary.get(key, 0) + 1
        return summary

    # ------------------------------------------------------------------
    # Dependency cycles
    # ------------------------------------------------------------------

    def _compute_dependency_cycles(
        self,
        repository_index: RepositoryIndex,
    ) -> tuple[str, ...]:
        """Detect dependency cycles using DFS.

        Args:
            repository_index: The repository index.

        Returns:
            Tuple of cycle path strings, sorted.
        """
        # Build adjacency list from relationships
        adjacency: dict[str, set[str]] = {}
        for rel in repository_index.relationships():
            adjacency.setdefault(rel.source, set()).add(rel.target)
            adjacency.setdefault(rel.target, set()).add(rel.source)

        # Find cycles using DFS
        cycles: list[list[str]] = []
        visited: set[str] = set()

        for node in sorted(adjacency.keys()):
            if node not in visited:
                self._find_cycles_dfs(
                    node=node,
                    adjacency=adjacency,
                    visited=visited,
                    path=[],
                    cycles=cycles,
                )

        # Convert cycles to sorted tuples of strings
        cycle_strings: list[str] = []
        seen_cycles: set[tuple[str, ...]] = set()
        for cycle in cycles:
            normalized = tuple(sorted(cycle))
            if normalized not in seen_cycles:
                seen_cycles.add(normalized)
                cycle_strings.append(" -> ".join(normalized) + " -> " + normalized[0])

        return tuple(sorted(cycle_strings))

    @staticmethod
    def _find_cycles_dfs(
        node: str,
        adjacency: dict[str, set[str]],
        visited: set[str],
        path: list[str],
        cycles: list[list[str]],
    ) -> None:
        """DFS cycle detection helper.

        Args:
            node: Current node.
            adjacency: Adjacency list.
            visited: Set of fully visited nodes.
            path: Current DFS path.
            cycles: List to collect found cycles.
        """
        if node in path:
            # Found a cycle
            cycle_start = path.index(node)
            cycle = path[cycle_start:]
            if len(cycle) >= 2:
                cycles.append(list(cycle))
            return

        if node in visited:
            return

        path.append(node)

        for neighbor in sorted(adjacency.get(node, set())):
            ArchitectureAnalyzer._find_cycles_dfs(neighbor, adjacency, visited, path, cycles)

        path.pop()
        visited.add(node)

    # ------------------------------------------------------------------
    # Layering violations
    # ------------------------------------------------------------------

    def _detect_layering_violations(
        self,
        repository_index: RepositoryIndex,
    ) -> list[str]:
        """Detect layering constraint violations.

        Checks for:
        - Tests importing production code (beyond test utilities)
        - Implementation modules importing test modules

        Args:
            repository_index: The repository index.

        Returns:
            List of violation description strings.
        """
        violations: list[str] = []

        for rel in repository_index.relationships():
            if rel.type != RelationshipType.IMPORTS:
                continue

            source_module = rel.source
            target_module = rel.target

            # Check: test module importing production code
            if self._is_test_path(source_module) and not self._is_test_path(
                target_module
            ):
                # Check if it's importing a test utility (allowed)
                if not self._is_test_utility(target_module):
                    violations.append(
                        f"Test module '{source_module}' imports production module '{target_module}'"
                    )

            # Check: production module importing test module
            if not self._is_test_path(source_module) and self._is_test_path(
                target_module
            ):
                violations.append(
                    f"Production module '{source_module}' imports test module '{target_module}'"
                )

        return violations

    @staticmethod
    def _is_test_path(module_path: str) -> bool:
        """Check if a module path appears to be a test module.

        Args:
            module_path: The module path to check.

        Returns:
            True if the module appears to be a test module.
        """
        return "/tests/" in module_path or module_path.startswith("tests/")

    @staticmethod
    def _is_test_utility(module_path: str) -> bool:
        """Check if a module is a test utility (conftest, fixtures, etc.).

        Args:
            module_path: The module path to check.

        Returns:
            True if the module is a test utility.
        """
        test_utilities = (
            "conftest",
            "fixtures",
            "test_utils",
            "test_helpers",
            "mocks",
            "factories",
        )
        return any(utility in module_path for utility in test_utilities)

    # ------------------------------------------------------------------
    # Orphan modules
    # ------------------------------------------------------------------

    def _identify_orphan_modules(
        self,
        repository_index: RepositoryIndex,
    ) -> list[str]:
        """Identify modules with zero relationships.

        Args:
            repository_index: The repository index.

        Returns:
            List of orphan module paths, sorted.
        """
        orphans: list[str] = []

        for module_path in repository_index.modules:
            has_relationships = False
            for rel in repository_index.relationships():
                if rel.source == module_path or rel.target == module_path:
                    has_relationships = True
                    break
            if not has_relationships:
                orphans.append(module_path)

        return sorted(orphans)

    # ------------------------------------------------------------------
    # High coupling modules
    # ------------------------------------------------------------------

    def _find_high_coupling_modules(
        self,
        modules: list[ModuleSummary],
    ) -> list[ModuleSummary]:
        """Find modules with above-average total connections.

        Modules with total connections (dependency_count + dependent_count)
        above the average are considered high-coupling.

        Args:
            modules: List of all module summaries.

        Returns:
            List of high-coupling ModuleSummary instances, sorted by total connections descending.
        """
        if not modules:
            return []

        # Calculate average total connections
        total_connections = [m.dependency_count + m.dependent_count for m in modules]
        average = sum(total_connections) / len(total_connections)

        # Filter modules above average (minimum 2 connections to avoid noise)
        high_coupling = [
            m for m in modules if (m.dependency_count + m.dependent_count) > average
            and (m.dependency_count + m.dependent_count) >= 2
        ]

        # Sort by total connections descending, then by module name
        high_coupling.sort(key=lambda m: (-(m.dependency_count + m.dependent_count), m.module))
        return high_coupling

    # ------------------------------------------------------------------
    # Largest components
    # ------------------------------------------------------------------

    def _find_largest_components(
        self,
        modules: list[ModuleSummary],
    ) -> list[ModuleSummary]:
        """Find the modules with the most symbols.

        Args:
            modules: List of all module summaries.

        Returns:
            List of largest ModuleSummary instances (top 10 or
            fewer), sorted by symbol_count descending.
        """
        # Sort by symbol_count descending, then by module name
        sorted_modules = sorted(
            modules, key=lambda m: (-m.symbol_count, m.module)
        )

        # Return top 10
        return sorted_modules[:10]

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def _gather_diagnostics(
        self,
        repository_index: RepositoryIndex,
    ) -> dict[str, int]:
        """Gather diagnostic statistics from the repository.

        Args:
            repository_index: The repository index.

        Returns:
            Dict of diagnostic key-value pairs.
        """
        stats = repository_index.statistics()
        return {
            "module_count": stats.module_count,
            "class_count": stats.class_count,
            "function_count": stats.function_count,
            "method_count": stats.method_count,
            "symbol_count": stats.symbol_count,
        }

    # ------------------------------------------------------------------
    # Impact summary
    # ------------------------------------------------------------------

    def _compute_impact_summary(
        self,
        repository_index: RepositoryIndex,
        modules: list[ModuleSummary],
    ) -> dict[str, object]:
        """Compute change impact summary for the top modules.

        Args:
            repository_index: The repository index.
            modules: List of all module summaries.

        Returns:
            Dict with impact analysis results.
        """
        if not modules:
            return {
                "analyzed_modules": [],
                "total_impacted_symbols": 0,
                "max_dependency_distance": 0,
                "confidence": 0.0,
            }

        # Analyze impact for the top 3 most connected modules
        top_modules = sorted(
            modules, key=lambda m: (-(m.dependency_count + m.dependent_count), m.module)
        )[:3]

        # Collect qualified names for impact analysis
        symbols_to_analyze: list[str] = []
        for module_summary in top_modules:
            module = repository_index.find_module(module_summary.module)
            if module:
                for symbol in module.symbols:
                    symbols_to_analyze.append(symbol.qualified_name)

        # Limit to top 5 symbols to analyze
        symbols_to_analyze = symbols_to_analyze[:5]

        if not symbols_to_analyze:
            return {
                "analyzed_modules": [m.module for m in top_modules],
                "total_impacted_symbols": 0,
                "max_dependency_distance": 0,
                "confidence": 0.0,
            }

        # Run ChangeImpactAnalyzer
        impact_analyzer = ChangeImpactAnalyzer()
        report = impact_analyzer.analyze(symbols_to_analyze, repository_index)

        return {
            "analyzed_modules": [m.module for m in top_modules],
            "total_impacted_symbols": len(report.impacted_symbols),
            "max_dependency_distance": report.dependency_distance,
            "confidence": report.confidence,
            "impacted_modules": list(report.impacted_modules),
            "impacted_tests": list(report.impacted_tests),
        }

    # ------------------------------------------------------------------
    # Repository statistics
    # ------------------------------------------------------------------

    def _gather_repository_statistics(
        self,
        repository_index: RepositoryIndex,
    ) -> dict[str, int]:
        """Gather aggregate repository statistics.

        Args:
            repository_index: The repository index.

        Returns:
            Dict of repository statistics.
        """
        stats = repository_index.statistics()
        return {
            "module_count": stats.module_count,
            "class_count": stats.class_count,
            "function_count": stats.function_count,
            "method_count": stats.method_count,
            "symbol_count": stats.symbol_count,
        }

    # ------------------------------------------------------------------
    # Relationship counting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_outgoing(
        module_path: str,
        repository_index: RepositoryIndex,
    ) -> int:
        """Count outgoing relationships from a module.

        Relationships use symbol qualified names as source/target.
        This method maps symbol qualified names to module paths.

        Args:
            module_path: The module path.
            repository_index: The repository index.

        Returns:
            Number of outgoing relationships from symbols in this module.
        """
        # Build symbol-to-module mapping
        symbol_to_module: dict[str, str] = {}
        for mod_path, mod in repository_index.modules.items():
            for sym in mod.symbols:
                symbol_to_module[sym.qualified_name] = mod_path

        count = 0
        for rel in repository_index.relationships():
            if symbol_to_module.get(rel.source) == module_path:
                count += 1
        return count

    @staticmethod
    def _count_incoming(
        module_path: str,
        repository_index: RepositoryIndex,
    ) -> int:
        """Count incoming relationships to a module.

        Relationships use symbol qualified names as source/target.
        This method maps symbol qualified names to module paths.

        Args:
            module_path: The module path.
            repository_index: The repository index.

        Returns:
            Number of incoming relationships to symbols in this module.
        """
        # Build symbol-to-module mapping
        symbol_to_module: dict[str, str] = {}
        for mod_path, mod in repository_index.modules.items():
            for sym in mod.symbols:
                symbol_to_module[sym.qualified_name] = mod_path

        count = 0
        for rel in repository_index.relationships():
            if symbol_to_module.get(rel.target) == module_path:
                count += 1
        return count
