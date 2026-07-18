"""Tests for the refactoring models."""

from __future__ import annotations

import enum

import pytest

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


class TestEvidenceType:
    """Tests for EvidenceType enum."""

    def test_evidence_type_has_all_values(self) -> None:
        assert hasattr(EvidenceType, "DEPENDENCY")
        assert hasattr(EvidenceType, "STATISTIC")
        assert hasattr(EvidenceType, "DIAGNOSTIC")
        assert hasattr(EvidenceType, "ARCHITECTURE")

    def test_evidence_type_values(self) -> None:
        assert EvidenceType.DEPENDENCY.value == "dependency"
        assert EvidenceType.STATISTIC.value == "statistic"
        assert EvidenceType.DIAGNOSTIC.value == "diagnostic"
        assert EvidenceType.ARCHITECTURE.value == "architecture"


class TestRefactoringCategory:
    """Tests for RefactoringCategory enum."""

    def test_category_has_all_values(self) -> None:
        assert hasattr(RefactoringCategory, "HIGH_COUPLING")
        assert hasattr(RefactoringCategory, "LARGE_MODULE")
        assert hasattr(RefactoringCategory, "DEAD_CODE")
        assert hasattr(RefactoringCategory, "ORPHAN_MODULE")
        assert hasattr(RefactoringCategory, "CIRCULAR_DEPENDENCY")
        assert hasattr(RefactoringCategory, "EXCESSIVE_DEPENDENCIES")

    def test_category_values(self) -> None:
        assert RefactoringCategory.HIGH_COUPLING.value == "HIGH_COUPLING"
        assert RefactoringCategory.LARGE_MODULE.value == "LARGE_MODULE"
        assert RefactoringCategory.DEAD_CODE.value == "DEAD_CODE"
        assert RefactoringCategory.ORPHAN_MODULE.value == "ORPHAN_MODULE"
        assert RefactoringCategory.CIRCULAR_DEPENDENCY.value == "CIRCULAR_DEPENDENCY"
        assert RefactoringCategory.EXCESSIVE_DEPENDENCIES.value == "EXCESSIVE_DEPENDENCIES"


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_has_all_values(self) -> None:
        assert hasattr(Severity, "INFO")
        assert hasattr(Severity, "LOW")
        assert hasattr(Severity, "MEDIUM")
        assert hasattr(Severity, "HIGH")

    def test_severity_values(self) -> None:
        assert Severity.INFO.value == "info"
        assert Severity.LOW.value == "low"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.HIGH.value == "high"


class TestRefactoringEvidence:
    """Tests for RefactoringEvidence immutable dataclass."""

    def test_evidence_creation(self) -> None:
        evidence = RefactoringEvidence(
            type=EvidenceType.DEPENDENCY,
            source="diagnostics",
            message="Test message",
            reference="test_ref",
        )
        assert evidence.type == EvidenceType.DEPENDENCY
        assert evidence.source == "diagnostics"
        assert evidence.message == "Test message"
        assert evidence.reference == "test_ref"

    def test_evidence_is_immutable(self) -> None:
        evidence = RefactoringEvidence(
            type=EvidenceType.STATISTIC,
            source="repository",
            message="Test message",
            reference="test_ref",
        )
        with pytest.raises(AttributeError):
            evidence.type = EvidenceType.DEPENDENCY  # type: ignore[misc]

    def test_evidence_fields_are_immutable(self) -> None:
        evidence = RefactoringEvidence(
            type=EvidenceType.STATISTIC,
            source="repository",
            message="Test message",
            reference="test_ref",
        )
        with pytest.raises(AttributeError):
            evidence.type = EvidenceType.DEPENDENCY  # pyright: ignore[reportAttributeAccessIssue]


class TestRefactoringSummary:
    """Tests for RefactoringSummary immutable dataclass."""

    def test_summary_creation(self) -> None:
        summary = RefactoringSummary(
            total_opportunities=5,
            high=2,
            medium=2,
            low=1,
            info=0,
        )
        assert summary.total_opportunities == 5
        assert summary.high == 2
        assert summary.medium == 2
        assert summary.low == 1
        assert summary.info == 0

    def test_summary_is_immutable(self) -> None:
        summary = RefactoringSummary(
            total_opportunities=5,
            high=2,
            medium=2,
            low=1,
            info=0,
        )
        with pytest.raises(AttributeError):
            summary.total_opportunities = 10  # type: ignore[misc]


class TestRepositoryStatistics:
    """Tests for RepositoryStatistics immutable dataclass."""

    def test_statistics_creation(self) -> None:
        stats = RepositoryStatistics(
            modules=10,
            symbols=100,
            relationships=50,
            diagnostics=5,
        )
        assert stats.modules == 10
        assert stats.symbols == 100
        assert stats.relationships == 50
        assert stats.diagnostics == 5

    def test_statistics_is_immutable(self) -> None:
        stats = RepositoryStatistics(
            modules=10,
            symbols=100,
            relationships=50,
            diagnostics=5,
        )
        with pytest.raises(AttributeError):
            stats.modules = 20  # type: ignore[misc]


