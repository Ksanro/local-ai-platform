"""Deterministic tests for changed-file promotion observability.

The change-aware ranking signal is only useful if it can be *observed*, and the
claim worth observing is narrow: did the working-tree bonus change the context
that is actually sent?  "A sent symbol carries the bonus" and "the bonus changed
what was sent" are different statements, so every stage-level test here runs the
same request twice - once with the signal and once without - and checks the
counts against the difference between the two packages.  The difference itself is
``changed_context_differs``, and it is the whole composed package that gets
compared, because a flat bonus is a reordering signal: a request where the
supporting symbols swap places changed what the model reads even though the
primary and the membership are identical.  ``changed_baseline_status`` says
whether that comparison ran, was provably unnecessary, or failed.  Everything is
count only: no test here touches Git or a model, and none of them can put a path,
module name or symbol name into a log line or a session record.
"""

from __future__ import annotations

import logging
from typing import Any, Final

import pytest

from packages.context.context_package import ContextPackage
from packages.context.delta import SentSymbolTracker
from packages.context.models import ContextCandidate
from packages.context.scoring import RankingReason
from packages.pipeline.context import PipelineContext
from packages.pipeline.stages import repository_context as stage_module
from packages.pipeline.stages.repository_context import (
    INERT_PROMOTION,
    RepositoryContextStage,
    changed_file_promotion_counts,
)
from packages.repository.index.models import (
    Module,
    RepositoryIndex,
    RepositoryStatistics,
    Symbol,
)
from packages.repository.symbols.models import SymbolType

#: The measurements the counter function returns.
COUNT_KEYS = (
    "changed_files_count",
    "changed_symbols_selected",
    "changed_primary_promoted",
    "changed_symbols_promoted",
    "changed_context_differs",
    "changed_baseline_status",
)

#: What a stage result, a log line and a session record all state together.
PROMOTION_KEYS = COUNT_KEYS + ("changed_files_signal",)

QUERY = "widget"
CHANGED_MODULE = "modules/beta"
UNCHANGED_MODULE = "modules/alpha"
CHANGED_SYMBOL = "modules.beta.WidgetRunner"
UNCHANGED_SYMBOL = "modules.alpha.WidgetStore"
CHANGED_METHOD = "modules.beta.WidgetRunner.run"
UNRELATED_SYMBOL = "modules.beta.parse_settings"
#: Below the ranking floor on its own; the bonus is what lifts it into range.
HIDDEN_SYMBOL = "modules.beta._parse_settings"

#: The bonus cannot move this one: the changed module's symbol already leads.
SAME_QUERY = "how does the widget runner work"
#: The bonus does move this one: the unchanged module's symbol leads by name.
FLIP_QUERY = "how does the widget store work"
#: No symbol in the changed module answers this query, so nothing can differ.
NO_BONUS_QUERY = "how does the store work"
#: In the reorder index the leader holds and only the order behind it moves.
REORDER_QUERY = "how does WidgetStore work"
ALPHA_HELPER = "modules.alpha.parse_widgets"
BETA_HELPER = "modules.beta.parse_widget_data"

#: Marks an argument the caller did not pass, distinct from an explicit ``None``.
_UNSET: Final = object()

#: Anything a count-only field must never contain.
FORBIDDEN = (
    ".py",
    "/",
    "\\",
    "modules/",
    "modules.",
    "WidgetRunner",
    "WidgetStore",
    "parse_settings",
    "parse_widgets",
    "parse_widget_data",
    "simulated git failure",
    "simulated build failure",
    "simulated baseline failure",
    "simulated query failure",
)


class _StubSource:
    """Changed-module source with a fixed answer and no Git behind it."""

    def __init__(self, paths: frozenset[str]) -> None:
        self.paths = paths

    def module_paths(self) -> frozenset[str]:
        """Return the scripted paths."""
        return self.paths


class _BrokenSource:
    """A changed-module source that always fails, detail and all."""

    def module_paths(self) -> frozenset[str]:
        raise RuntimeError("simulated git failure")


class _RecordingTracker(SentSymbolTracker):
    """A delta tracker that records every read and write made for a request."""

    def __init__(self, maxsize: int = 256) -> None:
        super().__init__(maxsize=maxsize)
        self.lookups = 0
        self.stored: list[tuple[str, frozenset[str]]] = []

    def get(self, conversation_key: str) -> set[str]:
        """Count the lookup, then behave exactly like the real tracker."""
        self.lookups += 1
        return super().get(conversation_key)

    def store(self, conversation_key: str, symbols: set[str]) -> None:
        """Record the write, then behave exactly like the real tracker."""
        self.stored.append((conversation_key, frozenset(symbols)))
        super().store(conversation_key, symbols)


@pytest.fixture
def builder_spy(monkeypatch: pytest.MonkeyPatch) -> list[frozenset[str]]:
    """Replace the stage's builder with a subclass that logs each construction.

    One entry per ``ContextBuilder`` built for the request, holding the changed
    module set that builder was given - so a counterfactual baseline that was
    never asked for is impossible to hide.
    """
    real = stage_module.ContextBuilder
    seen: list[frozenset[str]] = []

    class _Spy(real):  # type: ignore[valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            seen.append(frozenset(kwargs.get("changed_modules", ())))

    monkeypatch.setattr(stage_module, "ContextBuilder", _Spy)
    return seen


