"""Tests for the ChangeImpactAnalyzer.

Verifies direct impact, transitive impact, deterministic traversal,
ordering, confidence calculation, maximum depth, and immutable models.
"""

from __future__ import annotations

import pytest

from packages.repository.impact.analyzer import ChangeImpactAnalyzer, _compute_confidence
from packages.repository.impact.models import ImpactNode
from packages.repository.index.models import (
    Module,
    Relationship,
    RepositoryIndex,
    RepositoryStatistics,
)
from packages.repository.symbols.models import (
    RelationshipType,
    Symbol,
    SymbolType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_symbol(
    name: str,
    qualified_name: str,
    symbol_type: SymbolType,
    module: str = "main.py",
    lineno: int = 1,
) -> Symbol:
    """Create a Symbol for testing."""
    return Symbol(
        id=qualified_name,
        name=name,
        qualified_name=qualified_name,
        symbol_type=symbol_type,
        module=module,
        lineno=lineno,
    )


def _make_index(
    symbols: list[Symbol],
    relationships: list[Relationship] | None = None,
    modules: dict[str, Module] | None = None,
) -> RepositoryIndex:
    """Create a RepositoryIndex for testing."""
    if modules is None:
        modules = {}
        for sym in symbols:
            if sym.module not in modules:
                modules[sym.module] = Module(path=sym.module)
            modules[sym.module].symbols.append(sym)

    rels = relationships or []

    # Compute statistics
    class_count = sum(1 for s in symbols if s.symbol_type == SymbolType.CLASS)
    function_count = sum(1 for s in symbols if s.symbol_type == SymbolType.FUNCTION)
    method_count = sum(1 for s in symbols if s.symbol_type == SymbolType.METHOD)

    statistics = RepositoryStatistics(
        module_count=len(modules),
        class_count=class_count,
        function_count=function_count,
        method_count=method_count,
        symbol_count=len(symbols),
    )

    return RepositoryIndex(
        modules=modules,
        _symbols=symbols,
        _relationships=rels,
        _statistics=statistics,
    )


# ---------------------------------------------------------------------------
# Direct impact tests
# ---------------------------------------------------------------------------


class TestDirectImpact:
    """Tests for direct (distance=1) impact analysis."""

    def test_single_symbol_no_relationships(self) -> None:
        """A symbol with no relationships should produce empty impact."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        assert report.root_symbols == ("main.App",)
        assert report.impacted_symbols == ()
        assert report.dependency_distance == 0
        assert report.confidence == 0.0

    def test_single_defines_relationship(self) -> None:
        """A DEFINES relationship should show DEPENDENCY impact."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        assert report.root_symbols == ("main.App",)
        assert len(report.impacted_symbols) == 1
        assert report.impacted_symbols[0].qualified_name == "main.App.run"
        assert report.impacted_symbols[0].distance == 1
        assert report.impacted_symbols[0].reason == "DEPENDENCY"

    def test_incoming_defines_relationship(self) -> None:
        """An incoming DEFINES relationship should show DEPENDENCY impact."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App.run"],
            repository_index=index,
        )

        assert report.root_symbols == ("main.App.run",)
        assert len(report.impacted_symbols) == 1
        assert report.impacted_symbols[0].qualified_name == "main.App"
        assert report.impacted_symbols[0].reason == "DEPENDENCY"

    def test_imports_relationship(self) -> None:
        """An IMPORTS relationship should show IMPORT impact."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("Helper", "main.Helper", SymbolType.CLASS, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.Helper",
                type=RelationshipType.IMPORTS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        assert len(report.impacted_symbols) == 1
        assert report.impacted_symbols[0].qualified_name == "main.Helper"
        assert report.impacted_symbols[0].reason == "IMPORT"

    def test_inherits_relationship(self) -> None:
        """An INHERITS relationship should show INHERITANCE impact."""
        symbols = [
            _make_symbol("Base", "main.Base", SymbolType.CLASS, "main.py"),
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.Base",
                type=RelationshipType.INHERITS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        assert len(report.impacted_symbols) == 1
        assert report.impacted_symbols[0].qualified_name == "main.Base"
        assert report.impacted_symbols[0].reason == "INHERITANCE"

    def test_calls_relationship_callee(self) -> None:
        """A CALLS relationship outgoing should show CALLEE impact."""
        symbols = [
            _make_symbol("Caller", "main.caller", SymbolType.FUNCTION, "main.py"),
            _make_symbol("Callee", "main.callee", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.caller",
                target="main.callee",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.caller"],
            repository_index=index,
        )

        callee_nodes = [n for n in report.impacted_symbols if n.reason == "CALLEE"]
        assert len(callee_nodes) == 1
        assert callee_nodes[0].qualified_name == "main.callee"

    def test_calls_relationship_caller(self) -> None:
        """A CALLS relationship incoming should show CALLER impact."""
        symbols = [
            _make_symbol("Caller", "main.caller", SymbolType.FUNCTION, "main.py"),
            _make_symbol("Callee", "main.callee", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.caller",
                target="main.callee",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.callee"],
            repository_index=index,
        )

        caller_nodes = [n for n in report.impacted_symbols if n.reason == "CALLER"]
        assert len(caller_nodes) == 1
        assert caller_nodes[0].qualified_name == "main.caller"

    def test_multiple_relationship_types(self) -> None:
        """Multiple relationship types should all be detected."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("Base", "main.Base", SymbolType.CLASS, "main.py"),
            _make_symbol("Helper", "main.Helper", SymbolType.FUNCTION, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.Base",
                type=RelationshipType.INHERITS,
            ),
            Relationship(
                source="main.App",
                target="main.Helper",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        assert len(report.impacted_symbols) == 3

        reasons = {n.qualified_name: n.reason for n in report.impacted_symbols}
        assert reasons["main.Base"] == "INHERITANCE"
        assert reasons["main.Helper"] == "CALLEE"
        assert reasons["main.App.run"] == "DEPENDENCY"


# ---------------------------------------------------------------------------
# Transitive impact tests
# ---------------------------------------------------------------------------


class TestTransitiveImpact:
    """Tests for transitive (distance > 1) impact analysis."""

    def test_transitive_via_defines(self) -> None:
        """Transitive DEFINES relationships should be detected."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
            _make_symbol("process", "main.App.run.process", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
            Relationship(
                source="main.App.run",
                target="main.App.run.process",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        # Direct: main.App.run (distance 1)
        # Transitive: main.App.run.process (distance 2)
        assert len(report.impacted_symbols) == 2

        direct = [n for n in report.impacted_symbols if n.distance == 1]
        transitive = [n for n in report.impacted_symbols if n.distance == 2]

        assert len(direct) == 1
        assert direct[0].qualified_name == "main.App.run"

        assert len(transitive) == 1
        assert transitive[0].qualified_name == "main.App.run.process"

    def test_transitive_via_calls(self) -> None:
        """Transitive CALLS relationships should be detected."""
        symbols = [
            _make_symbol("A", "main.A", SymbolType.FUNCTION, "main.py"),
            _make_symbol("B", "main.B", SymbolType.FUNCTION, "main.py"),
            _make_symbol("C", "main.C", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.A",
                target="main.B",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="main.B",
                target="main.C",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.A"],
            repository_index=index,
        )

        # Direct: main.B (distance 1, CALLEE)
        # Transitive: main.C (distance 2, CALLEE)
        callees = [n for n in report.impacted_symbols if n.reason == "CALLEE"]
        assert len(callees) == 2

        direct = [n for n in callees if n.distance == 1]
        transitive = [n for n in callees if n.distance == 2]

        assert len(direct) == 1
        assert direct[0].qualified_name == "main.B"

        assert len(transitive) == 1
        assert transitive[0].qualified_name == "main.C"

    def test_bidirectional_relationships(self) -> None:
        """Both directions of a relationship should be detected depending
        on which end is queried as the root symbol."""
        symbols = [
            _make_symbol("A", "main.A", SymbolType.FUNCTION, "main.py"),
            _make_symbol("B", "main.B", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.A",
                target="main.B",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()

        # Query from A: B is the CALLEE (outgoing)
        report_a = analyzer.analyze(
            symbols=["main.A"],
            repository_index=index,
        )
        callees = [n for n in report_a.impacted_symbols if n.reason == "CALLEE"]
        assert len(callees) == 1
        assert callees[0].qualified_name == "main.B"

        # Query from B: A is the CALLER (incoming)
        report_b = analyzer.analyze(
            symbols=["main.B"],
            repository_index=index,
        )
        callers = [n for n in report_b.impacted_symbols if n.reason == "CALLER"]
        assert len(callers) == 1
        assert callers[0].qualified_name == "main.A"

    def test_multiple_root_symbols(self) -> None:
        """Multiple root symbols should all be analyzed."""
        symbols = [
            _make_symbol("A", "main.A", SymbolType.FUNCTION, "main.py"),
            _make_symbol("B", "main.B", SymbolType.FUNCTION, "main.py"),
            _make_symbol("C", "main.C", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.A",
                target="main.C",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="main.B",
                target="main.C",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.A", "main.B"],
            repository_index=index,
        )

        assert report.root_symbols == ("main.A", "main.B")
        callees = [n for n in report.impacted_symbols if n.reason == "CALLEE"]
        assert len(callees) == 1
        assert callees[0].qualified_name == "main.C"

    def test_shortest_path_wins_multi_root(self) -> None:
        """When two roots reach the same node at different distances,
        the shorter distance should be kept."""
        symbols = [
            _make_symbol("A", "main.A", SymbolType.FUNCTION, "main.py"),
            _make_symbol("B", "main.B", SymbolType.FUNCTION, "main.py"),
            _make_symbol("C", "main.C", SymbolType.FUNCTION, "main.py"),
            _make_symbol("D", "main.D", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            # A directly calls C (distance 1 from A)
            Relationship(
                source="main.A",
                target="main.C",
                type=RelationshipType.CALLS,
            ),
            # B calls D, D calls C (distance 2 from B)
            Relationship(
                source="main.B",
                target="main.D",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="main.D",
                target="main.C",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.A", "main.B"],
            repository_index=index,
        )

        c_nodes = [n for n in report.impacted_symbols if n.qualified_name == "main.C"]
        assert len(c_nodes) == 1
        # C should be at distance 1 (direct from A), not distance 2 (via B→D)
        assert c_nodes[0].distance == 1


# ---------------------------------------------------------------------------
# Deterministic traversal tests
# ---------------------------------------------------------------------------


class TestDeterministicTraversal:
    """Tests for deterministic traversal ordering."""

    def test_deterministic_ordering(self) -> None:
        """Results should be sorted by (distance, qualified_name)."""
        symbols = [
            _make_symbol("Z", "main.Z", SymbolType.FUNCTION, "main.py"),
            _make_symbol("A", "main.A", SymbolType.FUNCTION, "main.py"),
            _make_symbol("M", "main.M", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.Root",
                target="main.Z",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="main.Root",
                target="main.A",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="main.Root",
                target="main.M",
                type=RelationshipType.CALLS,
            ),
        ]
        # Add Root symbol
        root_symbols = [
            _make_symbol("Root", "main.Root", SymbolType.FUNCTION, "main.py"),
        ] + symbols
        index = _make_index(root_symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.Root"],
            repository_index=index,
        )

        names = [n.qualified_name for n in report.impacted_symbols]
        assert names == sorted(names)

    def test_repeated_analyses_identical(self) -> None:
        """Repeated analyses should produce identical results."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report1 = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )
        report2 = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        assert report1.impacted_symbols == report2.impacted_symbols
        assert report1.impacted_modules == report2.impacted_modules
        assert report1.dependency_distance == report2.dependency_distance
        assert report1.confidence == report2.confidence


# ---------------------------------------------------------------------------
# Confidence calculation tests
# ---------------------------------------------------------------------------


class TestConfidenceCalculation:
    """Tests for the confidence calculation formula."""

    def test_single_relationship_high_confidence(self) -> None:
        """One relationship should produce high confidence."""
        confidence = _compute_confidence(1, 1)
        assert confidence == 1.0

    def test_two_relationships_distance_1(self) -> None:
        """Two relationships at distance 1 should reduce confidence slightly."""
        confidence = _compute_confidence(2, 1)
        # base_score=1.0, penalty=1+(2-1)*0.1=1.1
        # confidence = 1.0/1.1 ≈ 0.909
        assert 0.90 <= confidence <= 0.92

    def test_many_relationships_distance_1(self) -> None:
        """Many relationships should significantly reduce confidence."""
        confidence = _compute_confidence(20, 1)
        # base_score=1.0, penalty=1+(20-1)*0.1=2.9
        # confidence = 1.0/2.9 ≈ 0.345
        assert 0.33 <= confidence <= 0.36

    def test_distance_2_reduces_confidence(self) -> None:
        """Distance 2 should reduce base_score to 0.8."""
        confidence = _compute_confidence(1, 2)
        # base_score=0.8, penalty=1.0
        # confidence = 0.8/1.0 = 0.8
        assert confidence == 0.8

    def test_distance_3_reduces_confidence(self) -> None:
        """Distance > 2 should reduce base_score to 0.6."""
        confidence = _compute_confidence(1, 3)
        # base_score=0.6, penalty=1.0
        # confidence = 0.6/1.0 = 0.6
        assert confidence == 0.6

    def test_zero_relationships(self) -> None:
        """Zero relationships should produce 0.0 confidence."""
        confidence = _compute_confidence(0, 1)
        # No relationships means no impact, confidence is 0.0
        assert confidence == 0.0

    def test_confidence_clamped_to_1(self) -> None:
        """Confidence should never exceed 1.0."""
        confidence = _compute_confidence(1, 1)
        assert confidence <= 1.0

    def test_confidence_clamped_to_0(self) -> None:
        """Confidence should never go below 0.0."""
        # Many relationships with deep distance
        confidence = _compute_confidence(100, 5)
        assert confidence >= 0.0


# ---------------------------------------------------------------------------
# Maximum depth tests
# ---------------------------------------------------------------------------


class TestMaxDepth:
    """Tests for maximum depth configuration."""

    def test_depth_1_limits_to_direct(self) -> None:
        """max_depth=1 should only include direct relationships."""
        symbols = [
            _make_symbol("A", "main.A", SymbolType.FUNCTION, "main.py"),
            _make_symbol("B", "main.B", SymbolType.FUNCTION, "main.py"),
            _make_symbol("C", "main.C", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.A",
                target="main.B",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="main.B",
                target="main.C",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer(max_depth=1)
        report = analyzer.analyze(
            symbols=["main.A"],
            repository_index=index,
        )

        # Only main.B should be at distance 1
        callees = [n for n in report.impacted_symbols if n.reason == "CALLEE"]
        assert len(callees) == 1
        assert callees[0].qualified_name == "main.B"
        assert callees[0].distance == 1

        # main.C should NOT appear (it's at distance 2)
        c_nodes = [n for n in report.impacted_symbols if n.qualified_name == "main.C"]
        assert len(c_nodes) == 0

    def test_depth_2_includes_transitive(self) -> None:
        """max_depth=2 should include transitive relationships."""
        symbols = [
            _make_symbol("A", "main.A", SymbolType.FUNCTION, "main.py"),
            _make_symbol("B", "main.B", SymbolType.FUNCTION, "main.py"),
            _make_symbol("C", "main.C", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.A",
                target="main.B",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="main.B",
                target="main.C",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer(max_depth=2)
        report = analyzer.analyze(
            symbols=["main.A"],
            repository_index=index,
        )

        callees = [n for n in report.impacted_symbols if n.reason == "CALLEE"]
        assert len(callees) == 2

        names_by_distance = {}
        for n in callees:
            names_by_distance[n.distance] = n.qualified_name

        assert names_by_distance[1] == "main.B"
        assert names_by_distance[2] == "main.C"

    def test_invalid_depth_raises(self) -> None:
        """Invalid max_depth should raise ValueError."""
        with pytest.raises(ValueError, match="max_depth must be"):
            ChangeImpactAnalyzer(max_depth=0)

        with pytest.raises(ValueError, match="max_depth must be"):
            ChangeImpactAnalyzer(max_depth=-5)

    def test_unlimited_depth(self) -> None:
        """max_depth=-1 should allow unlimited traversal."""
        symbols = [
            _make_symbol("A", "main.A", SymbolType.FUNCTION, "main.py"),
            _make_symbol("B", "main.B", SymbolType.FUNCTION, "main.py"),
            _make_symbol("C", "main.C", SymbolType.FUNCTION, "main.py"),
            _make_symbol("D", "main.D", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.A",
                target="main.B",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="main.B",
                target="main.C",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="main.C",
                target="main.D",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer(max_depth=-1)
        report = analyzer.analyze(
            symbols=["main.A"],
            repository_index=index,
        )

        callees = [n for n in report.impacted_symbols if n.reason == "CALLEE"]
        assert len(callees) == 3

    def test_default_depth_is_2(self) -> None:
        """Default max_depth should be 2."""
        analyzer = ChangeImpactAnalyzer()
        assert analyzer.max_depth == 2


# ---------------------------------------------------------------------------
# Empty / edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_symbols_raises(self) -> None:
        """Empty symbols list should raise ValueError."""
        analyzer = ChangeImpactAnalyzer()
        index = _make_index([])

        with pytest.raises(ValueError, match="symbols must contain"):
            analyzer.analyze(
                symbols=[],
                repository_index=index,
            )

    def test_unknown_symbol_returns_empty(self) -> None:
        """Unknown symbol should return empty report."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.Unknown"],
            repository_index=index,
        )

        assert report.root_symbols == ("main.Unknown",)
        assert report.impacted_symbols == ()
        assert report.dependency_distance == 0
        assert report.confidence == 0.0

    def test_no_impacted_modules(self) -> None:
        """Report with no impacted modules should have empty tuple."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        assert report.impacted_modules == ()

    def test_impacted_modules_from_relationships(self) -> None:
        """Impacted modules should include modules of impacted symbols."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("Helper", "main.Helper", SymbolType.FUNCTION, "helper.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.Helper",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        assert "helper.py" in report.impacted_modules

    def test_duplicate_relationships_deduplicated(self) -> None:
        """Duplicate relationships should be deduplicated."""
        symbols = [
            _make_symbol("A", "main.A", SymbolType.FUNCTION, "main.py"),
            _make_symbol("B", "main.B", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.A",
                target="main.B",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="main.A",
                target="main.B",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.A"],
            repository_index=index,
        )

        # Should only appear once
        b_nodes = [n for n in report.impacted_symbols if n.qualified_name == "main.B"]
        assert len(b_nodes) == 1


# ---------------------------------------------------------------------------
# Test discovery tests
# ---------------------------------------------------------------------------


class TestTestDiscovery:
    """Tests for test module discovery."""

    def test_discovers_test_modules(self) -> None:
        """Test modules linked to impacted symbols should be discovered."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol(
                "test_app",
                "tests.test_app.test_app",
                SymbolType.FUNCTION,
                "tests/test_app.py",
            ),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="tests.test_app.test_app",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        assert "tests/test_app.py" in report.impacted_tests

    def test_no_test_relationships(self) -> None:
        """No test relationships should return empty test list."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        assert report.impacted_tests == ()


# ---------------------------------------------------------------------------
# Immutable report tests
# ---------------------------------------------------------------------------


class TestImmutableReport:
    """Tests for report immutability."""

    def test_report_is_frozen(self) -> None:
        """ImpactReport should be immutable."""
        from dataclasses import FrozenInstanceError

        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["main.App"],
            repository_index=index,
        )

        with pytest.raises(FrozenInstanceError):
            report.root_symbols = ()  # type: ignore[misc]

    def test_impacted_nodes_are_frozen(self) -> None:
        """ImpactNode instances should be immutable."""
        from dataclasses import FrozenInstanceError

        node = ImpactNode(
            qualified_name="main.App",
            module="main.py",
            distance=1,
            reason="CALLEE",
        )

        with pytest.raises(FrozenInstanceError):
            node.qualified_name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration test for the full analysis pipeline."""

    def test_full_analysis_pipeline(self) -> None:
        """Test the complete analysis with multiple relationship types."""
        symbols = [
            _make_symbol("Gateway", "gateway.Gateway", SymbolType.CLASS, "gateway.py"),
            _make_symbol("Handler", "gateway.Handler", SymbolType.CLASS, "gateway.py"),
            _make_symbol("Process", "gateway.Handler.process", SymbolType.METHOD, "gateway.py"),
            _make_symbol("Logger", "logger.Logger", SymbolType.CLASS, "logger.py"),
            _make_symbol("log", "logger.Logger.log", SymbolType.METHOD, "logger.py"),
            _make_symbol(
                "test_gateway",
                "tests.test_gateway.test_gateway",
                SymbolType.FUNCTION,
                "tests/test_gateway.py",
            ),
        ]

        relationships = [
            # Gateway defines Handler
            Relationship(
                source="gateway.Gateway",
                target="gateway.Handler",
                type=RelationshipType.DEFINES,
            ),
            # Gateway defines process method
            Relationship(
                source="gateway.Handler",
                target="gateway.Handler.process",
                type=RelationshipType.DEFINES,
            ),
            # Gateway calls Logger
            Relationship(
                source="gateway.Gateway",
                target="logger.Logger",
                type=RelationshipType.CALLS,
            ),
            # Handler.process calls Logger.log
            Relationship(
                source="gateway.Handler.process",
                target="logger.Logger.log",
                type=RelationshipType.CALLS,
            ),
            # Test calls Gateway
            Relationship(
                source="tests.test_gateway.test_gateway",
                target="gateway.Gateway",
                type=RelationshipType.CALLS,
            ),
        ]

        index = _make_index(symbols, relationships)

        analyzer = ChangeImpactAnalyzer()
        report = analyzer.analyze(
            symbols=["gateway.Gateway"],
            repository_index=index,
        )

        # Verify root symbols
        assert report.root_symbols == ("gateway.Gateway",)

        # Verify impacted symbols
        assert len(report.impacted_symbols) > 0

        # Verify all are at distance 1 or 2
        for node in report.impacted_symbols:
            assert node.distance in (1, 2)

        # Verify impacted modules
        assert "gateway.py" in report.impacted_modules
        assert "logger.py" in report.impacted_modules

        # Verify confidence is reasonable
        assert 0.0 <= report.confidence <= 1.0

        # Verify dependency distance
        assert report.dependency_distance >= 1
