"""Tests for the structured Context Package v2.

Verifies:
- primary symbol selection
- supporting symbols ordering and deduplication
- callers/callees alphabetical ordering
- module ordering (alphabetical)
- duplicate prevention
- deterministic ordering
- serialization order
- repeated executions produce identical output

Acceptance Criteria
-------------------

- primary symbol
- supporting symbols
- callers
- callees
- module ordering
- duplicate prevention
- deterministic ordering
- serialization order
- repeated executions identical
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from packages.context.composer import ContextComposer
from packages.context.context_package import (
    ContextMetadata,
    ContextPackage,
    RelationshipSummary,
)
from packages.context.models import (
    ContextBudgetResult,
    ContextCandidate,
    ContextResult,
)

if TYPE_CHECKING:
    pass


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
# Primary Symbol
# ------------------------------------------------------------------


class TestPrimarySymbol:
    """Tests for primary symbol selection."""

    def test_first_candidate_is_primary(self) -> None:
        """Verify the first candidate becomes the primary symbol."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.B", "mod.py", score=50),
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == "mod.A"

    def test_empty_candidates(self) -> None:
        """Verify empty candidates produces empty primary symbol."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == ""

    def test_single_candidate(self) -> None:
        """Verify single candidate becomes primary."""
        candidate = _make_candidate("a", "main.App", "main.py", score=42)
        result = _make_result([candidate], ["main.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == "main.App"

    def test_explicit_primary_symbol(self) -> None:
        """Verify explicit primary symbol is used."""
        candidates = [
            _make_candidate("a", "mod.B", "mod.py", score=50),
            _make_candidate("b", "mod.A", "mod.py", score=100),
        ]
        primary = _make_candidate("p", "mod.Primary", "mod.py", score=200)
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result, primary)

        assert package.primary_symbol == "mod.Primary"


# ------------------------------------------------------------------
# Supporting Symbols
# ------------------------------------------------------------------


class TestSupportingSymbols:
    """Tests for supporting symbols ordering and deduplication."""

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

    def test_no_duplicates(self) -> None:
        """Verify duplicate symbols are removed."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.B", "mod.py", score=50),
            _make_candidate("c", "mod.A", "mod.py", score=30),  # duplicate
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.supporting_symbols == ["mod.B"]
        assert "mod.A" not in package.supporting_symbols

    def test_empty_candidates(self) -> None:
        """Verify empty candidates produces empty supporting symbols."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.supporting_symbols == []

    def test_single_candidate(self) -> None:
        """Verify single candidate produces empty supporting symbols."""
        candidate = _make_candidate("a", "main.App", "main.py")
        result = _make_result([candidate], ["main.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.supporting_symbols == []

    def test_deterministic_order(self) -> None:
        """Verify supporting symbols are deterministically ordered."""
        candidates = [
            _make_candidate("c", "mod.C", "mod.py", score=10),
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.B", "mod.py", score=50),
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        # Primary is first candidate (mod.C), supporting are the rest in order.
        assert package.primary_symbol == "mod.C"
        assert package.supporting_symbols == ["mod.A", "mod.B"]


# ------------------------------------------------------------------
# Related Callers
# ------------------------------------------------------------------


class TestRelatedCallers:
    """Tests for related callers ordering."""

    def test_callers_sorted_alphabetically(self) -> None:
        """Verify callers are sorted alphabetically."""
        candidates = [
            _make_candidate("a", "mod.Z", "mod.py", score=100),
            _make_candidate("b", "mod.A", "mod.py", score=50),
            _make_candidate("c", "mod.M", "mod.py", score=30),
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        # Callers should be sorted alphabetically.
        assert package.related_callers == sorted(package.related_callers)

    def test_empty_callers(self) -> None:
        """Verify empty callers when no candidates."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_callers == []

    def test_no_duplicate_callers(self) -> None:
        """Verify no duplicate callers."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.A", "mod.py", score=50),  # duplicate
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_callers.count("mod.A") <= 1


# ------------------------------------------------------------------
# Related Callees
# ------------------------------------------------------------------


class TestRelatedCallees:
    """Tests for related callees ordering."""

    def test_callees_sorted_alphabetically(self) -> None:
        """Verify callees are sorted alphabetically."""
        candidates = [
            _make_candidate("a", "mod.Z", "mod.py", score=100),
            _make_candidate("b", "mod.A", "mod.py", score=50),
            _make_candidate("c", "mod.M", "mod.py", score=30),
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        # Callees should be sorted alphabetically.
        assert package.related_callees == sorted(package.related_callees)

    def test_empty_callees(self) -> None:
        """Verify empty callees when no candidates."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_callees == []

    def test_no_duplicate_callees(self) -> None:
        """Verify no duplicate callees."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.A", "mod.py", score=50),  # duplicate
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_callees.count("mod.A") <= 1


# ------------------------------------------------------------------
# Module Ordering
# ------------------------------------------------------------------


class TestModuleOrdering:
    """Tests for related modules ordering."""

    def test_modules_sorted_alphabetically(self) -> None:
        """Verify modules are sorted alphabetically."""
        candidates = [
            _make_candidate("a", "mod.Z", "z_module.py", score=100),
            _make_candidate("b", "mod.A", "a_module.py", score=50),
            _make_candidate("c", "mod.M", "m_module.py", score=30),
        ]
        result = _make_result(candidates, ["z_module.py", "a_module.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_modules == sorted(package.related_modules)

    def test_empty_modules(self) -> None:
        """Verify empty modules when no candidates."""
        result = _make_result([], [])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_modules == []

    def test_unique_modules(self) -> None:
        """Verify modules are unique."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.B", "mod.py", score=50),
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_modules.count("mod.py") == 1