def _stage(
    *,
    changed: bool = True,
    index: RepositoryIndex | None = None,
    source: Any = _UNSET,
    **kwargs: Any,
) -> RepositoryContextStage:
    """Build a stage with the signal wired to the fixture's changed module."""
    if source is _UNSET:
        source = _StubSource(frozenset({CHANGED_MODULE})) if changed else None
    return RepositoryContextStage(
        index=_index() if index is None else index,
        changed_files=source,
        **kwargs,
    )


def _sent(result: Any) -> set[str]:
    """The symbols a stage result actually sends, primary included."""
    package = result.data["package"] if result.data is not None else None
    if package is None:
        return set()
    return {package.primary_symbol, *package.supporting_symbols} - {""}


def _candidate(qualified_name: str, module: str, *reasons: RankingReason) -> ContextCandidate:
    """Build a candidate carrying the given ranking reasons."""
    return ContextCandidate(
        symbol_id=qualified_name,
        qualified_name=qualified_name,
        module=module,
        symbol_type=SymbolType.CLASS.value,
        reasons=list(reasons),
    )


def _package(primary: str = "", *supporting: str) -> ContextPackage:
    """Build a composed package by symbol name only, as the composer would."""
    return ContextPackage(
        primary_symbol=primary,
        supporting_symbols=list(supporting),
        estimated_tokens=10,
    )


def _index(*, with_unrelated: bool = False) -> RepositoryIndex:
    """A two-module index whose symbols all answer the fixture query.

    With ``with_unrelated`` the changed module gains a symbol that no query
    names, which is what a mostly unrelated dirty file looks like.
    """
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
        Symbol(
            id=CHANGED_METHOD,
            name="run",
            qualified_name=CHANGED_METHOD,
            symbol_type=SymbolType.METHOD,
            module=CHANGED_MODULE,
            lineno=7,
        ),
    ]
    if with_unrelated:
        # A public symbol in the dirty module that no query names still clears
        # MINIMUM_CANDIDATE_SCORE (which is 1) and is therefore sent by both arms
        # - it must never be counted as either selected or promoted.  A private
        # one falls below that floor and is never sent at all.
        symbols.extend(
            [
                Symbol(
                    id=UNRELATED_SYMBOL,
                    name="parse_settings",
                    qualified_name=UNRELATED_SYMBOL,
                    symbol_type=SymbolType.FUNCTION,
                    module=CHANGED_MODULE,
                    lineno=9,
                ),
                Symbol(
                    id=HIDDEN_SYMBOL,
                    name="_parse_settings",
                    qualified_name=HIDDEN_SYMBOL,
                    symbol_type=SymbolType.FUNCTION,
                    module=CHANGED_MODULE,
                    lineno=11,
                ),
            ]
        )
    modules = {
        UNCHANGED_MODULE: Module(path=UNCHANGED_MODULE, symbols=[symbols[0]]),
        CHANGED_MODULE: Module(path=CHANGED_MODULE, symbols=symbols[1:]),
    }
    return RepositoryIndex(
        modules=modules,
        _symbols=symbols,
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=len(modules),
            class_count=2,
            function_count=2 if with_unrelated else 0,
            method_count=1,
            symbol_count=len(symbols),
        ),
    )


def _reorder_index() -> RepositoryIndex:
    """An index where the bonus can only reorder: the leader holds, names tie.

    ``WidgetStore`` answers :data:`REORDER_QUERY` by exact name and leads in both
    arms.  Every other symbol scores the same flat amount, so the unchanged
    module's helper sorts first by name until the bonus lifts the changed
    module's symbols past it.  Order moves, membership and primary do not - the
    case a set comparison reports as no change at all.
    """
    specs = [
        (UNCHANGED_SYMBOL, UNCHANGED_MODULE, SymbolType.CLASS, 3),
        (ALPHA_HELPER, UNCHANGED_MODULE, SymbolType.FUNCTION, 7),
        (CHANGED_SYMBOL, CHANGED_MODULE, SymbolType.CLASS, 5),
        (CHANGED_METHOD, CHANGED_MODULE, SymbolType.METHOD, 9),
        (BETA_HELPER, CHANGED_MODULE, SymbolType.FUNCTION, 12),
    ]
    symbols = [
        Symbol(
            id=qname,
            name=qname.rsplit(".", 1)[-1],
            qualified_name=qname,
            symbol_type=symbol_type,
            module=module,
            lineno=lineno,
        )
        for qname, module, symbol_type, lineno in specs
    ]
    modules: dict[str, Module] = {}
    for symbol in symbols:
        modules.setdefault(symbol.module, Module(path=symbol.module, symbols=[])).symbols.append(
            symbol
        )
    return RepositoryIndex(
        modules=modules,
        _symbols=symbols,
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=len(modules),
            class_count=2,
            function_count=2,
            method_count=1,
            symbol_count=len(symbols),
        ),
    )


def _context(*messages: dict[str, object]) -> PipelineContext:
    """A minimal pipeline context carrying one user turn by default."""
    return PipelineContext(
        request_id="test-promotion",
        request={
            "messages": list(messages)
            or [{"role": "user", "content": f"how does the {QUERY} runner work"}]
        },
    )

# ---------------------------------------------------------------------------
# The counter function
# ---------------------------------------------------------------------------


