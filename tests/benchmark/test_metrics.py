"""Tests for the benchmark metrics module.

Verifies scoring functions: symbol precision, module precision,
relationship precision, budget compliance, and overall score.
"""

from __future__ import annotations

import pytest

from packages.benchmark.metrics import (
    WEIGHT_BUDGET_COMPLIANCE,
    WEIGHT_MODULE_PRECISION,
    WEIGHT_RELATIONSHIP_PRECISION,
    WEIGHT_SYMBOL_PRECISION,
    budget_compliance,
    module_precision,
    overall_score,
    relationship_precision,
    symbol_precision,
)


class TestSymbolPrecision:
    """Tests for symbol_precision function."""

    def test_exact_match(self) -> None:
        """All expected symbols retrieved — score should be 1.0."""
        retrieved = {"a.b.c", "x.y.z"}
        expected = {"a.b.c", "x.y.z"}
        assert symbol_precision(retrieved, expected) == pytest.approx(1.0)

    def test_no_match(self) -> None:
        """No expected symbols retrieved — score should be 0.0."""
        retrieved = {"wrong.one", "wrong.two"}
        expected = {"a.b.c", "x.y.z"}
        assert symbol_precision(retrieved, expected) == pytest.approx(0.0)

    def test_partial_match(self) -> None:
        """Half of expected symbols retrieved — score should be < 1.0."""
        retrieved = {"a.b.c", "wrong.one"}
        expected = {"a.b.c", "x.y.z"}
        score = symbol_precision(retrieved, expected)
        # precision = 1/2 = 0.5, recall = 1/2 = 0.5
        # f1 = 2 * 0.5 * 0.5 / (0.5 + 0.5) = 0.5
        assert score == pytest.approx(0.5)

    def test_empty_retrieved_nonempty_expected(self) -> None:
        """Nothing retrieved but expected — score should be 0.0."""
        retrieved: set[str] = set()
        expected = {"a.b.c"}
        assert symbol_precision(retrieved, expected) == pytest.approx(0.0)

    def test_empty_both(self) -> None:
        """Nothing expected and nothing retrieved — score should be 1.0."""
        retrieved: set[str] = set()
        expected: set[str] = set()
        assert symbol_precision(retrieved, expected) == pytest.approx(1.0)

    def test_more_retrieved_than_expected(self) -> None:
        """More symbols retrieved than expected — precision penalized."""
        retrieved = {"a.b.c", "extra.one", "extra.two", "extra.three"}
        expected = {"a.b.c"}
        # precision = 1/4 = 0.25, recall = 1/1 = 1.0
        # f1 = 2 * 0.25 * 1.0 / (0.25 + 1.0) = 0.5 / 1.25 = 0.4
        score = symbol_precision(retrieved, expected)
        assert score == pytest.approx(0.4)


class TestModulePrecision:
    """Tests for module_precision function."""

    def test_exact_match(self) -> None:
        """All expected modules retrieved — score should be 1.0."""
        retrieved = {"mod/a.py", "mod/b.py"}
        expected = {"mod/a.py", "mod/b.py"}
        assert module_precision(retrieved, expected) == pytest.approx(1.0)

    def test_no_match(self) -> None:
        """No expected modules retrieved — score should be 0.0."""
        retrieved = {"wrong/x.py", "wrong/y.py"}
        expected = {"mod/a.py", "mod/b.py"}
        assert module_precision(retrieved, expected) == pytest.approx(0.0)

    def test_partial_match(self) -> None:
        """Half of expected modules retrieved."""
        retrieved = {"mod/a.py", "wrong/z.py"}
        expected = {"mod/a.py", "mod/b.py"}
        # precision = 1/2 = 0.5, recall = 1/2 = 0.5, f1 = 0.5
        assert module_precision(retrieved, expected) == pytest.approx(0.5)

    def test_empty_both(self) -> None:
        """Nothing expected and nothing retrieved — score should be 1.0."""
        retrieved: set[str] = set()
        expected: set[str] = set()
        assert module_precision(retrieved, expected) == pytest.approx(1.0)


