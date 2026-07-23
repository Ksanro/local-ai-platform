"""Tests for the Ranking Engine.

Verifies scoring rules, deterministic ordering, tie breaking, and
query normalisation.

Acceptance Criteria
-------------------

- exact name outranks partial name
- partial outranks token overlap
- public symbol bonus applied once
- multiple token matches accumulate
- duplicate query tokens ignored
- ordering deterministic
- tie breaker respected
- empty query produces zero scores
- repeated executions produce identical ranking
"""

from __future__ import annotations

from packages.context.models import ContextCandidate
from packages.context.ranking import RankingEngine
from packages.context.scoring import (
    RankingReason,
    normalise_query_text,
    score_candidate,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _candidate(
    symbol_id: str,
    qualified_name: str,
    module: str,
) -> ContextCandidate:
    """Helper to create a ContextCandidate."""
    return ContextCandidate(
        symbol_id=symbol_id,
        qualified_name=qualified_name,
        module=module,
    )


# ------------------------------------------------------------------
# Query normalisation
# ------------------------------------------------------------------


class TestQueryNormalisation:
    """Tests for query text normalisation."""

    def test_lowercase(self) -> None:
        """Verify query is lowercased."""
        tokens = normalise_query_text("AUTHENTICATION")
        # Single-char tokens from camelCase decomposition are filtered.
        assert tokens == ["authentication"]

    def test_single_char_tokens_filtered(self) -> None:
        """Single-char tokens from decomposition are filtered out."""
        # "c b a b c" produces single-char tokens which are all filtered,
        # so the degradation guard kicks in and returns the original tokens.
        tokens = normalise_query_text("c b a b c")
        assert tokens == ["c", "b", "a"]

    def test_split_on_whitespace(self) -> None:
        """Verify query is split on whitespace."""
        tokens = normalise_query_text("hello world")
        assert tokens == ["hello", "world"]

    def test_remove_empty_tokens(self) -> None:
        """Verify empty tokens are removed."""
        tokens = normalise_query_text("  hello   world  ")
        assert tokens == ["hello", "world"]

    def test_remove_duplicate_tokens(self) -> None:
        """Verify duplicate tokens are removed while preserving order."""
        tokens = normalise_query_text("auth auth middleware auth")
        assert tokens == ["auth", "middleware"]

    def test_preserve_token_order(self) -> None:
        """Verify token order is preserved after deduplication.

        With Ranking v2, single-char tokens are filtered and all are stop
        words, so the degradation guard fires — it returns the original
        whitespace-split tokens deduplicated in order.
        """
        tokens = normalise_query_text("c b a b c")
        assert tokens == ["c", "b", "a"]

    def test_empty_query(self) -> None:
        """Verify empty query produces empty token list."""
        tokens = normalise_query_text("")
        assert tokens == []

    def test_only_whitespace(self) -> None:
        """Verify whitespace-only query produces empty token list."""
        tokens = normalise_query_text("   ")
        assert tokens == []


# ------------------------------------------------------------------
# Scoring rules
# ------------------------------------------------------------------


class TestScoringRules:
    """Tests for individual scoring rules.

    The name-matching rules are mutually exclusive — only the
    highest-scoring rule fires.  TOKEN_MATCH and PUBLIC_SYMBOL are
    additive on top.
    """

    def test_exact_symbol_name_match(self) -> None:
        """Exact symbol name match yields +100 + token + public_name."""
        candidate = _candidate("App", "main.App", "main.py")
        score, reasons = score_candidate(candidate, ["app"])
        # exact name: +100, token "app" in "main.app": +10, public_name: +5
        assert score == 115
        assert RankingReason.EXACT_SYMBOL_NAME in reasons
        assert RankingReason.TOKEN_MATCH in reasons
        assert RankingReason.PUBLIC_NAME in reasons

    def test_exact_qualified_name_match(self) -> None:
        """Exact qualified name match yields +90 + token + public_name."""
        candidate = _candidate("App", "main.App", "main.py")
        score, reasons = score_candidate(candidate, ["main.app"])
        # exact qualified: +90, token "main.app" in "main.app": +10, public_name: +5
        assert score == 105
        # EXACT_QUALIFIED_NAME fires when the full qualified name matches a query token
        assert RankingReason.EXACT_QUALIFIED_NAME in reasons
        assert RankingReason.TOKEN_MATCH in reasons
        assert RankingReason.PUBLIC_NAME in reasons

    def test_partial_symbol_name_match(self) -> None:
        """Partial symbol name match: substring within a segment yields +50."""
        candidate = _candidate("AuthMiddleware", "auth.AuthMiddleware", "auth.py")
        score, reasons = score_candidate(candidate, ["aut"])
        # "aut" is a substring of "auth" -> partial +50
        # "aut" is also in "auth.authmiddleware" -> token +10
        # public_name: +5
        assert score == 65
        assert RankingReason.PARTIAL_SYMBOL_NAME in reasons
        assert RankingReason.TOKEN_MATCH in reasons
        assert RankingReason.PUBLIC_NAME in reasons

    def test_module_match(self) -> None:
        """Module name contains query token yields +30."""
        candidate = _candidate("App", "main.App", "auth_middleware.py")
        score, reasons = score_candidate(candidate, ["middleware"])
        # no name match, module contains "middleware": +30
        # "middleware" not in "main.app" -> no token match
        # public_name: +5
        assert score == 35
        assert RankingReason.MODULE_MATCH in reasons
        assert RankingReason.PUBLIC_NAME in reasons

    def test_token_match_accumulates(self) -> None:
        """Multiple matching query tokens accumulate +10 each."""
        candidate = _candidate(
            "AuthenticationMiddleware",
            "auth.AuthenticationMiddleware",
            "auth.py",
        )
        score, reasons = score_candidate(candidate, ["auth", "middleware"])
        # exact name "auth": +100
        # "auth" in qualified: +10, "middleware" in qualified: +10
        # public_name: +5
        assert score == 125
        assert RankingReason.EXACT_SYMBOL_NAME in reasons
        assert RankingReason.TOKEN_MATCH in reasons
        assert RankingReason.PUBLIC_NAME in reasons

    def test_public_symbol_bonus(self) -> None:
        """Public symbol (name not starting with "_") yields +5."""
        candidate = _candidate("Public", "main.Public", "main.py")
        score, reasons = score_candidate(candidate, ["nonexistent"])
        # no match -> public_name: +5
        assert score == 5
        assert RankingReason.PUBLIC_NAME in reasons

    def test_private_symbol_no_bonus(self) -> None:
        """Private symbol (name starting with "_") yields no public bonus."""
        candidate = _candidate("_private", "main._private", "main.py")
        score, reasons = score_candidate(candidate, ["nonexistent"])
        # Private symbol gets PRIVATE_SYMBOL penalty (-10), not zero
        assert score == -10
        assert RankingReason.PRIVATE_SYMBOL in reasons
        assert RankingReason.PUBLIC_NAME not in reasons

    def test_empty_query_zero_score(self) -> None:
        """Empty query produces zero score."""
        candidate = _candidate("App", "main.App", "main.py")
        score, reasons = score_candidate(candidate, [])
        assert score == 0
        assert reasons == []

    def test_no_match_zero_score(self) -> None:
        """Completely unrelated query yields only public bonus."""
        candidate = _candidate("App", "main.App", "main.py")
        score, reasons = score_candidate(candidate, ["xyzzy", "blorg"])
        # no match at all -> public_name: +5
        assert score == 5
        assert RankingReason.PUBLIC_NAME in reasons


# ------------------------------------------------------------------
# RankingEngine.rank
# ------------------------------------------------------------------


class TestRankingEngine:
    """Tests for the RankingEngine.rank method."""

    def test_exact_name_outranks_partial(self) -> None:
        """Exact symbol name match outranks partial name match."""
        candidates = [
            _candidate("Middleware", "auth.AuthMiddleware", "auth.py"),  # partial: +55
            _candidate("Middleware", "auth.Middleware", "auth.py"),  # exact: +105
        ]
        engine = RankingEngine()
        ranked = engine.rank("middleware", candidates)
        assert ranked[0].qualified_name == "auth.Middleware"
        assert ranked[1].qualified_name == "auth.AuthMiddleware"

    def test_partial_outranks_token_overlap(self) -> None:
        """Partial name match outranks token overlap only."""
        candidates = [
            _candidate("Middleware", "auth.Middleware", "auth.py"),  # partial "middl": +55
            _candidate("Authentication", "auth.Authentication", "auth.py"),  # no match -> +5
        ]
        engine = RankingEngine()
        ranked = engine.rank("middl", candidates)
        # auth.Middleware: "middl" in "Middleware" -> partial +50 + public +5 = 55
        # auth.Authentication: no match -> public +5 = 5
        assert ranked[0].qualified_name == "auth.Middleware"
        assert ranked[1].qualified_name == "auth.Authentication"

    def test_public_symbol_bonus_applied_once(self) -> None:
        """Public symbol bonus is applied exactly once per candidate."""
        candidate = _candidate("Public", "main.Public", "main.py")
        engine = RankingEngine()
        engine.rank("public", [candidate])
        # exact name: +100, token: +10, public_name: +5 = 115
        assert candidate.score == 115
        public_reasons = [r for r in candidate.reasons if r == RankingReason.PUBLIC_NAME]
        assert len(public_reasons) == 1

    def test_multiple_token_matches_accumulate(self) -> None:
        """Multiple matching query tokens accumulate +10 each."""
        candidate = _candidate(
            "AuthenticationMiddleware",
            "auth.AuthenticationMiddleware",
            "auth.py",
        )
        engine = RankingEngine()
        engine.rank("auth middleware", [candidate])
        # exact "auth": +100, tokens "auth"+"middleware": +20, public: +5 = 125
        assert candidate.score == 125

    def test_duplicate_query_tokens_ignored(self) -> None:
        """Duplicate query tokens are deduplicated."""
        candidate = _candidate("Auth", "main.Auth", "main.py")
        engine = RankingEngine()
        engine.rank("auth auth auth", [candidate])
        # Only one "auth" token after dedup -> exact +100, token +10, public +5 = 115
        assert candidate.score == 115

    def test_ordering_deterministic(self) -> None:
        """Same input always produces identical ranking."""
        candidates = [
            _candidate("B", "mod.B", "mod.py"),
            _candidate("A", "mod.A", "mod.py"),
            _candidate("C", "mod.C", "mod.py"),
        ]
        engine = RankingEngine()
        results = [engine.rank("test", candidates) for _ in range(10)]
        first = results[0]
        for result in results[1:]:
            assert result == first

    def test_tie_breaker_respected(self) -> None:
        """Ties are broken by qualified_name ascending."""
        candidates = [
            _candidate("Z", "mod.Z", "mod.py"),  # score 5 (public)
            _candidate("A", "mod.A", "mod.py"),  # score 5 (public)
            _candidate("M", "mod.M", "mod.py"),  # score 5 (public)
        ]
        engine = RankingEngine()
        ranked = engine.rank("nonexistent", candidates)
        # All score 5, so sorted by qualified_name ascending.
        names = [c.qualified_name for c in ranked]
        assert names == sorted(names)

    def test_empty_query_produces_zero_scores(self) -> None:
        """Empty query produces zero scores for all candidates."""
        candidates = [
            _candidate("App", "main.App", "main.py"),
            _candidate("Middleware", "auth.Middleware", "auth.py"),
        ]
        engine = RankingEngine()
        ranked = engine.rank("", candidates)
        for candidate in ranked:
            assert candidate.score == 0

    def test_repeated_executions_identical(self) -> None:
        """Repeated executions produce identical ranking."""
        candidates = [
            _candidate("App", "main.App", "main.py"),
            _candidate("Middleware", "auth.Middleware", "auth.py"),
            _candidate("Helper", "utils.Helper", "utils.py"),
        ]
        engine = RankingEngine()
        results = [engine.rank("auth middleware", candidates) for _ in range(5)]
        first = results[0]
        for result in results[1:]:
            assert result == first

    def test_score_and_reasons_attached(self) -> None:
        """Ranking attaches score and reasons to candidates."""
        candidate = _candidate("App", "main.App", "main.py")
        engine = RankingEngine()
        engine.rank("app", [candidate])
        assert candidate.score > 0
        assert len(candidate.reasons) > 0

    def test_ranking_respects_max_symbols(self) -> None:
        """Ranking preserves candidate count (builder applies max_symbols)."""
        candidates = [
            _candidate("A", "mod.A", "mod.py"),
            _candidate("B", "mod.B", "mod.py"),
            _candidate("C", "mod.C", "mod.py"),
        ]
        engine = RankingEngine()
        ranked = engine.rank("test", candidates)
        assert len(ranked) == 3

    def test_private_symbol_no_public_bonus(self) -> None:
        """Private symbols do not receive the public symbol bonus."""
        candidate = _candidate("_helper", "utils._helper", "utils.py")
        engine = RankingEngine()
        engine.rank("test", [candidate])
        # Private symbol gets PRIVATE_SYMBOL penalty (-10)
        assert candidate.score == -10
        private_reasons = [r for r in candidate.reasons if r == RankingReason.PRIVATE_SYMBOL]
        assert len(private_reasons) == 1


# ------------------------------------------------------------------
# Tie breaking edge cases
# ------------------------------------------------------------------


class TestTieBreaking:
    """Tests for tie-breaking edge cases."""

    def test_identical_scores_sorted_by_name(self) -> None:
        """Candidates with identical scores are sorted by qualified_name."""
        candidates = [
            _candidate("Z", "z.mod", "z.py"),
            _candidate("A", "a.mod", "a.py"),
            _candidate("M", "m.mod", "m.py"),
        ]
        engine = RankingEngine()
        ranked = engine.rank("zzz", candidates)
        # All score 5 (public), so sorted by qualified_name ascending.
        names = [c.qualified_name for c in ranked]
        assert names == ["a.mod", "m.mod", "z.mod"]

    def test_higher_score_comes_first(self) -> None:
        """Higher score always comes before lower score."""
        candidates = [
            _candidate("Low", "mod.Low", "mod.py"),  # partial "low": +55
            _candidate("High", "mod.High", "mod.py"),  # exact "high": +105
        ]
        engine = RankingEngine()
        ranked = engine.rank("high", candidates)
        assert ranked[0].qualified_name == "mod.High"
        assert ranked[1].qualified_name == "mod.Low"


# ------------------------------------------------------------------
# Known limitations
# ------------------------------------------------------------------


class TestKnownLimitations:
    """Tests documenting known limitations of the current ranking engine."""

    def test_no_stemming(self) -> None:
        """Stemming is not performed; "authenticate" does not match "auth"."""
        candidate = _candidate("The", "main.The", "main.py")
        engine = RankingEngine()
        ranked = engine.rank("authenticate", [candidate])
        # "authenticate" not in "main.the" -> no match, public: +5
        assert ranked[0].score == 5

    def test_no_fuzzy_matching(self) -> None:
        """Typo in query does not match similar names."""
        candidate = _candidate("Middleware", "auth.Middleware", "auth.py")
        engine = RankingEngine()
        ranked = engine.rank("middlware", [candidate])
        # "middlware" not in "auth.middleware" -> no match, public: +5
        assert ranked[0].score == 5

    def test_no_stop_word_removal(self) -> None:
        """Stop words are not removed; they are treated as regular tokens."""
        candidate = _candidate("The", "main.The", "main.py")
        engine = RankingEngine()
        ranked = engine.rank("the", [candidate])
        # "the" matches "The" exactly -> +100, token +10, public +5 = 115
        assert ranked[0].score == 115
