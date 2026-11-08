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

import ast
import textwrap
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
# Source span helpers
# ---------------------------------------------------------------------------


def _span_start_line(symbol: Symbol) -> int:
    """First line of ``symbol``'s span: earliest decorator, else its ``def``.

    Args:
        symbol: The symbol whose span start is wanted.

    Returns:
        A 1-based line number inside the symbol's module.
    """
    start = symbol.lineno
    if symbol.start_lineno is not None and symbol.start_lineno < start:
        start = symbol.start_lineno
    return start


def _span_lines(source: str, start_line: int, end_line: int) -> str | None:
    """Return lines ``start_line``..``end_line`` of ``source``, inclusive.

    Line endings are kept as they appear in ``source``, so a span carries its
    original indentation and — when the file has one — its trailing newline.
    Line numbers outside the file are clamped to it.

    Args:
        source: The complete text of the symbol's module.
        start_line: 1-based first line of the span.
        end_line: 1-based last line of the span.

    Returns:
        The span text, or ``None`` when ``source`` holds no lines at all.
    """
    lines = source.splitlines(keepends=True)
    if not lines:
        return None
    lo = min(max(start_line, 1), len(lines))
    hi = min(max(end_line, lo), len(lines))
    return "".join(lines[lo - 1 : hi])


def _legacy_docstring(source: str) -> str | None:
    """Return the first triple-quoted string anywhere in ``source``.

    This is the span-less fallback: for a real module it is almost always the
    module docstring rather than the symbol's own docstring.

    Args:
        source: The complete text of the symbol's module.

    Returns:
        The docstring text, or ``None`` when the source has no such string.
    """
    import re

    match = re.search(r'^\s*("""|\'\'\')(.*?)\1', source, re.DOTALL)
    if match:
        return match.group(2).strip() or None
    return None


def _dedent_span(span: str) -> str:
    """Strip a span's own indentation so it can be parsed on its own.

    ``textwrap.dedent`` removes the *common* prefix, which is nothing at all
    when the symbol holds a multi-line string written flush to the left margin
    inside its body.  Falling back to the leading whitespace of the first line
    removes exactly the indentation the definition itself carries.

    Args:
        span: The decorator-inclusive span text.

    Returns:
        The dedented span text.
    """
    dedented = textwrap.dedent(span)
    if dedented != span:
        return dedented
    indent = span[: len(span) - len(span.lstrip())]
    if not indent:
        return span
    return "\n".join(
        line[len(indent) :] if line.startswith(indent) else line
        for line in span.splitlines()
    )


def _definition_node(
    tree: ast.AST, lineno: int
) -> ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None:
    """Return the ``def``/``class`` statement a parsed span is built from.

    Args:
        tree: The parsed span.
        lineno: 1-based line the definition is expected on, relative to the
            first line of the span.

    Returns:
        The node defined on ``lineno``, or — when no definition matches —
        the first definition node found in the span.
    """
    first: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.lineno == lineno:
                return node
            if first is None:
                first = node
    return first


