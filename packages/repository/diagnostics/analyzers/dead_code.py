"""Dead code analyzer.

Detects functions and methods with no callers using only the
RepositoryIndex relationships — no AST re-parsing.

Entry points are excluded:
- Functions named ``main`` at module scope (no directory component).
- Future versions may introduce configurable EntryPointExtractors.

Abstract methods are excluded:
- Only methods explicitly decorated with ``@abstractmethod`` or
  ``@abc.abstractmethod`` are excluded.
- No naming conventions or inheritance inference.

Algorithm: O(V + E) where V is the number of symbols and E is the
number of CALLS relationships.  A BFS from all callers marks
every reachable symbol.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.models import DeadSymbol, RepositoryDiagnostics
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import RelationshipType, SymbolType

if TYPE_CHECKING:
    pass


# Exact decorator strings that mark a method as abstract.
_ABSTRACT_DECORATORS: frozenset[str] = frozenset({
    "abstractmethod",
    "abc.abstractmethod",
})


class DeadCodeAnalyzer(DiagnosticsAnalyzer):
    """Detects functions and methods with no callers.

    Uses only RepositoryIndex relationships to build a call graph and
    identify symbols that are never invoked.

    Complexity: O(V + E) — single BFS traversal over the call graph.
    """

    @property
    def name(self) -> str:
        """Analyzer name."""
        return "dead_code"

    def analyze(
        self,
        repository_index: RepositoryIndex,
    ) -> RepositoryDiagnostics:
        """Run dead code analysis.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A ``RepositoryDiagnostics`` with dead code findings.
        """
        # Build a set of all callers (sources of CALLS relationships).
        callers: set[str] = set()
        calls_edges: list[tuple[str, str]] = []

        for rel in repository_index.relationships():
            if rel.type == RelationshipType.CALLS:
                callers.add(rel.source)
                calls_edges.append((rel.source, rel.target))

        # Build a set of all symbols that are called (directly or transitively).
        # BFS from all callers.
        reachable: set[str] = set(callers)
        adjacency: dict[str, list[str]] = {}
        for src, tgt in calls_edges:
            if src not in adjacency:
                adjacency[src] = []
            adjacency[src].append(tgt)

        queue: deque[str] = deque(sorted(callers))
        while queue:
            current = queue.popleft()
            for neighbor in sorted(adjacency.get(current, [])):
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    queue.append(neighbor)

        # Build a set of entry points: functions named ``main`` at module
        # scope (no directory component in the module path).
        entry_points: set[str] = set()
        for sym in repository_index.symbols():
            if sym.symbol_type == SymbolType.FUNCTION and sym.name == "main":
                # Module scope: no directory component in path.
                module_path = sym.module
                if "/" not in module_path and "\\" not in module_path:
                    entry_points.add(sym.qualified_name)

        # Build a set of abstract methods to exclude.
        abstract_methods: set[str] = set()
        for sym in repository_index.symbols():
            if sym.symbol_type == SymbolType.METHOD:
                for dec in sym.decorators:
                    if dec in _ABSTRACT_DECORATORS:
                        abstract_methods.add(sym.qualified_name)
                        break

        # Collect dead symbols.
        dead_symbols: list[DeadSymbol] = []
        seen: set[str] = set()

        for sym in repository_index.symbols():
            if sym.symbol_type not in (SymbolType.FUNCTION, SymbolType.METHOD):
                continue

            qname = sym.qualified_name

            # Skip if already seen (dedup)
            if qname in seen:
                continue
            seen.add(qname)

            # Skip entry points
            if qname in entry_points:
                continue

            # Skip abstract methods
            if qname in abstract_methods:
                continue

            # Skip if called (reachable)
            if qname in reachable:
                continue

            dead_symbols.append(DeadSymbol(
                qualified_name=qname,
                symbol_type=sym.symbol_type,
                module=sym.module,
                lineno=sym.lineno,
            ))

        return RepositoryDiagnostics(
            dead_symbols=tuple(dead_symbols),
        )
