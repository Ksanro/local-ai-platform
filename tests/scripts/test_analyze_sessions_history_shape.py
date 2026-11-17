"""Tests for the history-shape cap simulation in scripts/analyze_sessions.py.

The analyzer reads the ``history.shape`` summary a gateway request recorded and
answers, offline, what ``packages.pipeline.history.cap_history`` would have done
to that message list at a candidate budget.  Three things make that a claim that
has to be pinned rather than eyeballed:

- the walk has to be the *production* walk - atomic groups kept whole, the
  protected group reserved and charged before anything else is considered,
  system groups kept at no cost, newest-first until the first group that does
  not fit - and not a simpler policy that happens to agree most of the time;
- the recorded detail is bounded.  A summary that stopped early states the mass
  it left out, so a simulation can prove where a cap stops only for a budget the
  recorded prefix actually covers.  Beyond that the honest answer is
  "indeterminate", never an extrapolated cut point;
- ``last_user_group`` repeats the prefix's entry for the protected group rather
  than adding a group, so a walk that charged both would reserve the same
  messages twice and report a cap that never runs.

Records written before ``APP_HISTORY_SHAPE_LOG_ENABLED`` exist, and records
whose measurement could not run are counted apart from the ones that can be
simulated - an absent measurement must never read as a transcript of zero
tokens.  Nothing here reads message content, and nothing here enables a cap.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from typing import Any

from packages.pipeline.history import _message_token_count, cap_history
from packages.pipeline.history_shape import (
    _protected_history_index,
    summarize_history_shape,
)
from scripts.analyze_sessions import (
    HISTORY_CAP_CANDIDATE_BUDGETS,
    _print_history_shape_simulation,
    analyze,
    classify_history_shape,
    history_cap_simulation_summary,
    simulate_cap_from_shape,
)

BUDGET = 1000


def _group(
    ordinal: int,
    *,
    messages: int = 1,
    tokens: int = 0,
    eligible: int | None = None,
    has_system: bool = False,
    protected: bool = False,
    orphan_calls: int = 0,
    orphan_results: int = 0,
) -> dict[str, Any]:
    """One atomic group, as a ``history-shape-v2`` summary states it.

    ``eligible`` defaults to ``tokens``.  A system group, or a group whose only
    non-system member is the protected message, is the case that has to say
    otherwise, and it says so at the call site rather than by omission.
    """
    return {
        "ordinal": ordinal,
        "message_count": messages,
        "tokens": tokens,
        "cap_eligible_tokens": tokens if eligible is None else eligible,
        "roles": {},
        "has_system": has_system,
        "has_last_user": protected,
        "has_tool_calls": False,
        "has_tool_results": False,
        "pairing_complete": not (orphan_calls or orphan_results),
        "orphan_tool_calls": orphan_calls,
        "orphan_tool_results": orphan_results,
    }
def _shape(
    groups: list[dict[str, Any]],
    *,
    recorded: int | None = None,
    protected_ordinal: int | None = 0,
    last_user_distance: int | None = 0,
) -> dict[str, Any]:
    """A whole summary derived from its groups, so its totals cannot disagree.

    Args:
        groups: Every group of the transcript, newest first - the order the
            summary's ``ordinal`` field counts in.
        recorded: How many of those the bounded detail wrote out.  The rest are
            stated as omitted rather than left unmentioned.
        protected_ordinal: The ordinal of the group holding the position capping
            never drops, or ``None`` when nothing was protected.
        last_user_distance: ``None`` says the list held no ``user`` message at
            all, which is what separates a no-user protected position from a
            transcript with nothing to protect.

    Returns:
        A ``history-shape-v2`` measured summary.
    """
    keep = len(groups) if recorded is None else recorded
    prefix = groups[:keep]
    omitted = groups[keep:]
    reserved = next((g for g in groups if g["ordinal"] == protected_ordinal), None)
    messages = sum(g["message_count"] for g in groups)
    eligible = sum(g["cap_eligible_tokens"] for g in groups)
    return {
        "schema": "history-shape-v2",
        "status": "measured",
        "chars_per_token": 4.0,
        "message_count": messages,
        "system_message_count": sum(g["message_count"] for g in groups if g["has_system"]),
        "non_system_message_count": sum(
            g["message_count"] for g in groups if not g["has_system"]
        ),
        "history_tokens": sum(g["tokens"] for g in groups),
        "cap_eligible_tokens": eligible,
        "group_count": len(groups),
        "recorded_groups": len(prefix),
        "omitted_groups": len(omitted),
        "recorded_tokens": sum(g["tokens"] for g in prefix),
        "omitted_tokens": sum(g["tokens"] for g in omitted),
        "recorded_cap_eligible_tokens": sum(g["cap_eligible_tokens"] for g in prefix),
        "omitted_cap_eligible_tokens": sum(g["cap_eligible_tokens"] for g in omitted),
        "omitted_messages": messages - sum(g["message_count"] for g in prefix),
        "detail_complete": not omitted,
        "last_message_role": "user",
        "last_user_distance": last_user_distance,
        "last_user_group": reserved,
        "assistant_with_tool_calls": 0,
        "tool_result_count": 0,
        "complete_tool_groups": sum(1 for g in groups if g["pairing_complete"]),
        "orphan_tool_calls": sum(g["orphan_tool_calls"] for g in groups),
        "orphan_tool_results": sum(g["orphan_tool_results"] for g in groups),
        "groups": prefix,
    }


def _record(shape: Any) -> dict[str, Any]:
    """One session record, with the summary nested the way the logger nests it."""
    history: dict[str, Any] = {"cap_enabled": False, "cap_applied": False}
    if shape is not _ABSENT:
        history["shape"] = shape
    return {"status": "ok", "history": history}


#: Sentinel meaning "this record never stated a shape at all".
_ABSENT = object()


def _printed(records: list[dict[str, Any]]) -> str:
    """The section as it reaches stdout."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        _print_history_shape_simulation(records)
    return buffer.getvalue()

