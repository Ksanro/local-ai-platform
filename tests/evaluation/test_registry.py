"""Tests for registry functions.

Verifies:
- Metric registration
- Category registration
- Duplicate elimination
- Lookup
- Listing
- Reset
- Coverage >95%
"""

from __future__ import annotations

import pytest

from packages.evaluation.registry import (
    get_category,
    get_metric,
    list_categories,
    list_metrics,
    register_category,
    register_metric,
    reset_registry,
)


# ---------------------------------------------------------------------------
# Test: Metric Registration
# ---------------------------------------------------------------------------


class TestMetricRegistration:
    """Tests for metric registration."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        reset_registry()

    def test_register_metric(self) -> None:
        """Should register a metric."""
        def compute_value() -> float:
            return 1.0

        register_metric(
            name="test_metric",
            computation=compute_value,
            weight=0.5,
            description="Test metric",
        )

        metric = get_metric("test_metric")
        assert metric is not None
        assert metric["weight"] == 0.5
        assert metric["description"] == "Test metric"

    def test_register_metric_default_weight(self) -> None:
        """Should use default weight of 1.0."""
        def compute_value() -> float:
            return 1.0

        register_metric(
            name="test_metric",
            computation=compute_value,
        )

        metric = get_metric("test_metric")
        assert metric is not None
        assert metric["weight"] == 1.0

    def test_register_metric_default_description(self) -> None:
        """Should use empty description by default."""
        def compute_value() -> float:
            return 1.0

        register_metric(
            name="test_metric",
            computation=compute_value,
        )

        metric = get_metric("test_metric")
        assert metric is not None
        assert metric["description"] == ""

    def test_register_metric_stores_computation(self) -> None:
        """Should store computation function."""
        def compute_value() -> float:
            return 42.0

        register_metric(
            name="test_metric",
            computation=compute_value,
        )

        metric = get_metric("test_metric")
        assert metric is not None
        assert metric["computation"] is compute_value
        assert metric["computation"]() == 42.0

    def test_register_metric_duplicate_ignored(self) -> None:
        """Duplicate metric name should be ignored."""
        def compute_value_1() -> float:
            return 1.0

        def compute_value_2() -> float:
            return 2.0

        register_metric(
            name="test_metric",
            computation=compute_value_1,
            weight=0.5,
        )

        register_metric(
            name="test_metric",
            computation=compute_value_2,
            weight=1.0,
        )

        metric = get_metric("test_metric")
        assert metric is not None
        assert metric["weight"] == 0.5
        assert metric["computation"] is compute_value_1

    def test_get_metric_not_found(self) -> None:
        """Should return None for non-existent metric."""
        result = get_metric("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Test: Category Registration
# ---------------------------------------------------------------------------


class TestCategoryRegistration:
    """Tests for category registration."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        reset_registry()

    def test_register_category(self) -> None:
        """Should register a category."""
        register_category(
            name="Test Category",
            weight=0.3,
            metric_names=["metric1", "metric2"],
            description="Test category",
        )

        category = get_category("Test Category")
        assert category is not None
        assert category["weight"] == 0.3
        assert category["metric_names"] == ["metric1", "metric2"]
        assert category["description"] == "Test category"

    def test_register_category_default_metric_names(self) -> None:
        """Should use empty list for default metric names."""
        register_category(
            name="Test Category",
            weight=0.3,
        )

        category = get_category("Test Category")
        assert category is not None
        assert category["metric_names"] == []

    def test_register_category_none_metric_names(self) -> None:
        """Should convert None to empty list."""
        register_category(
            name="Test Category",
            weight=0.3,
            metric_names=None,
        )

        category = get_category("Test Category")
        assert category is not None
        assert category["metric_names"] == []

    def test_register_category_duplicate_ignored(self) -> None:
        """Duplicate category name should be ignored."""
        register_category(
            name="Test Category",
            weight=0.3,
            metric_names=["metric1"],
        )

        register_category(
            name="Test Category",
            weight=0.5,
            metric_names=["metric2"],
        )

        category = get_category("Test Category")
        assert category is not None
        assert category["weight"] == 0.3
        assert category["metric_names"] == ["metric1"]

    def test_get_category_not_found(self) -> None:
        """Should return None for non-existent category."""
        result = get_category("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Test: Listing
# ---------------------------------------------------------------------------


class TestListing:
    """Tests for listing functions."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        reset_registry()

    def test_list_metrics_empty(self) -> None:
        """Should return empty tuple when no metrics registered."""
        result = list_metrics()
        assert result == ()

    def test_list_metrics_single(self) -> None:
        """Should return single metric name."""
        def compute_value() -> float:
            return 1.0

        register_metric(
            name="test_metric",
            computation=compute_value,
        )

        result = list_metrics()
        assert result == ("test_metric",)

    def test_list_metrics_multiple(self) -> None:
        """Should return all metric names in order."""
        def compute_a() -> float:
            return 1.0

        def compute_b() -> float:
            return 2.0

        register_metric(
            name="metric_a",
            computation=compute_a,
        )
        register_metric(
            name="metric_b",
            computation=compute_b,
        )

        result = list_metrics()
        assert result == ("metric_a", "metric_b")

    def test_list_categories_empty(self) -> None:
        """Should return empty tuple when no categories registered."""
        result = list_categories()
        assert result == ()

    def test_list_categories_single(self) -> None:
        """Should return single category name."""
        register_category(
            name="Test Category",
            weight=0.3,
        )

        result = list_categories()
        assert result == ("Test Category",)

    def test_list_categories_multiple(self) -> None:
        """Should return all category names in order."""
        register_category(
            name="Category A",
            weight=0.3,
        )
        register_category(
            name="Category B",
            weight=0.5,
        )

        result = list_categories()
        assert result == ("Category A", "Category B")


# ---------------------------------------------------------------------------
# Test: Duplicate Elimination
# ---------------------------------------------------------------------------


class TestDuplicateElimination:
    """Tests for duplicate elimination."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        reset_registry()

    def test_metric_duplicate_no_error(self) -> None:
        """Registering duplicate metric should not raise."""
        def compute_value() -> float:
            return 1.0

        register_metric(
            name="test_metric",
            computation=compute_value,
        )
        register_metric(
            name="test_metric",
            computation=compute_value,
        )

        # Should still have only one
        metrics = list_metrics()
        assert metrics == ("test_metric",)

    def test_category_duplicate_no_error(self) -> None:
        """Registering duplicate category should not raise."""
        register_category(
            name="Test Category",
            weight=0.3,
        )
        register_category(
            name="Test Category",
            weight=0.5,
        )

        # Should still have only one
        categories = list_categories()
        assert categories == ("Test Category",)


# ---------------------------------------------------------------------------
# Test: Reset
# ---------------------------------------------------------------------------


class TestReset:
    """Tests for registry reset."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        reset_registry()

    def test_reset_clears_metrics(self) -> None:
        """Reset should clear all metrics."""
        def compute_value() -> float:
            return 1.0

        register_metric(
            name="test_metric",
            computation=compute_value,
        )
        assert list_metrics() == ("test_metric",)

        reset_registry()

        assert list_metrics() == ()

    def test_reset_clears_categories(self) -> None:
        """Reset should clear all categories."""
        register_category(
            name="Test Category",
            weight=0.3,
        )
        assert list_categories() == ("Test Category",)

        reset_registry()

        assert list_categories() == ()

    def test_reset_clears_both(self) -> None:
        """Reset should clear both metrics and categories."""
        def compute_value() -> float:
            return 1.0

        register_metric(
            name="test_metric",
            computation=compute_value,
        )
        register_category(
            name="Test Category",
            weight=0.3,
        )

        reset_registry()

        assert list_metrics() == ()
        assert list_categories() == ()

    def test_reset_allows_re_registration(self) -> None:
        """After reset, same names can be re-registered."""
        def compute_value_1() -> float:
            return 1.0

        register_metric(
            name="test_metric",
            computation=compute_value_1,
        )

        reset_registry()

        def compute_value_2() -> float:
            return 2.0

        register_metric(
            name="test_metric",
            computation=compute_value_2,
        )

        metric = get_metric("test_metric")
        assert metric is not None
        assert metric["computation"]() == 2.0


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        reset_registry()

    def test_empty_name_metric(self) -> None:
        """Should handle empty metric name."""
        def compute_value() -> float:
            return 1.0

        register_metric(
            name="",
            computation=compute_value,
        )

        metric = get_metric("")
        assert metric is not None

    def test_empty_name_category(self) -> None:
        """Should handle empty category name."""
        register_category(
            name="",
            weight=0.0,
        )

        category = get_category("")
        assert category is not None

    def test_zero_weight_metric(self) -> None:
        """Should handle zero weight."""
        def compute_value() -> float:
            return 1.0

        register_metric(
            name="test_metric",
            computation=compute_value,
            weight=0.0,
        )

        metric = get_metric("test_metric")
        assert metric is not None
        assert metric["weight"] == 0.0

    def test_zero_weight_category(self) -> None:
        """Should handle zero weight."""
        register_category(
            name="Test Category",
            weight=0.0,
        )

        category = get_category("Test Category")
        assert category is not None
        assert category["weight"] == 0.0

    def test_unicode_name(self) -> None:
        """Should handle unicode in names."""
        def compute_value() -> float:
            return 1.0

        register_metric(
            name="metric_\u4f60\u597d",
            computation=compute_value,
        )

        metric = get_metric("metric_\u4f60\u597d")
        assert metric is not None