def test_counts_are_count_only() -> None:
    """The counter returns exactly the four measurements, and no names."""
    counts = changed_file_promotion_counts(
        _package(CHANGED_SYMBOL, UNCHANGED_SYMBOL),
        [
            _candidate(CHANGED_SYMBOL, CHANGED_MODULE, RankingReason.CHANGED_FILE),
            _candidate(UNCHANGED_SYMBOL, UNCHANGED_MODULE),
        ],
        frozenset({CHANGED_MODULE}),
        _package(CHANGED_SYMBOL, UNCHANGED_SYMBOL),
    )

    assert set(counts) == set(COUNT_KEYS)
    assert isinstance(counts["changed_primary_promoted"], bool)
    assert isinstance(counts["changed_context_differs"], bool)
    assert isinstance(counts["changed_baseline_status"], str)
    for key in ("changed_files_count", "changed_symbols_selected", "changed_symbols_promoted"):
        assert isinstance(counts[key], int)
        assert not isinstance(counts[key], bool)
    assert not any(forbidden in repr(counts) for forbidden in FORBIDDEN)


def test_no_package_reports_safe_inert_counts() -> None:
    """Nothing assembled still states every field, and all of them inert."""
    assert changed_file_promotion_counts(None, (), frozenset(), None) == {
        "changed_files_count": 0,
        "changed_symbols_selected": 0,
        "changed_primary_promoted": False,
        "changed_symbols_promoted": 0,
        "changed_context_differs": False,
        "changed_baseline_status": "none",
    }


def test_identical_context_is_selected_but_not_promoted() -> None:
    """The review defect, at counter level: the same package is no promotion.

    Two arms can send the same symbols with different scores.  The bonus is then
    present in the sent context without having changed any of it, and only a
    counterfactual baseline can tell the two claims apart.
    """
    package = _package(CHANGED_SYMBOL, CHANGED_METHOD, UNCHANGED_SYMBOL)
    candidates = [
        _candidate(CHANGED_SYMBOL, CHANGED_MODULE, RankingReason.CHANGED_FILE),
        _candidate(CHANGED_METHOD, CHANGED_MODULE, RankingReason.CHANGED_FILE),
        _candidate(UNCHANGED_SYMBOL, UNCHANGED_MODULE),
    ]

    counts = changed_file_promotion_counts(
        package, candidates, frozenset({CHANGED_MODULE}), package
    )

    assert counts["changed_symbols_selected"] == 2
    assert counts["changed_primary_promoted"] is False
    assert counts["changed_symbols_promoted"] == 0
    # Identical packages in both arms: nothing about the context changed, and the
    # record says so from the comparison rather than from a guess.
    assert counts["changed_context_differs"] is False
    assert counts["changed_baseline_status"] == "built"


def test_a_reorder_of_the_same_symbols_is_a_change() -> None:
    """The defect this closes: a reordered context is not an inert one.

    A flat bonus is a reordering signal, so the common honest answer is "the same
    symbols, in a different order".  Comparing the primary alone and the rest as
    sets would call that no change at all, and the model does read the two in a
    different order.
    """
    counts = changed_file_promotion_counts(
        _package(CHANGED_SYMBOL, UNCHANGED_SYMBOL, CHANGED_METHOD),
        [
            _candidate(CHANGED_SYMBOL, CHANGED_MODULE, RankingReason.CHANGED_FILE),
            _candidate(UNCHANGED_SYMBOL, UNCHANGED_MODULE),
            _candidate(CHANGED_METHOD, CHANGED_MODULE, RankingReason.CHANGED_FILE),
        ],
        frozenset({CHANGED_MODULE}),
        _package(CHANGED_SYMBOL, CHANGED_METHOD, UNCHANGED_SYMBOL),
    )

    assert counts["changed_context_differs"] is True
    assert counts["changed_primary_promoted"] is False
    assert counts["changed_symbols_promoted"] == 0
    assert counts["changed_symbols_selected"] == 2
    assert counts["changed_baseline_status"] == "built"


def test_primary_flip_without_a_symbol_flip() -> None:
    """A different leader from the same sent set is a primary flip, not more."""
    counts = changed_file_promotion_counts(
        _package(CHANGED_SYMBOL, CHANGED_METHOD, UNCHANGED_SYMBOL),
        [
            _candidate(CHANGED_SYMBOL, CHANGED_MODULE, RankingReason.CHANGED_FILE),
            _candidate(CHANGED_METHOD, CHANGED_MODULE, RankingReason.CHANGED_FILE),
            _candidate(UNCHANGED_SYMBOL, UNCHANGED_MODULE),
        ],
        frozenset({CHANGED_MODULE}),
        _package(UNCHANGED_SYMBOL, CHANGED_SYMBOL, CHANGED_METHOD),
    )

    assert counts["changed_primary_promoted"] is True
    assert counts["changed_symbols_promoted"] == 0
    assert counts["changed_symbols_selected"] == 2
    # A different leader is a changed context even when the sent set is identical.
    assert counts["changed_context_differs"] is True


