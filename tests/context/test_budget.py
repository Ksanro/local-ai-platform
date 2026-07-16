"""Tests for the Context Budget Engine.

Verifies estimation constants, formula correctness, budget boundaries,
determinism, and repeated execution stability.
"""

from __future__ import annotations

import pytest

from packages.context.budget import TOKENS_PER_MODULE, TOKENS_PER_SYMBOL, ContextBudget
from packages.context.models import ContextBudgetResult, ContextCandidate

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_candidate(
    symbol_id: str,
    qualified_name: str,
    module: str,
) -> ContextCandidate:
    """Create a ContextCandidate for testing."""
    return ContextCandidate(
        symbol_id=symbol_id,
        qualified_name=qualified_name,
        module=module,
    )


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------


class TestConstants:
    """Tests for estimation constants."""

    def test_tokens_per_symbol(self) -> None:
        """Verify TOKENS_PER_SYMBOL is 80."""
        assert TOKENS_PER_SYMBOL == 80

    def test_tokens_per_module(self) -> None:
        """Verify TOKENS_PER_MODULE is 150."""
        assert TOKENS_PER_MODULE == 150


# ------------------------------------------------------------------
# Formula
# ------------------------------------------------------------------


class TestFormula:
    """Tests for the estimation formula."""

    def test_zero_candidates(self) -> None:
        """Verify zero candidates produces zero tokens."""
        engine = ContextBudget()
        result = engine.estimate([], [], max_tokens=4096)
        assert result.estimated_tokens == 0
        assert result.estimated_symbols == 0
        assert result.estimated_modules == 0

    def test_single_symbol(self) -> None:
        """Verify single symbol produces 80 tokens."""
        engine = ContextBudget()
        candidates = [_make_candidate("a", "main.a", "main.py")]
        result = engine.estimate(candidates, [], max_tokens=4096)
        assert result.estimated_tokens == 80
        assert result.estimated_symbols == 1
        assert result.estimated_modules == 0

    def test_single_module(self) -> None:
        """Verify single module produces 150 tokens."""
        engine = ContextBudget()
        result = engine.estimate([], ["main.py"], max_tokens=4096)
        assert result.estimated_tokens == 150
        assert result.estimated_symbols == 0
        assert result.estimated_modules == 1

    def test_single_symbol_and_module(self) -> None:
        """Verify one symbol in one module: 80 + 150 = 230."""
        engine = ContextBudget()
        candidates = [_make_candidate("a", "main.a", "main.py")]
        result = engine.estimate(candidates, ["main.py"], max_tokens=4096)
        assert result.estimated_tokens == 230
        assert result.estimated_symbols == 1
        assert result.estimated_modules == 1

    def test_multiple_symbols(self) -> None:
        """Verify multiple symbols: symbols * 80."""
        engine = ContextBudget()
        candidates = [
            _make_candidate("a", "main.a", "main.py"),
            _make_candidate("b", "main.b", "main.py"),
            _make_candidate("c", "main.c", "main.py"),
        ]
        result = engine.estimate(candidates, [], max_tokens=4096)
        assert result.estimated_tokens == 240  # 3 * 80

    def test_multiple_modules(self) -> None:
        """Verify multiple modules: modules * 150."""
        engine = ContextBudget()
        result = engine.estimate([], ["a.py", "b.py", "c.py"], max_tokens=4096)
        assert result.estimated_tokens == 450  # 3 * 150

    def test_symbols_and_modules(self) -> None:
        """Verify combined: symbols * 80 + modules * 150."""
        engine = ContextBudget()
        candidates = [
            _make_candidate("a", "main.a", "main.py"),
            _make_candidate("b", "utils.b", "utils.py"),
        ]
        result = engine.estimate(candidates, ["main.py", "utils.py"], max_tokens=4096)
        assert result.estimated_tokens == 460  # 2*80 + 2*150

    def test_duplicate_symbols_count_once(self) -> None:
        """Verify duplicate symbol_ids are counted once."""
        engine = ContextBudget()
        candidates = [
            _make_candidate("a", "main.a", "main.py"),
            _make_candidate("a", "main.a", "other.py"),  # same symbol_id
        ]
        result = engine.estimate(candidates, ["main.py"], max_tokens=4096)
        assert result.estimated_symbols == 1
        assert result.estimated_tokens == 230  # 1*80 + 1*150


# ------------------------------------------------------------------
# Budget boundaries
# ------------------------------------------------------------------


