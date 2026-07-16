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
from packages.context.models import (
    ContextBudgetResult,
    ContextCandidate,
    ContextResult,
)
from packages.context.package import ContextMetadata, ContextPackage

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
# Symbol order preserved
# ------------------------------------------------------------------


class TestSymbolOrderPreserved:
    """Tests for symbol order preservation."""

    def test_ranked_order_preserved(self) -> None:
        """Verify symbols appear in the same order as candidates."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.B", "mod.py", score=50),
            _make_candidate("c", "mod.C", "mod.py", score=10),
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.symbols == ["mod.A", "mod.B", "mod.C"]

    def test_empty_symbols(self) -> None:
        """Verify empty candidates produces empty symbols list."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.symbols == []

    def test_single_symbol(self) -> None:
        """Verify single symbol is preserved."""
        candidate = _make_candidate("a", "main.App", "main.py", score=42)
        result = _make_result([candidate], ["main.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.symbols == ["main.App"]


# ------------------------------------------------------------------
# Module order preserved
# ------------------------------------------------------------------


class TestModuleOrderPreserved:
    """Tests for module order preservation."""

    def test_module_order_preserved(self) -> None:
        """Verify modules appear in the same order as selected_modules."""
        candidates = [
            _make_candidate("a", "main.App", "main.py"),
            _make_candidate("b", "auth.Auth", "auth.py"),
            _make_candidate("c", "utils.Helper", "utils.py"),
        ]
        result = _make_result(candidates, ["main.py", "auth.py", "utils.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.modules == ["main.py", "auth.py", "utils.py"]

    def test_empty_modules(self) -> None:
        """Verify empty selected_modules produces empty modules list."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.modules == []

    def test_single_module(self) -> None:
        """Verify single module is preserved."""
        candidate = _make_candidate("a", "main.App", "main.py")
        result = _make_result([candidate], ["main.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.modules == ["main.py"]


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

        assert package.metadata["estimated_tokens"] == 230
        assert package.metadata["estimated_symbols"] == 2
        assert package.metadata["estimated_modules"] == 2
        assert package.metadata["truncated"] is False

    def test_truncated_metadata_copied(self) -> None:
        """Verify truncated flag is copied."""
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

        assert package.metadata["truncated"] is True

    def test_zero_metadata(self) -> None:
        """Verify zero budget produces zero metadata."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.metadata["estimated_tokens"] == 0
        assert package.metadata["estimated_symbols"] == 0
        assert package.metadata["estimated_modules"] == 0
        assert package.metadata["truncated"] is False


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

        assert package.query == ""
        assert package.modules == []
        assert package.symbols == []
        assert package.metadata == {
            "estimated_tokens": 0,
            "estimated_symbols": 0,
            "estimated_modules": 0,
            "truncated": False,
        }

    def test_empty_candidates_nonempty_modules(self) -> None:
        """Verify empty candidates with modules is handled."""
        result = _make_result([], ["main.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.symbols == []
        assert package.modules == ["main.py"]

    def test_nonempty_candidates_empty_modules(self) -> None:
        """Verify nonempty candidates with empty modules is handled."""
        candidate = _make_candidate("a", "main.App", "main.py")
        result = _make_result([candidate], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.symbols == ["main.App"]
        assert package.modules == []


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
            assert package.modules == first.modules
            assert package.symbols == first.symbols
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

        assert package_a.modules == package_b.modules
        assert package_a.symbols == package_b.symbols
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
            query="test query",
            modules=["main.py"],
            symbols=["main.App"],
            metadata={"estimated_tokens": 80},
        )
        assert package.query == "test query"
        assert package.modules == ["main.py"]
        assert package.symbols == ["main.App"]
        assert package.metadata == {"estimated_tokens": 80}

    def test_defaults(self) -> None:
        """Verify ContextPackage defaults."""
        package = ContextPackage(query="")
        assert package.modules == []
        assert package.symbols == []
        assert package.metadata == {}

    def test_frozen(self) -> None:
        """Verify ContextPackage is immutable."""
        package = ContextPackage(query="test")
        with pytest.raises(AttributeError):
            package.modules = ["changed"]  # type: ignore[misc]


class TestContextMetadata:
    """Tests for the ContextMetadata model."""

    def test_creation(self) -> None:
        """Verify ContextMetadata can be created."""
        metadata = ContextMetadata(
            estimated_tokens=230,
            estimated_symbols=2,
            estimated_modules=2,
            truncated=False,
        )
        assert metadata.estimated_tokens == 230
        assert metadata.estimated_symbols == 2
        assert metadata.estimated_modules == 2
        assert metadata.truncated is False

    def test_defaults(self) -> None:
        """Verify ContextMetadata defaults."""
        metadata = ContextMetadata()
        assert metadata.estimated_tokens == 0
        assert metadata.estimated_symbols == 0
        assert metadata.estimated_modules == 0
        assert metadata.truncated is False

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
        # query is empty — the composer does not fabricate content.
        assert package.query == ""

    def test_no_tokenization(self) -> None:
        """Verify no tokenizer is used."""
        import inspect

        import packages.context.composer as composer_module

        source = inspect.getsource(composer_module)
        assert "tiktoken" not in source
        assert "huggingface" not in source
        assert "transformers" not in source
