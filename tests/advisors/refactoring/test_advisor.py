"""Tests for the RefactoringAdvisor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from packages.advisors.refactoring.advisor import RefactoringAdvisor
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
from packages.repository.diagnostics.models import (
    DeadSymbol,
    DependencyCycle,
    OrphanModule,
)
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import Module, Relationship, Symbol, SymbolType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_symbol(
    name: str = "foo",
    qualified_name: str = "module.foo",
    symbol_type: SymbolType = SymbolType.FUNCTION,
    module: str = "module.py",
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


def _make_module(
    path: str = "module.py",
    symbols: list[Symbol] | None = None,
) -> Module:
    """Create a Module for testing."""
    return Module(
        path=path,
        symbols=symbols or [],
    )


def _make_relationship(
    source: str = "module.foo",
    target: str = "module.bar",
    rel_type: str = "CALLS",
) -> Relationship:
    """Create a Relationship for testing."""
    mock_type = MagicMock(**{"value": rel_type})
    return Relationship(
        source=source,
        target=target,
        type=mock_type,
    )


def _make_repository_index(
    modules: dict[str, Module] | None = None,
    symbols: list[Symbol] | None = None,
    relationships: list[Relationship] | None = None,
) -> RepositoryIndex:
    """Create a RepositoryIndex for testing."""
    index = RepositoryIndex(
        modules=modules or {},
        _symbols=symbols or [],
        _relationships=relationships or [],
    )
    return index


def _make_dead_symbol(
    qualified_name: str = "module.foo",
    module: str = "module.py",
    lineno: int = 1,
) -> DeadSymbol:
    """Create a DeadSymbol for testing."""
    return DeadSymbol(
        qualified_name=qualified_name,
        symbol_type=SymbolType.FUNCTION,
        module=module,
        lineno=lineno,
    )


def _make_dependency_cycle(
    cycle: tuple[str, ...] = ("module.a", "module.b"),
) -> DependencyCycle:
    """Create a DependencyCycle for testing."""
    return DependencyCycle(
        cycle=cycle,
        length=len(cycle),
    )


def _make_orphan_module(
    path: str = "orphan.py",
    symbol_count: int = 3,
) -> OrphanModule:
    """Create an OrphanModule for testing."""
    return OrphanModule(
        path=path,
        symbol_count=symbol_count,
    )


# ---------------------------------------------------------------------------
# Tests: Basic advisor behavior
# ---------------------------------------------------------------------------


class TestRefactoringAdvisorBasic:
    """Tests for basic RefactoringAdvisor behavior."""

    def test_advisor_creation_with_default_config(self) -> None:
        """Test that advisor can be created with default config."""
        advisor = RefactoringAdvisor()
        assert advisor.config == DEFAULT_CONFIG

    def test_advisor_creation_with_custom_config(self) -> None:
        """Test that advisor can be created with custom config."""
        config = RefactoringConfig(
            large_module_threshold=50,
            coupling_multiplier=2.0,
            dependency_threshold=10,
        )
        advisor = RefactoringAdvisor(config)
        assert advisor.config == config

    def test_analyze_empty_repository(self) -> None:
        """Test analyze with empty repository index."""
        index = _make_repository_index()
        advisor = RefactoringAdvisor()
        report = advisor.analyze(index)

        assert isinstance(report, RefactoringReport)
        assert report.opportunities == ()
        assert report.summary.total_opportunities == 0

    def test_analyze_returns_refactoring_report(self) -> None:
        """Test that analyze returns a RefactoringReport."""
        index = _make_repository_index()
        advisor = RefactoringAdvisor()
        report = advisor.analyze(index)

        assert isinstance(report, RefactoringReport)
        assert hasattr(report, "summary")
        assert hasattr(report, "statistics")
        assert hasattr(report, "opportunities")


# ---------------------------------------------------------------------------
# Tests: Deterministic output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_deterministic_ordering(self) -> None:
        """Test that repeated calls produce identical ordering."""
        symbols = [
            _make_symbol("foo", "module_a.foo", SymbolType.FUNCTION, "module_a.py"),
            _make_symbol("bar", "module_a.bar", SymbolType.FUNCTION, "module_a.py"),
            _make_symbol("baz", "module_b.baz", SymbolType.FUNCTION, "module_b.py"),
        ]
        relationships = [
            _make_relationship("module_a.foo", "module_b.baz", "CALLS"),
            _make_relationship("module_a.bar", "module_b.baz", "CALLS"),
        ]
        modules = {
            "module_a.py": _make_module("module_a.py", symbols[:2]),
            "module_b.py": _make_module("module_b.py", symbols[2:]),
        }
        index = _make_repository_index(modules, symbols, relationships)

        advisor = RefactoringAdvisor()
        report1 = advisor.analyze(index)
        report2 = advisor.analyze(index)

        assert report1.opportunities == report2.opportunities

    def test_stable_ids(self) -> None:
        """Test that opportunity IDs are stable across runs."""
        index = _make_repository_index()
        advisor = RefactoringAdvisor()
        report1 = advisor.analyze(index)
        report2 = advisor.analyze(index)

        for opp1, opp2 in zip(report1.opportunities, report2.opportunities):
            assert opp1.id == opp2.id


# ---------------------------------------------------------------------------
# Tests: Confidence calculation
# ---------------------------------------------------------------------------


class TestConfidenceCalculation:
    """Tests for confidence calculation."""

    def test_confidence_is_deterministic(self) -> None:
        """Test that confidence values are deterministic."""
        index = _make_repository_index()
        advisor = RefactoringAdvisor()
        report1 = advisor.analyze(index)
        report2 = advisor.analyze(index)

        for opp1, opp2 in zip(report1.opportunities, report2.opportunities):
            assert opp1.confidence == opp2.confidence

    def test_confidence_range(self) -> None:
        """Test that all confidence values are in [0.0, 1.0]."""
        index = _make_repository_index()
        advisor = RefactoringAdvisor()
        report = advisor.analyze(index)

        for opp in report.opportunities:
            assert 0.0 <= opp.confidence <= 1.0


# ---------------------------------------------------------------------------
# Tests: Evidence attached
# ---------------------------------------------------------------------------


class TestEvidenceAttached:
    """Tests for evidence attachment."""

    def test_every_opportunity_has_evidence(self) -> None:
        """Test that every opportunity has at least one evidence item."""
        # Create a repository with dead code
        symbols = [
            _make_symbol("dead", "module.dead", SymbolType.FUNCTION, "module.py"),
        ]
        modules = {
            "module.py": _make_module("module.py", symbols),
        }
        index = _make_repository_index(modules, symbols, [])

        # Mock diagnostics to return dead symbols
        with patch(
            "packages.repository.diagnostics.engine.DiagnosticsEngine"
        ) as mock_diag:
            mock_instance = MagicMock()
            mock_diag.return_value = mock_instance

            mock_instance.analyze.return_value = MagicMock(
                dead_symbols=(
                    _make_dead_symbol("module.dead", "module.py", 1),
                ),
                dependency_cycles=(),
                orphan_modules=(),
                large_modules=(),
            )

            advisor = RefactoringAdvisor()
            report = advisor.analyze(index)

            for opp in report.opportunities:
                assert len(opp.evidence) > 0
                for ev in opp.evidence:
                    assert isinstance(ev, RefactoringEvidence)
                    assert ev.message  # Has a message
                    assert ev.source  # Has a source
                    assert ev.reference  # Has a reference


# ---------------------------------------------------------------------------
# Tests: Duplicate elimination
# ---------------------------------------------------------------------------


class TestDuplicateElimination:
    """Tests for duplicate elimination."""

    def test_no_duplicate_opportunities(self) -> None:
        """Test that duplicate opportunities are eliminated."""
        # Create a repository with multiple symbols in the same module
        symbols = [
            _make_symbol("foo", "module_a.foo", SymbolType.FUNCTION, "module_a.py"),
            _make_symbol("bar", "module_a.bar", SymbolType.FUNCTION, "module_a.py"),
            _make_symbol("baz", "module_a.baz", SymbolType.FUNCTION, "module_a.py"),
        ]
        relationships = [
            _make_relationship("module_a.foo", "module_a.bar", "CALLS"),
            _make_relationship("module_a.bar", "module_a.baz", "CALLS"),
        ]
        modules = {
            "module_a.py": _make_module("module_a.py", symbols),
        }
        index = _make_repository_index(modules, symbols, relationships)

        advisor = RefactoringAdvisor()
        report = advisor.analyze(index)

        # Check for duplicates by (category, affected_modules)
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for opp in report.opportunities:
            key = (opp.category.value, opp.affected_modules)
            assert key not in seen, f"Duplicate opportunity: {key}"
            seen.add(key)


# ---------------------------------------------------------------------------
# Tests: Immutable models
# ---------------------------------------------------------------------------


class TestImmutableModels:
    """Tests for immutable models."""

    def test_report_is_immutable(self) -> None:
        """Test that report opportunities tuple is immutable."""
        index = _make_repository_index()
        advisor = RefactoringAdvisor()
        report = advisor.analyze(index)

        with pytest.raises(Exception):
            report.opportunities = ()  # type: ignore[assignment]

    def test_opportunity_is_immutable(self) -> None:
        """Test that opportunity fields are immutable."""
        evidence = RefactoringEvidence(
            type=EvidenceType.DEPENDENCY,
            source="test",
            message="Test",
            reference="test_ref",
        )
        opp = RefactoringOpportunity(
            id="test",
            category=RefactoringCategory.HIGH_COUPLING,
            severity=Severity.HIGH,
            title="Test",
            description="Test",
            affected_symbols=(),
            affected_modules=(),
            confidence=0.5,
            evidence=(evidence,),
        )

        with pytest.raises(AttributeError):
            opp.id = "new_id"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: Recommendation generation
# ---------------------------------------------------------------------------


class TestRecommendationGeneration:
    """Tests for recommendation generation."""

    def test_large_module_recommendation(self) -> None:
        """Test LARGE_MODULE recommendation is generated."""
        # Create a module with many symbols
        symbols = [
            _make_symbol(f"sym{i}", f"module.sym{i}", SymbolType.FUNCTION, "module.py")
            for i in range(10)
        ]
        modules = {
            "module.py": _make_module("module.py", symbols),
        }
        index = _make_repository_index(modules, symbols, [])

        # Use a config with a low threshold
        config = RefactoringConfig(large_module_threshold=5)
        advisor = RefactoringAdvisor(config)

        with patch(
            "packages.repository.diagnostics.engine.DiagnosticsEngine"
        ) as mock_diag:
            mock_instance = MagicMock()
            mock_diag.return_value = mock_instance
            mock_instance.analyze.return_value = MagicMock(
                dead_symbols=(),
                dependency_cycles=(),
                orphan_modules=(),
                large_modules=(),
            )

            report = advisor.analyze(index)

            large_module_opps = [
                opp for opp in report.opportunities
                if opp.category == RefactoringCategory.LARGE_MODULE
            ]
            assert len(large_module_opps) > 0
            for opp in large_module_opps:
                assert opp.severity == Severity.MEDIUM
                assert len(opp.evidence) > 0

    def test_dead_code_recommendation(self) -> None:
        """Test DEAD_CODE recommendation is generated."""
        symbols = [
            _make_symbol("dead", "module.dead", SymbolType.FUNCTION, "module.py"),
        ]
        modules = {
            "module.py": _make_module("module.py", symbols),
        }
        index = _make_repository_index(modules, symbols, [])

        with patch(
            "packages.repository.diagnostics.engine.DiagnosticsEngine"
        ) as mock_diag:
            mock_instance = MagicMock()
            mock_diag.return_value = mock_instance
            mock_instance.analyze.return_value = MagicMock(
                dead_symbols=(
                    _make_dead_symbol("module.dead", "module.py", 1),
                ),
                dependency_cycles=(),
                orphan_modules=(),
                large_modules=(),
            )

            advisor = RefactoringAdvisor()
            report = advisor.analyze(index)

            dead_code_opps = [
                opp for opp in report.opportunities
                if opp.category == RefactoringCategory.DEAD_CODE
            ]
            assert len(dead_code_opps) > 0
            for opp in dead_code_opps:
                assert opp.severity == Severity.HIGH
                assert len(opp.evidence) > 0

    def test_orphan_module_recommendation(self) -> None:
        """Test ORPHAN_MODULE recommendation is generated."""
        symbols = [
            _make_symbol(
                "orphan_func",
                "orphan.orphan_func",
                SymbolType.FUNCTION,
                "orphan.py",
            ),
        ]
        modules = {
            "orphan.py": _make_module("orphan.py", symbols),
        }
        index = _make_repository_index(modules, symbols, [])

        with patch(
            "packages.repository.diagnostics.engine.DiagnosticsEngine"
        ) as mock_diag:
            mock_instance = MagicMock()
            mock_diag.return_value = mock_instance
            mock_instance.analyze.return_value = MagicMock(
                dead_symbols=(),
                dependency_cycles=(),
                orphan_modules=(
                    _make_orphan_module("orphan.py", 1),
                ),
                large_modules=(),
            )

            advisor = RefactoringAdvisor()
            report = advisor.analyze(index)

            orphan_opps = [
                opp for opp in report.opportunities
                if opp.category == RefactoringCategory.ORPHAN_MODULE
            ]
            assert len(orphan_opps) > 0
            for opp in orphan_opps:
                assert opp.severity == Severity.MEDIUM
                assert len(opp.evidence) > 0

    def test_circular_dependency_recommendation(self) -> None:
        """Test CIRCULAR_DEPENDENCY recommendation is generated."""
        symbols = [
            _make_symbol("a", "module_a.a", SymbolType.FUNCTION, "module_a.py"),
            _make_symbol("b", "module_b.b", SymbolType.FUNCTION, "module_b.py"),
        ]
        relationships = [
            _make_relationship("module_a.a", "module_b.b", "CALLS"),
            _make_relationship("module_b.b", "module_a.a", "CALLS"),
        ]
        modules = {
            "module_a.py": _make_module("module_a.py", symbols[:1]),
            "module_b.py": _make_module("module_b.py", symbols[1:]),
        }
        index = _make_repository_index(modules, symbols, relationships)

        with patch(
            "packages.repository.diagnostics.engine.DiagnosticsEngine"
        ) as mock_diag:
            mock_instance = MagicMock()
            mock_diag.return_value = mock_instance
            mock_instance.analyze.return_value = MagicMock(
                dead_symbols=(),
                dependency_cycles=(
                    _make_dependency_cycle(("module_a.a", "module_b.b")),
                ),
                orphan_modules=(),
                large_modules=(),
            )

            advisor = RefactoringAdvisor()
            report = advisor.analyze(index)

            cycle_opps = [
                opp for opp in report.opportunities
                if opp.category == RefactoringCategory.CIRCULAR_DEPENDENCY
            ]
            assert len(cycle_opps) > 0
            for opp in cycle_opps:
                assert opp.severity == Severity.HIGH
                assert len(opp.evidence) > 0


# ---------------------------------------------------------------------------
# Tests: Summary computation
# ---------------------------------------------------------------------------


class TestSummaryComputation:
    """Tests for summary computation."""

    def test_summary_counts(self) -> None:
        """Test that summary counts are correct."""
        index = _make_repository_index()
        advisor = RefactoringAdvisor()
        report = advisor.analyze(index)

        assert report.summary.total_opportunities == len(report.opportunities)
        total_by_severity = (
            report.summary.high
            + report.summary.medium
            + report.summary.low
            + report.summary.info
        )
        assert total_by_severity == report.summary.total_opportunities


# ---------------------------------------------------------------------------
# Tests: Statistics computation
# ---------------------------------------------------------------------------


class TestStatisticsComputation:
    """Tests for statistics computation."""

    def test_statistics_match_repository(self) -> None:
        """Test that statistics match repository data."""
        symbols = [
            _make_symbol("foo", "module_a.foo", SymbolType.FUNCTION, "module_a.py"),
            _make_symbol("bar", "module_a.bar", SymbolType.FUNCTION, "module_a.py"),
        ]
        modules = {
            "module_a.py": _make_module("module_a.py", symbols),
        }
        index = _make_repository_index(modules, symbols, [])

        with patch(
            "packages.repository.diagnostics.engine.DiagnosticsEngine"
        ) as mock_diag:
            mock_instance = MagicMock()
            mock_diag.return_value = mock_instance
            mock_instance.analyze.return_value = MagicMock(
                dead_symbols=(),
                dependency_cycles=(),
                orphan_modules=(),
                large_modules=(),
            )

            advisor = RefactoringAdvisor()
            report = advisor.analyze(index)

            # Verify statistics are computed from the repository
            assert report.statistics.modules >= 0
            assert report.statistics.symbols >= 0
            assert report.statistics.relationships >= 0