def test_symbols_the_baseline_never_sent_are_counted() -> None:
    """A symbol that only exists in the sent set because of the bonus counts."""
    counts = changed_file_promotion_counts(
        _package(CHANGED_SYMBOL, CHANGED_METHOD),
        [
            _candidate(CHANGED_SYMBOL, CHANGED_MODULE, RankingReason.CHANGED_FILE),
            _candidate(CHANGED_METHOD, CHANGED_MODULE, RankingReason.CHANGED_FILE),
        ],
        frozenset({CHANGED_MODULE}),
        _package(UNCHANGED_SYMBOL, CHANGED_SYMBOL),
    )

    assert counts["changed_symbols_promoted"] == 1
    assert counts["changed_primary_promoted"] is True
    assert counts["changed_context_differs"] is True


def test_disabled_signal_never_considers_a_baseline() -> None:
    """With no changed modules there is nothing to attribute, baseline or not."""
    counts = changed_file_promotion_counts(
        _package(CHANGED_SYMBOL, CHANGED_METHOD),
        [_candidate(CHANGED_SYMBOL, CHANGED_MODULE, RankingReason.CHANGED_FILE)],
        frozenset(),
        _package(UNCHANGED_SYMBOL),
    )

    assert counts == {
        "changed_files_count": 0,
        "changed_symbols_selected": 0,
        "changed_primary_promoted": False,
        "changed_symbols_promoted": 0,
        "changed_context_differs": False,
        "changed_baseline_status": "none",
    }


def test_missing_baseline_does_not_invent_a_promotion() -> None:
    """An attempted comparison that produced nothing is stated as failed.

    A request that could not be measured must not read as a measured zero, so the
    status carries the difference while every difference field stays inert.
    """
    counts = changed_file_promotion_counts(
        _package(CHANGED_SYMBOL),
        [_candidate(CHANGED_SYMBOL, CHANGED_MODULE, RankingReason.CHANGED_FILE)],
        frozenset({CHANGED_MODULE}),
        None,
        1,
    )

    assert counts["changed_symbols_selected"] == 1
    assert counts["changed_primary_promoted"] is False
    assert counts["changed_symbols_promoted"] == 0
    assert counts["changed_context_differs"] is False
    assert counts["changed_baseline_status"] == "failed"


def test_no_bonus_candidate_needs_no_comparison() -> None:
    """Zero bonus candidates makes the two arms identical by construction.

    The count turns that into a proof rather than an assumption, and it is also
    what keeps the extra build off requests that cannot possibly differ.
    """
    counts = changed_file_promotion_counts(
        _package(UNCHANGED_SYMBOL),
        [_candidate(UNCHANGED_SYMBOL, UNCHANGED_MODULE)],
        frozenset({CHANGED_MODULE}),
        None,
        0,
    )

    assert counts["changed_files_count"] == 1
    assert counts["changed_symbols_selected"] == 0
    assert counts["changed_context_differs"] is False
    assert counts["changed_primary_promoted"] is False
    assert counts["changed_symbols_promoted"] == 0
    assert counts["changed_baseline_status"] == "skipped_no_bonus"


def test_promotion_is_counted_on_the_final_package() -> None:
    """A primary and a supporting symbol carrying the bonus each count once."""
    counts = changed_file_promotion_counts(
        _package(CHANGED_SYMBOL, UNCHANGED_SYMBOL, CHANGED_METHOD),
        [
            _candidate(CHANGED_SYMBOL, CHANGED_MODULE, RankingReason.CHANGED_FILE),
            _candidate(CHANGED_METHOD, CHANGED_MODULE, RankingReason.CHANGED_FILE),
            _candidate(UNCHANGED_SYMBOL, UNCHANGED_MODULE),
        ],
        frozenset({CHANGED_MODULE}),
        _package(CHANGED_SYMBOL, UNCHANGED_SYMBOL, CHANGED_METHOD),
    )

    assert counts["changed_files_count"] == 1
    assert counts["changed_symbols_selected"] == 2


def test_bonus_without_selection_is_not_counted() -> None:
    """A promoted candidate trimmed out of the package is not counted.

    ``changed_files_count`` stays above zero, which is what separates "the signal
    was read but never reached the model" from "nothing is modified".
    """
    counts = changed_file_promotion_counts(
        _package(UNCHANGED_SYMBOL),
        [
            _candidate(UNCHANGED_SYMBOL, UNCHANGED_MODULE),
            _candidate(CHANGED_SYMBOL, CHANGED_MODULE, RankingReason.CHANGED_FILE),
        ],
        frozenset({CHANGED_MODULE}),
        _package(UNCHANGED_SYMBOL),
    )

    assert counts["changed_files_count"] == 1
    assert counts["changed_symbols_selected"] == 0
    assert counts["changed_symbols_promoted"] == 0


def test_reason_free_selection_counts_nothing() -> None:
    """Without the recorded bonus the same package reports a clean zero."""
    counts = changed_file_promotion_counts(
        _package(CHANGED_SYMBOL, CHANGED_METHOD),
        [
            _candidate(CHANGED_SYMBOL, CHANGED_MODULE),
            _candidate(CHANGED_METHOD, CHANGED_MODULE),
        ],
        frozenset({CHANGED_MODULE}),
        _package(CHANGED_SYMBOL, CHANGED_METHOD),
    )

    assert counts["changed_symbols_selected"] == 0
    assert counts["changed_files_count"] == 1