class TestRecordClassification:
    """What a record's shape can and cannot be asked."""

    def test_records_with_no_shape_are_not_read_as_empty_histories(self) -> None:
        """A log that predates the summary yields a sweep with nothing in it."""
        records = [{"status": "ok"}, {"status": "ok", "history": {"cap_enabled": False}}]

        summary = history_cap_simulation_summary(records)

        assert summary["records"] == 2
        assert summary["tally"]["no_shape"] == 2
        assert summary["usable"] == 0
        for entry in summary["budgets"]:
            assert entry["usable"] == 0
            assert entry["exact"] == 0
            assert entry["indeterminate"] == 0
            assert entry["messages_dropped"]["n"] == 0

    def test_unavailable_unknown_and_malformed_are_three_separate_tallies(self) -> None:
        """An unrun measurement, a foreign schema and a broken one differ."""
        records = [
            _record({"schema": "history-shape-v2", "status": "unavailable"}),
            _record({"schema": "history-shape-v1", "status": "measured"}),
            _record("not even a dict"),
            _record({"schema": 2, "status": "measured"}),
        ]

        tally = history_cap_simulation_summary(records)["tally"]

        assert tally["unavailable"] == 1
        assert tally["unknown_schema"] == 1
        assert tally["malformed"] == 2
        assert tally["measured"] == 0

    def test_a_measured_shape_missing_a_walk_field_is_malformed(self) -> None:
        """Defaulting an absent total to zero would say "this needs no cap"."""
        shape = _shape([_group(0, tokens=10)])
        del shape["cap_eligible_tokens"]

        assert classify_history_shape(_record(shape)) == ("malformed", None)

    def test_a_bool_where_a_count_belongs_is_malformed(self) -> None:
        """``True`` is an ``int`` to Python, and is not one message."""
        shape = _shape([_group(0, tokens=10)])
        shape["message_count"] = True

        assert classify_history_shape(_record(shape)) == ("malformed", None)

    def test_a_negative_eligible_partition_is_malformed(self) -> None:
        """A negative mass is a broken writer, not a transcript to clamp away.

        The sum is left true in both cases so what fails is the sign and not the
        arithmetic: ``-1 + 21`` and ``21 + -1`` both still equal the total.
        """
        for key in ("recorded_cap_eligible_tokens", "omitted_cap_eligible_tokens"):
            other = next(
                name
                for name in ("recorded_cap_eligible_tokens", "omitted_cap_eligible_tokens")
                if name != key
            )
            shape = _shape([_group(0, tokens=10), _group(1, tokens=10)], recorded=1)
            shape[key] = -1
            shape[other] = 21

            assert classify_history_shape(_record(shape)) == ("malformed", None), key

    def test_an_eligible_partition_that_misses_the_total_is_malformed(self) -> None:
        """``recorded + omitted`` must equal ``cap_eligible_tokens`` exactly.

        The walk reads a truncated detail by that equation, so a summary that
        does not add up is agreement between two numbers the record broke, and it
        gets counted as malformed rather than clamped back into the sweep.
        """
        shape = _shape([_group(0, tokens=10), _group(1, tokens=10)], recorded=1)
        shape["omitted_cap_eligible_tokens"] = 9

        assert classify_history_shape(_record(shape)) == ("malformed", None)

    def test_an_eligible_partition_that_overshoots_the_total_is_malformed(self) -> None:
        shape = _shape([_group(0, tokens=10), _group(1, tokens=10)], recorded=1)
        shape["recorded_cap_eligible_tokens"] = 11

        assert classify_history_shape(_record(shape)) == ("malformed", None)

    def test_a_partition_field_left_out_is_malformed(self) -> None:
        """Both halves are required, because the zero of one is an answer."""
        for key in ("recorded_cap_eligible_tokens", "omitted_cap_eligible_tokens"):
            shape = _shape([_group(0, tokens=10), _group(1, tokens=10)], recorded=1)
            del shape[key]

            assert classify_history_shape(_record(shape)) == ("malformed", None), key

    def test_a_summary_whose_partition_holds_is_usable(self) -> None:
        shape = _shape([_group(0, tokens=10), _group(1, tokens=10)], recorded=1)

        assert classify_history_shape(_record(shape))[0] == "measured"

    def test_a_bounded_prefix_of_nothing_is_usable_not_malformed(self) -> None:
        """An empty detail is a real state the sweep has to be able to report."""
        shape = _shape(
            [_group(0, tokens=10), _group(1, tokens=10)],
            recorded=0,
            protected_ordinal=None,
        )

        kind, returned = classify_history_shape(_record(shape))

        assert kind == "measured"
        assert returned is not None and returned["groups"] == []

    def test_the_classifications_cover_every_record_once(self) -> None:
        """No record is counted twice and none is silently dropped."""
        shapes: list[Any] = [
            _ABSENT,
            {"schema": "history-shape-v2", "status": "unavailable"},
            {"schema": "history-shape-v3", "status": "measured"},
            None,
            _shape([_group(0, tokens=1)]),
        ]

        summary = history_cap_simulation_summary([_record(s) for s in shapes])

        assert sum(summary["tally"].values()) == len(shapes)
        assert summary["usable"] == 1


