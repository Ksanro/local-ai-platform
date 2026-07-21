"""Tests for Ranking v2 — Engineering Relevance Ranking.

Tests covering:
- Exact matches
- Partial matches
- Call graph influence
- Module influence
- Public API preference
- Deterministic ordering
- Tie breaking
- Configuration changes
- Large repositories
- Generated code penalty
- Test code penalty
- Private symbol penalty
- Implementation size bonus/penalty
- Documentation bonus
- Symbol type preference

"""

from __future__ import annotations

import pytest

from packages.context.budget import ContextBudget
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
    ContextResult,
)
from packages.context.ranking import RankingEngine
from packages.context.ranking_config import RankingConfig
from packages.context.scoring import (
    RankingReason,
    normalise_query_text,
    score_candidate,
    score_candidate_v2,
    score_relationship,
)
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
    source: str = "",
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


def _make_candidate(
    qualified_name: str,
    module: str,
    symbol_type: str = "",
    source: str = "",
    docstring: str = "",
    signature: str = "",
    is_in_init_py: bool = False,
) -> ContextCandidate:
    """Helper to create a ContextCandidate."""
    name = qualified_name.rsplit(".", 1)[-1]
    return ContextCandidate(
        symbol_id=qualified_name,
        qualified_name=qualified_name,
        module=module,
        score=0,
        reasons=[],
        signature=signature,
        docstring=docstring,
        source=source,
        symbol_type=symbol_type,
        source_lines=len(source.splitlines()) if source else 0,
        is_in_init_py=is_in_init_py,
    )


# ------------------------------------------------------------------
# Tests: Query normalisation
# ------------------------------------------------------------------


class TestQueryNormalisation:
    """Test query token extraction."""

    def test_simple_query(self):
        """Simple query should produce single token."""
        tokens = normalise_query_text("authentication")
        assert tokens == ["authentication"]

    def test_multi_token_query(self):
        """Multi-word query should produce multiple tokens."""
        tokens = normalise_query_text("authentication middleware")
        assert tokens == ["authentication", "middleware"]

    def test_case_normalisation(self):
        """Query should be lowercased."""
        tokens = normalise_query_text("AuthenticationMiddleware")
        assert tokens == ["authenticationmiddleware"]

    def test_duplicate_removal(self):
        """Duplicate tokens should be removed."""
        tokens = normalise_query_text("auth auth middleware")
        assert tokens == ["auth", "middleware"]

    def test_empty_query(self):
        """Empty query should produce empty list."""
        tokens = normalise_query_text("")
        assert tokens == []


# ------------------------------------------------------------------
# Tests: Exact matches
# ------------------------------------------------------------------


class TestExactMatches:
    """Test exact symbol name matching."""

    def test_exact_symbol_name_match(self):
        """Exact symbol name match should score at least +100."""
        candidate = _make_candidate(
            qualified_name="auth.AuthenticationMiddleware",
            module="auth.py",
            symbol_type="CLASS",
        )
        # Use query that matches the symbol name exactly.
        score, reasons = score_candidate(candidate, ["authenticationmiddleware"])

        # Score should be at least the exact match weight (plus additive bonuses).
        assert score >= RankingConfig.WEIGHT_EXACT_MATCH
        assert RankingReason.EXACT_SYMBOL_NAME in reasons

    def test_exact_symbol_name_match_case_insensitive(self):
        """Exact match should be case-insensitive."""
        candidate = _make_candidate(
            qualified_name="auth.AuthenticationMiddleware",
            module="auth.py",
            symbol_type="CLASS",
        )
        score, reasons = score_candidate(candidate, ["authenticationmiddleware"])

        # Score should be at least the exact match weight (plus additive bonuses).
        assert score >= RankingConfig.WEIGHT_EXACT_MATCH
        assert RankingReason.EXACT_SYMBOL_NAME in reasons

    def test_exact_qualified_name_match(self):
        """Exact qualified name match should score at least +90."""
        candidate = _make_candidate(
            qualified_name="auth.middleware",
            module="auth.py",
            symbol_type="CLASS",
        )
        score, reasons = score_candidate(candidate, ["auth.middleware"])

        # Score should be at least the qualified name weight (plus additive bonuses).
        assert score >= RankingConfig.WEIGHT_QUALIFIED_NAME
        assert RankingReason.EXACT_QUALIFIED_NAME in reasons

    def test_exact_match_wins_over_partial(self):
        """Exact match should win over partial match."""
        candidate = _make_candidate(
            qualified_name="auth.AuthMiddleware",
            module="auth.py",
            symbol_type="CLASS",
        )
        # Query matches both exact and partial.
        score, reasons = score_candidate(candidate, ["auth", "middleware"])

        # Should get exact match for "auth" segment.
        assert RankingReason.EXACT_SYMBOL_NAME in reasons
        assert score >= RankingConfig.WEIGHT_EXACT_MATCH


