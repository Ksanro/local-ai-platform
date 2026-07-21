"""Tests for the Context Budget Engine.

Verifies estimation constants, formula correctness, budget boundaries,
determinism, and repeated execution stability.
"""

from __future__ import annotations

import pytest

from packages.context.budget import CHARS_PER_TOKEN, ContextBudget
from packages.context.models import ContextBudgetResult, ContextCandidate

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_candidate(
    symbol_id: str,
    qualified_name: str,
    module: str,
    source: str = "",
    source_preview: str = "",
    signature: str = "",
    docstring: str = "",
) -> ContextCandidate:
    """Create a ContextCandidate for testing."""
    return ContextCandidate(
        symbol_id=symbol_id,
        qualified_name=qualified_name,
        module=module,
        source=source,
        source_preview=source_preview,
        signature=signature,
        docstring=docstring,
    )


def _expected_tokens(candidates: list[ContextCandidate], modules: list[str]) -> int:
    """Compute expected token estimate from actual content using CHARS_PER_TOKEN."""
    total_chars = 0
    for candidate in candidates:
        if candidate.source:
            total_chars += len(candidate.source)
        if candidate.source_preview:
            total_chars += len(candidate.source_preview)
        if candidate.signature:
            total_chars += len(candidate.signature)
        if candidate.docstring:
            total_chars += len(candidate.docstring)
        total_chars += len(candidate.qualified_name)
        total_chars += len(candidate.module)
    for module in modules:
        total_chars += len(module)
    return int(total_chars / CHARS_PER_TOKEN) if total_chars > 0 else 0


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------


class TestConstants:
    """Tests for estimation constants."""

    def test_chars_per_token_value(self) -> None:
        """Verify CHARS_PER_TOKEN is 4.0."""
        assert CHARS_PER_TOKEN == 4.0

    def test_ranking_config_exists(self) -> None:
        """Verify RankingConfig is accessible."""
        from packages.context.ranking_config import RankingConfig
        assert hasattr(RankingConfig, 'WEIGHT_EXACT_MATCH')
        assert hasattr(RankingConfig, 'MAX_CANDIDATES')


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
        """Verify single symbol estimate matches content-based formula."""
        engine = ContextBudget()
        candidates = [_make_candidate("a", "main.a", "main.py")]
        result = engine.estimate(candidates, [], max_tokens=4096)
        assert result.estimated_tokens == _expected_tokens(candidates, [])
        assert result.estimated_symbols == 1
        assert result.estimated_modules == 0

    def test_single_module(self) -> None:
        """Verify single module estimate matches content-based formula."""
        engine = ContextBudget()
        result = engine.estimate([], ["main.py"], max_tokens=4096)
        assert result.estimated_tokens == _expected_tokens([], ["main.py"])
        assert result.estimated_symbols == 0
        assert result.estimated_modules == 1

    def test_single_symbol_and_module(self) -> None:
        """Verify one symbol in one module: content-based estimate."""
        engine = ContextBudget()
        candidates = [_make_candidate("a", "main.a", "main.py")]
        result = engine.estimate(candidates, ["main.py"], max_tokens=4096)
        assert result.estimated_tokens == _expected_tokens(candidates, ["main.py"])
        assert result.estimated_symbols == 1
        assert result.estimated_modules == 1

    def test_multiple_symbols(self) -> None:
        """Verify multiple symbols: content-based estimate."""
        engine = ContextBudget()
        candidates = [
            _make_candidate("a", "main.a", "main.py"),
            _make_candidate("b", "main.b", "main.py"),
            _make_candidate("c", "main.c", "main.py"),
        ]
        result = engine.estimate(candidates, [], max_tokens=4096)
        assert result.estimated_tokens == _expected_tokens(candidates, [])

    def test_multiple_modules(self) -> None:
        """Verify multiple modules: content-based estimate."""
        engine = ContextBudget()
        result = engine.estimate([], ["a.py", "b.py", "c.py"], max_tokens=4096)
        assert result.estimated_tokens == _expected_tokens([], ["a.py", "b.py", "c.py"])

    def test_symbols_and_modules(self) -> None:
        """Verify combined: content-based estimate."""
        engine = ContextBudget()
        candidates = [
            _make_candidate("a", "main.a", "main.py"),
            _make_candidate("b", "utils.b", "utils.py"),
        ]
        result = engine.estimate(candidates, ["main.py", "utils.py"], max_tokens=4096)
        assert result.estimated_tokens == _expected_tokens(candidates, ["main.py", "utils.py"])

    def test_duplicate_symbols_count_once(self) -> None:
        """Verify duplicate symbol_ids are counted once."""
        engine = ContextBudget()
        candidates = [
            _make_candidate("a", "main.a", "main.py"),
            _make_candidate("a", "main.a", "other.py"),  # same symbol_id
        ]
        result = engine.estimate(candidates, ["main.py"], max_tokens=4096)
        assert result.estimated_symbols == 1
        # estimated_tokens uses actual content, not per-symbol constants
        assert result.estimated_tokens == _expected_tokens(candidates, ["main.py"])

    def test_monotonic_adding_candidate(self) -> None:
        """Adding a candidate never decreases estimated_tokens."""
        engine = ContextBudget()
        candidates = [_make_candidate("a", "main.a", "main.py")]
        result1 = engine.estimate(candidates, [], max_tokens=4096)
        candidates.append(_make_candidate("b", "main.b", "main.py"))
        result2 = engine.estimate(candidates, [], max_tokens=4096)
        assert result2.estimated_tokens >= result1.estimated_tokens

    def test_long_source_yields_larger_estimate(self) -> None:
        """Long source yields larger estimate than one with only qualified_name."""
        engine = ContextBudget()
        short_candidate = _make_candidate("a", "main.a", "main.py")
        long_candidate = _make_candidate(
            "b", "main.b", "main.py",
            source="def b():\n    " + "x = 1\n" * 100,
        )
        result_short = engine.estimate([short_candidate], [], max_tokens=4096)
        result_long = engine.estimate([long_candidate], [], max_tokens=4096)
        assert result_long.estimated_tokens > result_short.estimated_tokens


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
        max_tok = 4096
        candidates = [_make_candidate("a", "main.a", "main.py")]
        result = engine.estimate(candidates, [], max_tokens=max_tok)
        # The estimate will be some value; within_budget should be True if estimate <= max_tokens
        assert result.within_budget == (result.estimated_tokens <= max_tok)
        assert result.truncated == (result.estimated_tokens > max_tok)

    def test_budget_exceeded(self) -> None:
        """Verify budget exceeded: estimated > max_tokens."""
        engine = ContextBudget()
        candidates = [_make_candidate("a", "main.a", "main.py")]
        result = engine.estimate(candidates, [], max_tokens=0)
        assert result.within_budget is False
        assert result.truncated is True

    def test_budget_boundary_inversion(self) -> None:
        """Verify within_budget is True when estimated <= max_tokens, False otherwise."""
        engine = ContextBudget()
        candidates = [_make_candidate("a", "main.a", "main.py")]
        est = _expected_tokens(candidates, [])

        # Below budget
        result_below = engine.estimate(candidates, [], max_tokens=est + 1)
        assert result_below.within_budget is True
        assert result_below.truncated is False

        # At budget
        result_at = engine.estimate(candidates, [], max_tokens=est)
        assert result_at.within_budget is True
        assert result_at.truncated is False

        # Above budget
        result_above = engine.estimate(candidates, [], max_tokens=est - 1)
        assert result_above.within_budget is False
        assert result_above.truncated is True

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