class TestTheWalk:
    """``cap_history``'s rule, reproduced from the summary rather than re-invented."""

    def test_a_record_under_every_candidate_budget_never_caps(self) -> None:
        """Rule 6: the transform is a no-op below the budget, at each candidate."""
        record = _record(
            _shape([_group(0, tokens=100), _group(1, tokens=9, eligible=0, has_system=True)])
        )

        summary = history_cap_simulation_summary([record])

        assert summary["usable"] == 1
        for entry in summary["budgets"]:
            assert entry["exact"] == 1
            assert entry["indeterminate"] == 0
            assert entry["capped"] == 0
            assert entry["unchanged"] == 1

    def test_the_first_group_that_does_not_fit_ends_the_walk(self) -> None:
        """Rule 3: a group that cannot be kept whole is not kept at all."""
        shape = _shape([_group(0, tokens=1200), _group(1, tokens=100)], protected_ordinal=None)

        result = simulate_cap_from_shape(shape, BUDGET)

        assert result["outcome"] == "capped"
        assert result["cut_ordinal"] == 0
        assert result["dropped_messages"] == 2
        assert result["dropped_cap_eligible_tokens"] == 1300
        assert result["kept_groups"] == 0

    def test_groups_are_kept_newest_first_and_not_by_size(self) -> None:
        """An older small group is dropped while a newer large one is still tried."""
        shape = _shape(
            [_group(0, tokens=900), _group(1, tokens=5000), _group(2, tokens=100)],
            protected_ordinal=None,
        )

        result = simulate_cap_from_shape(shape, BUDGET)

        # The newest group fits, the next does not, and the walk stops there: the
        # 100-token group older than the cut is dropped although it would have fit.
        assert result["cut_ordinal"] == 1
        assert result["dropped_messages"] == 2
        assert result["dropped_cap_eligible_tokens"] == 5100

    def test_system_groups_cost_nothing_and_cannot_cause_the_cut(self) -> None:
        """Rule 1: a system group is neither a step of the walk nor a price."""
        shape = _shape(
            [
                _group(0, tokens=900),
                _group(1, tokens=50000, eligible=0, has_system=True),
                _group(2, tokens=200),
            ],
            protected_ordinal=None,
        )

        result = simulate_cap_from_shape(shape, BUDGET)

        assert result["cut_ordinal"] == 2
        assert result["dropped_messages"] == 1
        assert result["dropped_cap_eligible_tokens"] == 200

    def test_a_system_message_older_than_the_detail_is_still_kept(self) -> None:
        """An unrecorded system group is kept, not dropped with the tail."""
        shape = _shape(
            [_group(0, tokens=1200), _group(1, tokens=50, eligible=0, has_system=True)],
            recorded=1,
            protected_ordinal=None,
        )

        result = simulate_cap_from_shape(shape, BUDGET)

        assert result["exact"] is True
        assert result["dropped_messages"] == 1

    def test_the_protected_group_in_the_prefix_is_reserved_once(self) -> None:
        """``last_user_group`` repeats the prefix entry; charging both is a bug.

        The protected message inside the group is the only free thing in it, so
        the group's other member spends budget - exactly once, not twice.
        """
        shape = _shape(
            [
                _group(0, messages=2, tokens=900, eligible=450, protected=True),
                _group(1, tokens=600),
                _group(2, tokens=100),
            ]
        )
        assert shape["last_user_group"] is shape["groups"][0]

        result = simulate_cap_from_shape(shape, BUDGET)

        # Charged once, the reservation leaves 550 of 1000, and the 600-token
        # group does not fit in it.  Double-counting would have charged 900 and
        # reported 250 dropped rather than 700.
        assert result["charged_tokens"] == 450
        assert result["cut_ordinal"] == 1
        assert result["dropped_messages"] == 2
        assert result["dropped_cap_eligible_tokens"] == 700

    def test_the_protected_group_beyond_the_prefix_is_still_kept_whole(self) -> None:
        """A bounded list cannot lose the one group the cap always keeps."""
        shape = _shape(
            [
                _group(0, tokens=300),
                _group(1, tokens=250),
                _group(2, tokens=400),
                _group(3, tokens=400),
                _group(4, messages=2, tokens=1100, eligible=100, protected=True),
            ],
            recorded=2,
            protected_ordinal=4,
        )

        result = simulate_cap_from_shape(shape, 500)

        # Reserved group (ordinal 4) is absent from ``groups`` yet kept; the
        # walk fits ordinal 0 and stops at 1, dropping 1, 2 and 3.
        assert result["exact"] is True
        assert result["reserved_tokens"] == 100
        assert result["cut_ordinal"] == 1
        assert result["dropped_messages"] == 3
        assert result["dropped_cap_eligible_tokens"] == 1050

    def test_a_reservation_bigger_than_the_budget_keeps_the_group_alone(self) -> None:
        """The cap cannot fit the protected group and still cannot split it."""
        shape = _shape(
            [
                _group(0, messages=2, tokens=5000, eligible=5000, protected=True),
                _group(1, tokens=10),
            ]
        )

        result = simulate_cap_from_shape(shape, BUDGET)

        assert result["outcome"] == "capped"
        assert result["cut_ordinal"] == 1
        assert result["dropped_messages"] == 1
        assert result["dropped_cap_eligible_tokens"] == 10

    def test_with_no_candidate_group_no_budget_drops_anything(self) -> None:
        """The other half of the reservation: everything left is system text.

        ``cap_history`` returns such a list untouched even over budget, because
        the only group it could drop is the one it is forbidden to split.
        """
        shape = _shape(
            [
                _group(0, messages=3, tokens=9000, eligible=8000, protected=True),
                _group(1, tokens=100, eligible=0, has_system=True),
            ]
        )

        result = simulate_cap_from_shape(shape, BUDGET)

        assert result["outcome"] == "unchanged"
        assert result["reason"] == "nothing_chargeable"
        assert result["dropped_messages"] == 0

    def test_a_no_user_shape_protects_a_position_not_a_user_message(self) -> None:
        """Rule 2's fallback: the group can be an assistant call and its result."""
        shape = _shape(
            [
                _group(0, messages=2, tokens=1000, eligible=500, protected=True),
                _group(1, tokens=700),
            ],
            last_user_distance=None,
        )

        result = simulate_cap_from_shape(shape, BUDGET)

        assert result["protected_position_without_user"] is True
        assert result["reserved_tokens"] == 500
        assert result["cut_ordinal"] == 1
        assert result["dropped_messages"] == 1

    def test_a_shape_with_nothing_to_protect_walks_the_ordinary_order(self) -> None:
        """An all-assistant list has no reservation and no free message."""
        shape = _shape(
            [_group(0, tokens=600), _group(1, tokens=600)],
            protected_ordinal=None,
            last_user_distance=None,
        )

        result = simulate_cap_from_shape(shape, BUDGET)

        assert result["reserved_tokens"] == 0
        assert result["cut_ordinal"] == 1
        assert result["dropped_messages"] == 1
        assert result["dropped_cap_eligible_tokens"] == 600

