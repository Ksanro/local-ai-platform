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

    # ------------------------------------------------------------------
    # Source-aware access (Context Quality v2)
    # ------------------------------------------------------------------

    def get_symbol_source(self, qualified_name: str) -> str | None:
        """Return the complete source body for a symbol.

        Reads from the stored ``Module.source`` field.  No AST parsing
        is performed.

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            The complete source text of the symbol's module, or ``None``
            if the symbol or its module is not found.
        """
        for module in self.modules.values():
            for sym in module.symbols:
                if sym.qualified_name == qualified_name:
                    return module.source if module.source else None
        return None

    def get_symbol_signature(self, qualified_name: str) -> str | None:
        """Return the signature line for a symbol.

        Returns the first non-empty line of the symbol's source (typically
        the ``def`` or ``class`` declaration).

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            The signature line text, stripped of leading/trailing
            whitespace, or ``None`` if not found.
        """
        source = self.get_symbol_source(qualified_name)
        if source is None:
            return None
        for line in source.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
        return None

    def get_symbol_docstring(self, qualified_name: str) -> str | None:
        """Return the docstring content for a symbol.

        Extracts the first triple-quoted string from the symbol's source.

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            The docstring content, or ``None`` if no docstring found.
        """
        source = self.get_symbol_source(qualified_name)
        if source is None:
            return None
        import re
        # Match triple-quoted docstrings (single or double quotes)
        pattern = r'(?<!\w)r?("""|\'\'\'|\3)(.*?)\3'
        match = re.search(r'^\s*("""|\'\'\')(.*?)\1', source, re.DOTALL)
        if match:
            return match.group(2).strip() or None
        return None

    def get_symbol_location(
        self, qualified_name: str
    ) -> tuple[str, int, int | None] | None:
        """Return the source location for a symbol.

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            A tuple of ``(module_path, start_line, end_line)`` where
            ``end_line`` is the last line of the source or ``None`` if
            the end cannot be determined.  Returns ``None`` if not found.
        """
        for module_path, module in self.modules.items():
            for sym in module.symbols:
                if sym.qualified_name == qualified_name:
                    source = module.source
                    if source:
                        lines = source.splitlines()
                        end_line = len(lines) if lines else None
                        return (module_path, sym.lineno, end_line)
                    return (module_path, sym.lineno, None)
        return None

    def get_symbol_decorators(self, qualified_name: str) -> list[str] | None:
        """Return the decorators for a symbol.

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            List of decorator names (without ``@``), or ``None`` if not
            found.
        """
        source = self.get_symbol_source(qualified_name)
        if source is None:
            return None
        # Extract the short name from qualified_name (last segment)
        short_name = qualified_name.rsplit(".", 1)[-1]
        # Find the symbol definition and collect preceding decorators
        lines = source.splitlines()
        in_symbol = False
        decorators: list[str] = []
        for line in lines:
            stripped = line.strip()
            # Check if this is the symbol's definition line
            if not in_symbol:
                if f"def {short_name}" in stripped or f"class {short_name}" in stripped:
                    in_symbol = True
            else:
                if stripped.startswith("@"):
                    decorators.append(stripped[1:].split("(")[0].split()[0])
        return decorators if decorators else None

    def get_symbol_source_excerpts(
        self, qualified_name: str, max_tokens: int = 256
    ) -> str | None:
        """Return a truncated source excerpt for supporting symbols.

        Args:
            qualified_name: The fully qualified symbol name.
            max_tokens: Maximum token budget for the excerpt.

        Returns:
            Truncated source text, or ``None`` if not found.
        """
        source = self.get_symbol_source(qualified_name)
        if source is None:
            return None
        # Estimate tokens (rough: 4 chars per token)
        max_chars = max_tokens * 4
        if len(source) > max_chars:
            return source[:max_chars] + "\n    # ... (truncated)"
        return source

    def get_symbol_full_context(
        self, qualified_name: str
    ) -> dict[str, str | int | int | None | list[str] | None]:
        """Return complete source context for a symbol.

        This is the consolidated accessor used by the Context Builder
        to enrich candidates with engineering-grade information.

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            Dictionary with keys: ``signature``, ``docstring``,
            ``decorators``, ``location``, ``source``.
        """
        signature = self.get_symbol_signature(qualified_name)
        docstring = self.get_symbol_docstring(qualified_name)
        decorators = self.get_symbol_decorators(qualified_name)
        location = self.get_symbol_location(qualified_name)
        source = self.get_symbol_source(qualified_name)

        return {
            "signature": signature or "",
            "docstring": docstring or "",
            "decorators": decorators or [],
            "location": location,
            "source": source or "",
        }
