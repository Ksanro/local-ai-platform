"""Repository Index Builder.

Constructs an immutable :class:`RepositoryIndex` from a filesystem path
by delegating symbol extraction to the existing :class:`PythonAstExtractor`.

The builder is stateless between calls — repeated builds of the same path
produce identical :class:`RepositoryIndex` instances (deterministic).
"""

from __future__ import annotations

from pathlib import Path

from packages.repository.index.models import (
    RepositoryIndex,
    RepositoryStatistics,
)
from packages.repository.relationships.registry import RelationshipRegistry
from packages.repository.symbols.extractor import SymbolExtractor
from packages.repository.symbols.models import (
    Module,
    Relationship,
    Symbol,
    SymbolGraph,
    SymbolType,
)
from packages.repository.symbols.python_ast import PythonAstExtractor


class RepositoryIndexBuilder:
    """Builds a :class:`RepositoryIndex` from a filesystem path.

    Attributes:
        _extractor: The symbol extractor used to parse source files.
            Defaults to :class:`PythonAstExtractor` when not specified.
        _registry: The relationship extractor registry.  Defaults to a
            :class:`RelationshipRegistry` with :class:`CallExtractor`
            registered when not specified.
    """

    def __init__(
        self,
        extractor: SymbolExtractor | None = None,
        registry: RelationshipRegistry | None = None,
    ) -> None:
        """Initialise the builder.

        Args:
            extractor: A ``SymbolExtractor`` implementation.  Defaults to
                ``PythonAstExtractor`` when ``None``.
            registry: A ``RelationshipRegistry``.  Defaults to a fresh
                registry with ``CallExtractor`` registered when ``None``.
        """
        self._extractor = extractor or PythonAstExtractor()
        if registry is None:
            # Lazy import to avoid circular imports at module load time.
            from packages.repository.relationships.call_extractor import (
                CallExtractor,
            )

            registry = RelationshipRegistry()
            registry.register(CallExtractor())
        self._registry = registry

    def build(self, path: Path) -> RepositoryIndex:
        """Build a :class:`RepositoryIndex` from the given path.

        Extracts symbols from all Python source files under ``path``,
        runs all registered relationship extractors, computes aggregate
        statistics, and returns a fully constructed :class:`RepositoryIndex`.

        Args:
            path: Path to a Python source file or directory.

        Returns:
            A :class:`RepositoryIndex` containing all discovered modules,
            symbols, relationships, and statistics.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            NotADirectoryError: If ``path`` is not a directory.
        """
        graph = self._extractor.extract(path)

        modules: dict[str, Module] = {}
        symbols: list[Symbol] = []
        relationships: list[Relationship] = []

        for module_path, module in graph.modules.items():
            modules[module_path] = module
            symbols.extend(module.symbols)
            relationships.extend(module.relationships)

        # Run relationship extractors.
        empty_stats = RepositoryStatistics(
            module_count=0,
            class_count=0,
            function_count=0,
            method_count=0,
            symbol_count=0,
        )
        relationship_rels = self._registry.extract(
            RepositoryIndex(
                modules=modules,
                _symbols=symbols,
                _relationships=relationships,
                _statistics=empty_stats,
            )
        )
        relationships.extend(relationship_rels)

        statistics = self._compute_statistics(symbols, len(modules))

        return RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=relationships,
            _statistics=statistics,
        )

    @staticmethod
    def _compute_statistics(
        symbols: list[Symbol],
        module_count: int,
    ) -> RepositoryStatistics:
        """Compute aggregate statistics from a list of symbols.

        Args:
            symbols: All symbols across all modules.
            module_count: Number of modules in the repository.

        Returns:
            A :class:`RepositoryStatistics` dataclass with computed values.
        """
        class_count = sum(1 for s in symbols if s.symbol_type == SymbolType.CLASS)
        function_count = sum(
            1 for s in symbols if s.symbol_type == SymbolType.FUNCTION
        )
        method_count = sum(1 for s in symbols if s.symbol_type == SymbolType.METHOD)

        return RepositoryStatistics(
            module_count=module_count,
            class_count=class_count,
            function_count=function_count,
            method_count=method_count,
            symbol_count=len(symbols),
        )