def _span_docstring(source: str, symbol: Symbol) -> str | None:
    """Return the symbol's own docstring, read from its span with ``ast``.

    The span is dedented before it is parsed, because a method's lines all
    carry the indentation of its class.  A module docstring is never used as
    a fallback, and a span that does not parse yields ``None``.

    Args:
        source: The complete text of the symbol's module.
        symbol: A symbol that carries ``end_lineno``.

    Returns:
        The docstring text, or ``None`` when the symbol has no own docstring.
    """
    start_line = _span_start_line(symbol)
    end_line = symbol.end_lineno if symbol.end_lineno is not None else symbol.lineno
    span = _span_lines(source, start_line, end_line)
    if span is None:
        return None
    try:
        tree = ast.parse(_dedent_span(span))
    except (SyntaxError, ValueError):
        return None
    node = _definition_node(tree, symbol.lineno - start_line + 1)
    if node is None:
        return None
    docstring = ast.get_docstring(node, clean=True)
    if not docstring:
        return None
    return docstring.strip() or None


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

    def _find_symbol(self, qualified_name: str) -> tuple[str, Module, Symbol] | None:
        """Return the first module/symbol pair matching ``qualified_name``.

        Every source-aware accessor performs this walk once per call; no
        span index is built or cached.

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            ``(module_path, module, symbol)``, or ``None`` when the symbol
            is not in the index.
        """
        for module_path, module in self.modules.items():
            for sym in module.symbols:
                if sym.qualified_name == qualified_name:
                    return module_path, module, sym
        return None

    def get_symbol_source(self, qualified_name: str) -> str | None:
        """Return the source text for a symbol.

        When the symbol carries ``end_lineno`` — every symbol produced by the
        AST extractor — the result is the symbol's own decorator-inclusive
        span: lines ``start_lineno``..``end_lineno`` of the module source,
        with the original indentation kept and the span's trailing newline
        preserved as it appears in the file.  Nothing from before or after the
        symbol is included.

        When ``end_lineno`` is ``None`` (a hand-built fixture, or any other
        constructor that does not record spans) the legacy fallback applies
        and the complete source of the module is returned, exactly as before
        spans existed.  No AST parsing is performed.

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            The symbol's source text, or ``None`` if the symbol or its
            module is not found, or the module carries no source.
        """
        found = self._find_symbol(qualified_name)
        if found is None:
            return None
        _, module, symbol = found
        if not module.source:
            return None
        if symbol.end_lineno is None:
            return module.source
        return _span_lines(
            module.source, _span_start_line(symbol), symbol.end_lineno
        )

    def get_symbol_signature(self, qualified_name: str) -> str | None:
        """Return the signature line for a symbol.

        When the symbol carries ``end_lineno`` the result is the symbol's own
        ``def``/``class`` line — the line at ``lineno``, stripped.  Decorator
        lines are not part of the signature, and a multi-line ``def`` is
        reported as its first line only; the remainder of it sits inside
        ``get_symbol_source``.

        When ``end_lineno`` is ``None`` the legacy fallback applies: the first
        non-empty, non-comment line of the module's complete source, which for
        a real file is the module header rather than the symbol.

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            The signature line text, stripped of leading/trailing
            whitespace, or ``None`` if not found.
        """
        found = self._find_symbol(qualified_name)
        if found is None:
            return None
        _, module, symbol = found
        if symbol.end_lineno is not None:
            lines = module.source.splitlines()
            if 1 <= symbol.lineno <= len(lines):
                return lines[symbol.lineno - 1].strip() or None
            return None
        if not module.source:
            return None
        for line in module.source.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
        return None

    def get_symbol_docstring(self, qualified_name: str) -> str | None:
        """Return the docstring content for a symbol.

        When the symbol carries ``end_lineno`` its own span is dedented,
        parsed with ``ast``, and read with ``ast.get_docstring``.  A module
        docstring is never a fallback, and a span that does not parse yields
        ``None``.

        When ``end_lineno`` is ``None`` the legacy fallback applies: the first
        triple-quoted string found anywhere in the module's complete source,
        which for a real file is the module docstring.

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            The docstring content, or ``None`` if no docstring found.
        """
        found = self._find_symbol(qualified_name)
        if found is None:
            return None
        _, module, symbol = found
        if not module.source:
            return None
        if symbol.end_lineno is None:
            return _legacy_docstring(module.source)
        return _span_docstring(module.source, symbol)

    def get_symbol_location(
        self, qualified_name: str
    ) -> tuple[str, int, int | None] | None:
        """Return the source location for a symbol.

        When the symbol carries ``end_lineno`` the result is
        ``(module_path, lineno, end_lineno)`` — the symbol's own span.  When
        ``end_lineno`` is ``None`` the legacy fallback applies and ``end_line``
        is the last line of the module's source, as it has always been.

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            A tuple of ``(module_path, start_line, end_line)`` where
            ``start_line`` is the symbol's ``def``/``class`` line and
            ``end_line`` is the last line of the symbol, or of the source in
            the legacy case.  Returns ``None`` if not found.
        """
        found = self._find_symbol(qualified_name)
        if found is None:
            return None
        module_path, module, symbol = found
        if symbol.end_lineno is not None:
            return (module_path, symbol.lineno, symbol.end_lineno)
        if module.source:
            lines = module.source.splitlines()
            return (module_path, symbol.lineno, len(lines) if lines else None)
        return (module_path, symbol.lineno, None)

    def get_symbol_decorators(self, qualified_name: str) -> list[str] | None:
        """Return the decorators for a symbol.

        When the symbol carries ``end_lineno`` the AST-derived
        ``Symbol.decorators`` are returned — the names the extractor read from
        the lines *before* the ``def``.  A symbol with no decorator yields
        ``None``, matching the not-found contract.

        When ``end_lineno`` is ``None`` the legacy fallback applies: the source
        after the ``def`` line is scanned for ``@`` markers, so decorators that
        precede the definition are not collected.

        Args:
            qualified_name: The fully qualified symbol name.

        Returns:
            List of decorator names (without ``@``), or ``None`` if not
            found or the symbol carries none.
        """
        found = self._find_symbol(qualified_name)
        if found is None:
            return None
        _, module, symbol = found
        if symbol.end_lineno is not None:
            return list(symbol.decorators) if symbol.decorators else None
        source = module.source
        if not source:
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
        self,
        qualified_name: str,
        max_tokens: int = 256,
        chars_per_token: float = 4.0,
    ) -> str | None:
        """Return a truncated source excerpt for supporting symbols.

        Args:
            qualified_name: The fully qualified symbol name.
            max_tokens: Maximum token budget for the excerpt.
            chars_per_token: Characters-per-token ratio used to convert the
                token budget into a character cap.  Callers may pass a
                model-calibrated ratio; the platform default is 4.0.

        Returns:
            Truncated source text, or ``None`` if not found.
        """
        source = self.get_symbol_source(qualified_name)
        if source is None:
            return None
        # Estimate tokens (rough: chars_per_token characters per token)
        max_chars = int(max_tokens * chars_per_token)
        if len(source) > max_chars:
            return source[:max_chars] + "\n    # ... (truncated)"
        return source

    def get_symbol_full_context(self, qualified_name: str) -> dict[str, object]:
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