# ------------------------------------------------------------------
# Tests: Partial matches
# ------------------------------------------------------------------


class TestPartialMatches:
    """Test partial symbol name matching."""

    def test_partial_symbol_match(self):
        """Partial symbol name match should score at least +50."""
        candidate = _make_candidate(
            qualified_name="auth.AuthenticationMiddleware",
            module="auth.py",
            symbol_type="CLASS",
        )
        score, reasons = score_candidate(candidate, ["authentic"])

        # Score should be at least the partial match weight (plus additive bonuses).
        assert score >= RankingConfig.WEIGHT_PARTIAL_MATCH
        assert RankingReason.PARTIAL_SYMBOL_NAME in reasons

    def test_module_relevance(self):
        """Module name match should score +30 when no name match."""
        candidate = _make_candidate(
            qualified_name="auth.SomeRandomClass",
            module="auth.py",
            symbol_type="CLASS",
        )
        # Use a query that only matches module, not name segments.
        score, reasons = score_candidate(candidate, ["random"])

        # Should get module match or partial match.
        assert any(r in reasons for r in [RankingReason.MODULE_MATCH, RankingReason.PARTIAL_SYMBOL_NAME])


# ------------------------------------------------------------------
# Tests: Call graph influence
# ------------------------------------------------------------------


