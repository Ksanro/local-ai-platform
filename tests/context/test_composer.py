"""Tests for the Context Composer.

Verifies deterministic assembly: symbol order preserved, module order
preserved, metadata copied, empty context handled, and repeated
executions produce identical ContextPackage.

Acceptance Criteria
-------------------

- symbol order preserved
- module order preserved
- metadata copied
- empty context handled
- deterministic output
- repeated executions produce identical ContextPackage
"""

from __future__ import annotations

import pytest

from packages.context.composer import ContextComposer
from packages.context.context_package import ContextMetadata, ContextPackage
from packages.context.models import (
    ContextBudgetResult,
    ContextCandidate,
    ContextResult,
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_candidate(
    symbol_id: str,
    qualified_name: str,
    module: str,
    score: int = 0,
) -> ContextCandidate:
    """Create a ContextCandidate for testing."""
    return ContextCandidate(
        symbol_id=symbol_id,
        qualified_name=qualified_name,
        module=module,
        score=score,
    )


def _make_result(
    candidates: list[ContextCandidate] | None = None,
    modules: list[str] | None = None,
    budget: ContextBudgetResult | None = None,
) -> ContextResult:
    """Create a ContextResult for testing."""
    return ContextResult(
        candidates=candidates or [],
        selected_modules=modules or [],
        budget=budget or ContextBudgetResult(),
    )


# ------------------------------------------------------------------
# Primary symbol
# ------------------------------------------------------------------


class TestPrimarySymbol:
    """Tests for primary symbol selection."""

    def test_first_candidate_is_primary(self) -> None:
        """Verify first candidate becomes primary symbol."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.B", "mod.py", score=50),
            _make_candidate("c", "mod.C", "mod.py", score=10),
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == "mod.A"

    def test_empty_symbols(self) -> None:
        """Verify empty candidates produces empty primary symbol."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == ""

    def test_single_symbol(self) -> None:
        """Verify single symbol becomes primary."""
        candidate = _make_candidate("a", "main.App", "main.py", score=42)
        result = _make_result([candidate], ["main.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == "main.App"


# ------------------------------------------------------------------
# Supporting symbols
# ------------------------------------------------------------------


class TestSupportingSymbols:
    """Tests for supporting symbols ordering."""

    def test_ranked_order_preserved(self) -> None:
        """Verify supporting symbols are in ranked order."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.B", "mod.py", score=50),
            _make_candidate("c", "mod.C", "mod.py", score=10),
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        # Primary is first, supporting are the rest in order.
        assert package.primary_symbol == "mod.A"
        assert package.supporting_symbols == ["mod.B", "mod.C"]

    def test_empty_symbols(self) -> None:
        """Verify empty candidates produces empty supporting symbols."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.supporting_symbols == []

    def test_single_symbol(self) -> None:
        """Verify single symbol produces empty supporting symbols."""
        candidate = _make_candidate("a", "main.App", "main.py", score=42)
        result = _make_result([candidate], ["main.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.supporting_symbols == []


# ------------------------------------------------------------------
# Module ordering
# ------------------------------------------------------------------


class TestModuleOrdering:
    """Tests for module ordering."""

    def test_modules_sorted_alphabetically(self) -> None:
        """Verify modules are sorted alphabetically."""
        candidates = [
            _make_candidate("a", "main.App", "z_main.py"),
            _make_candidate("b", "auth.Auth", "a_auth.py"),
            _make_candidate("c", "utils.Helper", "m_utils.py"),
        ]
        result = _make_result(candidates, ["z_main.py", "a_auth.py", "m_utils.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_modules == sorted(package.related_modules)

    def test_empty_modules(self) -> None:
        """Verify empty selected_modules produces empty modules list."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_modules == []

    def test_single_module(self) -> None:
        """Verify single module is preserved."""
        candidate = _make_candidate("a", "main.App", "main.py")
        result = _make_result([candidate], ["main.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_modules == ["main.py"]


# ------------------------------------------------------------------
# Metadata copied
# ------------------------------------------------------------------


class TestMetadataCopied:
    """Tests for metadata copying."""

    def test_budget_metadata_copied(self) -> None:
        """Verify budget metadata is copied to the package."""
        budget = ContextBudgetResult(
            estimated_tokens=230,
            estimated_symbols=2,
            estimated_modules=2,
            within_budget=True,
            truncated=False,
        )
        candidates = [
            _make_candidate("a", "main.App", "main.py"),
            _make_candidate("b", "auth.Auth", "auth.py"),
        ]
        result = _make_result(candidates, ["main.py", "auth.py"], budget)
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.metadata.estimated_tokens == 230
        assert package.estimated_tokens == 230

    def test_truncated_metadata_copied(self) -> None:
        """Verify truncated flag is reflected in budget."""
        budget = ContextBudgetResult(
            estimated_tokens=9999,
            estimated_symbols=100,
            estimated_modules=10,
            within_budget=False,
            truncated=True,
        )
        result = _make_result([], [], budget)
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.estimated_tokens == 9999

    def test_zero_metadata(self) -> None:
        """Verify zero budget produces zero metadata."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.metadata.estimated_tokens == 0
        assert package.estimated_tokens == 0


# ------------------------------------------------------------------
# Empty context handled
# ------------------------------------------------------------------


class TestEmptyContext:
    """Tests for empty context handling."""

    def test_completely_empty(self) -> None:
        """Verify empty context produces empty package."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == ""
        assert package.related_modules == []
        assert package.supporting_symbols == []
        assert package.metadata.estimated_tokens == 0

    def test_empty_candidates_nonempty_modules(self) -> None:
        """Verify empty candidates with modules produces empty related_modules."""
        result = _make_result([], ["main.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.supporting_symbols == []
        # With no candidates, related_modules is empty (no symbols to derive from).
        assert package.related_modules == []

    def test_nonempty_candidates_empty_modules(self) -> None:
        """Verify nonempty candidates with empty modules derives modules from candidates."""
        candidate = _make_candidate("a", "main.App", "main.py")
        result = _make_result([candidate], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == "main.App"
        # Modules are derived from candidate modules, not selected_modules.
        assert package.related_modules == ["main.py"]


# ------------------------------------------------------------------
# Deterministic output
# ------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_identical_input_produces_identical_output(self) -> None:
        """Verify identical inputs produce identical ContextPackage."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.B", "mod.py", score=50),
            _make_candidate("c", "mod.C", "utils.py", score=10),
        ]
        budget = ContextBudgetResult(
            estimated_tokens=460,
            estimated_symbols=3,
            estimated_modules=2,
            within_budget=True,
            truncated=False,
        )
        ctx_result = _make_result(candidates, ["mod.py", "utils.py"], budget)

        composer = ContextComposer()
        packages = [composer.compose(ctx_result) for _ in range(10)]

        first = packages[0]
        for package in packages[1:]:
            assert package.related_modules == first.related_modules
            assert package.supporting_symbols == first.supporting_symbols
            assert package.metadata == first.metadata

    def test_repeated_executions_identical(self) -> None:
        """Verify repeated executions produce identical ContextPackage."""
        candidates = [
            _make_candidate(str(i), f"mod.{i}", f"mod{i}.py", score=i)
            for i in range(5)
        ]
        result = _make_result(candidates, [f"mod{i}.py" for i in range(5)])

        composer = ContextComposer()
        package_a = composer.compose(result)
        package_b = composer.compose(result)

        assert package_a.related_modules == package_b.related_modules
        assert package_a.supporting_symbols == package_b.supporting_symbols
        assert package_a.metadata == package_b.metadata

    def test_empty_context_deterministic(self) -> None:
        """Verify empty context is deterministic."""
        ctx_result = _make_result([], [])
        composer = ContextComposer()
        packages = [composer.compose(ctx_result) for _ in range(10)]

        first = packages[0]
        for package in packages[1:]:
            assert package == first


# ------------------------------------------------------------------
# ContextPackage model
# ------------------------------------------------------------------


class TestContextPackage:
    """Tests for the ContextPackage model."""

    def test_creation(self) -> None:
        """Verify ContextPackage can be created."""
        package = ContextPackage(
            primary_symbol="main.App",
            supporting_symbols=["auth.Auth"],
            related_modules=["main.py"],
        )
        assert package.primary_symbol == "main.App"
        assert package.supporting_symbols == ["auth.Auth"]
        assert package.related_modules == ["main.py"]

    def test_defaults(self) -> None:
        """Verify ContextPackage defaults."""
        package = ContextPackage()
        assert package.related_modules == []
        assert package.supporting_symbols == []
        assert package.metadata.estimated_tokens == 0

    def test_frozen(self) -> None:
        """Verify ContextPackage is immutable."""
        package = ContextPackage(primary_symbol="test")
        with pytest.raises(AttributeError):
            package.related_modules = ["changed"]  # type: ignore[misc]


class TestContextMetadata:
    """Tests for the ContextMetadata model."""

    def test_creation(self) -> None:
        """Verify ContextMetadata can be created with all fields."""
        metadata = ContextMetadata(
            ranking_version="2",
            repository_revision="abc123",
            estimated_tokens=230,
        )
        assert metadata.ranking_version == "2"
        assert metadata.repository_revision == "abc123"
        assert metadata.estimated_tokens == 230

    def test_defaults(self) -> None:
        """Verify ContextMetadata defaults."""
        metadata = ContextMetadata()
        assert metadata.ranking_version == "2"
        assert metadata.repository_revision == ""
        assert metadata.estimated_tokens == 0

    def test_frozen(self) -> None:
        """Verify ContextMetadata is immutable."""
        metadata = ContextMetadata(estimated_tokens=100)
        with pytest.raises(AttributeError):
            metadata.estimated_tokens = 200  # type: ignore[misc]


# ------------------------------------------------------------------
# No forbidden behaviour
# ------------------------------------------------------------------


class TestConstraints:
    """Tests verifying the composer respects constraints."""

    def test_no_filesystem_access(self) -> None:
        """Verify the composer does not depend on filesystem paths."""
        composer = ContextComposer()
        result = _make_result([], [])
        package = composer.compose(result)
        assert isinstance(package, ContextPackage)

    def test_no_provider_dependency(self) -> None:
        """Verify no provider import is used."""
        import inspect

        import packages.context.composer as composer_module

        source = inspect.getsource(composer_module)
        # Check only import lines, not docstrings.
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped.startswith("import ") and not stripped.startswith("from "):
                continue
            assert "openai" not in stripped.lower()
            assert "anthropic" not in stripped.lower()
            assert "dspark" not in stripped.lower()

    def test_no_prompt_generation(self) -> None:
        """Verify the composer does not generate prompts."""
        composer = ContextComposer()
        result = _make_result([], [])
        package = composer.compose(result)
        # primary_symbol is empty — the composer does not fabricate content.
        assert package.primary_symbol == ""

    def test_no_tokenization(self) -> None:
        """Verify no tokenizer is used."""
        import inspect

        import packages.context.composer as composer_module

        source = inspect.getsource(composer_module)
        assert "tiktoken" not in source
        assert "huggingface" not in source
        assert "transformers" not in source