class TestRefactoringOpportunity:
    """Tests for RefactoringOpportunity immutable dataclass."""

    def test_opportunity_creation(self) -> None:
        evidence = RefactoringEvidence(
            type=EvidenceType.DEPENDENCY,
            source="diagnostics",
            message="Test evidence",
            reference="test_ref",
        )
        opportunity = RefactoringOpportunity(
            id="HIGH_COUPLING:module_a",
            category=RefactoringCategory.HIGH_COUPLING,
            severity=Severity.HIGH,
            title="High coupling",
            description="Module has high coupling",
            affected_symbols=("sym1", "sym2"),
            affected_modules=("module_a",),
            confidence=0.9,
            evidence=(evidence,),
        )
        assert opportunity.id == "HIGH_COUPLING:module_a"
        assert opportunity.category == RefactoringCategory.HIGH_COUPLING
        assert opportunity.severity == Severity.HIGH
        assert opportunity.title == "High coupling"
        assert opportunity.description == "Module has high coupling"
        assert opportunity.affected_symbols == ("sym1", "sym2")
        assert opportunity.affected_modules == ("module_a",)
        assert opportunity.confidence == 0.9
        assert opportunity.evidence == (evidence,)

    def test_opportunity_is_immutable(self) -> None:
        evidence = RefactoringEvidence(
            type=EvidenceType.DEPENDENCY,
            source="diagnostics",
            message="Test evidence",
            reference="test_ref",
        )
        opportunity = RefactoringOpportunity(
            id="HIGH_COUPLING:module_a",
            category=RefactoringCategory.HIGH_COUPLING,
            severity=Severity.HIGH,
            title="High coupling",
            description="Module has high coupling",
            affected_symbols=("sym1", "sym2"),
            affected_modules=("module_a",),
            confidence=0.9,
            evidence=(evidence,),
        )
        with pytest.raises(AttributeError):
            opportunity.id = "NEW_ID"  # type: ignore[misc]

    def test_opportunity_evidence_is_immutable_tuple(self) -> None:
        evidence = RefactoringEvidence(
            type=EvidenceType.DEPENDENCY,
            source="diagnostics",
            message="Test evidence",
            reference="test_ref",
        )
        opportunity = RefactoringOpportunity(
            id="HIGH_COUPLING:module_a",
            category=RefactoringCategory.HIGH_COUPLING,
            severity=Severity.HIGH,
            title="High coupling",
            description="Module has high coupling",
            affected_symbols=("sym1", "sym2"),
            affected_modules=("module_a",),
            confidence=0.9,
            evidence=(evidence,),
        )
        # Tuple is immutable, so this should raise TypeError
        with pytest.raises(TypeError):
            opportunity.evidence[0] = evidence  # type: ignore[index]


class TestRefactoringReport:
    """Tests for RefactoringReport immutable dataclass."""

    def test_report_creation(self) -> None:
        evidence = RefactoringEvidence(
            type=EvidenceType.DEPENDENCY,
            source="diagnostics",
            message="Test evidence",
            reference="test_ref",
        )
        opportunity = RefactoringOpportunity(
            id="HIGH_COUPLING:module_a",
            category=RefactoringCategory.HIGH_COUPLING,
            severity=Severity.HIGH,
            title="High coupling",
            description="Module has high coupling",
            affected_symbols=("sym1", "sym2"),
            affected_modules=("module_a",),
            confidence=0.9,
            evidence=(evidence,),
        )
        summary = RefactoringSummary(
            total_opportunities=1,
            high=1,
            medium=0,
            low=0,
            info=0,
        )
        stats = RepositoryStatistics(
            modules=10,
            symbols=100,
            relationships=50,
            diagnostics=5,
        )
        report = RefactoringReport(
            summary=summary,
            statistics=stats,
            opportunities=(opportunity,),
        )
        assert report.summary == summary
        assert report.statistics == stats
        assert report.opportunities == (opportunity,)

    def test_report_is_immutable(self) -> None:
        evidence = RefactoringEvidence(
            type=EvidenceType.DEPENDENCY,
            source="diagnostics",
            message="Test evidence",
            reference="test_ref",
        )
        opportunity = RefactoringOpportunity(
            id="HIGH_COUPLING:module_a",
            category=RefactoringCategory.HIGH_COUPLING,
            severity=Severity.HIGH,
            title="High coupling",
            description="Module has high coupling",
            affected_symbols=("sym1", "sym2"),
            affected_modules=("module_a",),
            confidence=0.9,
            evidence=(evidence,),
        )
        summary = RefactoringSummary(
            total_opportunities=1,
            high=1,
            medium=0,
            low=0,
            info=0,
        )
        stats = RepositoryStatistics(
            modules=10,
            symbols=100,
            relationships=50,
            diagnostics=5,
        )
        report = RefactoringReport(
            summary=summary,
            statistics=stats,
            opportunities=(opportunity,),
        )
        with pytest.raises(AttributeError):
            report.summary = summary  # type: ignore[misc]

    def test_report_opportunities_are_immutable_tuples(self) -> None:
        evidence = RefactoringEvidence(
            type=EvidenceType.DEPENDENCY,
            source="diagnostics",
            message="Test evidence",
            reference="test_ref",
        )
        opportunity = RefactoringOpportunity(
            id="HIGH_COUPLING:module_a",
            category=RefactoringCategory.HIGH_COUPLING,
            severity=Severity.HIGH,
            title="High coupling",
            description="Module has high coupling",
            affected_symbols=("sym1", "sym2"),
            affected_modules=("module_a",),
            confidence=0.9,
            evidence=(evidence,),
        )
        summary = RefactoringSummary(
            total_opportunities=1,
            high=1,
            medium=0,
            low=0,
            info=0,
        )
        stats = RepositoryStatistics(
            modules=10,
            symbols=100,
            relationships=50,
            diagnostics=5,
        )
        report = RefactoringReport(
            summary=summary,
            statistics=stats,
            opportunities=(opportunity,),
        )
        # Tuple is immutable, so this should raise TypeError
        with pytest.raises(TypeError):
            report.opportunities[0] = opportunity  # type: ignore[index]