class TestBudgetBoundaries:
    """Tests for budget boundary conditions."""

    def test_within_budget(self) -> None:
        """Verify within_budget is True when estimated <= max_tokens."""
        engine = ContextBudget()
        result = engine.estimate([], [], max_tokens=0)
        assert result.within_budget is True
        assert result.truncated is False

    def test_exact_boundary(self) -> None:
        """Verify exact boundary: estimated == max_tokens is within budget."""
        engine = ContextBudget()
        candidates = [_make_candidate("a", "main.a", "main.py")]
        result = engine.estimate(candidates, [], max_tokens=80)
        assert result.within_budget is True
        assert result.truncated is False

    def test_budget_exceeded(self) -> None:
        """Verify budget exceeded: estimated > max_tokens."""
        engine = ContextBudget()
        candidates = [_make_candidate("a", "main.a", "main.py")]
        result = engine.estimate(candidates, [], max_tokens=79)
        assert result.within_budget is False
        assert result.truncated is True

    def test_budget_exceeded_by_one(self) -> None:
        """Verify exceeded by one token."""
        engine = ContextBudget()
        candidates = [_make_candidate("a", "main.a", "main.py")]
        result = engine.estimate(candidates, [], max_tokens=79)
        assert result.estimated_tokens == 80
        assert result.within_budget is False
        assert result.truncated is True

    def test_large_budget(self) -> None:
        """Verify large budget accepts any reasonable context."""
        engine = ContextBudget()
        candidates = [
            _make_candidate(str(i), f"main.{i}", "main.py")
            for i in range(100)
        ]
        result = engine.estimate(candidates, ["main.py"], max_tokens=100000)
        assert result.within_budget is True
        assert result.truncated is False


# ------------------------------------------------------------------
# Determinism
# ------------------------------------------------------------------


class TestDeterminism:
    """Tests for deterministic estimates."""

    def test_deterministic_estimates(self) -> None:
        """Verify identical inputs produce identical results."""
        engine = ContextBudget()
        candidates = [
            _make_candidate("a", "main.a", "main.py"),
            _make_candidate("b", "utils.b", "utils.py"),
            _make_candidate("c", "auth.c", "auth.py"),
        ]
        results = [
            engine.estimate(candidates, ["main.py", "utils.py", "auth.py"], max_tokens=4096)
            for _ in range(10)
        ]
        first = results[0]
        for result in results[1:]:
            assert result.estimated_tokens == first.estimated_tokens
            assert result.estimated_symbols == first.estimated_symbols
            assert result.estimated_modules == first.estimated_modules
            assert result.within_budget == first.within_budget
            assert result.truncated == first.truncated

    def test_repeated_executions_identical(self) -> None:
        """Verify repeated executions produce identical results."""
        engine = ContextBudget()
        candidates = [
            _make_candidate(str(i), f"mod.{i}", f"mod{i}.py")
            for i in range(5)
        ]
        result_a = engine.estimate(candidates, [f"mod{i}.py" for i in range(5)], max_tokens=2000)
        result_b = engine.estimate(candidates, [f"mod{i}.py" for i in range(5)], max_tokens=2000)
        assert result_a == result_b

    def test_empty_repeated(self) -> None:
        """Verify empty inputs are deterministic."""
        engine = ContextBudget()
        results = [
            engine.estimate([], [], max_tokens=4096)
            for _ in range(10)
        ]
        first = results[0]
        for result in results[1:]:
            assert result == first


# ------------------------------------------------------------------
# ContextBudgetResult model
# ------------------------------------------------------------------


class TestContextBudgetResult:
    """Tests for the ContextBudgetResult model."""

    def test_frozen(self) -> None:
        """Verify ContextBudgetResult is immutable."""
        result = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=1,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )
        with pytest.raises(AttributeError):
            result.estimated_tokens = 200  # type: ignore[misc]

    def test_equality(self) -> None:
        """Verify equality compares all fields."""
        a = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=1,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )
        b = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=1,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )
        assert a == b

    def test_inequality_on_budget(self) -> None:
        """Verify inequality when within_budget differs."""
        a = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=1,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )
        b = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=1,
            estimated_modules=1,
            within_budget=False,
            truncated=True,
        )
        assert a != b


# ------------------------------------------------------------------
# No forbidden behaviour
# ------------------------------------------------------------------


class TestConstraints:
    """Tests verifying the budget engine respects constraints."""

    def test_no_filesystem_access(self) -> None:
        """Verify the engine does not depend on filesystem paths."""
        engine = ContextBudget()
        # All inputs are in-memory; no file paths needed.
        result = engine.estimate([], [], max_tokens=4096)
        assert isinstance(result, ContextBudgetResult)

    def test_no_tokenizer_dependency(self) -> None:
        """Verify no tokenizer import is used."""
        import inspect

        import packages.context.budget as budget_module

        source = inspect.getsource(budget_module)
        assert "tiktoken" not in source
        assert "huggingface" not in source
        assert "transformers" not in source
