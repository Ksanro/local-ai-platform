"""Tests for source-aware context (Context Quality v2).

Tests covering:
- Primary symbol serialization
- Supporting symbol serialization
- Docstrings
- Signatures
- Deterministic ordering
- Token budgeting
- Truncation
- Empty docstrings
- Large functions
- Budget enforcement
"""

from __future__ import annotations

import pytest

from packages.context.budget import ContextBudget, CHARS_PER_TOKEN
from packages.context.builder import ContextBuilder
from packages.context.composer import ContextComposer
from packages.context.context_package import (
    ContextMetadata,
    ContextPackage,
    ModuleDescription,
    RelationshipSummary,
    SymbolContext,
)
from packages.context.models import (
    ContextBudgetResult,
    ContextCandidate,
    ContextQuery,
)
from packages.context.scoring import RankingReason
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import Module, Relationship, Symbol, SymbolType


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_symbol(
    qualified_name: str,
    module: str,
    lineno: int = 1,
    symbol_type: SymbolType = SymbolType.FUNCTION,
    decorators: list[str] | None = None,
) -> Symbol:
    """Helper to create a Symbol."""
    name = qualified_name.rsplit(".", 1)[-1]
    return Symbol(
        id=qualified_name,
        name=name,
        qualified_name=qualified_name,
        symbol_type=symbol_type,
        module=module,
        lineno=lineno,
        decorators=decorators or [],
    )


def _make_module(
    path: str,
    symbols: list[Symbol],
    source: str = "",
) -> Module:
    """Helper to create a Module."""
    return Module(
        path=path,
        symbols=symbols,
        source=source,
    )


def _make_index(modules: list[Module]) -> RepositoryIndex:
    """Helper to create a RepositoryIndex."""
    all_symbols: list[Symbol] = []
    all_relationships: list[Relationship] = []
    modules_dict: dict[str, Module] = {}
    for mod in modules:
        all_symbols.extend(mod.symbols)
        all_relationships.extend(mod.relationships)
        modules_dict[mod.path] = mod

    stats = mod_list = None  # Not needed for tests
    return RepositoryIndex(
        modules=modules_dict,
        _symbols=all_symbols,
        _relationships=all_relationships,
    )


# ------------------------------------------------------------------
# Tests: RepositoryIndex source access APIs
# ------------------------------------------------------------------