class TestBoundedDetail:
    """What a truncated summary can and cannot be asked."""

    def test_a_small_budget_is_exact_where_a_larger_one_is_indeterminate(self) -> None:
        """The prefix covers the cut for one budget and not for the next."""
        shape = _shape(
            [
                _group(0, tokens=8000),
                _group(1, tokens=9000),
                _group(2, tokens=8000),
                _group(3, tokens=9000),
            ],
            recorded=2,
            protected_ordinal=None,
        )

        small = simulate_cap_from_shape(shape, 16384)
        large = simulate_cap_from_shape(shape, 32768)

        assert small["exact"] is True
        assert small["cut_ordinal"] == 1
        assert small["dropped_messages"] == 3
        assert small["dropped_cap_eligible_tokens"] == 26000
        # Everything the record wrote out fits inside 32,768, and it still says
        # 34,000 eligible tokens exist.  Where the cap would stop is not in the
        # record, so the answer is that it is not known - not an extrapolation.
        assert large["outcome"] == "indeterminate"
        assert large["exact"] is False
        assert large["dropped_messages"] is None
        assert large["dropped_cap_eligible_tokens"] is None
        assert large["charged_tokens"] == 17000

    def test_an_incomplete_detail_is_still_exact_once_the_totals_answer(self) -> None:
        """A budget above the whole history needs no detail to settle."""
        shape = _shape(
            [_group(0, tokens=8000), _group(1, tokens=20000)],
            recorded=1,
            protected_ordinal=None,
        )

        result = simulate_cap_from_shape(shape, 32768)

        assert result["outcome"] == "unchanged"
        assert result["exact"] is True
        assert result["detail_complete"] is False
        assert result["dropped_messages"] == 0

    def test_a_detail_short_only_by_system_groups_is_exact_unchanged(self) -> None:
        """``detail_complete`` says the list is short; the partition says by
        nothing a budget could pay for, which is a settled record not an open one.
        """
        shape = _shape(
            [
                _group(0, messages=2, tokens=5000, eligible=5000, protected=True),
                _group(1, tokens=100, eligible=0, has_system=True),
            ],
            recorded=1,
        )

        result = simulate_cap_from_shape(shape, BUDGET)

        assert result["detail_complete"] is False
        assert result["exact"] is True
        assert result["outcome"] == "unchanged"
        assert result["reason"] == "nothing_chargeable"
        assert result["dropped_messages"] == 0
        assert result["dropped_cap_eligible_tokens"] == 0

    def test_a_hidden_zero_cost_candidate_with_a_spent_reservation_is_indeterminate(
        self,
    ) -> None:
        """No eligible mass omitted is not yet "nothing droppable omitted".

        A group of empty non-system messages costs a budget nothing and is still a
        candidate: ``cap_history`` asks it the same ``charged + cost <= budget``
        question it asks any other, so once the reservation has spent the budget
        the cap stops at it.  When that group sits beyond the recorded detail the
        record cannot say which group the stop was, and the honest answer is that
        it does not know - not "unchanged".
        """
        groups = [
            _group(0, messages=2, tokens=5000, eligible=5000, protected=True),
            _group(1, tokens=100, eligible=0, has_system=True),
            _group(2, tokens=0, eligible=0),
        ]

        truncated = simulate_cap_from_shape(_shape(groups, recorded=2), BUDGET)
        complete = simulate_cap_from_shape(_shape(groups), BUDGET)

        assert truncated["outcome"] == "indeterminate"
        assert truncated["reason"] == "zero_cost_candidate_unseen"
        assert truncated["dropped_messages"] is None
        # Write the same transcript out in full and the cut is provable: the walk
        # reaches the empty group, cannot fit it, and drops it alone.
        assert complete["outcome"] == "capped"
        assert complete["cut_ordinal"] == 2
        assert complete["dropped_messages"] == 1
        assert complete["dropped_cap_eligible_tokens"] == 0

    def test_the_sweep_reports_how_far_the_detail_reaches(self) -> None:
        """An indeterminate record still says which smaller budgets are exact."""
        shape = _shape(
            [_group(0, tokens=8000), _group(1, tokens=8000), _group(2, tokens=9000)],
            recorded=2,
            protected_ordinal=None,
        )

        entry = history_cap_simulation_summary([_record(shape)])["budgets"][0]

        assert entry["indeterminate"] == 1
        assert entry["indeterminate_coverage"]["n"] == 1
        assert entry["indeterminate_coverage"]["max"] == 16000


