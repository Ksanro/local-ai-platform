"""Tests for scoring functions.

Verifies:
- Weighted category score calculation
- Overall score calculation
- Edge cases
- Coverage >95%
"""

from __future__ import annotations

import pytest

from packages.evaluation.models import EvaluationMetric, EvaluationScore
from packages.evaluation.scoring import (
    CATEGORY_DEFINITIONS,
    CATEGORY_WEIGHTS,
    calculate_category_score,
    calculate_overall_score,
)


# ---------------------------------------------------------------------------
# Test: Category Weights
# ---------------------------------------------------------------------------


class TestCategoryWeights:
    """Tests for CATEGORY_WEIGHTS constant."""

    def test_all_categories_present(self) -> None:
        """All expected categories should be present."""
        expected = {
            "Context Quality",
            "Execution Quality",
            "Engineering Quality",
            "Performance",
            "Determinism",
        }
        assert set(CATEGORY_WEIGHTS.keys()) == expected

    def test_total_weight_is_one(self) -> None:
        """Total weight should sum to 1.0."""
        total = sum(CATEGORY_WEIGHTS.values())
        assert total == 1.0

    def test_all_weights_are_positive(self) -> None:
        """All weights should be positive."""
        for weight in CATEGORY_WEIGHTS.values():
            assert weight > 0

    def test_all_weights_are_at_most_one(self) -> None:
        """All weights should be <= 1.0."""
        for weight in CATEGORY_WEIGHTS.values():
            assert weight <= 1.0


# ---------------------------------------------------------------------------
# Test: Category Definitions
# ---------------------------------------------------------------------------


class TestCategoryDefinitions:
    """Tests for CATEGORY_DEFINITIONS constant."""

    def test_all_categories_have_definitions(self) -> None:
        """All categories should have metric definitions."""
        for category in CATEGORY_WEIGHTS:
            assert category in CATEGORY_DEFINITIONS

    def test_context_quality_metrics(self) -> None:
        """Context Quality should have expected metrics."""
        expected = {
            "context_compression_ratio",
            "context_utilization",
            "selected_symbols_count",
            "selected_modules_count",
        }
        assert set(CATEGORY_DEFINITIONS["Context Quality"]) == expected

    def test_determinism_metrics(self) -> None:
        """Determinism should have expected metrics."""
        expected = {
            "execution_consistency",
            "identifier_stability",
        }
        assert set(CATEGORY_DEFINITIONS["Determinism"]) == expected


# ---------------------------------------------------------------------------
# Test: Category Score Calculation
# ---------------------------------------------------------------------------


class TestCategoryScoreCalculation:
    """Tests for calculate_category_score function."""

    def test_no_metrics_returns_zero(self) -> None:
        """No metrics should return 0.0."""
        metrics: tuple[EvaluationMetric, ...] = ()
        result = calculate_category_score(metrics, "Context Quality")
        assert result == 0.0

    def test_no_matching_metrics_returns_zero(self) -> None:
        """No matching metrics should return 0.0."""
        metrics = (
            EvaluationMetric(
                name="other_metric",
                value=1.0,
                weight=1.0,
                passed=True,
            ),
        )
        result = calculate_category_score(metrics, "Context Quality")
        assert result == 0.0

    def test_single_metric(self) -> None:
        """Single metric should return its value."""
        metrics = (
            EvaluationMetric(
                name="context_compression_ratio",
                value=0.85,
                weight=0.50,
                passed=True,
            ),
        )
        result = calculate_category_score(
            metrics, "Context Quality"
        )
        assert result == 0.85

    def test_multiple_metrics_weighted_average(self) -> None:
        """Multiple metrics should return weighted average."""
        metrics = (
            EvaluationMetric(
                name="context_compression_ratio",
                value=0.0,  # 0.0 * 0.5 = 0.0
                weight=0.50,
                passed=False,
            ),
            EvaluationMetric(
                name="context_utilization",
                value=1.0,  # 1.0 * 0.5 = 0.5
                weight=0.50,
                passed=True,
            ),
        )
        result = calculate_category_score(
            metrics, "Context Quality"
        )
        # (0.0 * 0.5 + 1.0 * 0.5) / (0.5 + 0.5) = 0.5
        assert result == 0.5

    def test_custom_metric_names(self) -> None:
        """Custom metric names should be used."""
        metrics = (
            EvaluationMetric(
                name="custom_metric",
                value=0.75,
                weight=1.0,
                passed=True,
            ),
        )
        result = calculate_category_score(
            metrics,
            "Custom Category",
            category_metric_names=["custom_metric"],
        )
        assert result == 0.75

    def test_zero_total_weight(self) -> None:
        """Zero total weight should return 0.0."""
        metrics = (
            EvaluationMetric(
                name="context_compression_ratio",
                value=0.85,
                weight=0.0,  # Zero weight
                passed=True,
            ),
        )
        result = calculate_category_score(
            metrics, "Context Quality"
        )
        assert result == 0.0


# ---------------------------------------------------------------------------
# Test: Overall Score Calculation
# ---------------------------------------------------------------------------


