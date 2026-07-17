"""Data models for Repository Diagnostics.

Defines the immutable dataclasses that represent the output of the
DiagnosticsEngine — dead code, orphans, large modules, and statistics.

All collections are deterministic — sorted by qualified_name or path
so consumers never depend on iteration order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.repository.symbols.models import SymbolType

# ---------------------------------------------------------------------------
# Diagnostic result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeadSymbol:
    """A symbol identified as dead code.

    Attributes:
        qualified_name: Fully qualified name of the dead symbol.
        symbol_type: The category of the symbol.
        module: Source file path relative to the repository root.
        lineno: 1-based line number where the symbol is defined.
    """

    qualified_name: str
    symbol_type: SymbolType
    module: str
    lineno: int


@dataclass(frozen=True)
class DependencyCycle:
    """A detected dependency cycle.

    Attributes:
        cycle: Ordered list of qualified names forming the cycle.
        length: Number of symbols in the cycle (len of cycle).
    """

    cycle: tuple[str, ...]
    length: int


@dataclass(frozen=True)
class OrphanModule:
    """A module identified as orphaned.

    Attributes:
        path: File path relative to the repository root.
        symbol_count: Number of symbols defined in the module.
    """

    path: str
    symbol_count: int


@dataclass(frozen=True)
class LargeModule:
    """A module identified as large.

    Attributes:
        path: File path relative to the repository root.
        symbol_count: Number of symbols defined in the module.
    """

    path: str
    symbol_count: int


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleStatistics:
    """Module-level aggregate statistics.

    Attributes:
        module_count: Number of modules analyzed.
        average_symbols: Average symbols per module (0 if no modules).
        largest_module: Path of the module with the most symbols.
        largest_module_symbol_count: Number of symbols in the largest module.
        largest_call_graph: Path of the module with the most relationships.
        largest_call_graph_size: Number of relationships in the largest call graph.
        average_relationships: Average relationships per module (0 if no modules).
        relationship_density: Ratio of relationships to possible pairs (0-1).
    """

    module_count: int = 0
    average_symbols: float = 0.0
    largest_module: str = ""
    largest_module_symbol_count: int = 0
    largest_call_graph: str = ""
    largest_call_graph_size: int = 0
    average_relationships: float = 0.0
    relationship_density: float = 0.0


@dataclass(frozen=True)
class GraphStatistics:
    """Graph-level aggregate statistics.

    Attributes:
        connected_components: Number of connected components in the graph.
        maximum_call_depth: Maximum call chain depth (0 if no CALLS relationships).
        average_out_degree: Average outgoing edges per node.
        average_in_degree: Average incoming edges per node.
    """

    connected_components: int = 0
    maximum_call_depth: int = 0
    average_out_degree: float = 0.0
    average_in_degree: float = 0.0


# ---------------------------------------------------------------------------
# RepositoryDiagnostics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepositoryDiagnostics:
    """Complete diagnostics output from the DiagnosticsEngine.

    Attributes:
        dead_symbols: Sorted list of dead code symbols.
        dependency_cycles: Sorted list of dependency cycles.
        orphan_modules: Sorted list of orphan modules.
        large_modules: Sorted list of large modules.
        module_statistics: Module-level aggregate statistics.
        graph_statistics: Graph-level aggregate statistics.
        warnings: List of non-fatal diagnostic warnings.
    """

    dead_symbols: tuple[DeadSymbol, ...] = field(default_factory=tuple)
    dependency_cycles: tuple[DependencyCycle, ...] = field(default_factory=tuple)
    orphan_modules: tuple[OrphanModule, ...] = field(default_factory=tuple)
    large_modules: tuple[LargeModule, ...] = field(default_factory=tuple)
    module_statistics: ModuleStatistics = field(default_factory=ModuleStatistics)
    graph_statistics: GraphStatistics = field(default_factory=GraphStatistics)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Ensure deterministic ordering of all collections."""
        object.__setattr__(
            self,
            "dead_symbols",
            tuple(
                sorted(
                    self.dead_symbols,
                    key=lambda s: (s.qualified_name, s.module, s.lineno),
                )
            ),
        )
        object.__setattr__(
            self,
            "dependency_cycles",
            tuple(sorted(self.dependency_cycles, key=lambda c: c.cycle)),
        )
        object.__setattr__(
            self,
            "orphan_modules",
            tuple(sorted(self.orphan_modules, key=lambda m: m.path)),
        )
        object.__setattr__(
            self,
            "large_modules",
            tuple(sorted(self.large_modules, key=lambda m: m.path)),
        )
        object.__setattr__(
            self,
            "warnings",
            tuple(sorted(self.warnings)),
        )
