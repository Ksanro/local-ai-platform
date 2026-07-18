"""Refactoring Advisor.

Orchestrates public Repository APIs into a RefactoringReport.

Architecture
------------

RepositoryIndex
        |
        v
DiagnosticsEngine (dead code, orphans, cycles, large modules)
        |
        v
ArchitectureAnalyzer (coupling, layering, impact)
        |
        v
RefactoringAdvisor (orchestrates all -> RefactoringReport)

Usage
-----

.. code-block:: python

    from packages.advisors.refactoring.advisor import RefactoringAdvisor
    from packages.advisors.refactoring.config import DEFAULT_CONFIG

    advisor = RefactoringAdvisor()
    report = advisor.analyze(repository_index=index)

Constraints
-----------

The advisor must **not**:

- parse Python
- inspect AST
- traverse filesystem
- invoke providers
- mutate repository state
- recompute dependency graphs

Only orchestrates public services.

Public API
----------

.. code-block:: python

    from packages.advisors.refactoring.advisor import RefactoringAdvisor

    advisor = RefactoringAdvisor()
    report = advisor.analyze(repository_index)
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from packages.advisors.refactoring.confidence import compute_confidence
from packages.advisors.refactoring.config import DEFAULT_CONFIG, RefactoringConfig
from packages.advisors.refactoring.models import (
    EvidenceType,
    RefactoringCategory,
    RefactoringEvidence,
    RefactoringOpportunity,
    RefactoringReport,
    RefactoringSummary,
    RepositoryStatistics,
    Severity,
)
from packages.repository.index.models import RepositoryIndex

if TYPE_CHECKING:
    from packages.repository.diagnostics.models import RepositoryDiagnostics


class RefactoringAdvisor:
    """Orchestrates public Repository APIs into a RefactoringReport.

    The advisor composes the following services:

    1. RepositoryIndex — modules, symbols, relationships, statistics
    2. DiagnosticsEngine — dead code, cycles, orphans, large modules
    3. ArchitectureAnalyzer — coupling, layering, impact

    It never duplicates logic from these services.

    Attributes:
        config: Configuration for threshold tuning.
    """

    def __init__(self, config: RefactoringConfig | None = None) -> None:
        """Initialize the advisor.

        Args:
            config: Configuration for threshold tuning.
                Uses ``DEFAULT_CONFIG`` when ``None``.
        """
        self.config = config if config is not None else DEFAULT_CONFIG

    def analyze(
        self,
        repository_index: RepositoryIndex,
    ) -> RefactoringReport:
        """Analyze the repository and produce a RefactoringReport.

        For each module in the repository, the advisor:

        1. Gathers diagnostics (dead code, cycles, orphans, large modules)
        2. Computes coupling metrics from the architecture review
        3. Generates recommendations using config thresholds
        4. Computes confidence for each recommendation
        5. Deduplicates by (category, affected_modules)
        6. Sorts by severity desc, confidence desc, id asc

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A ``RefactoringReport`` with all refactoring opportunities.
        """
        opportunities: list[RefactoringOpportunity] = []

        # Gather diagnostics
        diagnostics = self._get_diagnostics(repository_index)

        # Generate recommendations from each source
        opportunities.extend(self._find_high_coupling(repository_index))
        opportunities.extend(self._find_large_modules(repository_index))
        opportunities.extend(self._find_dead_code(diagnostics))
        opportunities.extend(self._find_orphan_modules(diagnostics))
        opportunities.extend(
            self._find_circular_dependencies(repository_index, diagnostics)
        )
        opportunities.extend(
            self._find_excessive_dependencies(repository_index, self.config.dependency_threshold)
        )

        # Deduplicate by (category, affected_modules)
        opportunities = self._deduplicate(opportunities)

        # Compute summary
        summary = self._compute_summary(opportunities)

        # Compute statistics
        stats = self._compute_statistics(repository_index, diagnostics)

        return RefactoringReport(
            summary=summary,
            statistics=stats,
            opportunities=tuple(opportunities),
        )

    # ------------------------------------------------------------------
    # Recommendation: HIGH_COUPLING
    # ------------------------------------------------------------------

    def _find_high_coupling(
        self,
        repository_index: RepositoryIndex,
    ) -> list[RefactoringOpportunity]:
        """Find modules with above-average total connections.

        A module is flagged when its total connections
        (dependency_count + dependent_count) exceed
        ``average * coupling_multiplier``.

        Args:
            repository_index: The repository index.

        Returns:
            List of HIGH_COUPLING opportunities.
        """
        opportunities: list[RefactoringOpportunity] = []

        # Compute per-module relationship counts
        outgoing: dict[str, int] = defaultdict(int)
        incoming: dict[str, int] = defaultdict(int)

        for rel in repository_index.relationships():
            outgoing[rel.source] += 1
            incoming[rel.target] += 1

        # Build module-level stats
        module_stats: dict[str, tuple[int, int, int]] = {}

        for mod_path, module in repository_index.modules.items():
            # Count outgoing relationships from symbols in this module
            out_count = 0
            in_count = 0
            for sym in module.symbols:
                out_count += outgoing.get(sym.qualified_name, 0)
                in_count += incoming.get(sym.qualified_name, 0)

            module_stats[mod_path] = (out_count, in_count, len(module.symbols))

        if not module_stats:
            return []

        # Calculate average total connections
        total_connections = [
            (stats[0] + stats[1]) for stats in module_stats.values()
        ]
        average = sum(total_connections) / len(total_connections)

        threshold = average * self.config.coupling_multiplier

        for mod_path, (out_count, in_count, symbol_count) in sorted(
            module_stats.items()
        ):
            total = out_count + in_count
            if total > threshold and total >= 2:
                evidence: list[RefactoringEvidence] = [
                    RefactoringEvidence(
                        type=EvidenceType.DEPENDENCY,
                        source="architecture",
                        message=(
                            f"Module has {total} total connections "
                            f"({out_count} outgoing, {in_count} incoming)."
                        ),
                        reference=mod_path,
                    ),
                    RefactoringEvidence(
                        type=EvidenceType.STATISTIC,
                        source="architecture",
                        message=(
                            f"Average total connections across all modules: "
                            f"{average:.1f}."
                        ),
                        reference=mod_path,
                    ),
                ]

                confidence = compute_confidence(
                    category=RefactoringCategory.HIGH_COUPLING,
                    evidence_count=len(evidence),
                    completeness=1.0,
                )

                module_or_none = repository_index.find_module(mod_path)
                affected_symbols = tuple(
                    sym.qualified_name for sym in module_or_none.symbols
                ) if module_or_none is not None else ()

                opportunities.append(
                    RefactoringOpportunity(
                        id=f"{RefactoringCategory.HIGH_COUPLING.value}:{mod_path}",
                        category=RefactoringCategory.HIGH_COUPLING,
                        severity=Severity.HIGH,
                        title=f"High coupling detected in {mod_path}",
                        description=(
                            f"Module '{mod_path}' has {total} total connections, "
                            f"exceeding the average ({average:.1f}) by "
                            f"{self.config.coupling_multiplier}x. "
                            f"Consider reducing dependencies or splitting the module."
                        ),
                        affected_symbols=affected_symbols,
                        affected_modules=(mod_path,),
                        confidence=confidence,
                        evidence=tuple(evidence),
                    )
                )

        return opportunities

    # ------------------------------------------------------------------
    # Recommendation: LARGE_MODULE
    # ------------------------------------------------------------------

    def _find_large_modules(
        self,
        repository_index: RepositoryIndex,
    ) -> list[RefactoringOpportunity]:
        """Find modules exceeding the configurable symbol threshold.

        Args:
            repository_index: The repository index.

        Returns:
            List of LARGE_MODULE opportunities.
        """
        opportunities: list[RefactoringOpportunity] = []
        threshold = self.config.large_module_threshold

        for mod_path, module in sorted(repository_index.modules.items()):
            symbol_count = len(module.symbols)
            if symbol_count >= threshold:
                evidence: list[RefactoringEvidence] = [
                    RefactoringEvidence(
                        type=EvidenceType.STATISTIC,
                        source="repository",
                        message=(
                            f"Module has {symbol_count} symbols "
                            f"(threshold: {threshold})."
                        ),
                        reference=mod_path,
                    ),
                ]

                confidence = compute_confidence(
                    category=RefactoringCategory.LARGE_MODULE,
                    evidence_count=len(evidence),
                    completeness=0.9,
                )

                affected_symbols = tuple(
                    sym.qualified_name for sym in module.symbols
                )

                opportunities.append(
                    RefactoringOpportunity(
                        id=f"{RefactoringCategory.LARGE_MODULE.value}:{mod_path}",
                        category=RefactoringCategory.LARGE_MODULE,
                        severity=Severity.MEDIUM,
                        title=f"Large module detected: {mod_path}",
                        description=(
                            f"Module '{mod_path}' has {symbol_count} symbols, "
                            f"exceeding the threshold of {threshold}. "
                            f"Consider splitting into smaller, more focused modules."
                        ),
                        affected_symbols=affected_symbols,
                        affected_modules=(mod_path,),
                        confidence=confidence,
                        evidence=tuple(evidence),
                    )
                )

        return opportunities

    # ------------------------------------------------------------------
    # Recommendation: DEAD_CODE
    # ------------------------------------------------------------------

    @staticmethod
    def _find_dead_code(
        diagnostics: RepositoryDiagnostics,
    ) -> list[RefactoringOpportunity]:
        """Find dead code from diagnostics.

        Args:
            diagnostics: The diagnostics result.

        Returns:
            List of DEAD_CODE opportunities.
        """
        opportunities: list[RefactoringOpportunity] = []

        if not diagnostics.dead_symbols:
            return []

        # Group dead symbols by module
        dead_by_module: dict[str, list[str]] = defaultdict(list)
        for dead in diagnostics.dead_symbols:
            dead_by_module[dead.module].append(dead.qualified_name)

        for mod_path in sorted(dead_by_module.keys()):
            dead_symbols = sorted(dead_by_module[mod_path])
            evidence: list[RefactoringEvidence] = [
                RefactoringEvidence(
                    type=EvidenceType.DIAGNOSTIC,
                    source="diagnostics",
                    message=(
                        f"Found {len(dead_symbols)} dead symbols in this module."
                    ),
                    reference=mod_path,
                ),
            ]

            # Add individual symbol evidence
            for sym in dead_symbols[:5]:  # Limit to first 5 for evidence
                evidence.append(
                    RefactoringEvidence(
                        type=EvidenceType.DIAGNOSTIC,
                        source="diagnostics",
                        message=f"Dead symbol: {sym}",
                        reference=sym,
                    )
                )

            confidence = compute_confidence(
                category=RefactoringCategory.DEAD_CODE,
                evidence_count=len(evidence),
                completeness=1.0,
            )

            opportunities.append(
                RefactoringOpportunity(
                    id=f"{RefactoringCategory.DEAD_CODE.value}:{mod_path}",
                    category=RefactoringCategory.DEAD_CODE,
                    severity=Severity.HIGH,
                    title=f"Dead code detected in {mod_path}",
                    description=(
                        f"Module '{mod_path}' contains {len(dead_symbols)} "
                        f"unreachable symbols. These symbols are never referenced "
                        f"by any other code in the repository."
                    ),
                    affected_symbols=tuple(dead_symbols),
                    affected_modules=(mod_path,),
                    confidence=confidence,
                    evidence=tuple(evidence),
                )
            )

        return opportunities

    # ------------------------------------------------------------------
    # Recommendation: ORPHAN_MODULE
    # ------------------------------------------------------------------

    @staticmethod
    def _find_orphan_modules(
        diagnostics: RepositoryDiagnostics,
    ) -> list[RefactoringOpportunity]:
        """Find orphan modules from diagnostics.

        Args:
            diagnostics: The diagnostics result.

        Returns:
            List of ORPHAN_MODULE opportunities.
        """
        opportunities: list[RefactoringOpportunity] = []

        if not diagnostics.orphan_modules:
            return []

        for orphan in diagnostics.orphan_modules:
            evidence: list[RefactoringEvidence] = [
                RefactoringEvidence(
                    type=EvidenceType.DIAGNOSTIC,
                    source="diagnostics",
                    message=(
                        f"Module '{orphan.path}' has zero relationships "
                        f"({orphan.symbol_count} symbols)."
                    ),
                    reference=orphan.path,
                ),
            ]

            confidence = compute_confidence(
                category=RefactoringCategory.ORPHAN_MODULE,
                evidence_count=len(evidence),
                completeness=1.0,
            )

            opportunities.append(
                RefactoringOpportunity(
                    id=f"{RefactoringCategory.ORPHAN_MODULE.value}:{orphan.path}",
                    category=RefactoringCategory.ORPHAN_MODULE,
                    severity=Severity.MEDIUM,
                    title=f"Orphan module detected: {orphan.path}",
                    description=(
                        f"Module '{orphan.path}' has zero relationships with "
                        f"any other module. It defines {orphan.symbol_count} symbols "
                        f"but is never imported and imports nothing."
                    ),
                    affected_symbols=(),
                    affected_modules=(orphan.path,),
                    confidence=confidence,
                    evidence=tuple(evidence),
                )
            )

        return opportunities

    # ------------------------------------------------------------------
    # Recommendation: CIRCULAR_DEPENDENCY
    # ------------------------------------------------------------------

    @staticmethod
    def _find_circular_dependencies(
        repository_index: RepositoryIndex,
        diagnostics: RepositoryDiagnostics,
    ) -> list[RefactoringOpportunity]:
        """Find circular dependencies from diagnostics.

        Args:
            repository_index: The repository index.
            diagnostics: The diagnostics result.

        Returns:
            List of CIRCULAR_DEPENDENCY opportunities.
        """
        opportunities: list[RefactoringOpportunity] = []

        if not diagnostics.dependency_cycles:
            return []

        for cycle in diagnostics.dependency_cycles:
            # Collect all modules involved in the cycle
            affected_modules: set[str] = set()
            affected_symbols: set[str] = set()

            for qname in cycle.cycle:
                affected_symbols.add(qname)
                # Find the module for this symbol
                sym_list = repository_index.find(qname)
                if sym_list:
                    affected_modules.add(sym_list[0].module)

            evidence: list[RefactoringEvidence] = [
                RefactoringEvidence(
                    type=EvidenceType.DEPENDENCY,
                    source="diagnostics",
                    message=(
                        f"Dependency cycle of length {cycle.length}: "
                        f"{' -> '.join(cycle.cycle)}"
                    ),
                    reference=" -> ".join(cycle.cycle),
                ),
            ]

            confidence = compute_confidence(
                category=RefactoringCategory.CIRCULAR_DEPENDENCY,
                evidence_count=len(evidence),
                completeness=1.0,
            )

            opportunities.append(
                RefactoringOpportunity(
                    id=(
                        f"{RefactoringCategory.CIRCULAR_DEPENDENCY.value}:"
                        f"{','.join(sorted(affected_modules))}"
                    ),
                    category=RefactoringCategory.CIRCULAR_DEPENDENCY,
                    severity=Severity.HIGH,
                    title="Circular dependency detected",
                    description=(
                        f"Dependency cycle of length {cycle.length}: "
                        f"{' -> '.join(cycle.cycle)}. "
                        f"Circular dependencies make code harder to understand, "
                        f"test, and maintain."
                    ),
                    affected_symbols=tuple(sorted(affected_symbols)),
                    affected_modules=tuple(sorted(affected_modules)),
                    confidence=confidence,
                    evidence=tuple(evidence),
                )
            )

        return opportunities

    # ------------------------------------------------------------------
    # Recommendation: EXCESSIVE_DEPENDENCIES
    # ------------------------------------------------------------------

    @staticmethod
    def _find_excessive_dependencies(
        repository_index: RepositoryIndex,
        threshold: int,
    ) -> list[RefactoringOpportunity]:
        """Find modules with excessive outgoing relationships.

        Args:
            repository_index: The repository index.
            threshold: Number of outgoing relationships to flag.

        Returns:
            List of EXCESSIVE_DEPENDENCIES opportunities.
        """
        opportunities: list[RefactoringOpportunity] = []

        # Count outgoing relationships per symbol
        outgoing: dict[str, int] = defaultdict(int)

        for rel in repository_index.relationships():
            outgoing[rel.source] += 1

        for source, count in sorted(outgoing.items()):
            if count > threshold:
                # Find the module for this source
                sym_list = repository_index.find(source)
                if sym_list:
                    module_path = sym_list[0].module
                else:
                    module_path = source

                evidence: list[RefactoringEvidence] = [
                    RefactoringEvidence(
                        type=EvidenceType.DEPENDENCY,
                        source="repository",
                        message=(
                            f"Symbol has {count} outgoing relationships "
                            f"(threshold: {threshold})."
                        ),
                        reference=module_path,
                    ),
                ]

                confidence = compute_confidence(
                    category=RefactoringCategory.EXCESSIVE_DEPENDENCIES,
                    evidence_count=len(evidence),
                    completeness=0.9,
                )

                opportunities.append(
                    RefactoringOpportunity(
                        id=(
                            f"{RefactoringCategory.EXCESSIVE_DEPENDENCIES.value}:"
                            f"{module_path}"
                        ),
                        category=RefactoringCategory.EXCESSIVE_DEPENDENCIES,
                        severity=Severity.MEDIUM,
                        title=f"Excessive dependencies in {module_path}",
                        description=(
                            f"Symbol '{source}' has {count} outgoing relationships, "
                            f"exceeding the threshold of {threshold}. "
                            f"Consider reducing the number of dependencies."
                        ),
                        affected_symbols=(source,),
                        affected_modules=(module_path,),
                        confidence=confidence,
                        evidence=tuple(evidence),
                    )
                )

        return opportunities

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(
        opportunities: list[RefactoringOpportunity],
    ) -> list[RefactoringOpportunity]:
        """Remove duplicate opportunities.

        Duplicates are identified by (category, affected_modules) tuple.
        When duplicates are found, the one with higher confidence is kept.

        Args:
            opportunities: List of opportunities to deduplicate.

        Returns:
            Deduplicated list of opportunities.
        """
        seen: dict[tuple[str, tuple[str, ...]], RefactoringOpportunity] = {}

        for opp in opportunities:
            key = (opp.category.value, opp.affected_modules)
            if key not in seen:
                seen[key] = opp
            elif opp.confidence > seen[key].confidence:
                seen[key] = opp

        return sorted(seen.values(), key=lambda o: o.id)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_summary(
        opportunities: list[RefactoringOpportunity],
    ) -> RefactoringSummary:
        """Compute summary statistics from opportunities.

        Args:
            opportunities: List of opportunities.

        Returns:
            RefactoringSummary with counts by severity.
        """
        high = sum(1 for o in opportunities if o.severity == Severity.HIGH)
        medium = sum(1 for o in opportunities if o.severity == Severity.MEDIUM)
        low = sum(1 for o in opportunities if o.severity == Severity.LOW)
        info = sum(1 for o in opportunities if o.severity == Severity.INFO)

        return RefactoringSummary(
            total_opportunities=len(opportunities),
            high=high,
            medium=medium,
            low=low,
            info=info,
        )

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_statistics(
        repository_index: RepositoryIndex,
        diagnostics: RepositoryDiagnostics,
    ) -> RepositoryStatistics:
        """Compute repository statistics.

        Args:
            repository_index: The repository index.
            diagnostics: The diagnostics result.

        Returns:
            RepositoryStatistics.
        """
        stats = repository_index.statistics()
        return RepositoryStatistics(
            modules=stats.module_count,
            symbols=stats.symbol_count,
            relationships=len(repository_index.relationships()),
            diagnostics=(
                len(diagnostics.dead_symbols)
                + len(diagnostics.dependency_cycles)
                + len(diagnostics.orphan_modules)
                + len(diagnostics.large_modules)
            ),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_diagnostics(
        repository_index: RepositoryIndex,
    ) -> RepositoryDiagnostics:
        """Run the diagnostics engine on the repository index.

        This is a direct call to the public DiagnosticsEngine API.

        Args:
            repository_index: The repository index.

        Returns:
            The diagnostics result.
        """
        from packages.repository.diagnostics.engine import DiagnosticsEngine

        return DiagnosticsEngine().analyze(repository_index)