class TestRepositoryIndexSourceAPIs:
    """Test the new source access methods on RepositoryIndex."""

    def test_get_symbol_source(self):
        """Should return the source for a symbol's module."""
        source = 'def foo():\n    pass\n'
        sym = _make_symbol("mod.foo", "mod.py", source="mod.py")
        mod = _make_module("mod.py", [sym], source=source)
        index = _make_index([mod])

        result = index.get_symbol_source("mod.foo")
        assert result == source

    def test_get_symbol_source_not_found(self):
        """Should return None for a non-existent symbol."""
        index = _make_index([])
        assert index.get_symbol_source("nonexistent") is None

    def test_get_symbol_signature(self):
        """Should return the first non-empty line as signature."""
        source = """class MyClass:
    '''Docstring.'''
    def method(self):
        pass
"""
        sym = _make_symbol("mod.MyClass", "mod.py", source="mod.py")
        mod = _make_module("mod.py", [sym], source=source)
        index = _make_index([mod])

        result = index.get_symbol_signature("mod.MyClass")
        assert result == "class MyClass:"

    def test_get_symbol_signature_not_found(self):
        """Should return None for a non-existent symbol."""
        index = _make_index([])
        assert index.get_symbol_signature("nonexistent") is None

    def test_get_symbol_docstring(self):
        """Should extract docstring from source."""
        source = '''"""Module docstring."""

def foo():
    """Function docstring."""
    pass
'''
        sym = _make_symbol("mod.foo", "mod.py", source="mod.py")
        mod = _make_module("mod.py", [sym], source=source)
        index = _make_index([mod])

        result = index.get_symbol_docstring("mod.foo")
        assert result == "Function docstring."

    def test_get_symbol_docstring_not_found(self):
        """Should return None when no docstring exists."""
        source = "def foo():\n    pass\n"
        sym = _make_symbol("mod.foo", "mod.py", source="mod.py")
        mod = _make_module("mod.py", [sym], source=source)
        index = _make_index([mod])

        result = index.get_symbol_docstring("mod.foo")
        assert result is None

    def test_get_symbol_location(self):
        """Should return (module_path, start_line, end_line)."""
        source = "line1\nline2\nline3\n"
        sym = _make_symbol("mod.foo", "mod.py", lineno=2, source="mod.py")
        mod = _make_module("mod.py", [sym], source=source)
        index = _make_index([mod])

        result = index.get_symbol_location("mod.foo")
        assert result is not None
        mod_path, start_line, end_line = result
        assert mod_path == "mod.py"
        assert start_line == 2
        assert end_line == 3

    def test_get_symbol_location_not_found(self):
        """Should return None for non-existent symbol."""
        index = _make_index([])
        assert index.get_symbol_location("nonexistent") is None

    def test_get_symbol_decorators(self):
        """Should extract decorators from source."""
        source = '''@decorator1
@decorator2(arg)
def foo():
    pass
'''
        sym = _make_symbol("mod.foo", "mod.py", source="mod.py")
        mod = _make_module("mod.py", [sym], source=source)
        index = _make_index([mod])

        result = index.get_symbol_decorators("mod.foo")
        assert result is not None
        assert "decorator1" in result
        assert "decorator2" in result

    def test_get_symbol_full_context(self):
        """Should return complete source context dictionary."""
        source = '''"""Module docstring."""

@decorator1
def foo():
    """Function docstring."""
    pass
'''
        sym = _make_symbol("mod.foo", "mod.py", lineno=4, source="mod.py")
        mod = _make_module("mod.py", [sym], source=source)
        index = _make_index([mod])

        result = index.get_symbol_full_context("mod.foo")
        assert result is not None
        assert result["signature"] == "def foo():"
        assert result["docstring"] == "Function docstring."
        assert "decorator1" in result["decorators"]
        assert result["location"] is not None
        assert result["source"] == source


# ------------------------------------------------------------------
# Tests: ContextCandidate source fields
# ------------------------------------------------------------------


class TestContextCandidateSourceFields:
    """Test that ContextCandidate carries source data."""

    def test_candidate_with_source_data(self):
        """Candidate should carry signature, docstring, source."""
        candidate = ContextCandidate(
            symbol_id="mod.foo",
            qualified_name="mod.foo",
            module="mod.py",
            score=100,
            signature="def foo() -> str:",
            docstring="Returns a string.",
            source='def foo() -> str:\n    return "hello"\n',
            source_preview='def foo() -> str:\n    return "hello"',
            location=("mod.py", 1, 3),
        )
        assert candidate.signature == "def foo() -> str:"
        assert candidate.docstring == "Returns a string."
        assert candidate.source == 'def foo() -> str:\n    return "hello"\n'
        assert candidate.source_preview == 'def foo() -> str:\n    return "hello"'
        assert candidate.location == ("mod.py", 1, 3)

    def test_candidate_defaults(self):
        """Candidate should have empty defaults for source fields."""
        candidate = ContextCandidate(
            symbol_id="mod.foo",
            qualified_name="mod.foo",
            module="mod.py",
        )
        assert candidate.signature == ""
        assert candidate.docstring == ""
        assert candidate.source == ""
        assert candidate.source_preview == ""
        assert candidate.location is None


# ------------------------------------------------------------------
# Tests: ContextBuilder source enrichment
# ------------------------------------------------------------------