def test_changed_modules_are_counted_even_with_no_symbols() -> None:
    """Several modified files read as a count, never as a list of paths."""
    counts = changed_file_promotion_counts(
        _package(CHANGED_SYMBOL),
        [_candidate(CHANGED_SYMBOL, CHANGED_MODULE, RankingReason.CHANGED_FILE)],
        frozenset({"modules/beta", "modules/gamma", "modules/delta"}),
        _package(CHANGED_SYMBOL),
    )

    assert counts["changed_files_count"] == 3
    assert counts["changed_symbols_selected"] == 1


def test_suppressed_symbol_is_not_counted() -> None:
    """A symbol the delta tracker filtered out is absent from the candidates."""
    before = changed_file_promotion_counts(
        _package(CHANGED_SYMBOL),
        [_candidate(CHANGED_SYMBOL, CHANGED_MODULE, RankingReason.CHANGED_FILE)],
        frozenset({CHANGED_MODULE}),
        _package(CHANGED_SYMBOL),
    )
    after_suppression = changed_file_promotion_counts(
        _package(""),
        [],
        frozenset({CHANGED_MODULE}),
        _package(CHANGED_SYMBOL),
    )

    assert before["changed_symbols_selected"] == 1
    assert after_suppression["changed_symbols_selected"] == 0
    assert after_suppression["changed_files_count"] == 1
    assert after_suppression["changed_primary_promoted"] is True


# ---------------------------------------------------------------------------
# Counterfactual promotion through the stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bonus_present_without_changing_anything() -> None:
    """The reproduced defect: identical context must never read as promotion.

    With the working tree dirty in ``modules/beta`` this query sends the same
    package in both arms, because the changed module's symbol was already first.
    Counting bonus-carrying symbols alone would call that a promotion.
    """
    off = await _stage(changed=False).execute(_context({"role": "user", "content": SAME_QUERY}))
    on = await _stage().execute(_context({"role": "user", "content": SAME_QUERY}))

    assert off.data is not None and on.data is not None
    assert off.data["package"] == on.data["package"]
    assert _sent(on) == _sent(off)

    assert on.data["changed_files_count"] == 1
    assert on.data["changed_symbols_selected"] > 0
    assert on.data["changed_primary_promoted"] is False
    assert on.data["changed_symbols_promoted"] == 0
    assert on.data["changed_context_differs"] is False
    assert on.data["changed_baseline_status"] == "built"
    assert on.data["changed_files_signal"] == "ok"

    assert off.data["changed_files_count"] == 0
    assert off.data["changed_symbols_selected"] == 0
    assert off.data["changed_primary_promoted"] is False
    assert off.data["changed_symbols_promoted"] == 0
    assert off.data["changed_context_differs"] is False
    assert off.data["changed_baseline_status"] == "none"
    assert off.data["changed_files_signal"] == "off"


@pytest.mark.asyncio
async def test_primary_flip_is_reported_as_a_promotion() -> None:
    """The genuine flip: the bonus replaces an explicitly named symbol."""
    off = await _stage(changed=False).execute(_context({"role": "user", "content": FLIP_QUERY}))
    on = await _stage().execute(_context({"role": "user", "content": FLIP_QUERY}))

    assert off.data is not None and on.data is not None
    assert _sent(on) == _sent(off)
    assert on.data["package"].primary_symbol != off.data["package"].primary_symbol

    assert on.data["changed_primary_promoted"] is True
    assert on.data["changed_symbols_promoted"] == len(_sent(on) - _sent(off))
    assert on.data["changed_symbols_selected"] > 0
    assert on.data["changed_context_differs"] is True
    assert on.data["changed_baseline_status"] == "built"
    assert off.data["changed_primary_promoted"] is False
    assert off.data["changed_symbols_promoted"] == 0
    assert off.data["changed_context_differs"] is False


@pytest.mark.asyncio
async def test_bonus_can_send_a_symbol_the_baseline_did_not() -> None:
    """Under a tight budget the two arms send different sets, and it is counted."""
    off = await _stage(changed=False, max_context_tokens=32).execute(
        _context({"role": "user", "content": FLIP_QUERY})
    )
    on = await _stage(max_context_tokens=32).execute(
        _context({"role": "user", "content": FLIP_QUERY})
    )

    assert off.data is not None and on.data is not None
    assert on.data["changed_primary_promoted"] is True
    assert on.data["changed_symbols_promoted"] == len(_sent(on) - _sent(off))
    assert on.data["changed_symbols_promoted"] >= 1


@pytest.mark.asyncio
async def test_unrelated_symbol_in_a_changed_module_is_neither_sent_nor_counted() -> None:
    """A dirty file's symbol no query names never reaches the promotion counts.

    The bonus is gated on query relevance, so a changed module's symbols that no
    token matches carry no bonus at all: the public one is sent in both arms
    because it clears the ranking floor by itself, and the private one is sent in
    neither.  Both must stay out of the counts, or "something in a dirty file was
    sent" would read as promotion on every request.
    """
    index = _index(with_unrelated=True)

    off = await _stage(changed=False, index=index).execute(
        _context({"role": "user", "content": FLIP_QUERY})
    )
    on = await _stage(index=index).execute(_context({"role": "user", "content": FLIP_QUERY}))

    assert off.data is not None and on.data is not None
    assert HIDDEN_SYMBOL not in _sent(off)
    assert HIDDEN_SYMBOL not in _sent(on)
    assert UNRELATED_SYMBOL in _sent(off)
    assert UNRELATED_SYMBOL in _sent(on)

    assert on.data["changed_files_count"] == 1
    assert on.data["changed_symbols_selected"] == 2
    assert on.data["changed_symbols_promoted"] == len(_sent(on) - _sent(off)) == 0


