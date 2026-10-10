"""Focused tests for the opt-in changed-file ranking signal.

The signal must be inert by default, must only ever reorder candidates that
already match the query, and must add exactly one bounded bonus to the symbols
that live in a locally modified module.
"""

from __future__ import annotations

from packages.context.builder import ContextBuilder
from packages.context.models import ContextCandidate, ContextQuery
from packages.context.ranking import RankingEngine
from packages.context.ranking_config import RankingConfig
from packages.context.scoring import RankingReason, carries_query_relevance
from packages.repository.index.models import RepositoryIndex, RepositoryStatistics
from packages.repository.symbols.models import Module, Symbol, SymbolType

QUERY = "widget"
CHANGED_MODULE = "modules/beta"
UNCHANGED_MODULE = "modules/alpha"
CHANGED_SYMBOL = "modules.beta.WidgetRunner"
UNCHANGED_SYMBOL = "modules.alpha.WidgetStore"
FILTERED_SYMBOL = "modules.beta._hidden"
UNRELATED_SYMBOL = "modules.beta.UnrelatedThing"


def _candidate(qualified_name: str, module: str) -> ContextCandidate:
    """Build a bare candidate for ranking tests."""
    return ContextCandidate(
        symbol_id=qualified_name,
        qualified_name=qualified_name,
        module=module,
        symbol_type=SymbolType.CLASS.value,
    )


def _candidates() -> list[ContextCandidate]:
    """Two equally relevant symbols, one public non-match, one no relevance."""
    return [
        _candidate(UNCHANGED_SYMBOL, UNCHANGED_MODULE),
        _candidate(CHANGED_SYMBOL, CHANGED_MODULE),
        _candidate(UNRELATED_SYMBOL, CHANGED_MODULE),
        _candidate(FILTERED_SYMBOL, CHANGED_MODULE),
    ]


def _rank(changed_modules: frozenset[str] = frozenset()) -> list[ContextCandidate]:
    """Rank the fixture candidates through a plain engine."""
    return RankingEngine(changed_modules=changed_modules).rank(QUERY, _candidates())


def _index() -> RepositoryIndex:
    """Build a tiny repository index mirroring the fixture candidates."""
    symbols = [
        Symbol(
            id=UNCHANGED_SYMBOL,
            name="WidgetStore",
            qualified_name=UNCHANGED_SYMBOL,
            symbol_type=SymbolType.CLASS,
            module=UNCHANGED_MODULE,
            lineno=3,
        ),
        Symbol(
            id=CHANGED_SYMBOL,
            name="WidgetRunner",
            qualified_name=CHANGED_SYMBOL,
            symbol_type=SymbolType.CLASS,
            module=CHANGED_MODULE,
            lineno=5,
        ),
    ]
    modules = {
        UNCHANGED_MODULE: Module(path=UNCHANGED_MODULE, symbols=[symbols[0]]),
        CHANGED_MODULE: Module(path=CHANGED_MODULE, symbols=[symbols[1]]),
    }
    return RepositoryIndex(
        modules=modules,
        _symbols=symbols,
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=len(modules),
            class_count=2,
            function_count=0,
            method_count=0,
            symbol_count=len(symbols),
        ),
    )


def _query() -> ContextQuery:
    """A query with relationship expansion off, for pure lexical ranking."""
    return ContextQuery(
        text=QUERY,
        max_symbols=10,
        max_modules=10,
        relationship_expansion=False,
    )


# ------------------------------------------------------------------
# Fixtures guard
# ------------------------------------------------------------------


def test_fixture_has_the_expected_score_split() -> None:
    """Guard the fixture: a relevance tie the working tree can break."""
    scores = {candidate.qualified_name: candidate.score for candidate in _rank()}

    assert scores[UNCHANGED_SYMBOL] == scores[CHANGED_SYMBOL] > 0
    assert scores[CHANGED_SYMBOL] + RankingConfig.WEIGHT_CHANGED_FILE > scores[UNCHANGED_SYMBOL]
    assert FILTERED_SYMBOL not in scores
    # The public non-match survives today's MINIMUM_CANDIDATE_SCORE filter, so
    # a score threshold alone could never keep the working tree off it.
    assert scores[UNRELATED_SYMBOL] >= RankingConfig.MINIMUM_CANDIDATE_SCORE
    assert _rank()[0].qualified_name == UNCHANGED_SYMBOL


