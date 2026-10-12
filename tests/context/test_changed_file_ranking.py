"""Focused tests for the opt-in changed-file ranking signal.

The signal must be inert by default, must only ever reorder candidates that
already match the query, and must add exactly one bounded bonus to the symbols
that live in a locally modified module.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

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


# ------------------------------------------------------------------
# Name priority versus the working tree
#
# Two conditions get conflated whenever the size of the working-tree bonus is
# argued about, and only one of them is the strong one:
#
# * a **name match** is ``RankingReason.EXACT_SYMBOL_NAME``, which fires when any
#   segment of the qualified name equals a query token - including the segments
#   of the module path.  A prompt that names nothing can still name-match a
#   symbol through its file path.
# * **named in the query** is stricter: the prompt text contains the symbol's own
#   name (or the name it is defined in).  This is the case a dirty file must not
#   outvote.
#
# How far behind a competitor a given bonus can reach is a property of a real
# index, so it is not asserted here from a number copied out of a notebook:
# ``scripts/quality_harness.py --changed-file-sweep`` prints it per query, and
# ``--changed-file-probe`` measures the same thing end to end through
# ``RepositoryContextStage``.  What these tests pin is the arithmetic both modes
# read - the flip point is the gap, or the gap plus one when the tie-break still
# favours the leader - and they never pin the shipped value of the weight.
# ------------------------------------------------------------------

NAMED_QUERY = "How does ContextBuilder enforce the token budget?"
NAMED_SYMBOL = "packages/context/builder.ContextBuilder"
NAMED_MODULE = "packages/context/builder"
MATCHED_SYMBOL = "packages/context/budget.ContextBudget"
MATCHED_MODULE = "packages/context/budget"
FILE_ONLY_SYMBOL = "packages/monitoring/metrics_server.MetricsServer"
FILE_ONLY_MODULE = "packages/monitoring/metrics_server"


#: The same pair under a query that names nothing.  ``ContextBuilder`` still
#: earns ``EXACT_SYMBOL_NAME`` there, from the ``context`` and ``builder`` segments
#: of its own module path - which is the difference between the two terms.
PATH_TOKEN_QUERY = "repository context"

#: A competitor that sorts after the leader, so the tie-break protects the leader.
LATER_SYMBOL = "packages/runtime/token_budget.AllocateBudget"
LATER_MODULE = "packages/runtime/token_budget"


def _name_candidates() -> list[ContextCandidate]:
    """The leader, a name-matched competitor, a later-sorting one, no relevance."""
    return [
        _candidate(NAMED_SYMBOL, NAMED_MODULE),
        _candidate(MATCHED_SYMBOL, MATCHED_MODULE),
        _candidate(LATER_SYMBOL, LATER_MODULE),
        _candidate(FILE_ONLY_SYMBOL, FILE_ONLY_MODULE),
    ]


def _rank_names(
    query: str = NAMED_QUERY, changed: frozenset[str] = frozenset()
) -> list[ContextCandidate]:
    """Rank the name fixture through a plain engine."""
    return RankingEngine(changed_modules=changed).rank(query, _name_candidates())


def _named_in(query: str, qualified_name: str) -> bool:
    """Whether the query text contains the symbol's own name, not a path segment.

    The module stem is deliberately excluded: in ``packages/context/budget.
    ContextBudget`` only ``ContextBudget`` (and anything it is nested in) is a
    name - ``budget`` is a file, and a prompt that says "token budget" says
    nothing about this symbol.
    """
    own = qualified_name.rsplit("/", 1)[-1].split(".")
    parts = own[1:] if len(own) > 1 else own
    return any(part.lower() in query.lower() for part in parts if part)


@contextmanager
def _weight(value: int) -> Iterator[None]:
    """Rank with a different working-tree weight for the duration of a block."""
    original = RankingConfig.WEIGHT_CHANGED_FILE
    RankingConfig.WEIGHT_CHANGED_FILE = value
    try:
        yield
    finally:
        RankingConfig.WEIGHT_CHANGED_FILE = original


def test_name_fixture_separates_the_two_name_conditions() -> None:
    """Guard the fixture: named in the query, name matched, and neither."""
    ranked = {c.qualified_name: (c.score, c.reasons) for c in _rank_names()}
    named_score, named_reasons = ranked[NAMED_SYMBOL]
    matched_score, matched_reasons = ranked[MATCHED_SYMBOL]
    file_score, file_reasons = ranked[FILE_ONLY_SYMBOL]

    assert _named_in(NAMED_QUERY, NAMED_SYMBOL)
    assert not _named_in(NAMED_QUERY, MATCHED_SYMBOL)
    # Both carry the same reason, so the reason is not what separates them.
    assert RankingReason.EXACT_SYMBOL_NAME in named_reasons
    assert RankingReason.EXACT_SYMBOL_NAME in matched_reasons
    assert not carries_query_relevance(file_reasons)
    assert named_score > matched_score > file_score


def test_a_query_that_names_nothing_still_matches_symbols_by_name() -> None:
    """The definition ``EXACT_SYMBOL_NAME`` actually implements.

    ``scoring.py`` fires it when *any* segment of the qualified name equals a
    query token, and module-path segments count.  "repository context" names no
    symbol at all, yet both fixture symbols earn the +100 exact-name bonus from
    the ``context`` segment of their own paths - and tie at the same score, which
    is the case where the working tree decides the primary at *any* nonzero
    weight.  Any sentence about the bonus "not outvoting a name match" has to say
    which of the two conditions it means; ``--changed-file-probe``'s
    ``path_token_gate`` case is the same effect on this repository's real index.
    """
    ranked = {c.qualified_name: (c.score, c.reasons) for c in _rank_names(PATH_TOKEN_QUERY)}

    assert RankingReason.EXACT_SYMBOL_NAME in ranked[NAMED_SYMBOL][1]
    assert not _named_in(PATH_TOKEN_QUERY, NAMED_SYMBOL)
    assert not _named_in(PATH_TOKEN_QUERY, MATCHED_SYMBOL)
    assert ranked[NAMED_SYMBOL][0] == ranked[MATCHED_SYMBOL][0]
    assert ranked[NAMED_SYMBOL][0] > ranked[LATER_SYMBOL][0]


def test_changed_file_cannot_take_the_primary_from_a_symbol_the_query_named() -> None:
    """The requirement the weight is argued over, at every weight below the gap.

    ``packages/context/budget.py`` is a genuine competitor - ContextBudget
    name-matches the token ``budget`` - and it is the file the user happens to be
    editing.  The named symbol has to stay first until the bonus reaches the gap.
    """
    scores = {c.qualified_name: c.score for c in _rank_names()}
    gap = scores[NAMED_SYMBOL] - scores[MATCHED_SYMBOL]

    for value in (1, 5, gap - 1):
        with _weight(value):
            ranked = _rank_names(changed=frozenset({MATCHED_MODULE}))

        assert ranked[0].qualified_name == NAMED_SYMBOL
        # The bonus was applied - it is simply not enough to outvote the name.
        assert RankingReason.CHANGED_FILE in ranked[1].reasons


def test_the_bonus_decides_a_relevance_tie_at_any_nonzero_weight() -> None:
    """What the signal is for, and why it does not need to be large."""
    for value in (1, RankingConfig.WEIGHT_CHANGED_FILE):
        with _weight(value):
            ranked = RankingEngine(changed_modules=frozenset({CHANGED_MODULE})).rank(
                QUERY, _candidates()
            )

        assert ranked[0].qualified_name == CHANGED_SYMBOL


def test_the_flip_point_is_the_gap_itself_when_the_tie_break_favours_the_file() -> None:
    """At an equal-plus-gap score, order falls to the tie-break, not to the leader.

    ``packages/context/budget.ContextBudget`` sorts before
    ``packages/context/builder.ContextBuilder``, so a bonus equal to the gap
    already hands it the primary.  That is why the ceiling is "below the gap"
    rather than "at or below the gap", and it is the arithmetic
    ``scripts/quality_harness.py --changed-file-sweep`` reports per query.
    """
    scores = {c.qualified_name: c.score for c in _rank_names()}
    gap = scores[NAMED_SYMBOL] - scores[MATCHED_SYMBOL]

    with _weight(gap):
        ranked = _rank_names(changed=frozenset({MATCHED_MODULE}))

    assert ranked[0].qualified_name == MATCHED_SYMBOL


def test_the_flip_point_is_the_gap_plus_one_when_the_leader_sorts_first() -> None:
    """The other half of the same arithmetic, for a competitor that sorts later."""
    scores = {c.qualified_name: c.score for c in _rank_names()}
    gap = scores[NAMED_SYMBOL] - scores[LATER_SYMBOL]

    with _weight(gap):
        assert _rank_names(changed=frozenset({LATER_MODULE}))[0].qualified_name == NAMED_SYMBOL
    with _weight(gap + 1):
        assert _rank_names(changed=frozenset({LATER_MODULE}))[0].qualified_name == LATER_SYMBOL


def test_a_dirty_file_alone_never_promotes_a_symbol_at_any_weight() -> None:
    """The relevance gate, not the number, is what keeps file state out.

    This holds whatever the owner decides ``WEIGHT_CHANGED_FILE`` should be, which
    is why the sweep and the probes - not a constant copied into a test - are the
    place the size question is answered.
    """
    for value in (1, 5, RankingConfig.WEIGHT_CHANGED_FILE, 1000):
        with _weight(value):
            ranked = _rank_names(changed=frozenset({FILE_ONLY_MODULE}))

        assert ranked[-1].qualified_name == FILE_ONLY_SYMBOL
        assert RankingReason.CHANGED_FILE not in ranked[-1].reasons