class TestShapeQualityCounters:
    """Pairing and protection readings, taken from the shape's own fields."""

    def test_orphans_are_counted_from_the_recorded_counters(self) -> None:
        shape = _shape(
            [
                _group(0, tokens=9000, orphan_calls=2),
                _group(1, tokens=9000, orphan_results=1),
            ],
            protected_ordinal=None,
        )

        summary = history_cap_simulation_summary([_record(shape)])

        assert summary["orphan_records"] == 1
        assert summary["orphan_tool_calls"] == 2
        assert summary["orphan_tool_results"] == 1
        # The per-budget column is budget-dependent only because a record no cap
        # touched cannot have had its orphans dropped by one.
        assert summary["budgets"][0]["capped_with_orphans"] == 1
        assert summary["budgets"][1]["capped_with_orphans"] == 0

    def test_a_record_without_orphans_contributes_to_no_orphan_counter(self) -> None:
        shape = _shape([_group(0, tokens=9000), _group(1, tokens=9000)], protected_ordinal=None)

        summary = history_cap_simulation_summary([_record(shape)])

        assert summary["orphan_records"] == 0
        assert summary["budgets"][0]["capped_with_orphans"] == 0

    def test_the_two_kinds_of_no_protected_turn_are_kept_apart(self) -> None:
        """A fallback position is not the same as having nothing to protect."""
        fallback = _shape([_group(0, tokens=10, protected=True)], last_user_distance=None)
        none_at_all = _shape(
            [_group(0, tokens=10)],
            protected_ordinal=None,
            last_user_distance=None,
        )

        summary = history_cap_simulation_summary([_record(fallback), _record(none_at_all)])

        assert summary["no_user_protected_records"] == 1
        assert summary["nothing_protected_records"] == 1