# ------------------------------------------------------------------
# Disabled behaviour
# ------------------------------------------------------------------


def test_disabled_by_default_keeps_current_ranking() -> None:
    """No changed-module set means today's behaviour exactly."""
    baseline = RankingEngine().rank(QUERY, _candidates())
    explicit_empty = _rank(frozenset())

    assert [c.qualified_name for c in explicit_empty] == [c.qualified_name for c in baseline]
    assert [c.score for c in explicit_empty] == [c.score for c in baseline]
    assert all(RankingReason.CHANGED_FILE not in c.reasons for c in baseline)


# ------------------------------------------------------------------
# Enabled behaviour
# ------------------------------------------------------------------


def test_changed_file_symbol_wins_the_relevance_tie() -> None:
    """A symbol in an edited file breaks a relevance tie in its favour."""
    ranked = _rank(frozenset({CHANGED_MODULE}))

    assert ranked[0].qualified_name == CHANGED_SYMBOL
    assert ranked[1].qualified_name == UNCHANGED_SYMBOL


def test_bonus_is_flat_and_applied_once() -> None:
    """The promoted candidate gains exactly the configured weight, once."""
    base = {c.qualified_name: c.score for c in _rank()}
    promoted = {c.qualified_name: c.score for c in _rank(frozenset({CHANGED_MODULE}))}

    assert promoted[CHANGED_SYMBOL] == base[CHANGED_SYMBOL] + RankingConfig.WEIGHT_CHANGED_FILE
    assert promoted[UNCHANGED_SYMBOL] == base[UNCHANGED_SYMBOL]


def test_reason_is_recorded_only_for_changed_modules() -> None:
    """Explainability: the signal shows up in the candidate reasons."""
    promoted = {c.qualified_name: c.reasons for c in _rank(frozenset({CHANGED_MODULE}))}

    assert RankingReason.CHANGED_FILE in promoted[CHANGED_SYMBOL]
    assert RankingReason.CHANGED_FILE not in promoted[UNCHANGED_SYMBOL]


def test_engine_counts_the_candidates_it_gave_the_bonus_to() -> None:
    """The count is what lets a caller prove a comparison cannot differ.

    ``UnrelatedThing`` sits in the changed module and clears the floor without
    the query, and ``_hidden`` never clears it, so neither may be counted: the
    number has to mean "the bonus moved this many candidates", not "this many
    candidates live in a dirty file".
    """
    engine = RankingEngine(changed_modules=frozenset({CHANGED_MODULE}))
    engine.rank(QUERY, _candidates())

    assert engine.changed_file_bonus_count == 1

    disabled = RankingEngine()
    disabled.rank(QUERY, _candidates())
    assert disabled.changed_file_bonus_count == 0

    clean = RankingEngine(changed_modules=frozenset())
    clean.rank(QUERY, _candidates())
    assert clean.changed_file_bonus_count == 0


def test_the_count_is_per_pass_and_not_cumulative() -> None:
    """A fresh ``rank()`` restates the number instead of adding to it."""
    engine = RankingEngine(changed_modules=frozenset({CHANGED_MODULE}))
    engine.rank(QUERY, _candidates())
    engine.rank(QUERY, _candidates())

    assert engine.changed_file_bonus_count == 1

    engine.rank(QUERY, _candidates())
    assert engine.changed_file_bonus_count == 1


def test_filtered_symbol_is_never_admitted() -> None:
    """The bonus cannot rescue a symbol that ranking would have dropped."""
    ranked = _rank(frozenset({CHANGED_MODULE}))

    assert all(c.qualified_name != FILTERED_SYMBOL for c in ranked)
    assert {c.qualified_name for c in ranked} == {c.qualified_name for c in _rank()}


def test_public_non_matching_symbol_in_changed_module_gets_no_bonus() -> None:
    """A public symbol the query never matched stays exactly where it was.

    ``modules.beta.UnrelatedThing`` lives in a changed module and clears
    ``MINIMUM_CANDIDATE_SCORE`` purely through ``PUBLIC_NAME`` and
    ``SYMBOL_TYPE_PREFERENCE``, which every public class carries.  The dirty
    file must not lift it over symbols the query actually matched.
    """
    base = {c.qualified_name: c.score for c in _rank()}
    promoted = {c.qualified_name: c.score for c in _rank(frozenset({CHANGED_MODULE}))}

    assert base[UNRELATED_SYMBOL] >= RankingConfig.MINIMUM_CANDIDATE_SCORE
    assert promoted[UNRELATED_SYMBOL] == base[UNRELATED_SYMBOL]
    reasons = {c.qualified_name: c.reasons for c in _rank(frozenset({CHANGED_MODULE}))}
    unrelated_reasons = reasons[UNRELATED_SYMBOL]
    assert RankingReason.CHANGED_FILE not in unrelated_reasons
    assert RankingReason.PUBLIC_NAME in unrelated_reasons
    assert not carries_query_relevance(unrelated_reasons)