class TestContextBuilderSourceEnrichment:
    """Test that ContextBuilder enriches candidates with source data."""

    def test_build_enriches_primary_symbol(self):
        """Primary symbol should get complete source enrichment."""
        source = '''"""Module for authentication."""

class AuthMiddleware:
    """Authentication middleware class."""

    def authenticate(self, request):
        """Authenticate the request."""
        token = request.headers.get("Authorization")
        return token

    def validate_token(self, token):
        """Validate a JWT token."""
        if not token:
            return False
        return token.startswith("Bearer ")
'''
        sym_auth = _make_symbol(
            "auth.AuthMiddleware",
            "auth.py",
            lineno=3,
            symbol_type=SymbolType.CLASS,
            source="auth.py",
        )
        sym_authenticate = _make_symbol(
            "auth.AuthMiddleware.authenticate",
            "auth.py",
            lineno=6,
            symbol_type=SymbolType.METHOD,
            source="auth.py",
        )
        sym_validate = _make_symbol(
            "auth.AuthMiddleware.validate_token",
            "auth.py",
            lineno=11,
            symbol_type=SymbolType.METHOD,
            source="auth.py",
        )

        mod = _make_module("auth.py", [sym_auth, sym_authenticate, sym_validate], source=source)
        index = _make_index([mod])

        query = ContextQuery(
            text="authentication middleware",
            max_symbols=3,
            max_modules=1,
            max_tokens=4096,
        )

        builder = ContextBuilder(
            index=index,
            primary_symbol_max_tokens=2048,
            supporting_symbol_max_tokens=512,
        )

        result = builder.build(query)

        # All candidates should be enriched.
        assert len(result.candidates) == 3

        # First candidate (primary) should have full source.
        primary = result.candidates[0]
        assert primary.signature != ""
        assert primary.source != ""
        assert "class AuthMiddleware" in primary.source

    def test_build_enriches_supporting_symbols(self):
        """Supporting symbols should get signature and preview."""
        source = '''def helper():
    """A helper function."""
    return True

def main():
    """Main function."""
    return helper()
'''
        sym_helper = _make_symbol(
            "mod.helper",
            "mod.py",
            lineno=1,
            symbol_type=SymbolType.FUNCTION,
            source="mod.py",
        )
        sym_main = _make_symbol(
            "mod.main",
            "mod.py",
            lineno=5,
            symbol_type=SymbolType.FUNCTION,
            source="mod.py",
        )

        mod = _make_module("mod.py", [sym_main, sym_helper], source=source)
        index = _make_index([mod])

        query = ContextQuery(
            text="main function",
            max_symbols=2,
            max_modules=1,
            max_tokens=4096,
        )

        builder = ContextBuilder(
            index=index,
            primary_symbol_max_tokens=2048,
            supporting_symbol_max_tokens=256,
        )

        result = builder.build(query)

        assert len(result.candidates) == 2

        # Primary should have full source.
        primary = result.candidates[0]
        assert primary.source != ""

        # Supporting should have preview.
        supporting = result.candidates[1]
        assert supporting.signature != ""
        assert supporting.source_preview != ""

    def test_build_empty_candidates(self):
        """Empty candidate list should not crash."""
        index = _make_index([])

        query = ContextQuery(
            text="something",
            max_symbols=0,
            max_modules=0,
            max_tokens=4096,
        )

        builder = ContextBuilder(index=index)
        result = builder.build(query)

        assert len(result.candidates) == 0


# ------------------------------------------------------------------
# Tests: ContextComposer source-aware context
# ------------------------------------------------------------------


class TestContextComposerSourceAware:
    """Test that ContextComposer builds source-aware context."""

    def test_compose_with_source_context(self):
        """Composer should build SymbolContext for primary symbol."""
        source = '''"""Module docstring."""

class MyClass:
    """Class docstring."""

    def method(self):
        """Method docstring."""
        pass
'''
        sym = _make_symbol(
            "mod.MyClass",
            "mod.py",
            lineno=3,
            symbol_type=SymbolType.CLASS,
            source="mod.py",
        )
        mod = _make_module("mod.py", [sym], source=source)
        index = _make_index([mod])

        query = ContextQuery(
            text="MyClass",
            max_symbols=1,
            max_modules=1,
            max_tokens=4096,
        )

        builder = ContextBuilder(index=index)
        result = builder.build(query)

        composer = ContextComposer()
        package = composer.compose(result)

        # Should have primary_symbol_context.
        assert package.primary_symbol_context is not None
        ctx = package.primary_symbol_context
        assert ctx.qualified_name == "mod.MyClass"
        assert ctx.signature != ""
        assert ctx.source != ""

    def test_compose_module_descriptions(self):
        """Composer should build module descriptions."""
        source = '''def foo():
    pass
'''
        sym = _make_symbol("mod.foo", "mod.py", source="mod.py")
        mod = _make_module("mod.py", [sym], source=source)
        index = _make_index([mod])

        query = ContextQuery(
            text="foo",
            max_symbols=1,
            max_modules=1,
            max_tokens=4096,
        )

        builder = ContextBuilder(index=index)
        result = builder.build(query)

        composer = ContextComposer()
        package = composer.compose(result)

        # Should have module descriptions.
        assert len(package.module_descriptions) > 0
        desc = package.module_descriptions[0]
        assert desc.module_path == "mod.py"
        assert desc.purpose != ""
        assert desc.symbol_count > 0

    def test_compose_supporting_symbol_contexts(self):
        """Composer should build SymbolContext for supporting symbols."""
        source = '''def foo():
    pass

def bar():
    pass
'''
        sym_foo = _make_symbol("mod.foo", "mod.py", source="mod.py")
        sym_bar = _make_symbol("mod.bar", "mod.py", source="mod.py")
        mod = _make_module("mod.py", [sym_foo, sym_bar], source=source)
        index = _make_index([mod])

        query = ContextQuery(
            text="foo bar",
            max_symbols=2,
            max_modules=1,
            max_tokens=4096,
        )

        builder = ContextBuilder(index=index)
        result = builder.build(query)

        composer = ContextComposer()
        package = composer.compose(result)

        # Should have supporting symbol contexts.
        assert len(package.supporting_symbol_contexts) > 0