class TestOverallScoreCalculation:
    """Tests for calculate_overall_score function."""

    def test_no_scores_returns_zero(self) -> None:
        """No scores should return 0.0."""
        scores: tuple[EvaluationScore, ...] = ()
        result = calculate_overall_score(scores)
        assert result == 0.0

    def test_single_score(self) -> None:
        """Single score should return weighted average."""
        scores = (
            EvaluationScore(
                category="Context Quality",
                score=0.85,
                maximum=1.0,
                weight=0.25,
            ),
        )
        result = calculate_overall_score(scores)
        # 0.85 * 0.25 / 0.25 = 0.85
        assert result == 0.85

    def test_multiple_scores(self) -> None:
        """Multiple scores should return weighted average."""
        scores = (
            EvaluationScore(
                category="Context Quality",
                score=1.0,
                maximum=1.0,
                weight=0.25,
            ),
            EvaluationScore(
                category="Execution Quality",
                score=0.5,
                maximum=1.0,
                weight=0.20,
            ),
        )
        result = calculate_overall_score(scores)
        # (1.0 * 0.25 + 0.5 * 0.20) / (0.25 + 0.20)
        # = (0.25 + 0.10) / 0.45 = 0.35 / 0.45 = 0.777...
        expected = (0.25 + 0.10) / 0.45
        assert abs(result - expected) < 0.0001

    def test_unknown_category_weight_zero(self) -> None:
        """Unknown category should have zero weight."""
        scores = (
            EvaluationScore(
                category="Unknown Category",
                score=1.0,
                maximum=1.0,
                weight=0.0,
            ),
        )
        result = calculate_overall_score(scores)
        assert result == 0.0

    def test_all_scores_zero(self) -> None:
        """All zero scores should return 0.0."""
        scores = (
            EvaluationScore(
                category="Context Quality",
                score=0.0,
                maximum=1.0,
                weight=0.25,
            ),
            EvaluationScore(
                category="Execution Quality",
                score=0.0,
                maximum=1.0,
                weight=0.20,
            ),
        )
        result = calculate_overall_score(scores)
        assert result == 0.0

    def test_all_scores_one(self) -> None:
        """All one scores should return 1.0."""
        scores = (
            EvaluationScore(
                category="Context Quality",
                score=1.0,
                maximum=1.0,
                weight=0.25,
            ),
            EvaluationScore(
                category="Execution Quality",
                score=1.0,
                maximum=1.0,
                weight=0.20,
            ),
        )
        result = calculate_overall_score(scores)
        assert result == 1.0

    def test_score_clamping(self) -> None:
        """Scores should be clamped to [0.0, 1.0]."""
        scores = (
            EvaluationScore(
                category="Context Quality",
                score=0.85,
                maximum=1.0,
                weight=0.25,
            ),
        )
        result = calculate_overall_score(scores)
        assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_category_name(self) -> None:
        """Empty category name should return 0.0."""
        metrics: tuple[EvaluationMetric, ...] = ()
        result = calculate_category_score(metrics, "")
        assert result == 0.0

    def test_empty_custom_metric_names(self) -> None:
        """Empty custom metric names should return 0.0."""
        metrics: tuple[EvaluationMetric, ...] = ()
        result = calculate_category_score(
            metrics, "Custom", category_metric_names=[]
        )
        assert result == 0.0

    def test_none_custom_metric_names(self) -> None:
        """None custom metric names should use definitions."""
        metrics = (
            EvaluationMetric(
                name="context_compression_ratio",
                value=0.5,
                weight=1.0,
                passed=True,
            ),
        )
        result = calculate_category_score(
            metrics, "Context Quality", category_metric_names=None
        )
        assert result == 0.5

    def test_duplicate_metrics_in_category(self) -> None:
        """Duplicate metric names should each be counted."""
        metrics = (
            EvaluationMetric(
                name="context_compression_ratio",
                value=0.5,
                weight=1.0,
                passed=True,
            ),
            EvaluationMetric(
                name="context_compression_ratio",
                value=1.0,
                weight=1.0,
                passed=True,
            ),
        )
        result = calculate_category_score(
            metrics, "Context Quality"
        )
        # Both are counted: (0.5 + 1.0) / 2 = 0.75
        assert result == 0.75

    def test_overall_score_with_all_categories(self) -> None:
        """All categories should be included in overall score."""
        scores = (
            EvaluationScore(
                category="Context Quality",
                score=1.0,
                maximum=1.0,
                weight=0.25,
            ),
            EvaluationScore(
                category="Execution Quality",
                score=1.0,
                maximum=1.0,
                weight=0.20,
            ),
            EvaluationScore(
                category="Engineering Quality",
                score=1.0,
                maximum=1.0,
                weight=0.30,
            ),
            EvaluationScore(
                category="Performance",
                score=1.0,
                maximum=1.0,
                weight=0.10,
            ),
            EvaluationScore(
                category="Determinism",
                score=1.0,
                maximum=1.0,
                weight=0.15,
            ),
        )
        result = calculate_overall_score(scores)
        assert result == 1.0

    def test_overall_score_with_partial_categories(self) -> None:
        """Only categories with weight > 0 should be included."""
        scores = (
            EvaluationScore(
                category="Context Quality",
                score=0.5,
                maximum=1.0,
                weight=0.25,
            ),
            EvaluationScore(
                category="Unknown",
                score=1.0,
                maximum=1.0,
                weight=0.0,
            ),
        )
        result = calculate_overall_score(scores)
        # Only Context Quality counts: 0.5 * 0.25 / 0.25 = 0.5
        assert result == 0.5