def test_non_matching_symbol_keeps_its_unchanged_position() -> None:
    """Ordering with the signal on only moves symbols that matched."""
    before = [c.qualified_name for c in _rank()]
    after = [c.qualified_name for c in _rank(frozenset({CHANGED_MODULE}))]

    assert after[0] == CHANGED_SYMBOL
    assert before[-1] == after[-1] == UNRELATED_SYMBOL
    assert sorted(before) == sorted(after)


def test_intrinsic_bonuses_are_not_query_relevance() -> None:
    """The gate is about matching, not about carrying a public name."""
    assert not carries_query_relevance(
        [RankingReason.PUBLIC_NAME, RankingReason.SYMBOL_TYPE_PREFERENCE]
    )
    assert carries_query_relevance([RankingReason.MODULE_MATCH])
    assert carries_query_relevance([RankingReason.PARTIAL_SYMBOL_NAME])
    assert carries_query_relevance([RankingReason.TOKEN_MATCH])
    assert carries_query_relevance([RankingReason.MODULE_TOKEN_MATCH])
    assert carries_query_relevance([RankingReason.EXACT_SYMBOL_NAME])
    assert carries_query_relevance([RankingReason.EXACT_QUALIFIED_NAME])
    # Relationship signals reach the primary symbol the query resolved to, so
    # they count as relevance by explicit decision.
    assert carries_query_relevance([RankingReason.DIRECT_CALLER])
    assert carries_query_relevance([RankingReason.SHARED_MODULE])
    assert carries_query_relevance([]) is False


def test_source_path_and_index_key_are_equivalent() -> None:
    """Callers may pass ``a/b.py`` or the index key ``a/b``."""
    by_key = [c.qualified_name for c in _rank(frozenset({CHANGED_MODULE}))]
    by_path = [c.qualified_name for c in _rank(frozenset({f"{CHANGED_MODULE}.py"}))]

    assert by_path == by_key


# ------------------------------------------------------------------
# Builder integration
# ------------------------------------------------------------------


def test_builder_threads_the_signal() -> None:
    """The builder's promotion chain keeps the working-tree ordering."""
    index = _index()
    baseline = ContextBuilder(index).build(_query())
    promoted = ContextBuilder(index, changed_modules=frozenset({CHANGED_MODULE})).build(_query())

    assert baseline.candidates[0].qualified_name == UNCHANGED_SYMBOL
    assert promoted.candidates[0].qualified_name == CHANGED_SYMBOL


def test_builder_default_leaves_existing_rankings_untouched() -> None:
    """Leaving the argument out must not move anything."""
    index = _index()
    default = ContextBuilder(index).build(_query())
    empty = ContextBuilder(index, changed_modules=frozenset()).build(_query())

    assert [c.qualified_name for c in default.candidates] == [
        c.qualified_name for c in empty.candidates
    ]
    assert [c.score for c in default.candidates] == [c.score for c in empty.candidates]


def test_builder_does_not_grow_the_context() -> None:
    """The signal reorders: it cannot add symbols or modules."""
    index = _index()
    baseline = ContextBuilder(index).build(_query())
    promoted = ContextBuilder(index, changed_modules=frozenset({CHANGED_MODULE})).build(_query())

    assert len(promoted.candidates) == len(baseline.candidates)
    assert sorted(promoted.selected_modules) == sorted(baseline.selected_modules)
    assert promoted.budget.estimated_tokens == baseline.budget.estimated_tokens


def test_builder_reports_the_bonus_count_on_the_result() -> None:
    """The count survives the builder so a caller never has to re-rank for it."""
    index = _index()
    baseline = ContextBuilder(index).build(_query())
    promoted = ContextBuilder(index, changed_modules=frozenset({CHANGED_MODULE})).build(_query())

    assert promoted.changed_bonus_count == 1
    assert baseline.changed_bonus_count == 0
    assert ContextBuilder(index).build(_query()).changed_bonus_count == 0