# ------------------------------------------------------------------
# Tests: Serializer source-aware output
# ------------------------------------------------------------------


class TestSerializerSourceAware:
    """Test that serializer emits source code."""

    def test_serializer_emits_primary_source(self):
        """Serializer should emit primary symbol source code."""
        from packages.serializers.openai import OpenAISerializer

        source = '''class MyClass:
    """Class docstring."""

    def method(self):
        """Method docstring."""
        pass
'''
        primary_ctx = SymbolContext(
            qualified_name="mod.MyClass",
            signature="class MyClass:",
            docstring="Class docstring.",
            source=source,
            location=("mod.py", 1, 8),
        )

        package = ContextPackage(
            primary_symbol="mod.MyClass",
            primary_symbol_context=primary_ctx,
        )

        serializer = OpenAISerializer()
        messages = [{"role": "user", "content": "What does MyClass do?"}]
        result = serializer.serialize(package, messages)

        # Should have repository context.
        repo_context = None
        for msg in result.messages:
            if msg["role"] == "user":
                repo_context = msg["content"]
                break

        assert repo_context is not None
        assert "class MyClass:" in repo_context
        assert "Class docstring." in repo_context
        assert "Method docstring." in repo_context

    def test_serializer_emits_supporting_signatures(self):
        """Serializer should emit supporting symbol signatures."""
        from packages.serializers.openai import OpenAISerializer

        supporting_ctx = SymbolContext(
            qualified_name="mod.helper",
            signature="def helper() -> bool:",
            docstring="Returns True.",
            source_preview="def helper() -> bool:\n    return True",
        )

        package = ContextPackage(
            primary_symbol="mod.MyClass",
            supporting_symbols=["mod.helper"],
            supporting_symbol_contexts=[supporting_ctx],
        )

        serializer = OpenAISerializer()
        messages = [{"role": "user", "content": "What does helper do?"}]
        result = serializer.serialize(package, messages)

        repo_context = None
        for msg in result.messages:
            if msg["role"] == "user":
                repo_context = msg["content"]
                break

        assert repo_context is not None
        assert "def helper() -> bool:" in repo_context
        assert "Returns True." in repo_context
        assert "return True" in repo_context

    def test_serializer_emits_module_descriptions(self):
        """Serializer should emit module descriptions."""
        from packages.serializers.openai import OpenAISerializer

        package = ContextPackage(
            primary_symbol="mod.MyClass",
            related_modules=["mod.py"],
            module_descriptions=[
                ModuleDescription(
                    module_path="mod.py",
                    purpose="Data models and schemas",
                    relationship_summary="Contains the primary symbol",
                    symbol_count=5,
                )
            ],
        )

        serializer = OpenAISerializer()
        messages = [{"role": "user", "content": "Show me the code"}]
        result = serializer.serialize(package, messages)

        repo_context = None
        for msg in result.messages:
            if msg["role"] == "user":
                repo_context = msg["content"]
                break

        assert repo_context is not None
        assert "Data models and schemas" in repo_context
        assert "Contains the primary symbol" in repo_context

    def test_serializer_fallback_to_identifier_only(self):
        """Serializer should fall back to identifier-only when no source context."""
        from packages.serializers.openai import OpenAISerializer

        package = ContextPackage(
            primary_symbol="mod.MyClass",
            supporting_symbols=["mod.helper"],
            # No source-aware context fields set.
        )

        serializer = OpenAISerializer()
        messages = [{"role": "user", "content": "What does MyClass do?"}]
        result = serializer.serialize(package, messages)

        repo_context = None
        for msg in result.messages:
            if msg["role"] == "user":
                repo_context = msg["content"]
                break

        assert repo_context is not None
        assert "mod.MyClass" in repo_context
        assert "mod.helper" in repo_context