# ------------------------------------------------------------------
# Duplicate Prevention
# ------------------------------------------------------------------


class TestDuplicatePrevention:
    """Tests for duplicate prevention across all collections."""

    def test_no_duplicate_supporting_symbols(self) -> None:
        """Verify no duplicate supporting symbols."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.A", "mod.py", score=50),
            _make_candidate("c", "mod.A", "mod.py", score=30),
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.supporting_symbols.count("mod.A") <= 1

    def test_no_duplicate_callers(self) -> None:
        """Verify no duplicate callers."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.A", "mod.py", score=50),
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_callers.count("mod.A") <= 1

    def test_no_duplicate_callees(self) -> None:
        """Verify no duplicate callees."""
        candidates = [
            _make_candidate("a", "mod.A", "mod.py", score=100),
            _make_candidate("b", "mod.A", "mod.py", score=50),
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.related_callees.count("mod.A") <= 1


# ------------------------------------------------------------------
# Deterministic Ordering
# ------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests for deterministic ordering."""

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
            assert package.primary_symbol == first.primary_symbol
            assert package.supporting_symbols == first.supporting_symbols
            assert package.related_callers == first.related_callers
            assert package.related_callees == first.related_callees
            assert package.related_modules == first.related_modules
            assert (
                package.relationship_summary == first.relationship_summary
            )

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

        assert package_a.primary_symbol == package_b.primary_symbol
        assert package_a.supporting_symbols == package_b.supporting_symbols
        assert package_a.related_callers == package_b.related_callers
        assert package_a.related_callees == package_b.related_callees
        assert package_a.related_modules == package_b.related_modules
        assert (
            package_a.relationship_summary == package_b.relationship_summary
        )

    def test_empty_context_deterministic(self) -> None:
        """Verify empty context is deterministic."""
        ctx_result = _make_result([], [])
        composer = ContextComposer()
        packages = [composer.compose(ctx_result) for _ in range(10)]

        first = packages[0]
        for package in packages[1:]:
            assert package.primary_symbol == first.primary_symbol
            assert package.supporting_symbols == first.supporting_symbols
            assert package.related_callers == first.related_callers
            assert package.related_callees == first.related_callees
            assert package.related_modules == first.related_modules


# ------------------------------------------------------------------
# Serialization Order
# ------------------------------------------------------------------


class TestSerializationOrder:
    """Tests for serialization order."""

    def test_repository_context_sections_in_order(self) -> None:
        """Verify repository context sections appear in correct order."""
        from packages.serializers.openai import OpenAISerializer

        package = ContextPackage(
            primary_symbol="auth.Auth",
            supporting_symbols=["auth.Helper", "utils.Util"],
            related_callers=["main.create_app"],
            related_callees=["auth.Token.create"],
            related_modules=["auth.py", "main.py", "utils.py"],
            relationship_summary=RelationshipSummary(
                caller_count=1,
                callee_count=1,
                module_count=3,
                symbol_count=4,
            ),
            estimated_tokens=230,
        )

        serializer = OpenAISerializer()
        messages = [{"role": "user", "content": "test query"}]
        provider_request = serializer.serialize(package, messages)

        # Find the repository context message (user role with context).
        repo_context = None
        for msg in provider_request.messages:
            if msg["role"] == "user" and "Primary symbol:" in msg["content"]:
                repo_context = msg["content"]
                break

        assert repo_context is not None

        # Verify section order by checking content positions.
        primary_pos = repo_context.index("Primary symbol:")
        supporting_pos = repo_context.index("Supporting symbols:")
        callers_pos = repo_context.index("Related callers:")
        callees_pos = repo_context.index("Related callees:")
        modules_pos = repo_context.index("Related modules:")

        # Verify order: primary before supporting before callers before
        # callees before modules.
        assert primary_pos < supporting_pos < callers_pos < callees_pos < modules_pos

    def test_empty_package_no_context(self) -> None:
        """Verify empty package produces no repository context."""
        from packages.serializers.openai import OpenAISerializer

        package = ContextPackage()
        serializer = OpenAISerializer()
        messages = [{"role": "user", "content": "test query"}]
        provider_request = serializer.serialize(package, messages)

        # Only system message and user messages, no repo context.
        repo_contexts = [
            msg for msg in provider_request.messages
            if msg["role"] == "user"
            and "Primary symbol:" in msg.get("content", "")
        ]
        assert len(repo_contexts) == 0

    def test_relationship_summary_included(self) -> None:
        """Verify relationship summary appears in output."""
        from packages.serializers.openai import OpenAISerializer

        package = ContextPackage(
            primary_symbol="auth.Auth",
            supporting_symbols=["auth.Helper"],
            related_callers=["main.create_app"],
            related_callees=["auth.Token.create"],
            related_modules=["auth.py", "main.py"],
            relationship_summary=RelationshipSummary(
                caller_count=1,
                callee_count=1,
                module_count=2,
                symbol_count=3,
            ),
            estimated_tokens=230,
        )

        serializer = OpenAISerializer()
        messages = [{"role": "user", "content": "test query"}]
        provider_request = serializer.serialize(package, messages)

        repo_context = None
        for msg in provider_request.messages:
            if msg["role"] == "user" and "Relationship summary:" in msg["content"]:
                repo_context = msg["content"]
                break

        assert repo_context is not None
        assert "Relationship summary:" in repo_context
        assert "1 callers" in repo_context
        assert "1 callees" in repo_context
        assert "2 modules" in repo_context
        assert "3 symbols" in repo_context


# ------------------------------------------------------------------
# ContextPackage Model
# ------------------------------------------------------------------


class TestContextPackage:
    """Tests for the ContextPackage model."""

    def test_creation(self) -> None:
        """Verify ContextPackage can be created."""
        package = ContextPackage(
            primary_symbol="auth.Auth",
            supporting_symbols=["auth.Helper"],
            related_callers=["main.create_app"],
            related_callees=["auth.Token.create"],
            related_modules=["auth.py", "main.py"],
            estimated_tokens=230,
        )
        assert package.primary_symbol == "auth.Auth"
        assert package.supporting_symbols == ["auth.Helper"]
        assert package.related_callers == ["main.create_app"]
        assert package.related_callees == ["auth.Token.create"]
        assert package.related_modules == ["auth.py", "main.py"]
        assert package.estimated_tokens == 230

    def test_defaults(self) -> None:
        """Verify ContextPackage defaults."""
        package = ContextPackage()
        assert package.primary_symbol == ""
        assert package.supporting_symbols == []
        assert package.related_callers == []
        assert package.related_callees == []
        assert package.related_modules == []
        assert package.estimated_tokens == 0

    def test_frozen(self) -> None:
        """Verify ContextPackage is immutable."""
        package = ContextPackage(primary_symbol="test")
        with pytest.raises(AttributeError):
            package.primary_symbol = "changed"  # type: ignore[misc]

    def test_deduplication_in_post_init(self) -> None:
        """Verify deduplication happens in __post_init__."""
        package = ContextPackage(
            primary_symbol="auth.Auth",
            supporting_symbols=["auth.A", "auth.B", "auth.A", "auth.C"],
        )
        assert package.supporting_symbols == ["auth.A", "auth.B", "auth.C"]


# ------------------------------------------------------------------
# RelationshipSummary Model
# ------------------------------------------------------------------


class TestRelationshipSummary:
    """Tests for the RelationshipSummary model."""

    def test_creation(self) -> None:
        """Verify RelationshipSummary can be created."""
        summary = RelationshipSummary(
            caller_count=1,
            callee_count=2,
            module_count=3,
            symbol_count=4,
        )
        assert summary.caller_count == 1
        assert summary.callee_count == 2
        assert summary.module_count == 3
        assert summary.symbol_count == 4

    def test_defaults(self) -> None:
        """Verify RelationshipSummary defaults."""
        summary = RelationshipSummary()
        assert summary.caller_count == 0
        assert summary.callee_count == 0
        assert summary.module_count == 0
        assert summary.symbol_count == 0

    def test_frozen(self) -> None:
        """Verify RelationshipSummary is immutable."""
        summary = RelationshipSummary(caller_count=1)
        with pytest.raises(AttributeError):
            summary.caller_count = 2  # type: ignore[misc]


# ------------------------------------------------------------------
# ContextMetadata Model
# ------------------------------------------------------------------


class TestContextMetadata:
    """Tests for the ContextMetadata model."""

    def test_creation(self) -> None:
        """Verify ContextMetadata can be created."""
        metadata = ContextMetadata(
            ranking_version="2",
            repository_revision="abc123",
            estimated_tokens=500,
        )
        assert metadata.ranking_version == "2"
        assert metadata.repository_revision == "abc123"
        assert metadata.estimated_tokens == 500
        assert metadata.generated_at is None

    def test_defaults(self) -> None:
        """Verify ContextMetadata defaults."""
        metadata = ContextMetadata()
        assert metadata.ranking_version == "1"
        assert metadata.repository_revision == ""
        assert metadata.estimated_tokens == 0
        assert metadata.generated_at is None

    def test_frozen(self) -> None:
        """Verify ContextMetadata is immutable."""
        metadata = ContextMetadata(ranking_version="2")
        with pytest.raises(AttributeError):
            metadata.ranking_version = "3"  # type: ignore[misc]

    def test_generated_at_must_be_none_for_determinism(self) -> None:
        """Verify generated_at is None by default for determinism."""
        metadata = ContextMetadata()
        assert metadata.generated_at is None


# ------------------------------------------------------------------
# No Forbidden Behaviour
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
            if not stripped.startswith("import ") and not stripped.startswith(
                "from "
            ):
                continue
            assert "openai" not in stripped.lower()
            assert "anthropic" not in stripped.lower()
            assert "dspark" not in stripped.lower()

    def test_no_prompt_generation(self) -> None:
        """Verify the composer does not generate prompts."""
        composer = ContextComposer()
        result = _make_result([], [])
        package = composer.compose(result)
        # No query field in the new model — the composer does not fabricate
        # content.
        assert package.primary_symbol == ""

    def test_no_tokenization(self) -> None:
        """Verify no tokenizer is used."""
        import inspect

        import packages.context.composer as composer_module

        source = inspect.getsource(composer_module)
        assert "tiktoken" not in source
        assert "huggingface" not in source
        assert "transformers" not in source

    def test_context_package_does_not_access_providers(self) -> None:
        """Verify ContextPackage does not import providers."""
        import inspect

        import packages.context.context_package as module

        source = inspect.getsource(module)
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped.startswith("import ") and not stripped.startswith(
                "from "
            ):
                continue
            assert "openai" not in stripped.lower()
            assert "anthropic" not in stripped.lower()
            assert "dspark" not in stripped.lower()

    def test_context_package_does_not_serialize(self) -> None:
        """Verify ContextPackage does not serialize itself."""
        import inspect

        import packages.context.context_package as module

        source = inspect.getsource(module)
        assert "json.dumps" not in source
        assert "json.loads" not in source
        assert "pickle" not in source
        assert "to_dict" not in source

    def test_context_package_does_not_rank(self) -> None:
        """Verify ContextPackage does not perform ranking."""
        import inspect

        import packages.context.context_package as module

        source = inspect.getsource(module)
        # Remove known allowed occurrences of "rank" in field names.
        cleaned = source.lower()
        cleaned = cleaned.replace("ranking_version", "")
        cleaned = cleaned.replace("ranked", "")
        # Check that no ranking logic (rank(), ranking engine, etc.) exists.
        assert "def rank" not in cleaned
        assert "rankingengine" not in cleaned
        assert ".rank(" not in cleaned

    def test_context_package_does_not_access_repository(self) -> None:
        """Verify ContextPackage does not access RepositoryIndex."""
        import inspect

        import packages.context.context_package as module

        source = inspect.getsource(module)
        assert "RepositoryIndex" not in source
        assert "symbol_graph" not in source


# ------------------------------------------------------------------
# Edge Cases
# ------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_only_primary_symbol(self) -> None:
        """Verify package with only primary symbol."""
        candidate = _make_candidate("a", "main.App", "main.py")
        result = _make_result([candidate], ["main.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == "main.App"
        assert package.supporting_symbols == []
        assert package.related_callers == []
        assert package.related_callees == []

    def test_many_duplicates(self) -> None:
        """Verify many duplicates are handled."""
        candidates = [
            _make_candidate(str(i), "mod.Same", "mod.py", score=i)
            for i in range(20)
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == "mod.Same"
        assert package.supporting_symbols == []

    def test_all_same_module(self) -> None:
        """Verify all symbols in same module."""
        candidates = [
            _make_candidate(str(i), f"mod.Symbol{i}", "mod.py", score=i)
            for i in range(5)
        ]
        result = _make_result(candidates, ["mod.py"])
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == "mod.Symbol0"
        assert "mod.py" in package.related_modules
        assert package.related_modules.count("mod.py") == 1

    def test_all_different_modules(self) -> None:
        """Verify all symbols in different modules."""
        candidates = [
            _make_candidate(str(i), f"mod{i}.Symbol", f"mod{i}.py", score=i)
            for i in range(5)
        ]
        result = _make_result(
            candidates, [f"mod{i}.py" for i in range(5)]
        )
        composer = ContextComposer()
        package = composer.compose(result)

        assert package.primary_symbol == "mod0.Symbol"
        assert len(package.related_modules) == 5
        assert package.related_modules == sorted(package.related_modules)