class TestDenominators:
    """Every figure says which records it divided."""

    def test_indeterminate_records_enter_no_percentile_and_no_rate(self) -> None:
        """A record whose cut is unknown cannot move a p50 of what was dropped."""
        capped = _shape(
            [
                _group(0, tokens=8000),
                _group(1, tokens=8000),
                _group(2, tokens=8000),
                _group(3, tokens=8000),
            ],
            protected_ordinal=None,
        )
        unknown = _shape(
            [_group(0, tokens=8000), _group(1, tokens=8000), _group(2, tokens=9000)],
            recorded=2,
            protected_ordinal=None,
        )

        summary = history_cap_simulation_summary([_record(capped), _record(unknown)])
        entry = summary["budgets"][0]

        assert entry["usable"] == 2
        assert entry["exact"] == 1
        assert entry["indeterminate"] == 1
        assert entry["capped"] == 1
        # One record answers and one does not; the percentile is over the one.
        assert entry["messages_dropped"]["n"] == 1
        assert entry["messages_dropped"]["p50"] == 2
        assert entry["messages_dropped"]["max"] == 2
        assert entry["tokens_dropped"]["p50"] == 16000
        assert entry["rate_capped"] == 1.0
        # One candidate budget up, both totals answer and neither is unknown.
        assert summary["budgets"][1]["exact"] == 2
        assert summary["budgets"][1]["indeterminate"] == 0

    def test_unusable_records_are_out_of_every_denominator(self) -> None:
        """A pre-summary record is not a measured zero-length history."""
        records = [
            _record(_ABSENT),
            _record({"schema": "history-shape-v2", "status": "unavailable"}),
            _record(_shape([_group(0, tokens=9000), _group(1, tokens=9000)])),
        ]

        summary = history_cap_simulation_summary(records)
        entry = summary["budgets"][0]

        assert summary["records"] == 3
        assert entry["usable"] == 1
        assert entry["exact"] == 1
        assert entry["capped"] == 1
        assert entry["rate_capped"] == 1.0


def _sys(chars: int) -> dict[str, Any]:
    return {"role": "system", "content": "s" * chars}


def _usr(chars: int) -> dict[str, Any]:
    return {"role": "user", "content": "u" * chars}


def _ast(chars: int) -> dict[str, Any]:
    return {"role": "assistant", "content": "a" * chars}


def _pair(call_id: str, body: int) -> list[dict[str, Any]]:
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": call_id, "content": "r" * body},
    ]


def _fan(call_id: str, results: int, body: int) -> list[dict[str, Any]]:
    """One assistant call and the several results that answer it."""
    call = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"{call_id}_{i}",
                "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
            }
            for i in range(results)
        ],
    }
    return [call] + [
        {"role": "tool", "tool_call_id": f"{call_id}_{i}", "content": "r" * body}
        for i in range(results)
    ]


#: Transcripts chosen for what they exercise: an atomic group the walk has to
#: move whole, a protected *position* rather than a protected user message,
#: nothing to protect at all, and a system message older than the newest group.
_PARITY_TRANSCRIPTS: dict[str, list[dict[str, Any]]] = {
    "plain exchange": [_sys(40), _usr(40), _ast(40), _usr(40)],
    "tool pair inside history": [_sys(40), *_pair("a", 4000), _ast(40), _usr(4000)],
    "fan out one call two results": [_sys(40), *_fan("b", 2, 3000), _usr(4000)],
    "no user trailing assistant": [_sys(40), *_pair("c", 4000), _ast(40)],
    "assistant only": [_ast(4000), _ast(4000)],
    "system older than history": [_usr(4000), _sys(40), *_pair("d", 4000), _usr(40)],
    "orphan result": [
        _sys(40),
        {"role": "tool", "tool_call_id": "z", "content": "r" * 400},
        _usr(40),
    ],
}

