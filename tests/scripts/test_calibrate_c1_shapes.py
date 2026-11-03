"""Tests for scripts/calibrate_c1_shapes.py, the count-only shape calibration.

The benchmark in ``scripts/bench_c1_latency.py`` calibrates its realistic cells against the
rows this script prints, so a row that names the wrong session quietly changes what the
benchmark claims to measure: a cell labelled p99 would hold something else.  What these
tests pin down is the one decision the script cannot get wrong and still print a plausible
number - which session a named rank points at.

The ordering is by total result characters, because that is the quantity C1's cost grows
with, and a reported row is one session's counts rather than each column taken at its own
rank: a conversation with the median message count and the most expensive result never
happened.
"""

from __future__ import annotations

import json
from typing import Any

from scripts.bench_c1_latency import OBSERVED_SHAPES
from scripts.calibrate_c1_shapes import (
    PERCENTILES,
    SHAPE_KEYS,
    percentile_shapes,
    render_python,
    scan_transcript,
)


def _sessions(total: int) -> list[dict[str, int]]:
    """Return ``total`` sessions whose result characters run from 1 to ``total``.

    Args:
        total: How many sessions the scan found.

    Returns:
        One row per session, cheapest first, each distinguishable by both the column the
        ranking reads and its message count.
    """
    return [{"result_chars": place, "messages": 2 * place} for place in range(1, total + 1)]


def test_p99_of_thirty_nine_sessions_is_the_most_expensive_one() -> None:
    """A named rank is the nearest rank, which is what the name states.

    Taking ``int(position * (total - 1))`` instead reports the session two places below the
    one asked for, so a p99 cell would be calibrated against the 38th of 39 conversations
    while its name said the busiest one.
    """
    shapes = percentile_shapes(_sessions(39))
    assert shapes["p99"]["result_chars"] == 39
    assert shapes["p95"]["result_chars"] == 38
    assert shapes["p90"]["result_chars"] == 36
    assert shapes["p50"]["result_chars"] == 20


def test_a_rank_that_divides_the_count_stays_on_its_own_row() -> None:
    """Binary fractions land a hair above a whole product, and must not buy the next row.

    The four cases here are the ones where that shows: 99% of 100 sessions is its 99th, not
    its 100th, and 50% of 40 is its 20th, not its 21st.
    """
    assert percentile_shapes(_sessions(100))["p99"]["result_chars"] == 99
    assert percentile_shapes(_sessions(40))["p50"]["result_chars"] == 20
    assert percentile_shapes(_sessions(10))["p90"]["result_chars"] == 9


def test_a_reported_row_is_one_session_not_a_percentile_of_every_column() -> None:
    """Every count in a row comes from the same conversation the rank named."""
    rows = _sessions(39)
    rows[-1]["distinct_targets"] = 7
    shapes = percentile_shapes(rows)
    assert shapes["p99"]["distinct_targets"] == 7
    assert shapes["p99"]["messages"] == 78
    # The row one rank below is a different session, and never had a target to count.
    assert shapes["p95"]["distinct_targets"] == 0


def test_one_session_is_every_percentile_of_itself() -> None:
    """A rank above the last row still names the only row there is, and no rows name none."""
    shapes = percentile_shapes(_sessions(1))
    assert {name: row["result_chars"] for name, row in shapes.items()} == {
        f"p{round(position * 100)}": 1 for position in PERCENTILES}
    assert percentile_shapes([]) == {}


def test_a_shape_row_holds_counts_keyed_as_the_table_is() -> None:
    """The literal the benchmark commits is whole and numeric, so it is safe to paste."""
    shapes = percentile_shapes(_sessions(39))
    assert set(shapes) == {f"p{round(position * 100)}" for position in PERCENTILES}
    assert all(set(row) == set(SHAPE_KEYS) for row in shapes.values())
    assert all(isinstance(value, int)
               for row in shapes.values() for value in row.values())


def test_the_paste_literal_is_python_and_not_a_set_of_names() -> None:
    """What ``--paste`` prints has to run, or the table it claims to be is prose.

    The renderer used to write each count with its key bare - ``{calls: 43}`` - which
    Python reads as a variable named ``calls``, so the literal raised ``NameError`` the
    moment anyone executed it.  Two rows are enough to show the whole shape of the
    problem: the text is valid, the keys are quoted, and the round trip is exact.
    """
    shapes = {"p50": {"calls": 1, "turns": 2}, "p99": {"calls": 3, "turns": 7}}
    namespace: dict[str, Any] = {}
    exec(render_python(shapes), namespace)  # noqa: S102
    assert namespace["OBSERVED_SHAPES"] == shapes


def test_the_committed_table_is_what_the_renderer_prints() -> None:
    """The benchmark's literal round-trips through the renderer and holds no other keys.

    The script puts one row on one line and this repository keeps to a hundred columns,
    so the committed table is that output re-wrapped rather than pasted character for
    character.  What has to stay true is that the counts and the column names are the
    ones the calibration prints, which is what these two assertions say.
    """
    namespace: dict[str, Any] = {}
    exec(render_python(OBSERVED_SHAPES), namespace)  # noqa: S102
    assert namespace["OBSERVED_SHAPES"] == OBSERVED_SHAPES
    assert all(set(row) == set(SHAPE_KEYS) for row in OBSERVED_SHAPES.values())


def test_a_chat_call_and_a_text_envelope_are_counted_in_their_own_columns() -> None:
    """``native_calls`` is the chat form's tally; ``envelope_calls`` is the legacy text one.

    The row used to carry the first of those numbers under the second's name, and to drop
    the second entirely - so a session whose results arrived as ``tool`` messages and a
    session whose results arrived as ``[tool for path] Result:`` headers looked the same
    in one column and neither looked like itself in the other.
    """
    messages = [
        {"role": "assistant", "content": "reading", "tool_calls": [
            {"id": "call_1", "type": "function", "function": {
                "name": "read_files",
                "arguments": json.dumps({"files": [{"path": "packages/pipeline/context.py"}]})}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "x" * 40},
        {"role": "user",
         "content": "[read_file for packages/pipeline/context.py] Result:\n" + "y" * 60},
    ]
    row = scan_transcript(messages)
    assert row["native_calls"] == 1
    assert row["envelope_calls"] == 1
    assert row["envelope_messages"] == 1
    # The two dialects sum into the columns a cell is built from, and neither is doubled.
    assert row["calls"] == 1
    assert row["others"] == 0


def test_a_stored_session_adds_to_no_dialect_column_at_all() -> None:
    """Block-form activity is what the committed zeros say it is: nothing in either column.

    Cline's own storage keeps a call as a ``tool_use`` block, which neither the chat-form
    reader nor the legacy header recognizes, so a session of only those reports zero in
    both columns while its ``calls`` and ``block_results`` say it was busy.
    """
    row = scan_transcript([{"role": "assistant", "content": [
        {"type": "tool_use", "name": "read_files", "id": "one",
         "input": {"files": [{"path": "packages/pipeline/context.py"}]}}]}])
    assert row["native_calls"] == 0
    assert row["envelope_calls"] == 0
    assert row["envelope_messages"] == 0
    assert row["calls"] == 1
    assert row["block_results"] == 0