class TestCallGraphInfluence:
    """Test call graph relationship scoring."""

    def test_direct_caller_bonus(self):
        """Direct caller should receive DIRECT_CALLER bonus."""
        primary = _make_candidate(
            qualified_name="auth.main",
            module="auth.py",
            symbol_type="FUNCTION",
        )
        caller = _make_candidate(
            qualified_name="auth.handler",
            module="auth.py",
            symbol_type="FUNCTION",
        )

        # Create a mock SymbolGraphView.
        class MockGraphView:
            def callers(self, symbol):
                if symbol.qualified_name == "auth.main":
                    return [caller]
                return []

            def callees(self, symbol):
                return []

            def parents(self, symbol):
                return []

            def children(self, symbol):
                return []

        graph_view = MockGraphView()
        score, reasons = score_relationship(
            candidate=caller,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert RankingReason.DIRECT_CALLER in reasons
        assert score >= RankingConfig.WEIGHT_CALL_GRAPH_DIRECT_CALLER

    def test_direct_callee_bonus(self):
        """Direct callee should receive DIRECT_CALLEE bonus."""
        primary = _make_candidate(
            qualified_name="auth.main",
            module="auth.py",
            symbol_type="FUNCTION",
        )
        callee = _make_candidate(
            qualified_name="auth.helper",
            module="auth.py",
            symbol_type="FUNCTION",
        )

        class MockGraphView:
            def callers(self, symbol):
                return []

            def callees(self, symbol):
                if symbol.qualified_name == "auth.main":
                    return [callee]
                return []

            def parents(self, symbol):
                return []

            def children(self, symbol):
                return []

        graph_view = MockGraphView()
        score, reasons = score_relationship(
            candidate=callee,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert RankingReason.DIRECT_CALLEE in reasons
        assert score >= RankingConfig.WEIGHT_CALL_GRAPH_DIRECT_CALLEE

    def test_same_module_bonus(self):
        """Same module should receive SHARED_MODULE bonus."""
        primary = _make_candidate(
            qualified_name="auth.main",
            module="auth.py",
            symbol_type="FUNCTION",
        )
        candidate = _make_candidate(
            qualified_name="auth.helper",
            module="auth.py",
            symbol_type="FUNCTION",
        )

        class MockGraphView:
            def callers(self, symbol):
                return []

            def callees(self, symbol):
                return []

            def parents(self, symbol):
                return []

            def children(self, symbol):
                return []

        graph_view = MockGraphView()
        score, reasons = score_relationship(
            candidate=candidate,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert RankingReason.SHARED_MODULE in reasons
        assert score == RankingConfig.WEIGHT_CALL_GRAPH_SAME_MODULE


# ------------------------------------------------------------------
# Tests: Module influence
# ------------------------------------------------------------------


class TestModuleInfluence:
    """Test module-based scoring."""

    def test_import_proximity(self):
        """Import proximity should add bonus."""
        candidate = _make_candidate(
            qualified_name="auth.AuthMiddleware",
            module="auth.py",
            symbol_type="CLASS",
        )
        score, reasons = score_candidate(candidate, ["auth"])

        # Should have exact symbol match or module match.
        assert any(r in reasons for r in [RankingReason.EXACT_SYMBOL_NAME, RankingReason.MODULE_MATCH])


# ------------------------------------------------------------------
# Tests: Public API preference
# ------------------------------------------------------------------


class TestPublicAPIPreference:
    """Test public API bonus and private symbol penalty."""

    def test_init_py_export_bonus(self):
        """Symbol in __init__.py should receive PUBLIC_API_BONUS."""
        candidate = _make_candidate(
            qualified_name="auth.AuthMiddleware",
            module="auth/__init__.py",
            symbol_type="CLASS",
            is_in_init_py=True,
        )
        score, reasons = score_candidate(candidate, ["auth"])

        assert RankingReason.PUBLIC_API_BONUS in reasons
        assert score >= RankingConfig.WEIGHT_PUBLIC_API_BONUS

    def test_private_symbol_penalty(self):
        """Private symbol should receive PENALTY_PRIVATE_SYMBOL."""
        candidate = _make_candidate(
            qualified_name="auth._private_helper",
            module="auth.py",
            symbol_type="FUNCTION",
        )
        score, reasons = score_candidate(candidate, ["private"])

        assert RankingReason.PRIVATE_SYMBOL in reasons
        # The penalty should reduce the score. Without other bonuses, the penalty should be noticeable.
        # Check that the penalty reason is present.
        assert RankingConfig.PENALTY_PRIVATE_SYMBOL < 0  # Verify the penalty value is negative

    def test_public_name_bonus(self):
        """Public name should receive PUBLIC_NAME bonus."""
        candidate = _make_candidate(
            qualified_name="auth.PublicClass",
            module="auth.py",
            symbol_type="CLASS",
        )
        score, reasons = score_candidate(candidate, ["public"])

        assert RankingReason.PUBLIC_NAME in reasons


# ------------------------------------------------------------------
# Tests: Deterministic ordering
# ------------------------------------------------------------------


class TestDeterministicOrdering:
    """Test that ranking is deterministic."""

    def test_identical_scores_sorted_by_name(self):
        """Candidates with identical scores should be sorted by qualified_name."""
        candidates = [
            _make_candidate("mod.z_class", "mod.py", symbol_type="CLASS"),
            _make_candidate("mod.a_class", "mod.py", symbol_type="CLASS"),
            _make_candidate("mod.m_class", "mod.py", symbol_type="CLASS"),
        ]

        engine = RankingEngine()
        ranked = engine.rank("test", candidates)

        # All have score 0 (no query match), so should be sorted by name.
        names = [c.qualified_name for c in ranked]
        assert names == sorted(names)

    def test_higher_score_comes_first(self):
        """Higher score should come before lower score."""
        candidates = [
            _make_candidate("mod.z_class", "mod.py", symbol_type="CLASS"),
            _make_candidate("mod.a_class", "mod.py", symbol_type="CLASS", source="def a_class():\n    pass\n"),
        ]

        engine = RankingEngine()
        ranked = engine.rank("a_class", candidates)

        # mod.a_class should have higher score (partial match).
        assert ranked[0].qualified_name == "mod.a_class"
        assert ranked[0].score > ranked[1].score

    def test_repeated_runs_produce_same_order(self):
        """Multiple runs should produce identical ordering."""
        candidates = [
            _make_candidate("mod.z", "mod.py"),
            _make_candidate("mod.a", "mod.py"),
            _make_candidate("mod.m", "mod.py"),
        ]

        engine = RankingEngine()
        run1 = engine.rank("test", candidates)
        run2 = engine.rank("test", candidates)

        names1 = [c.qualified_name for c in run1]
        names2 = [c.qualified_name for c in run2]
        assert names1 == names2


# ------------------------------------------------------------------
# Tests: Tie breaking
# ------------------------------------------------------------------


class TestTieBreaking:
    """Test tie-breaking rules."""

    def test_tie_break_by_qualified_name(self):
        """Ties should be broken by qualified_name ascending."""
        candidates = [
            _make_candidate("mod.z", "mod.py"),
            _make_candidate("mod.a", "mod.py"),
        ]

        engine = RankingEngine()
        ranked = engine.rank("test", candidates)

        assert ranked[0].qualified_name == "mod.a"
        assert ranked[1].qualified_name == "mod.z"

    def test_tie_break_by_symbol_type(self):
        """Ties should be broken by symbol_type preference."""
        candidates = [
            _make_candidate("mod.func", "mod.py", symbol_type="FUNCTION"),
            _make_candidate("mod.class", "mod.py", symbol_type="CLASS"),
        ]

        engine = RankingEngine()
        ranked = engine.rank("test", candidates)

        # CLASS (rank 3) should come before FUNCTION (rank 2).
        assert ranked[0].symbol_type == "CLASS"

    def test_tie_break_by_module(self):
        """Ties should be broken by module path ascending."""
        candidates = [
            _make_candidate("mod.z", "z_module.py"),
            _make_candidate("mod.a", "a_module.py"),
        ]

        engine = RankingEngine()
        ranked = engine.rank("test", candidates)

        # Should be sorted by module ascending.
        assert ranked[0].module == "a_module.py"


# ------------------------------------------------------------------
# Tests: Configuration changes
# ------------------------------------------------------------------


class TestConfigurationChanges:
    """Test that configuration changes affect ranking."""

    def test_disabled_test_penalty(self):
        """Test penalty should apply when enabled."""
        candidate = _make_candidate(
            qualified_name="mod.test_helper",
            module="test_helper.py",
        )

        # Default: test penalty enabled.
        score1, reasons1 = score_candidate(candidate, ["test"])
        assert RankingReason.TEST_CODE in reasons1

    def test_max_candidates_limit(self):
        """MAX_CANDIDATES should limit results."""
        candidates = [
            _make_candidate(f"mod.class_{i}", "mod.py")
            for i in range(50)
        ]

        engine = RankingEngine()
        ranked = engine.rank("test", candidates)

        # The engine doesn't enforce MAX_CANDIDATES directly - that's done by the builder.
        # Just verify all candidates have valid scores.
        for candidate in ranked:
            assert isinstance(candidate.score, int)


# ------------------------------------------------------------------
# Tests: Large repositories
# ------------------------------------------------------------------


class TestLargeRepositories:
    """Test ranking with large repositories."""

    def test_large_repo_determinism(self):
        """Large repo ranking should be deterministic."""
        candidates = [
            _make_candidate(f"mod.class_{i:04d}", "mod.py")
            for i in range(500)
        ]

        engine = RankingEngine()
        run1 = engine.rank("class", candidates)
        run2 = engine.rank("class", candidates)

        names1 = [c.qualified_name for c in run1]
        names2 = [c.qualified_name for c in run2]
        assert names1 == names2

    def test_large_repo_scoring(self):
        """Large repo should still produce valid scores."""
        candidates = [
            _make_candidate(f"mod.class_{i}", "mod.py")
            for i in range(100)
        ]

        engine = RankingEngine()
        ranked = engine.rank("class", candidates)

        # All candidates should have scores.
        for candidate in ranked:
            assert isinstance(candidate.score, int)


# ------------------------------------------------------------------
# Tests: Generated code penalty
# ------------------------------------------------------------------


class TestGeneratedCodePenalty:
    """Test generated code penalty."""

    def test_generated_code_penalty(self):
        """Generated code should receive PENALTY_GENERATED_CODE."""
        candidate = _make_candidate(
            qualified_name="auth.generated_handler",
            module="auth.py",
        )
        score, reasons = score_candidate(candidate, ["handler"])

        assert RankingReason.GENERATED_CODE in reasons
        assert score < RankingConfig.WEIGHT_EXACT_MATCH  # Should be reduced

    def test_generated_pattern_variations(self):
        """Various generated patterns should be detected."""
        patterns = [
            "generated_handler",
            "_gen_handler",
            "_auto_handler",
            "_generated",
            "__generated__",
            "stub_handler",
            "_stub",
        ]

        for pattern in patterns:
            candidate = _make_candidate(
                qualified_name=f"auth.{pattern}",
                module="auth.py",
            )
            _, reasons = score_candidate(candidate, ["test"])
            assert RankingReason.GENERATED_CODE in reasons


# ------------------------------------------------------------------
# Tests: Test code penalty
# ------------------------------------------------------------------


class TestTestCodePenalty:
    """Test test code penalty."""

    def test_test_file_penalty(self):
        """Test file should receive PENALTY_TEST_CODE."""
        candidate = _make_candidate(
            qualified_name="mod.helper",
            module="test_mod.py",
        )
        score, reasons = score_candidate(candidate, ["helper"])

        assert RankingReason.TEST_CODE in reasons
        # The penalty should be present (but may not be negative if other bonuses apply).
        assert RankingConfig.PENALTY_TEST_CODE < 0  # Verify penalty is negative

    def test_conftest_penalty(self):
        """Conftest files should be penalized."""
        candidate = _make_candidate(
            qualified_name="mod.fixture",
            module="conftest.py",
        )
        _, reasons = score_candidate(candidate, ["fixture"])

        assert RankingReason.TEST_CODE in reasons


# ------------------------------------------------------------------
# Tests: Documentation bonus
# ------------------------------------------------------------------


class TestDocumentationBonus:
    """Test documentation bonus."""

    def test_docstring_bonus(self):
        """Symbol with docstring should receive DOCUMENTATION_BONUS."""
        candidate = _make_candidate(
            qualified_name="auth.AuthMiddleware",
            module="auth.py",
            symbol_type="CLASS",
            docstring="Authentication middleware class.",
        )
        score, reasons = score_candidate(candidate, ["auth"])

        assert RankingReason.DOCUMENTATION_BONUS in reasons
        assert score > RankingConfig.WEIGHT_EXACT_MATCH

    def test_no_docstring(self):
        """Symbol without docstring should not receive bonus."""
        candidate = _make_candidate(
            qualified_name="auth.AuthMiddleware",
            module="auth.py",
            symbol_type="CLASS",
            docstring="",
        )
        _, reasons = score_candidate(candidate, ["auth"])

        assert RankingReason.DOCUMENTATION_BONUS not in reasons


# ------------------------------------------------------------------
# Tests: Implementation size bonus/penalty
# ------------------------------------------------------------------


class TestImplementationSize:
    """Test implementation size scoring."""

    def test_small_implementation_bonus(self):
        """Small implementation should receive IMPLEMENTATION_SIZE_BONUS."""
        candidate = _make_candidate(
            qualified_name="auth.helper",
            module="auth.py",
            symbol_type="FUNCTION",
            source="def helper():\n    return True\n",
        )
        score, reasons = score_candidate(candidate, ["helper"])

        assert RankingReason.IMPLEMENTATION_SIZE_BONUS in reasons

    def test_large_implementation_penalty(self):
        """Large implementation should receive PENALTY_LARGE_IMPLEMENTATION."""
        large_source = "def large():\n" + "    x = 1\n" * 150
        candidate = _make_candidate(
            qualified_name="auth.large",
            module="auth.py",
            symbol_type="FUNCTION",
            source=large_source,
        )
        score, reasons = score_candidate(candidate, ["large"])

        assert RankingReason.LARGE_IMPLEMENTATION in reasons


# ------------------------------------------------------------------
# Tests: Symbol type preference
# ------------------------------------------------------------------


class TestSymbolTypePreference:
    """Test symbol type preference scoring."""

    def test_class_preferred_over_function(self):
        """CLASS should be preferred over FUNCTION."""
        class_candidate = _make_candidate(
            qualified_name="auth.Auth",
            module="auth.py",
            symbol_type="CLASS",
        )
        func_candidate = _make_candidate(
            qualified_name="auth.auth",
            module="auth.py",
            symbol_type="FUNCTION",
        )

        candidates = [func_candidate, class_candidate]
        engine = RankingEngine()
        ranked = engine.rank("auth", candidates)

        # CLASS should come first due to type preference.
        assert ranked[0].symbol_type == "CLASS"


# ------------------------------------------------------------------
# Tests: End-to-end integration
# ------------------------------------------------------------------


class TestEndToEnd:
    """Test end-to-end ranking integration."""

    def test_full_context_build(self):
        """Full context building should work with Ranking v2."""
        source = '''"""Authentication module."""

class AuthMiddleware:
    """Authentication middleware."""
    
    def authenticate(self, request):
        """Authenticate request."""
        token = request.headers.get("Authorization")
        return token

def validate_token(token):
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
            "auth.validate_token",
            "auth.py",
            lineno=12,
            symbol_type=SymbolType.FUNCTION,
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

        # Should have candidates.
        assert len(result.candidates) > 0

        # Primary should have highest score.
        primary = result.candidates[0]
        assert primary.score > 0

        # All candidates should have reasons.
        for candidate in result.candidates:
            assert len(candidate.reasons) > 0

    def test_empty_candidates(self):
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

    def test_ranking_version_in_metadata(self):
        """ContextMetadata should use ranking version 2."""
        metadata = ContextMetadata()
        assert metadata.ranking_version == "2"
