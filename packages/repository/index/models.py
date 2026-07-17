"""Data models for the Repository Index.

Defines the immutable dataclasses that represent the complete structural
analysis of a repository — modules, symbols, relationships, and statistics.

The RepositoryIndex owns the full SymbolGraph data.  No duplication.
All public collections are sorted deterministically — by ``qualified_name``
first, then by ``lineno`` — so consumers never depend on filesystem
traversal order.

No public method exposes Python AST nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from packages.repository.symbols.models import (
    Module,
    Relationship,
    RelationshipType,
    Symbol,
    SymbolType,
)

__all__ = [
    "Module",
    "Relationship",
    "RelationshipType",
    "RepositoryIndex",
    "RepositoryStatistics",
    "Symbol",
    "SymbolType",
]

if TYPE_CHECKING:
    from collections.abc import Sequence


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RepositoryStatistics:
    """Aggregate statistics derived from the symbol graph.

    Attributes:
        module_count: Number of modules (source files) in the repository.
        class_count: Number of CLASS symbols.
        function_count: Number of FUNCTION symbols.
        method_count: Number of METHOD symbols.
        symbol_count: Total number of symbols across all types.
    """

    module_count: int = 0
    class_count: int = 0
    function_count: int = 0
    method_count: int = 0
    symbol_count: int = 0


# ---------------------------------------------------------------------------
# RepositoryIndex
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RepositoryIndex:
    """Complete structural index for a repository (or directory).

    Contains all modules, symbols, relationships, and aggregate statistics.
    The RepositoryIndex is immutable after construction — all collections
    are sorted deterministically.

    Attributes:
        modules: All discovered modules keyed by file path.
        symbols: All symbols across all modules.
        relationships: All relationships across all modules.
        statistics: Computed aggregate statistics.
    """

    modules: dict[str, Module] = field(default_factory=dict)
    _symbols: list[Symbol] = field(default_factory=list)
    _relationships: list[Relationship] = field(default_factory=list)
    _statistics: RepositoryStatistics = field(default_factory=RepositoryStatistics)

    # ------------------------------------------------------------------
    # Module access
    # ------------------------------------------------------------------

    def modules_list(self) -> Sequence[Module]:
        """Return all modules sorted by path.

        Returns:
            Sorted list of ``Module`` instances.
        """
        return sorted(self.modules.values(), key=lambda m: m.path)

    def find_module(self, path: str) -> Module | None:
        """Return the module with the given path, or ``None``.

        Args:
            path: Module path (file path relative to repository root).

        Returns:
            The ``Module`` if found, otherwise ``None``.
        """
        return self.modules.get(path)

    # ------------------------------------------------------------------
    # Symbol collections
    # ------------------------------------------------------------------

    def symbols(self) -> Sequence[Symbol]:
        """Return all symbols sorted by qualified_name, lineno.

        Deduplicates by ``qualified_name`` — the last occurrence wins.

        Returns:
            Sorted list of all ``Symbol`` instances.
        """
        seen: dict[str, Symbol] = {}
        for sym in self._symbols:
            seen[sym.qualified_name] = sym
        return sorted(seen.values(), key=lambda s: (s.qualified_name, s.lineno))

    def classes(self) -> Sequence[Symbol]:
        """Return all CLASS symbols sorted by qualified_name, lineno.

        Returns:
            Sorted list of ``Symbol`` instances with ``SymbolType.CLASS``.
        """
        return self._filtered_symbols(SymbolType.CLASS)

    def functions(self) -> Sequence[Symbol]:
        """Return all FUNCTION symbols sorted by qualified_name, lineno.

        Returns:
            Sorted list of ``Symbol`` instances with ``SymbolType.FUNCTION``.
        """
        return self._filtered_symbols(SymbolType.FUNCTION)

    def methods(self) -> Sequence[Symbol]:
        """Return all METHOD symbols sorted by qualified_name, lineno.

        Returns:
            Sorted list of ``Symbol`` instances with ``SymbolType.METHOD``.
        """
        return self._filtered_symbols(SymbolType.METHOD)

    # ------------------------------------------------------------------
    # Relationship access
    # ------------------------------------------------------------------

    def relationships(self) -> Sequence[Relationship]:
        """Return all relationships sorted by source, target, type.

        Returns:
            Sorted list of ``Relationship`` instances.
        """
        return sorted(
            self._relationships,
            key=lambda r: (r.source, r.target, r.type.value),
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def find(self, name: str) -> Sequence[Symbol]:
        """Find symbols by name or qualified_name.

        Matches against both the short ``name`` and the fully qualified
        ``qualified_name``.  Always returns a list (never ``None``).

        Args:
            name: The name or qualified name to search for.

        Returns:
            List of matching ``Symbol`` instances, deduplicated by
            ``qualified_name`` and sorted.
        """
        results: list[Symbol] = []
        seen: set[str] = set()

        for sym in self._symbols:
            if sym.name == name or sym.qualified_name == name:
                if sym.qualified_name not in seen:
                    seen.add(sym.qualified_name)
                    results.append(sym)

        return sorted(results, key=lambda s: (s.qualified_name, s.lineno))

    # ------------------------------------------------------------------
    # Statistics access
    # ------------------------------------------------------------------

    def statistics(self) -> RepositoryStatistics:
        """Return the repository statistics.

        Returns:
            The ``RepositoryStatistics`` instance.
        """
        return self._statistics

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _filtered_symbols(self, symbol_type: SymbolType) -> Sequence[Symbol]:
        """Return all symbols of a given type, sorted by qualified_name, lineno.

        Args:
            symbol_type: The symbol type to filter by.

        Returns:
            Sorted list of matching ``Symbol`` instances.
        """
        filtered = [s for s in self._symbols if s.symbol_type == symbol_type]
        return sorted(filtered, key=lambda s: (s.qualified_name, s.lineno))