class TestRelationshipPrecision:
    """Tests for relationship_precision function."""

    def test_exact_match(self) -> None:
        """All expected relationships retrieved — score should be 1.0."""
        retrieved = {"a→b", "c→d"}
        expected = {"a→b", "c→d"}
        assert relationship_precision(retrieved, expected) == pytest.approx(1.0)

    def test_no_match(self) -> None:
        """No expected relationships retrieved — score should be 0.0."""
        retrieved = {"x→y", "w→z"}
        expected = {"a→b", "c→d"}
        assert relationship_precision(retrieved, expected) == pytest.approx(0.0)

    def test_partial_match(self) -> None:
        """Half of expected relationships retrieved."""
        retrieved = {"a→b", "wrong→wrong"}
        expected = {"a→b", "c→d"}
        # precision = 1/2 = 0.5, recall = 1/2 = 0.5, f1 = 0.5
        assert relationship_precision(retrieved, expected) == pytest.approx(0.5)

    def test_empty_both(self) -> None:
        """Nothing expected and nothing retrieved — score should be 1.0."""
        retrieved: set[str] = set()
        expected: set[str] = set()
        assert relationship_precision(retrieved, expected) == pytest.approx(1.0)


class TestBudgetCompliance:
    """Tests for budget_compliance function."""

    def test_within_budget(self) -> None:
        """Estimated tokens equal to budget — should pass."""
        assert budget_compliance(100, 100) == 1.0

    def test_within_budget_under(self) -> None:
        """Estimated tokens under budget — should pass."""
        assert budget_compliance(50, 100) == 1.0

    def test_over_budget(self) -> None:
        """Estimated tokens over budget — should fail."""
        assert budget_compliance(150, 100) == 0.0

    def test_zero_budget(self) -> None:
        """Zero estimated with zero budget — should pass."""
        assert budget_compliance(0, 0) == 1.0

    def test_zero_estimated_nonzero_budget(self) -> None:
        """Zero estimated tokens with positive budget — should pass."""
        assert budget_compliance(0, 100) == 1.0


class TestOverallScore:
    """Tests for overall_score function."""

    def test_perfect_score(self) -> None:
        """All metrics perfect — overall score should be 1.0."""
        score = overall_score(1.0, 1.0, 1.0, 1.0)
        assert score == pytest.approx(1.0)

    def test_zero_all(self) -> None:
        """All metrics zero — overall score should be 0.0."""
        score = overall_score(0.0, 0.0, 0.0, 0.0)
        assert score == pytest.approx(0.0)

    def test_weighted_average(self) -> None:
        """Score is weighted average of all metrics."""
        # 40% * 1.0 + 20% * 0.5 + 20% * 0.0 + 20% * 1.0
        # = 0.4 + 0.1 + 0.0 + 0.2 = 0.7
        score = overall_score(1.0, 0.5, 0.0, 1.0)
        assert score == pytest.approx(0.7)

    def test_weights_sum_to_one(self) -> None:
        """All weights sum to 1.0."""
        total = (
            WEIGHT_SYMBOL_PRECISION
            + WEIGHT_MODULE_PRECISION
            + WEIGHT_RELATIONSHIP_PRECISION
            + WEIGHT_BUDGET_COMPLIANCE
        )
        assert total == pytest.approx(1.0)

    def test_clamped_to_one(self) -> None:
        """Score clamped to 1.0 even if floating point drift."""
        # All perfect — should be exactly 1.0
        score = overall_score(1.0, 1.0, 1.0, 1.0)
        assert score == pytest.approx(1.0)

    def test_clamped_to_zero(self) -> None:
        """Score clamped to 0.0 for all-zero input."""
        score = overall_score(0.0, 0.0, 0.0, 0.0)
        assert score == pytest.approx(0.0)

    def test_budget_alone(self) -> None:
        """Only budget compliance is 1.0, others are 0."""
        # 0.4 * 0 + 0.2 * 0 + 0.2 * 0 + 0.2 * 1 = 0.2
        score = overall_score(0.0, 0.0, 0.0, 1.0)
        assert score == pytest.approx(0.2)

    def test_symbol_dominates(self) -> None:
        """Only symbol precision is 1.0, others are 0."""
        # 0.4 * 1 + 0.2 * 0 + 0.2 * 0 + 0.2 * 0 = 0.4
        score = overall_score(1.0, 0.0, 0.0, 0.0)
        assert score == pytest.approx(0.4)