_PARITY_BUDGETS = (0, 1, 400, 1200, 4000, 17000, 131072)


def _charged_by_cap(messages: list[dict[str, Any]], kept: list[dict[str, Any]]) -> int:
    """What a budget really paid for, read off the messages the cap forwarded."""
    protected = _protected_history_index(messages)
    kept_ids = {id(message) for message in kept}
    return sum(
        _message_token_count(message)
        for index, message in enumerate(messages)
        if id(message) in kept_ids
        and message.get("role") != "system"
        and index != protected
    )


class TestProductionParity:
    """The recorded walk and ``cap_history`` reach the same decision."""

    def test_dropped_counts_and_charges_agree(self) -> None:
        for name, messages in _PARITY_TRANSCRIPTS.items():
            shape = summarize_history_shape(messages)
            for budget in _PARITY_BUDGETS:
                kept, dropped = cap_history(messages, max_history_tokens=budget)
                result = simulate_cap_from_shape(shape, budget)
                where = (name, budget)
                assert result["exact"] is True, where
                assert result["dropped_messages"] == dropped, where
                assert len(kept) == len(messages) - dropped, where
                assert result["charged_tokens"] == _charged_by_cap(messages, kept), where
                if result["outcome"] == "unchanged":
                    assert dropped == 0, where

    def test_a_truncated_detail_never_claims_a_cut_it_cannot_see(self) -> None:
        """With the bound forced down, only the provable answers stay exact."""
        for name, messages in _PARITY_TRANSCRIPTS.items():
            shape = summarize_history_shape(messages, max_groups=1)
            for budget in _PARITY_BUDGETS:
                kept, dropped = cap_history(messages, max_history_tokens=budget)
                result = simulate_cap_from_shape(shape, budget)
                where = (name, budget)
                if result["exact"]:
                    assert result["dropped_messages"] == dropped, where
                    assert result["charged_tokens"] == _charged_by_cap(messages, kept), where
                else:
                    assert result["outcome"] == "indeterminate", where
                    assert result["detail_complete"] is False, where
                    assert result["dropped_messages"] is None, where

    def test_a_detail_that_omits_only_system_groups_is_an_exact_no_op(self) -> None:
        """Incomplete detail and nothing chargeable left out are not the same thing.

        A summary bounded to one group can hide only an old system message, and
        then ``omitted_cap_eligible_tokens`` says zero while
        ``detail_complete`` says false.  Production has no candidate group left
        to drop there - system text is kept at any budget and the protected group
        is kept whole - so it returns the transcript untouched, and a simulation
        that read the incomplete flag as "unknown" would report a record that
        needs settling when the record already settled it.
        """
        messages = [
            _sys(40),
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_fat",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "a" * 40000},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_fat", "content": "r" * 400},
        ]
        shape = summarize_history_shape(messages, max_groups=1)

        # The shape says all three of: the detail is short, the protected group
        # is an assistant call and its result rather than a user message, and
        # nothing left out of the detail could ever spend a budget.
        assert shape["detail_complete"] is False
        assert shape["omitted_groups"] == 1
        assert shape["omitted_cap_eligible_tokens"] == 0
        assert shape["last_user_distance"] is None
        assert shape["last_user_group"] is not None
        assert shape["last_user_group"]["roles"] == {"assistant": 1, "tool": 1}

        reserved = int(shape["last_user_group"]["cap_eligible_tokens"])
        assert reserved > 0
        budget = reserved // 2

        kept, dropped = cap_history(messages, max_history_tokens=budget)
        result = simulate_cap_from_shape(shape, budget)

        assert dropped == 0
        assert len(kept) == len(messages)
        assert result["exact"] is True
        assert result["outcome"] == "unchanged"
        assert result["reason"] == "nothing_chargeable"
        assert result["dropped_messages"] == 0
        assert result["dropped_cap_eligible_tokens"] == 0
        assert result["charged_tokens"] == _charged_by_cap(messages, kept)


    def test_a_zero_cost_candidate_beyond_the_detail_is_not_claimed_unchanged(self) -> None:
        """The one case where "nothing eligible omitted" is not "nothing droppable".

        An assistant turn with no text anywhere in it is worth zero tokens and is
        still a candidate group, so once the reservation has spent the budget the
        cap stops at it.  A one-group detail hides that group behind the same
        zeros an omitted system group would write, so the record cannot name the
        cut; it says so.  Write the same transcript out in full and the very same
        budget becomes exact.
        """
        messages = [
            _sys(40),
            {"role": "assistant", "content": None},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_fatter",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "a" * 40000},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_fatter", "content": "r" * 400},
        ]
        protected_position = len(messages) - 1
        shape = summarize_history_shape(messages, max_groups=1)

        assert shape["detail_complete"] is False
        assert shape["omitted_cap_eligible_tokens"] == 0
        assert shape["last_user_group"] is not None
        assert int(shape["last_user_group"]["ordinal"]) == 0

        # An empty turn is worth nothing, so the eligible total is the
        # reservation, and any budget below it makes the cap stop at the first
        # candidate it is allowed to weigh.
        budget = int(shape["cap_eligible_tokens"]) // 2
        assert budget > 0
        assert shape["cap_eligible_tokens"] > budget

        kept, dropped = cap_history(messages, max_history_tokens=budget)
        result = simulate_cap_from_shape(shape, budget)

        assert dropped == len(messages) - len(kept)
        assert dropped > 0, "the empty group is a candidate the cap must stop at"
        assert len(kept) == protected_position  # system text and the reserved group
        assert result["outcome"] == "indeterminate"
        assert result["reason"] == "zero_cost_candidate_unseen"
        assert result["dropped_messages"] is None

        # The same transcript, recorded completely, is exact and agrees.
        whole = summarize_history_shape(messages)
        assert whole["detail_complete"] is True
        settled = simulate_cap_from_shape(whole, budget)
        assert settled["exact"] is True
        assert settled["outcome"] == "capped"
        assert settled["dropped_messages"] == dropped