@pytest.mark.asyncio
async def test_budget_trimming_removes_the_promotion_from_the_counts() -> None:
    """Only what survives into the package counts, in either direction."""
    off = await _stage(changed=False, max_context_tokens=16).execute(
        _context({"role": "user", "content": FLIP_QUERY})
    )
    on = await _stage(max_context_tokens=16).execute(
        _context({"role": "user", "content": FLIP_QUERY})
    )

    assert off.data is not None and on.data is not None
    package = on.data["package"]
    assert package.primary_symbol == CHANGED_SYMBOL
    # The second bonus-carrying symbol never survives this budget.
    assert CHANGED_METHOD not in package.supporting_symbols
    assert on.data["changed_files_count"] == 1
    assert on.data["changed_symbols_selected"] == 1
    assert on.data["changed_symbols_promoted"] == len(_sent(on) - _sent(off)) == 1
    assert off.data["changed_symbols_promoted"] == 0


@pytest.mark.asyncio
async def test_the_baseline_never_touches_the_delta_tracker() -> None:
    """The counterfactual borrows the filter; it must not read or write state."""
    turn_one = {"role": "user", "content": SAME_QUERY}
    reply = {"role": "assistant", "content": "it runs the widgets"}
    turn_two = {"role": "user", "content": f"{SAME_QUERY} again"}

    on = _stage()
    on_tracker = _RecordingTracker()
    on._tracker = on_tracker
    off = _stage(changed=False)
    off_tracker = _RecordingTracker()
    off._tracker = off_tracker

    first = await on.execute(_context(turn_one))
    second = await on.execute(_context(turn_one, reply, turn_two))
    await off.execute(_context(turn_one))
    off_second = await off.execute(_context(turn_one, reply, turn_two))

    assert first.data is not None and second.data is not None
    assert off_second.data is not None
    # One lookup and one store per request, never one per build.
    assert on_tracker.lookups == 2
    assert len(on_tracker.stored) == 2
    # Turn one stores exactly what turn one sent, so the baseline added nothing.
    assert on_tracker.stored[0][1] == frozenset(_sent(first))
    # And the baseline cannot have changed what the off arm would have stored.
    assert on_tracker.stored[-1][0] == off_tracker.stored[-1][0]
    assert on_tracker.stored[-1][1] == off_tracker.stored[-1][1]
    assert frozenset(_sent(second)) <= on_tracker.stored[-1][1]
    assert second.data["symbols_suppressed"] == off_second.data["symbols_suppressed"]
    assert second.data["changed_symbols_promoted"] == 0


@pytest.mark.asyncio
async def test_disabled_mode_builds_once_and_sends_the_same_context(
    builder_spy: list[frozenset[str]],
) -> None:
    """No source means no baseline build and no change to what is serialized."""
    explicit = RepositoryContextStage(index=_index(), changed_files=None)
    implicit = RepositoryContextStage(index=_index())

    context_a = _context({"role": "user", "content": FLIP_QUERY})
    context_b = _context({"role": "user", "content": FLIP_QUERY})
    first = await explicit.execute(context_a)
    second = await implicit.execute(context_b)

    assert first.data is not None and second.data is not None
    # Exactly one build per request: a disabled signal never pays for the
    # counterfactual, and two stage instances are two requests.
    assert len(builder_spy) == 2
    assert all(carried == frozenset() for carried in builder_spy)

    assert first.data["package"] == second.data["package"]
    request_a = context_a.get_metadata("provider_request")
    request_b = context_b.get_metadata("provider_request")
    assert request_a is not None and request_b is not None
    assert request_a.messages == request_b.messages

    assert {key: first.data[key] for key in PROMOTION_KEYS} == {
        key: second.data[key] for key in PROMOTION_KEYS
    }
    assert first.data["changed_files_signal"] == "off"


@pytest.mark.asyncio
async def test_an_enabled_request_builds_the_same_query_twice(
    builder_spy: list[frozenset[str]],
) -> None:
    """The counterfactual is a second build of the same query, without the set."""
    result = await _stage().execute(_context({"role": "user", "content": FLIP_QUERY}))

    assert result.data is not None
    assert builder_spy == [frozenset({CHANGED_MODULE}), frozenset()]
    assert result.data["changed_files_count"] == 1
    assert result.data["changed_baseline_ms"] >= 0
    assert result.data["changed_baseline_status"] == "built"
    assert result.data["changed_context_differs"] is True


@pytest.mark.asyncio
async def test_a_reorder_is_a_change_and_not_an_inert_result() -> None:
    """The defect this closes, at stage level: order alone is a change.

    Here the bonus can neither move the leader nor add a symbol - it only swaps
    the supporting symbols it lifted.  A comparison of the primary plus the rest
    as sets would call that "present but inert", and the model did read the same
    symbols in a different order.
    """
    off = await _stage(changed=False, index=_reorder_index()).execute(
        _context({"role": "user", "content": REORDER_QUERY})
    )
    on = await _stage(index=_reorder_index()).execute(
        _context({"role": "user", "content": REORDER_QUERY})
    )

    assert off.data is not None and on.data is not None
    assert on.data["package"].primary_symbol == off.data["package"].primary_symbol
    assert _sent(on) == _sent(off)
    assert [on.data["package"].primary_symbol, *on.data["package"].supporting_symbols] != [
        off.data["package"].primary_symbol, *off.data["package"].supporting_symbols
    ]

    assert on.data["changed_files_signal"] == "ok"
    assert on.data["changed_files_count"] == 1
    assert on.data["changed_symbols_selected"] > 0
    assert on.data["changed_context_differs"] is True
    assert on.data["changed_primary_promoted"] is False
    assert on.data["changed_symbols_promoted"] == 0
    assert on.data["changed_baseline_status"] == "built"