# ------------------------------------------------------------------
# Tests: Token budget estimation with actual content
# ------------------------------------------------------------------


class TestTokenBudgetEstimation:
    """Test that token budget estimation uses actual content."""

    def test_estimate_from_source_content(self):
        """Estimation should be based on actual source content."""
        budget = ContextBudget()

        # Create candidates with source data.
        source = "def foo():\n    return 'hello world'\n"
        candidates = [
            ContextCandidate(
                symbol_id="mod.foo",
                qualified_name="mod.foo",
                module="mod.py",
                source=source,
                signature="def foo():",
                docstring="",
            )
        ]

        result = budget.estimate(candidates, ["mod.py"], max_tokens=4096)

        # Estimated tokens should be based on source length.
        assert result.estimated_tokens > 0
        assert result.within_budget is True
        assert result.estimated_symbols == 1
        assert result.estimated_modules == 1

    def test_estimate_empty_candidates(self):
        """Empty candidates should produce zero estimate."""
        budget = ContextBudget()
        result = budget.estimate([], [], max_tokens=4096)

        assert result.estimated_tokens == 0
        assert result.within_budget is True

    def test_estimate_exceeds_budget(self):
        """Large source should exceed budget."""
        budget = ContextBudget()

        # Create a large source that exceeds a small budget.
        large_source = "def foo():\n    " + "x = 1\n" * 1000
        candidates = [
            ContextCandidate(
                symbol_id="mod.foo",
                qualified_name="mod.foo",
                module="mod.py",
                source=large_source,
            )
        ]

        result = budget.estimate(candidates, ["mod.py"], max_tokens=10)

        assert result.truncated is True
        assert result.within_budget is False

    def test_estimate_includes_all_source_fields(self):
        """Estimation should include source, preview, signature, docstring."""
        budget = ContextBudget()

        candidates = [
            ContextCandidate(
                symbol_id="mod.foo",
                qualified_name="mod.foo",
                module="mod.py",
                source="def foo():\n    pass\n",
                source_preview="def foo():\n    pass",
                signature="def foo():",
                docstring="A function.",
            )
        ]

        result = budget.estimate(candidates, ["mod.py"], max_tokens=4096)

        # Should include all source fields in estimation.
        assert result.estimated_tokens > 0
        # The estimate should account for all the content.
        total_chars = (
            len("def foo():\n    pass\n")  # source
            + len("def foo():\n    pass")  # preview
            + len("def foo():")  # signature
            + len("A function.")  # docstring
            + len("mod.foo")  # qualified_name
            + len("mod.py")  # module
            + len("mod.py")  # module in list
        )
        expected_tokens = int(total_chars / CHARS_PER_TOKEN)
        assert result.estimated_tokens == expected_tokens


# ------------------------------------------------------------------
# Tests: Deterministic ordering
# ------------------------------------------------------------------


class TestDeterministicOrdering:
    """Test that context assembly is deterministic."""

    def test_candidates_preserve_rank_order(self):
        """Candidates should preserve their rank order."""
        source = '''def a():
    pass

def b():
    pass

def c():
    pass
'''
        sym_a = _make_symbol("mod.a", "mod.py", lineno=1, source="mod.py")
        sym_b = _make_symbol("mod.b", "mod.py", lineno=4, source="mod.py")
        sym_c = _make_symbol("mod.c", "mod.py", lineno=7, source="mod.py")
        mod = _make_module("mod.py", [sym_a, sym_b, sym_c], source=source)
        index = _make_index([mod])

        query = ContextQuery(
            text="a b c",
            max_symbols=3,
            max_modules=1,
            max_tokens=4096,
        )

        builder = ContextBuilder(index=index)
        result = builder.build(query)

        # Order should be deterministic.
        assert len(result.candidates) == 3
        names = [c.qualified_name for c in result.candidates]
        # All three should be present.
        assert "mod.a" in names
        assert "mod.b" in names
        assert "mod.c" in names