class TestReportOutput:
    """The section prints what the pure functions computed, and nothing else."""

    def test_the_sweep_prints_one_row_per_candidate_budget(self) -> None:
        shape = _shape([_group(0, tokens=40000), _group(1, tokens=40000)])
        records = [_record(shape), _record(_ABSENT)]

        output = _printed(records)

        assert "HISTORY-SHAPE CAP SIMULATION" in output
        for budget in HISTORY_CAP_CANDIDATE_BUDGETS:
            assert str(budget) in output, budget
        assert "no cap is chosen or enabled" in output

    def test_a_log_that_stated_nothing_prints_a_sweep_of_zeros(self) -> None:
        output = _printed([{"status": "ok"}])

        assert "HISTORY-SHAPE CAP SIMULATION" in output
        assert "usable measured shapes:       0" in output
        assert "no history.shape" in output

    def test_the_section_prints_no_text_a_client_wrote(self) -> None:
        sentinel = "SECRET-C:/users/example/main.py"
        record: dict[str, Any] = {
            "status": "ok",
            "last_user_message": sentinel,
            "answer_preview": sentinel,
            "history": {"shape": _shape([_group(0, tokens=9000), _group(1, tokens=9000)])},
        }

        assert sentinel not in _printed([record])

    def test_malformed_shapes_do_not_stop_the_rest_of_the_report(self) -> None:
        """One unreadable shape cannot take the analyzer down with it."""
        records = [
            _record("a string where a summary belongs"),
            _record({"schema": "history-shape-v2", "status": "measured"}),
            _record(_shape([_group(0, tokens=9000), _group(1, tokens=9000)])),
        ]

        summary = history_cap_simulation_summary(records)

        assert summary["tally"]["malformed"] == 2
        assert summary["usable"] == 1
        assert summary["budgets"][0]["exact"] == 1

    def test_the_new_section_leaves_every_existing_section_in_place(self) -> None:
        record: dict[str, Any] = {
            "status": "ok",
            "intent": "EXPLAIN",
            "conversation_key": "conv-1",
            "request_id": "req-1",
            "timing": {
                "total_ms": 900.0,
                "pipeline_ms": 100.0,
                "provider_wait_ms": 800.0,
                "ttft_ms": 120.0,
            },
            "usage": {"prompt_tokens": 70000, "completion_tokens": 50},
            "context": {
                "status": "assembled",
                "estimated_tokens": 1000,
                "max_tokens": 4000,
                "symbols_selected": 3,
                "symbols_new": 3,
                "symbols_suppressed": 0,
            },
            "history": {"shape": _shape([_group(0, tokens=10)])},
        }

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            analyze([record])
        output = buffer.getvalue()

        for heading in (
            "SESSION LOG ANALYSIS",
            "INTENT DISTRIBUTION",
            "CONTEXT STATUS DISTRIBUTION",
            "LATENCY (ms)",
            "PROMPT TOKENS",
            "DELTA INJECTION EFFECTIVENESS",
            "TURNS PER CONVERSATION",
            "TIMING BREAKDOWN: pipeline vs provider",
            "LATENCY BY PROMPT SIZE",
            "CORRELATION COEFFICIENTS",
            "CONTEXT COST",
            "CHANGED-FILE PROMOTION",
            "FILE ACTIVITY",
            "HISTORY CAPPING",
            "HISTORY-SHAPE CAP SIMULATION",
            "5 SLOWEST REQUESTS",
            "END OF REPORT",
        ):
            assert heading in output, heading

