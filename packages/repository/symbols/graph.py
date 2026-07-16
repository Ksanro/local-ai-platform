"""SymbolGraph public API.

Provides read-only access to the symbol graph's contents.  All public
collections are sorted deterministically — by ``qualified_name`` first,
then by ``lineno`` — so consumers never depend on filesystem traversal
order.

No public method exposes Python AST nodes.
"""

from __future__ import annotations

__all__ = ["SymbolGraphView"]

from typing import TYPE_CHECKING

from packages.repository.symbols.models import (
    Module,
    RelationshipType,
    Symbol,
    SymbolGraph,
    SymbolType,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class SymbolGraphView:
    """Read-only view over a ``SymbolGraph``.

    Wraps a ``SymbolGraph`` and provides typed, sorted accessors.
    """

    def __init__(self, graph: SymbolGraph) -> None:
        """Initialise from a ``SymbolGraph``.

        Args:
            graph: The symbol graph to view.
        """
        self._graph = graph

    # ------------------------------------------------------------------
    # Module access
    # ------------------------------------------------------------------

    def modules(self) -> Sequence[Module]:
        """Return all modules sorted by path.

        Returns:
            Sorted list of ``Module`` instances.
        """
        return sorted(self._graph.modules.values(), key=lambda m: m.path)

    def module(self, path: str) -> Module | None:
        """Return the module with the given path, or ``None``.

        Args:
            path: Module path (file path relative to repository root).

        Returns:
            The ``Module`` if found, otherwise ``None``.
        """
        return self._graph.modules.get(path)

    # ------------------------------------------------------------------
    # Symbol collections
    # ------------------------------------------------------------------

    def classes(self) -> Sequence[Symbol]:
        """Return all CLASS symbols sorted by qualified_name, lineno.

        Returns:
            Sorted list of ``Symbol`` instances with ``SymbolType.CLASS``.
        """
        return self._sorted_symbols(SymbolType.CLASS)

    def functions(self) -> Sequence[Symbol]:
        """Return all FUNCTION symbols sorted by qualified_name, lineno.

        Returns:
            Sorted list of ``Symbol`` instances with ``SymbolType.FUNCTION``.
        """
        return self._sorted_symbols(SymbolType.FUNCTION)

    def methods(self) -> Sequence[Symbol]:
        """Return all METHOD symbols sorted by qualified_name, lineno.

        Returns:
            Sorted list of ``Symbol`` instances with ``SymbolType.METHOD``.
        """
        return self._sorted_symbols(SymbolType.METHOD)

    def symbols(self) -> Sequence[Symbol]:
        """Return all symbols sorted by qualified_name, lineno.

        Returns:
            Sorted list of all ``Symbol`` instances.
        """
        all_symbols: list[Symbol] = []
        for module in self._graph.modules.values():
            all_symbols.extend(module.symbols)
        return sorted(all_symbols, key=lambda s: (s.qualified_name, s.lineno))

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
            List of matching ``Symbol`` instances.
        """
        results: list[Symbol] = []
        for module in self._graph.modules.values():
            for sym in module.symbols:
                if sym.name == name or sym.qualified_name == name:
                    results.append(sym)
        # Deduplicate by qualified_name (same symbol may appear in
        # multiple modules if the same name is used).
        seen: set[str] = set()
        unique: list[Symbol] = []
        for sym in results:
            if sym.qualified_name not in seen:
                seen.add(sym.qualified_name)
                unique.append(sym)
        return sorted(unique, key=lambda s: (s.qualified_name, s.lineno))

    # ------------------------------------------------------------------
    # Relationship traversal (DEFINES only)
    # ------------------------------------------------------------------

    def children(self, symbol: Symbol) -> Sequence[Symbol]:
        """Return direct children of a symbol via DEFINES relationships.

        Only ``DEFINES`` relationships are traversed.  Other relationship
        types (``IMPORTS``, ``INHERITS``, ``CALLS``) are ignored.

        Args:
            symbol: The parent symbol.

        Returns:
            Sorted list of child ``Symbol`` instances.
        """
        children_ids: set[str] = set()
        for module in self._graph.modules.values():
            for rel in module.relationships:
                if rel.type == RelationshipType.DEFINES and rel.source == symbol.qualified_name:
                    children_ids.add(rel.target)

        # Build a lookup of all symbols by qualified_name.
        symbol_lookup: dict[str, Symbol] = {}
        for module in self._graph.modules.values():
            for sym in module.symbols:
                symbol_lookup[sym.qualified_name] = sym

        return sorted(
            (symbol_lookup[cid] for cid in children_ids if cid in symbol_lookup),
            key=lambda s: (s.qualified_name, s.lineno),
        )

    def parents(self, symbol: Symbol) -> Sequence[Symbol]:
        """Return direct parents of a symbol via DEFINES relationships.

        Only ``DEFINES`` relationships are traversed.  Other relationship
        types (``IMPORTS``, ``INHERITS``, ``CALLS``) are ignored.

        Args:
            symbol: The child symbol.

        Returns:
            Sorted list of parent ``Symbol`` instances.
        """
        parent_ids: set[str] = set()
        for module in self._graph.modules.values():
            for rel in module.relationships:
                if rel.type == RelationshipType.DEFINES and rel.target == symbol.qualified_name:
                    parent_ids.add(rel.source)

        # Build a lookup of all symbols by qualified_name.
        symbol_lookup: dict[str, Symbol] = {}
        for module in self._graph.modules.values():
            for sym in module.symbols:
                symbol_lookup[sym.qualified_name] = sym

        return sorted(
            (symbol_lookup[pid] for pid in parent_ids if pid in symbol_lookup),
            key=lambda s: (s.qualified_name, s.lineno),
        )

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def imports(self, module: str) -> Sequence[str]:
        """Return raw import text for a module.

        Args:
            module: Module path (file path relative to repository root).

        Returns:
            Sorted list of raw import strings as written in the source.
        """
        mod = self._graph.modules.get(module)
        if mod is None:
            return []
        return sorted(mod.imports)

    # ------------------------------------------------------------------
    # Call relationships (CALLS only)
    # ------------------------------------------------------------------

    def callers(self, symbol: Symbol) -> Sequence[Symbol]:
        """Return direct callers of a symbol via CALLS relationships.

        Only ``CALLS`` relationships are traversed.  Other relationship
        types (``IMPORTS``, ``INHERITS``, ``DEFINES``) are ignored.

        Args:
            symbol: The symbol to find callers for.

        Returns:
            Sorted list of ``Symbol`` instances that call this symbol.
        """
        caller_ids: set[str] = set()
        for module in self._graph.modules.values():
            for rel in module.relationships:
                if rel.type == RelationshipType.CALLS and rel.target == symbol.qualified_name:
                    caller_ids.add(rel.source)

        # Build a lookup of all symbols by qualified_name.
        symbol_lookup: dict[str, Symbol] = {}
        for module in self._graph.modules.values():
            for sym in module.symbols:
                symbol_lookup[sym.qualified_name] = sym

        return sorted(
            (symbol_lookup[cid] for cid in caller_ids if cid in symbol_lookup),
            key=lambda s: (s.qualified_name, s.lineno),
        )

    def callees(self, symbol: Symbol) -> Sequence[Symbol]:
        """Return direct callees of a symbol via CALLS relationships.

        Only ``CALLS`` relationships are traversed.  Other relationship
        types (``IMPORTS``, ``INHERITS``, ``DEFINES``) are ignored.

        Args:
            symbol: The symbol to find callees for.

        Returns:
            Sorted list of ``Symbol`` instances that this symbol calls.
        """
        callee_ids: set[str] = set()
        for module in self._graph.modules.values():
            for rel in module.relationships:
                if rel.type == RelationshipType.CALLS and rel.source == symbol.qualified_name:
                    callee_ids.add(rel.target)

        # Build a lookup of all symbols by qualified_name.
        symbol_lookup: dict[str, Symbol] = {}
        for module in self._graph.modules.values():
            for sym in module.symbols:
                symbol_lookup[sym.qualified_name] = sym

        return sorted(
            (symbol_lookup[cid] for cid in callee_ids if cid in symbol_lookup),
            key=lambda s: (s.qualified_name, s.lineno),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sorted_symbols(self, symbol_type: SymbolType) -> Sequence[Symbol]:
        """Return all symbols of a given type, sorted by qualified_name, lineno.

        Args:
            symbol_type: The symbol type to filter by.

        Returns:
            Sorted list of matching ``Symbol`` instances.
        """
        all_symbols: list[Symbol] = []
        for module in self._graph.modules.values():
            for sym in module.symbols:
                if sym.symbol_type == symbol_type:
                    all_symbols.append(sym)
        return sorted(all_symbols, key=lambda s: (s.qualified_name, s.lineno))