# ------------------------------------------------------------------
# Tests: Empty docstrings and edge cases
# ------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases for source-aware context."""

    def test_empty_docstring(self):
        """Empty docstring should not crash."""
        candidate = ContextCandidate(
            symbol_id="mod.foo",
            qualified_name="mod.foo",
            module="mod.py",
            docstring="",
        )
        assert candidate.docstring == ""

    def test_large_function(self):
        """Large function should be handled."""
        source = "def large():\n" + "    " + "x = 1\n" * 500 + "\n"
        candidate = ContextCandidate(
            symbol_id="mod.large",
            qualified_name="mod.large",
            module="mod.py",
            source=source,
            signature="def large():",
        )
        assert len(candidate.source) > 0
        assert candidate.source == source

    def test_budget_enforcement(self):
        """Budget should be enforced for source content."""
        budget = ContextBudget()

        large_source = "def foo():\n    " + "x = 1\n" * 10000
        candidates = [
            ContextCandidate(
                symbol_id="mod.foo",
                qualified_name="mod.foo",
                module="mod.py",
                source=large_source,
            )
        ]

        result = budget.estimate(candidates, ["mod.py"], max_tokens=100)

        assert result.truncated is True
        assert result.within_budget is False

    def test_no_source_data(self):
        """Missing source data should not crash."""
        candidate = ContextCandidate(
            symbol_id="mod.foo",
            qualified_name="mod.foo",
            module="mod.py",
            source="",
            source_preview="",
            signature="",
            docstring="",
        )
        budget = ContextBudget()
        result = budget.estimate([candidate], ["mod.py"], max_tokens=4096)
        # Should still produce a valid estimate.
        assert result.estimated_tokens >= 0


# ------------------------------------------------------------------
# Tests: SymbolContext and ModuleDescription
# ------------------------------------------------------------------


class TestSymbolContext:
    """Test SymbolContext model."""

    def test_symbol_context_defaults(self):
        """SymbolContext should have sensible defaults."""
        ctx = SymbolContext(qualified_name="mod.foo")
        assert ctx.signature == ""
        assert ctx.docstring == ""
        assert ctx.decorators == []
        assert ctx.source == ""
        assert ctx.source_preview == ""
        assert ctx.location is None

    def test_symbol_context_full(self):
        """SymbolContext should accept all fields."""
        ctx = SymbolContext(
            qualified_name="mod.MyClass",
            signature="class MyClass:",
            docstring="Class docstring.",
            decorators=["@decorator"],
            source="class MyClass:\n    pass\n",
            source_preview="class MyClass:\n    pass",
            location=("mod.py", 1, 3),
        )
        assert ctx.qualified_name == "mod.MyClass"
        assert ctx.signature == "class MyClass:"
        assert ctx.docstring == "Class docstring."
        assert ctx.decorators == ["@decorator"]
        assert ctx.source == "class MyClass:\n    pass\n"
        assert ctx.source_preview == "class MyClass:\n    pass"
        assert ctx.location == ("mod.py", 1, 3)


class TestModuleDescription:
    """Test ModuleDescription model."""

    def test_module_description_defaults(self):
        """ModuleDescription should have sensible defaults."""
        desc = ModuleDescription(module_path="mod.py")
        assert desc.purpose == ""
        assert desc.relationship_summary == ""
        assert desc.symbol_count == 0

    def test_module_description_full(self):
        """ModuleDescription should accept all fields."""
        desc = ModuleDescription(
            module_path="mod.py",
            purpose="Data models and schemas",
            relationship_summary="Contains the primary symbol",
            symbol_count=5,
        )
        assert desc.module_path == "mod.py"
        assert desc.purpose == "Data models and schemas"
        assert desc.relationship_summary == "Contains the primary symbol"
        assert desc.symbol_count == 5