@pytest.mark.asyncio
async def test_a_dirty_tree_the_query_ignores_builds_once(
    builder_spy: list[frozenset[str]],
) -> None:
    """The cost fix: a bonus that touched nothing is not worth a second build.

    The changed-module set only ever reaches the ranking engine, so with zero
    bonus candidates the two arms are identical by construction.  That is stated
    as its own status instead of being paid for and reported as a measurement.
    """
    result = await _stage().execute(_context({"role": "user", "content": NO_BONUS_QUERY}))

    assert result.data is not None
    assert builder_spy == [frozenset({CHANGED_MODULE})]
    assert result.data["symbols_selected"] > 0
    assert result.data["changed_files_signal"] == "ok"
    assert result.data["changed_files_count"] == 1
    assert result.data["changed_symbols_selected"] == 0
    assert result.data["changed_context_differs"] is False
    assert result.data["changed_primary_promoted"] is False
    assert result.data["changed_symbols_promoted"] == 0
    assert result.data["changed_baseline_status"] == "skipped_no_bonus"
    assert result.data["changed_baseline_ms"] == 0.0


@pytest.mark.asyncio
async def test_the_baseline_package_is_never_attached_anywhere() -> None:
    """The counterfactual reaches counts only: not the context, not the result."""
    stage = _stage()
    context = _context({"role": "user", "content": FLIP_QUERY})

    result = await stage.execute(context)

    assert result.data is not None
    assert "baseline_package" not in result.data
    assert context.context_package is result.data["package"]
    packages_in_result = [
        value for value in result.data.values() if isinstance(value, ContextPackage)
    ]
    assert packages_in_result == [context.context_package]


# ---------------------------------------------------------------------------
# Signal state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signal_is_off_without_a_source() -> None:
    """No source configured is a state of its own, not a clean tree."""
    result = await _stage(changed=False).execute(
        _context({"role": "user", "content": FLIP_QUERY})
    )

    assert result.data is not None
    assert result.data["changed_files_signal"] == "off"
    assert result.data["changed_files_count"] == 0
    assert result.data["changed_baseline_ms"] == 0


@pytest.mark.asyncio
async def test_signal_is_ok_with_a_clean_tree() -> None:
    """A source that answers with nothing is working, not unavailable."""
    stage = _stage(source=_StubSource(frozenset()))

    result = await stage.execute(_context({"role": "user", "content": FLIP_QUERY}))

    assert result.data is not None
    assert result.data["changed_files_signal"] == "ok"
    assert result.data["changed_files_count"] == 0
    assert result.data["changed_symbols_selected"] == 0
    assert result.data["changed_primary_promoted"] is False
    assert result.data["changed_symbols_promoted"] == 0


@pytest.mark.asyncio
async def test_signal_is_unavailable_when_the_source_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing source is stated as unavailable, and never breaks the request."""
    stage = _stage(source=_BrokenSource())

    with caplog.at_level(logging.DEBUG, logger="packages.pipeline.stages.repository_context"):
        result = await stage.execute(_context({"role": "user", "content": FLIP_QUERY}))

    assert result.success is True
    assert result.data is not None
    assert result.data["changed_files_signal"] == "unavailable"
    assert result.data["changed_files_count"] == 0
    assert result.data["changed_symbols_selected"] == 0
    assert result.data["changed_primary_promoted"] is False
    assert result.data["changed_symbols_promoted"] == 0
    lines = "\n".join(record.getMessage() for record in caplog.records)
    assert "changed_files_signal=unavailable" in lines
    assert "simulated git failure" not in lines


@pytest.mark.asyncio
async def test_a_comparison_that_fails_is_unmeasured_not_inert(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A baseline that cannot be built must not read as a bonus that did nothing.

    The request still sends what it ranked, so the failure is invisible unless the
    record states it: the status says "failed" and every difference field stays
    inert, which the analyzer can then keep out of both verdicts.
    """
    real = stage_module.ContextBuilder
    builds: list[frozenset[str]] = []

    class _FailOnBaseline(real):  # type: ignore[valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            builds.append(frozenset(kwargs.get("changed_modules", ())))

        def build(self, *args: Any, **kwargs: Any) -> Any:
            if not builds[-1]:  # the second pass is the one without the bonus
                raise RuntimeError("simulated baseline failure")
            return super().build(*args, **kwargs)

    monkeypatch.setattr(stage_module, "ContextBuilder", _FailOnBaseline)
    stage = _stage()

    with caplog.at_level(logging.DEBUG, logger="packages.pipeline.stages.repository_context"):
        result = await stage.execute(_context({"role": "user", "content": FLIP_QUERY}))

    assert result.success is True
    assert result.data is not None
    assert result.data["symbols_selected"] > 0
    assert result.data["changed_files_signal"] == "ok"
    assert result.data["changed_files_count"] == 1
    assert result.data["changed_symbols_selected"] == 2
    assert result.data["changed_baseline_status"] == "failed"
    assert result.data["changed_context_differs"] is False
    assert result.data["changed_primary_promoted"] is False
    assert result.data["changed_symbols_promoted"] == 0
    lines = "\n".join(record.getMessage() for record in caplog.records)
    assert "changed_baseline_status=failed" in lines
    assert "simulated baseline failure" not in lines


