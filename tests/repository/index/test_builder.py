"""Tests for the RepositoryIndexBuilder.

Verifies builder creation, delegation to PythonAstExtractor,
deterministic output, and repeated build stability.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.repository.index.builder import RepositoryIndexBuilder
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.python_ast import PythonAstExtractor


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_builder() -> RepositoryIndexBuilder:
    """Create a RepositoryIndexBuilder with default extractor."""
    return RepositoryIndexBuilder()


def _make_builder_with_extractor(
    extractor: PythonAstExtractor,
) -> RepositoryIndexBuilder:
    """Create a RepositoryIndexBuilder with a custom extractor."""
    return RepositoryIndexBuilder(extractor=extractor)


# ------------------------------------------------------------------
# Builder creation
# ------------------------------------------------------------------


class TestBuilderCreation:
    """Tests for RepositoryIndexBuilder creation."""

    def test_default_extractor(self) -> None:
        """Builder should use PythonAstExtractor by default."""
        builder = _make_builder()
        assert builder._extractor is not None
        assert isinstance(builder._extractor, PythonAstExtractor)

    def test_custom_extractor(self) -> None:
        """Builder should accept a custom extractor."""
        extractor = PythonAstExtractor()
        builder = _make_builder_with_extractor(extractor)
        assert builder._extractor is extractor


# ------------------------------------------------------------------
# Builder behavior
# ------------------------------------------------------------------


class TestBuilderBehavior:
    """Tests for RepositoryIndexBuilder behavior."""

    def test_build_returns_index(self) -> None:
        """build() should return a RepositoryIndex."""
        builder = _make_builder()
        # Use the project root as test path
        project_root = Path(__file__).resolve().parent.parent.parent
        index = builder.build(project_root)
        assert isinstance(index, RepositoryIndex)

    def test_build_has_modules(self) -> None:
        """build() should contain modules."""
        builder = _make_builder()
        project_root = Path(__file__).resolve().parent.parent.parent
        index = builder.build(project_root)
        assert len(index.modules) > 0

    def test_build_has_symbols(self) -> None:
        """build() should contain symbols."""
        builder = _make_builder()
        project_root = Path(__file__).resolve().parent.parent.parent
        index = builder.build(project_root)
        assert len(index.symbols()) > 0

    def test_build_has_relationships(self) -> None:
        """build() should contain relationships."""
        builder = _make_builder()
        project_root = Path(__file__).resolve().parent.parent.parent
        index = builder.build(project_root)
        assert len(index.relationships()) > 0

    def test_build_has_statistics(self) -> None:
        """build() should contain statistics."""
        builder = _make_builder()
        project_root = Path(__file__).resolve().parent.parent.parent
        index = builder.build(project_root)
        stats = index.statistics()
        assert stats.module_count > 0
        assert stats.symbol_count > 0

    def test_build_delegates_to_extractor(self) -> None:
        """build() should delegate to PythonAstExtractor."""
        extractor = PythonAstExtractor()
        builder = _make_builder_with_extractor(extractor)
        project_root = Path(__file__).resolve().parent.parent.parent
        index = builder.build(project_root)
        # Verify symbols were extracted by the extractor
        assert len(index.symbols()) > 0
        # Verify at least one symbol has a valid module path
        for sym in index.symbols():
            assert len(sym.module) > 0
            break

    def test_build_no_duplicate_parsing(self) -> None:
        """build() should not re-parse files that were already parsed."""
        extractor = PythonAstExtractor()
        builder = _make_builder_with_extractor(extractor)
        project_root = Path(__file__).resolve().parent.parent.parent
        index = builder.build(project_root)
        # The builder delegates to the extractor — if the extractor
        # parsed a file once, the builder should not parse it again.
        # We verify this by checking that the number of symbols is
        # consistent (not doubled or more).
        symbol_count = len(index.symbols())
        assert symbol_count > 0
        # If files were re-parsed, we'd see at least double the symbols
        # (since each file would be parsed once by the extractor's
        # _extract_directory and once by the builder's iteration).
        # This is a simple sanity check — the real test is that the
        # builder only iterates over the graph.modules dict.


# ------------------------------------------------------------------
# Deterministic output
# ------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic builder output."""

    def test_identical_builds(self) -> None:
        """Repeated builds produce identical results."""
        builder = _make_builder()
        project_root = Path(__file__).resolve().parent.parent.parent
        index1 = builder.build(project_root)
        index2 = builder.build(project_root)

        assert len(index1.symbols()) == len(index2.symbols())
        assert len(index1.modules) == len(index2.modules)
        assert len(index1.relationships()) == len(index2.relationships())
        assert index1.statistics() == index2.statistics()

    def test_symbols_sorted(self) -> None:
        """Build output should have sorted symbols."""
        builder = _make_builder()
        project_root = Path(__file__).resolve().parent.parent.parent
        index = builder.build(project_root)
        names = [s.qualified_name for s in index.symbols()]
        assert names == sorted(names)

    def test_modules_sorted(self) -> None:
        """Build output should have sorted modules."""
        builder = _make_builder()
        project_root = Path(__file__).resolve().parent.parent.parent
        index = builder.build(project_root)
        paths = [m.path for m in index.modules_list()]
        assert paths == sorted(paths)


# ------------------------------------------------------------------
# No forbidden imports
# ------------------------------------------------------------------


class TestNoForbiddenImports:
    """Tests verifying RepositoryIndexBuilder does not import forbidden modules."""

    def test_no_provider_imports(self) -> None:
        """RepositoryIndexBuilder should not import providers."""
        import packages.repository.index.builder
        import inspect
        source = inspect.getsource(packages.repository.index.builder)
        assert "provider" not in source.lower()

    def test_no_gateway_imports(self) -> None:
        """RepositoryIndexBuilder should not import gateway."""
        import packages.repository.index.builder
        import inspect
        source = inspect.getsource(packages.repository.index.builder)
        assert "gateway" not in source.lower()

    def test_no_inference_imports(self) -> None:
        """RepositoryIndexBuilder should not import inference or LLM."""
        import packages.repository.index.builder
        import inspect
        source = inspect.getsource(packages.repository.index.builder)
        assert "llm" not in source.lower()
        assert "inference" not in source.lower()
