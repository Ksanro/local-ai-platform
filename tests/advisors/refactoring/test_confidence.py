"""Tests for the confidence computation module."""

from __future__ import annotations

from enum import StrEnum

import pytest

from packages.advisors.refactoring.confidence import compute_confidence
from packages.advisors.refactoring.models import RefactoringCategory


class TestComputeConfidence:
    """Tests for compute_confidence function."""

    def test_high_coupling_single_evidence_complete(self) -> None:
        """HIGH_COUPLING with 1 evidence item and complete analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.HIGH_COUPLING,
            evidence_count=1,
            completeness=1.0,
        )
        # base=0.80, evidence=0.8, completeness=1.0 => 0.80 * 0.8 * 1.0 = 0.64
        assert confidence == 0.64

    def test_high_coupling_two_evidence_complete(self) -> None:
        """HIGH_COUPLING with 2 evidence items and complete analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.HIGH_COUPLING,
            evidence_count=2,
            completeness=1.0,
        )
        # base=0.80, evidence=0.9, completeness=1.0 => 0.80 * 0.9 * 1.0 = 0.72
        assert confidence == 0.72

    def test_high_coupling_three_evidence_complete(self) -> None:
        """HIGH_COUPLING with 3 evidence items and complete analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.HIGH_COUPLING,
            evidence_count=3,
            completeness=1.0,
        )
        # base=0.80, evidence=1.0, completeness=1.0 => 0.80 * 1.0 * 1.0 = 0.80
        assert confidence == 0.80

    def test_high_coupling_four_evidence_complete(self) -> None:
        """HIGH_COUPLING with 4 evidence items and complete analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.HIGH_COUPLING,
            evidence_count=4,
            completeness=1.0,
        )
        # base=0.80, evidence=1.0, completeness=1.0 => 0.80 * 1.0 * 1.0 = 0.80
        assert confidence == 0.80

    def test_large_module_single_evidence_partial(self) -> None:
        """LARGE_MODULE with 1 evidence item and partial analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.LARGE_MODULE,
            evidence_count=1,
            completeness=0.9,
        )
        # base=0.70, evidence=0.8, completeness=0.9 => 0.70 * 0.8 * 0.9 = 0.504 => 0.5
        assert confidence == 0.5

    def test_large_module_three_evidence_complete(self) -> None:
        """LARGE_MODULE with 3 evidence items and complete analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.LARGE_MODULE,
            evidence_count=3,
            completeness=1.0,
        )
        # base=0.70, evidence=1.0, completeness=1.0 => 0.70 * 1.0 * 1.0 = 0.70
        assert confidence == 0.70

    def test_dead_code_single_evidence_complete(self) -> None:
        """DEAD_CODE with 1 evidence item and complete analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.DEAD_CODE,
            evidence_count=1,
            completeness=1.0,
        )
        # base=0.90, evidence=0.8, completeness=1.0 => 0.90 * 0.8 * 1.0 = 0.72
        assert confidence == 0.72

    def test_dead_code_three_evidence_complete(self) -> None:
        """DEAD_CODE with 3 evidence items and complete analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.DEAD_CODE,
            evidence_count=3,
            completeness=1.0,
        )
        # base=0.90, evidence=1.0, completeness=1.0 => 0.90 * 1.0 * 1.0 = 0.90
        assert confidence == 0.90

    def test_orphan_module_single_evidence_complete(self) -> None:
        """ORPHAN_MODULE with 1 evidence item and complete analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.ORPHAN_MODULE,
            evidence_count=1,
            completeness=1.0,
        )
        # base=0.85, evidence=0.8, completeness=1.0 => 0.85 * 0.8 * 1.0 = 0.68
        assert confidence == 0.68

    def test_circular_dependency_single_evidence_complete(self) -> None:
        """CIRCULAR_DEPENDENCY with 1 evidence item and complete analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.CIRCULAR_DEPENDENCY,
            evidence_count=1,
            completeness=1.0,
        )
        # base=0.95, evidence=0.8, completeness=1.0 => 0.95 * 0.8 * 1.0 = 0.76
        assert confidence == 0.76

    def test_circular_dependency_three_evidence_complete(self) -> None:
        """CIRCULAR_DEPENDENCY with 3 evidence items and complete analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.CIRCULAR_DEPENDENCY,
            evidence_count=3,
            completeness=1.0,
        )
        # base=0.95, evidence=1.0, completeness=1.0 => 0.95 * 1.0 * 1.0 = 0.95
        assert confidence == 0.95

    def test_excessive_dependencies_single_evidence_partial(self) -> None:
        """EXCESSIVE_DEPENDENCIES with 1 evidence item and partial analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.EXCESSIVE_DEPENDENCIES,
            evidence_count=1,
            completeness=0.9,
        )
        # base=0.75, evidence=0.8, completeness=0.9 => 0.75 * 0.8 * 0.9 = 0.54
        assert confidence == 0.54

    def test_excessive_dependencies_single_evidence_complete(self) -> None:
        """EXCESSIVE_DEPENDENCIES with 1 evidence item and complete analysis."""
        confidence = compute_confidence(
            category=RefactoringCategory.EXCESSIVE_DEPENDENCIES,
            evidence_count=1,
            completeness=1.0,
        )
        # base=0.75, evidence=0.8, completeness=1.0 => 0.75 * 0.8 * 1.0 = 0.60
        assert confidence == 0.60

    def test_no_evidence(self) -> None:
        """Test with zero evidence items."""
        confidence = compute_confidence(
            category=RefactoringCategory.HIGH_COUPLING,
            evidence_count=0,
            completeness=1.0,
        )
        # base=0.80, evidence=0.5, completeness=1.0 => 0.80 * 0.5 * 1.0 = 0.40
        assert confidence == 0.40

    def test_clamping_to_one(self) -> None:
        """Test that confidence is clamped to 1.0 max."""
        confidence = compute_confidence(
            category=RefactoringCategory.CIRCULAR_DEPENDENCY,
            evidence_count=10,
            completeness=1.0,
        )
        # base=0.95, evidence=1.0, completeness=1.0 => 0.95 * 1.0 * 1.0 = 0.95
        assert confidence == 0.95

    def test_clamping_to_zero(self) -> None:
        """Test that confidence is clamped to 0.0 min."""
        confidence = compute_confidence(
            category=RefactoringCategory.LARGE_MODULE,
            evidence_count=0,
            completeness=0.0,
        )
        # base=0.70, evidence=0.5, completeness=0.0 => 0.70 * 0.5 * 0.0 = 0.0
        assert confidence == 0.0

    def test_unknown_category_default_base(self) -> None:
        """Test that unknown categories use default base score."""
        # Use an enum value not in _BASE_SCORES to test the fallback
        class UnknownCategory(StrEnum):
            UNKNOWN = "unknown"

        confidence = compute_confidence(
            category=UnknownCategory.UNKNOWN,  # type: ignore[arg-type]
            evidence_count=1,
            completeness=1.0,
        )
        # Unknown category falls back to base=0.70, evidence=0.8, completeness=1.0 => 0.70 * 0.8 * 1.0 = 0.56
        assert confidence == 0.56

    def test_known_category_behavior(self) -> None:
        """Test that LARGE_MODULE (known category) produces expected result."""
        confidence = compute_confidence(
            category=RefactoringCategory.LARGE_MODULE,
            evidence_count=1,
            completeness=1.0,
        )
        # LARGE_MODULE base=0.70, evidence=0.8, completeness=1.0 => 0.70 * 0.8 * 1.0 = 0.56
        assert confidence == 0.56

    def test_invalid_completeness_high(self) -> None:
        """Test that completeness > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="completeness must be in"):
            compute_confidence(
                category=RefactoringCategory.HIGH_COUPLING,
                evidence_count=1,
                completeness=1.5,
            )

    def test_invalid_completeness_low(self) -> None:
        """Test that completeness < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="completeness must be in"):
            compute_confidence(
                category=RefactoringCategory.HIGH_COUPLING,
                evidence_count=1,
                completeness=-0.1,
            )

    def test_invalid_evidence_count(self) -> None:
        """Test that negative evidence_count raises ValueError."""
        with pytest.raises(ValueError, match="evidence_count must be"):
            compute_confidence(
                category=RefactoringCategory.HIGH_COUPLING,
                evidence_count=-1,
                completeness=1.0,
            )

    def test_deterministic(self) -> None:
        """Test that the function is deterministic."""
        result1 = compute_confidence(
            category=RefactoringCategory.HIGH_COUPLING,
            evidence_count=2,
            completeness=0.9,
        )
        result2 = compute_confidence(
            category=RefactoringCategory.HIGH_COUPLING,
            evidence_count=2,
            completeness=0.9,
        )
        assert result1 == result2

    def test_all_categories_ranking(self) -> None:
        """Test that categories are ranked by base score."""
        # All categories with 3 evidence and complete analysis
        circular = compute_confidence(
            category=RefactoringCategory.CIRCULAR_DEPENDENCY,
            evidence_count=3,
            completeness=1.0,
        )
        dead = compute_confidence(
            category=RefactoringCategory.DEAD_CODE,
            evidence_count=3,
            completeness=1.0,
        )
        orphan = compute_confidence(
            category=RefactoringCategory.ORPHAN_MODULE,
            evidence_count=3,
            completeness=1.0,
        )
        high_coupling = compute_confidence(
            category=RefactoringCategory.HIGH_COUPLING,
            evidence_count=3,
            completeness=1.0,
        )
        excessive = compute_confidence(
            category=RefactoringCategory.EXCESSIVE_DEPENDENCIES,
            evidence_count=3,
            completeness=1.0,
        )
        large = compute_confidence(
            category=RefactoringCategory.LARGE_MODULE,
            evidence_count=3,
            completeness=1.0,
        )

        # Verify ranking: CIRCULAR > DEAD > ORPHAN > HIGH_COUPLING > EXCESSIVE > LARGE
        assert circular == 0.95
        assert dead == 0.90
        assert orphan == 0.85
        assert high_coupling == 0.80
        assert excessive == 0.75
        assert large == 0.70

    def test_rounding(self) -> None:
        """Test that confidence is rounded to 2 decimal places."""
        confidence = compute_confidence(
            category=RefactoringCategory.HIGH_COUPLING,
            evidence_count=2,
            completeness=0.9,
        )
        # base=0.80, evidence=0.9, completeness=0.9 => 0.80 * 0.9 * 0.9 = 0.648 => 0.65
        assert confidence == 0.65
        # Verify it's a float with at most 2 decimal places
        assert confidence == round(confidence, 2)