@pytest.mark.asyncio
async def test_a_degraded_request_states_the_signal_it_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request that assembled nothing still reports what the signal said.

    Falling back to the inert default here would write ``off`` over a working
    source, which is a different claim than "the stage never finished".
    """

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("simulated build failure")

    monkeypatch.setattr(stage_module.ContextBuilder, "build", _boom)
    stage = _stage()
    context = _context({"role": "user", "content": FLIP_QUERY})

    result = await stage.execute(context)

    assert result.success is True
    assert result.data is None
    assert context.get_metadata("changed_files_signal") == "ok"


@pytest.mark.asyncio
async def test_a_failure_before_the_read_says_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the signal was never consulted, the state is not a clean ``off``."""

    def _boom(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError("simulated query failure")

    monkeypatch.setattr(stage_module, "select_context_query_text", _boom)
    stage = _stage()
    context = _context({"role": "user", "content": FLIP_QUERY})

    result = await stage.execute(context)

    assert result.success is True
    assert result.data is None
    assert context.get_metadata("changed_files_signal") == "unavailable"


@pytest.mark.asyncio
async def test_signal_is_stated_on_the_path_with_no_candidates() -> None:
    """Even with nothing to send, the record says whether the signal ran."""
    stage = _stage()

    result = await stage.execute(_context({"role": "user", "content": "zzz qqq xyzzy plugh"}))

    assert result.data is not None
    assert result.data["changed_files_signal"] == "ok"
    assert result.data["changed_files_count"] == 1
    assert result.data["changed_symbols_selected"] == 0
    assert result.data["changed_primary_promoted"] is False
    assert result.data["changed_symbols_promoted"] == 0
    # Nothing ranked, so nothing could carry the bonus and no comparison was due.
    assert result.data["changed_context_differs"] is False
    assert result.data["changed_baseline_status"] == "skipped_no_bonus"


@pytest.mark.asyncio
async def test_changed_module_outside_the_index_is_seen_but_not_sent() -> None:
    """A modified file with no indexed symbols shows up as a count only."""
    stage = _stage(source=_StubSource(frozenset({"modules/gamma"})))

    result = await stage.execute(_context({"role": "user", "content": FLIP_QUERY}))

    assert result.data is not None
    assert result.data["changed_files_count"] == 1
    assert result.data["changed_symbols_selected"] == 0
    assert result.data["changed_primary_promoted"] is False
    assert result.data["changed_symbols_promoted"] == 0


@pytest.mark.asyncio
async def test_disabled_context_states_the_inert_promotion() -> None:
    """A request with context turned off still states every field."""
    stage = _stage()
    context = _context({"role": "user", "content": FLIP_QUERY})
    context.set_metadata("context_enabled", False)

    result = await stage.before(context)

    assert result is not None
    assert result.data is not None
    assert result.data["enabled"] is False
    assert {key: result.data[key] for key in PROMOTION_KEYS} == dict(INERT_PROMOTION)


@pytest.mark.asyncio
async def test_delta_suppression_lowers_both_counts() -> None:
    """A promoted supporting symbol already sent stops counting on turn two."""
    stage = _stage()

    first = await stage.execute(_context({"role": "user", "content": FLIP_QUERY}))
    second = await stage.execute(
        _context(
            {"role": "user", "content": FLIP_QUERY},
            {"role": "assistant", "content": "the store keeps widgets"},
            {"role": "user", "content": f"{FLIP_QUERY} again"},
        )
    )

    assert first.data is not None and second.data is not None
    assert second.data["symbols_suppressed"] >= 1
    assert first.data["changed_symbols_selected"] == 2
    assert second.data["changed_symbols_selected"] == 1
    assert first.data["changed_files_count"] == second.data["changed_files_count"] == 1


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [SAME_QUERY, FLIP_QUERY, REORDER_QUERY, NO_BONUS_QUERY])
async def test_stage_log_lines_are_count_only(
    caplog: pytest.LogCaptureFixture,
    query: str,
) -> None:
    """The completion line states counts and never a path, module, or symbol."""
    stage = _stage()

    with caplog.at_level(logging.DEBUG, logger="packages.pipeline.stages.repository_context"):
        result = await stage.execute(_context({"role": "user", "content": query}))

    assert result.data is not None
    lines = "\n".join(record.getMessage() for record in caplog.records)
    for key in PROMOTION_KEYS:
        assert f"{key}=" in lines, key
    assert "changed_baseline_ms=" in lines
    for forbidden in FORBIDDEN:
        assert forbidden not in lines, forbidden


@pytest.mark.asyncio
async def test_the_inert_promotion_carries_no_name() -> None:
    """The shared default is count-only, so no caller can leak through it."""
    assert set(INERT_PROMOTION) == set(PROMOTION_KEYS)
    assert not any(forbidden in repr(INERT_PROMOTION) for forbidden in FORBIDDEN)








