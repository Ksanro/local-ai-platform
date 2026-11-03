"""Tests for scripts/bench_c1_latency.py, the roadmap E3 paired-delta microbenchmark.

The script measures one number - the wall clock C1 adds to a request - by running two
arms of the same production method against the same transcript objects, the only
difference being whether the stage was constructed with a ``FileActivityTracker``.  What
this test guards is not timing, which no assertion can pin down, but the four things
that would make a timing number meaningless while still printing cleanly.

The first is the warm predecessor.  :func:`transcript_fingerprints` stores a conversation
state under the fingerprint of the transcript a request *saw* and finds it again through
the fingerprint of the messages before the newest assistant turn, so a seeding transcript
that is one message short of the right boundary produces a cold conversation wearing a
warm label.  The second is what the decision arm actually runs: the stage's own
``_observe_file_activity``, with a supplied package, because with ``index=None`` the
``execute`` path hands the observer no package at all and can never report a correlation.

The third is that the numbers a record carries are counts.  Envelope targets in these
transcripts are real repository files, so a payload that leaked a path would turn a
benchmark into a disclosure.  The fourth is the estimator's direction of error: the
interval that closes a measurement question must be the *wider* of the two methods in
each direction - the minimum of their lower bounds, the maximum of their upper ones -
because the narrower answer lets the luckier method hide the less favorable one.  One
function estimates that interval and one reads a verdict off it, and every test below
that asks what a set of blocks says reaches them the way ``--report`` does.
"""

from __future__ import annotations

import gc
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from packages.pipeline.file_activity import (
    FILE_ACTIVITY_CORRELATION_STATES,
    FILE_ACTIVITY_STATES,
)
from scripts import bench_c1_latency
from scripts.bench_c1_latency import (
    BATCHES,
    CELL_SHAPES,
    CELLS,
    FILLER_TEXT,
    INERT_KEYS,
    MAX_TRANSCRIPT_BYTES,
    Arm,
    _claim_row,
    _interval,
    _verdict,
    build_fixture,
    expand_shape,
    main,
    projected_bytes,
    real_targets,
    report,
    resolve_batch,
    run_block,
    run_diag,
    t_critical,
    warm_gate,
)

#: A cell small enough to build inside a test run: 10 native file envelopes, no seeding.
_SMALL = "N-count-10"

#: A cell name the matrix does not carry, for the tests that write block records by hand:
#: a report also lists the matrix cells its pattern matched nothing for, so borrowing a
#: real name would print a missing-cell line beside the row under test.
_SCRATCH = "G-pooled"


def _timed(block: int, delta_ms: float, status: str = "ok") -> dict[str, Any]:
    """Return one latency block record as a sweep would have written it.

    Args:
        block: The block index.
        delta_ms: What the block measured, candidate minus control.
        status: The block's own validity status; anything but ``ok`` means the record
            states no measurement, which is a thing a report has to respect.

    Returns:
        A record with both arms' means, so a pooled figure can be read off it, and no
        shape: these tests ask what the blocks say, not what the fixture held.
    """
    return {"cell": _SCRATCH, "block": block, "pass": "latency", "status": status,
            "candidate": {"mean_ms": delta_ms + 1.0}, "control": {"mean_ms": 1.0},
            "delta_ms": delta_ms, "shape": {}}


def _write(tmp_path: Path, pass_name: str, records: list[dict[str, Any]]) -> None:
    """Write block records where a report reads them back from."""
    lines = "\n".join(json.dumps(record) for record in records)
    (tmp_path / f"sweep-{pass_name}.jsonl").write_text(lines, encoding="utf-8")


def _one_row(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    """Run a report over ``tmp_path`` and return the single row it printed."""
    assert report(tmp_path, _SCRATCH) == 0
    return json.loads(capsys.readouterr().out)


def test_tiny_cell_reports_documented_shape() -> None:
    """A block record states its shape, both arms' samples, and a paired delta."""
    record = run_block(_SMALL, 1, False)
    assert record.get("status", "ok") == "ok"
    shape = record["shape"]
    # The shape is a pairing, not a description: every field carries what the fixture
    # built beside what the cell's shape commits it to, and the generated side is what
    # these assertions can read a number off.
    assert shape["envelopes"][0] == 10
    assert shape["calls"][0] == 10
    assert shape["other_events"][0] == 0
    assert shape["messages"][0] == shape["messages"][1]
    assert shape["transcript_bytes"][0] <= MAX_TRANSCRIPT_BYTES
    for arm in ("candidate", "control"):
        # A group is four invocations, two per arm, so one batch of one group yields two
        # samples to an arm and the order alternates by block parity.
        assert record[arm]["n"] == 2
        assert record[arm]["mean_ms"] > 0.0
    assert record["delta_ms"] == (record["candidate"]["mean_ms"]
                                  - record["control"]["mean_ms"])


def test_timed_transcript_is_restored_after_seeding() -> None:
    """Seeding must not leave the timed transcript truncated in either arm.

    A control arm that read a shorter transcript than the candidate would report a
    faster control and a bigger delta than C1 costs, which is the one failure mode a
    paired design cannot afford to hide.
    """
    fixture = build_fixture("R-p50-warm")
    messages = fixture["messages"]
    length = len(messages)
    roles = [message["role"] for message in messages]
    arm = Arm(fixture, "candidate")
    arm.prepare()
    # Restored means the same messages in the same order, and not merely the same count:
    # a message that drifted out of the turn it belonged to would leave the length alone
    # while changing what the timed call walks.
    assert [message["role"] for message in messages] == roles
    assert len(messages) == length
    arm.timed()
    assert len(messages) == length
    assert [message["role"] for message in messages] == roles
    # And the request still ends with its newest turn answered: the last tool reply sits
    # after the newest assistant turn, so the replay did not stop one message short of the
    # boundary a warm conversation is looked up by.
    newest_turn = max(index for index, message in enumerate(messages)
                      if "tool_calls" in message)
    last_reply = max(index for index, message in enumerate(messages)
                     if message["role"] == "tool")
    assert last_reply > newest_turn


def test_warm_gate_accepts_the_real_predecessor_only() -> None:
    """A prefix built by the fixture matches; a truncated one is rejected as invalid."""
    fixture = build_fixture("R-p50-warm")
    assert warm_gate(fixture) == (True, "matched")

    truncated = build_fixture("R-p50-warm")
    truncated["seed"] = truncated["messages"][:-1]
    assert warm_gate(truncated) == (False, "prefix_mismatch")


def test_warm_cell_measures_a_real_correlation() -> None:
    """The warm shape reports ``correlation=measured`` with files supplied earlier.

    This is the property that makes the decision number a *warm* later request of one
    conversation: with no package on the ``index=None`` path the correlation counters sit
    at zero, so the cell would be measuring a cold lookup while saying it was warm.
    """
    record = run_block("R-p50-warm", 1, True)
    correctness = record["correctness"]
    assert correctness["passed"] is True, correctness["checks"]
    payload = correctness["candidate"]
    assert payload["correlation"] == "measured"
    assert payload["context_files_touched"] > 0
    assert payload["changed_files_touched"] > 0
    assert correctness["control_payload"] == {}


def test_cold_cell_skips_seeding_and_reports_a_lineage_gap() -> None:
    """An unseeded tracker states a gap rather than claiming a measured correlation."""
    record = run_block("R-p99-cold", 1, True)
    correctness = record["correctness"]
    assert correctness["passed"] is True, correctness["checks"]
    assert correctness["candidate"]["correlation"] == "tracker_miss"
    assert correctness["expected"]["context_files_touched"] == 0
    assert correctness["candidate"]["context_files_touched"] == 0


def test_payload_carries_only_counts_and_closed_tokens() -> None:
    """No path crosses into the record, and every state word is one the schema allows."""
    for cell in (_SMALL, "R-p50-warm", "T-text-500"):
        payload = _payload_of_cell(cell)
        assert sorted(payload) == sorted(INERT_KEYS)
        for key, value in payload.items():
            if key in ("state", "correlation"):
                assert value in FILE_ACTIVITY_STATES + FILE_ACTIVITY_CORRELATION_STATES
            else:
                assert isinstance(value, int) and value >= 0
        for value in (v for v in payload.values() if isinstance(v, str)):
            assert "/" not in value and "\\" not in value and not value.endswith(".py")


def _payload_of_cell(cell: str) -> dict[str, Any]:
    """Return the activity section one cell's candidate arm records."""
    arm = Arm(build_fixture(cell), "candidate")
    arm.prepare()
    arm.timed()
    return arm.payload()


def test_retained_window_is_what_the_parse_bound_keeps() -> None:
    """A transcript past the bound retains the newest envelopes and counts the rest."""
    fixture = build_fixture("N-count-500")
    assert fixture["shape"]["envelopes"][0] == 500
    assert fixture["shape"]["envelopes"][1] == 500
    record = run_block("N-count-500", 1, True)
    assert record["correctness"]["passed"] is True, record["correctness"]["checks"]
    assert record["correctness"]["candidate"]["state"] == "partial"
    assert record["correctness"]["candidate"]["events_beyond_bound"] == 500 - 256


def test_projected_cap_refuses_an_oversized_fixture() -> None:
    """The 32 MB ceiling is consulted before allocation, not after."""
    assert projected_bytes(CELLS["N-size-1M"]) < MAX_TRANSCRIPT_BYTES
    huge = {"form": "native", "calls": 256, "others": 0, "chars": 1_000_000, "distinct": 256}
    assert projected_bytes(huge) > MAX_TRANSCRIPT_BYTES


def test_the_pooled_interval_is_the_wider_of_both_methods(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A conservative bound cannot be smaller than either method's own bound.

    Ten blocks of a cell that really costs nine milliseconds or more, read the way
    ``--report`` reads them: pooled, then estimated, then judged.  The interval has to
    contain both methods' claims, and the verdict has to be the one that says the
    question is closed.
    """
    deltas = [9.0 + block for block in range(1, 11)]
    _write(tmp_path, "latency", [_timed(block, delta)
                                 for block, delta in enumerate(deltas, start=1)])
    row = _one_row(tmp_path, capsys)
    assert row["timed"] == 10
    interval = _interval(deltas)
    assert interval["upper"] >= max(interval["t_upper"], interval["order_upper"])
    assert interval["lower"] <= min(interval["t_lower"], interval["order_lower"])
    assert interval["upper"] >= interval["lower"]
    assert row["verdict"] == "close_measured_actionable"


def test_the_interval_never_closes_on_a_favorable_method_alone(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """One block whose delta clears the threshold must not let the interval close.

    The order-statistic upper bound is what keeps a single lucky block from being read
    as proof of negligible cost, so an interval that straddles the threshold has to come
    back asking for more blocks rather than closing the question.
    """
    deltas = [0.4] * 9 + [9.0]
    _write(tmp_path, "latency", [_timed(block, delta)
                                 for block, delta in enumerate(deltas, start=1)])
    row = _one_row(tmp_path, capsys)
    assert row["verdict"] == "expansion_needed"
    assert row["upper_us"] >= 5000.0


def test_the_reports_lower_bound_is_the_conservative_one(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Eight blocks whose two methods disagree downward report the lower of the two.

    The deltas are the case the review put: seven of them near one millisecond and one at
    three.  The Student-*t* interval reaches down to about 0.65 ms; the order statistic on
    the 2.5% rank of eight blocks is simply the minimum, 0.8 ms.  Taking ``max`` of the two
    - which is what the pooled path used to do - reported 0.8, the narrower answer, and a
    cell can be closed as actionable from a lower bound the evidence does not support.
    """
    deltas = [1.0, 1.1, 0.9, 1.2, 0.8, 1.0, 3.0, 1.0]
    _write(tmp_path, "latency", [_timed(block, delta)
                                 for block, delta in enumerate(deltas, start=1)])
    interval = _interval(deltas)
    assert interval["order_lower"] == 0.8
    assert interval["t_lower"] < interval["order_lower"]
    assert interval["lower"] == pytest.approx(interval["t_lower"])
    row = _one_row(tmp_path, capsys)
    assert row["lower_us"] < 800.0
    assert row["lower_us"] == pytest.approx(650.7, abs=1.0)
    assert row["upper_us"] == pytest.approx(3000.0)


def test_a_block_that_failed_its_own_gate_is_no_measurement(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A block that failed validity is counted and named, never averaged in.

    One record is nothing to pool, and both facts have to survive into the row: the status
    that refused the block, and the verdict that says a single block closes nothing.
    """
    _write(tmp_path, "latency", [_timed(1, 9.0, status="invalid_x")])
    row = _one_row(tmp_path, capsys)
    assert row["timed"] == 0
    assert "delta_us" not in row
    assert row["statuses"] == ["invalid_x"]
    assert _verdict(_interval([9.0])) == "insufficient_blocks"


def test_a_correctness_block_is_not_a_ninth_observation(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A two-sample gate block and the timed blocks of a cell are different experiments.

    A gate block carries a delta - two invocations of each arm, timed as it goes - and a
    pooler that read the pass name off the file instead of the record would quietly mix a
    2-sample run into an 8-sample one and widen the interval with a number that was never
    meant to be a measurement.
    """
    _write(tmp_path, "latency", [_timed(block, 5.0) for block in range(1, 5)])
    gate = _timed(1, 899.0)
    gate["pass"] = "correctness"
    gate["candidate"] = {"mean_ms": 900.0}
    gate["correctness"] = {"passed": True}
    _write(tmp_path, "correctness", [gate])
    row = _one_row(tmp_path, capsys)
    assert row["timed"] == 4
    assert row["delta_us"] == 5000.0
    assert row["gate"] == "pass"


def test_t_critical_matches_the_known_five_percent_value() -> None:
    """The hand-rolled Student-t quantile agrees with the tabulated two-sided 95% value."""
    assert abs(t_critical(0.975, 1) - 12.706) < 0.01
    assert abs(t_critical(0.975, 19) - 2.093) < 0.005
    assert abs(t_critical(0.975, 1000) - 1.962) < 0.01


def test_cli_reports_one_json_object_per_invocation() -> None:
    """The script runs as a subprocess and exits 0 on a valid cell.

    The subprocess carries the fixture and the two arms' construction that a block
    measures, so this is the check that the module imports cleanly through the same entry
    point the benchmark harness uses.
    """
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench_c1_latency.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--pass", "correctness", "--cell", _SMALL, "--block", "1"],
        capture_output=True, text=True, timeout=180, check=False)
    assert completed.returncode == 0, completed.stderr
    record = json.loads(completed.stdout)
    assert record["correctness"]["passed"] is True
    assert record["warm_gate"] == "cold"
    assert record["batch"] == 1


def test_every_cell_names_a_supported_form_and_batch() -> None:
    """No cell can join the matrix without a calibrated sample count and a known form."""
    assert set(BATCHES) == set(CELLS)
    for cell, spec in CELLS.items():
        assert spec["form"] in ("native", "text"), cell
        if spec.get("gate_only"):
            # A gate cell exists to check a payload, not to produce a delta, so it runs
            # no timed invocations and a latency sweep reports it as not timed.
            assert BATCHES[cell] == 0, cell
        else:
            assert BATCHES[cell] >= 1, cell
        assert projected_bytes(spec) <= MAX_TRANSCRIPT_BYTES, cell
        if spec["form"] == "text":
            assert spec.get("warm", False) is False, cell


def test_gate_cell_reports_nothing_to_time() -> None:
    """A gate cell timed at all says it was not, rather than averaging no samples."""
    record = run_block("X-empty", 0, False)
    assert record["status"] == "not_timed"
    assert record["delta_ms"] is None
    assert record["candidate"]["n"] == 0
    assert record["shape"]["note"] == ["empty_transcript", "empty_transcript"]


def test_shape_claims_no_number_it_cannot_state() -> None:
    """A field no shape states pairs the built value against no claim at all."""
    shape = build_fixture(_SMALL)["shape"]
    assert shape["transcript_bytes"][1] is None
    assert shape["transcript_bytes"][0] > 0
    # Ten calls fit one batch, so the transcript is the opening turn, that batch's
    # assistant message and the ten results - and the fixture agrees with the arithmetic.
    assert shape["messages"] == [12, 12]


def test_a_gate_block_that_never_ran_fails_the_report(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A correctness block holding no comparison is a refusal, not a quiet pass.

    :func:`run_block` returns before it builds either arm when a transcript is over the
    ceiling or a warm gate matches nothing, and such a record carries no ``correctness``
    object at all.  Reading the verdict as ``r["correctness"]["passed"]`` raised KeyError
    there, so a report over a refused cell ended in a traceback instead of a FAIL.

    The cell is named rather than borrowed from the matrix: a report also lists the matrix
    cells its pattern matched but found nothing for, and a real cell name is a prefix of
    several others.
    """
    cell = "G-gate"
    ran = {"cell": cell, "pass": "correctness", "block": 0, "status": "ok",
           "correctness": {"passed": True}, "shape": {"envelopes": [10, 10]}}
    refused = {"cell": cell, "pass": "correctness", "block": 1,
               "status": "invalid_transcript_too_large", "shape": {"envelopes": [10, 10]}}
    (tmp_path / "sweep-correctness.jsonl").write_text(json.dumps(ran), encoding="utf-8")
    assert report(tmp_path, cell) == 0
    assert json.loads(capsys.readouterr().out)["gate"] == "pass"
    (tmp_path / "sweep-correctness.jsonl").write_text(
        "\n".join(json.dumps(record) for record in (ran, refused)), encoding="utf-8")
    assert report(tmp_path, cell) == 0
    row = json.loads(capsys.readouterr().out)
    assert row["gate"] == "FAIL"
    assert row["gate_statuses"] == ["invalid_transcript_too_large"]
    # A refused block is no measurement, so it cannot join the pooled delta either.
    assert row["timed"] == 0
    assert row["verdict"] == "no_usable_blocks"


def test_cli_batch_is_the_batch_the_record_reports() -> None:
    """``--batch N`` on a timed run reaches the record instead of being ignored.

    The latency path used to answer for the table whatever the caller asked for, so
    ``--batch 2`` on a cell the table puts at 165 still ran 165 groups and the flag only
    worked on the estimate pass.  ``N-count-10`` is the cell to check it on: ten
    envelopes, so a deeper batch costs milliseconds and the recorded number is the one
    the block ran.
    """
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench_c1_latency.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--pass", "latency", "--cell", _SMALL, "--batch", "2"],
        capture_output=True, text=True, timeout=180, check=False)
    assert completed.returncode == 0, completed.stderr
    record = json.loads(completed.stdout)
    assert record["status"] == "ok"
    assert record["batch"] == 2
    # A group is four invocations, two to an arm, so two groups leave four samples each.
    assert record["candidate"]["n"] == 4
    assert record["control"]["n"] == 4


def test_a_latency_block_proves_its_objects_fresh() -> None:
    """Every invocation builds its own objects, and the record has to be able to say so.

    Object ids were recorded for objects the arm then let go, so a freed stage's address
    went to the next one and the block reported a reuse that never happened; and the
    control arm's absent tracker recorded ``id(None)``, one constant, as a tracker seen
    on every invocation.  Either made ``objects_fresh`` false on blocks that were fresh.
    """
    record = run_block(_SMALL, 10, False)
    assert record["status"] == "ok"
    assert record["objects_fresh"] is True
    for arm, trackers in (("candidate", 20), ("control", 0)):
        freshness = record[f"{arm}_freshness"]
        assert freshness["invocations"] == 20
        assert freshness["distinct_stage"] == 20
        assert freshness["distinct_context"] == 20
        assert freshness["distinct_tracker"] == trackers


def test_a_warm_cell_without_batch_runs_its_table_value(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """With no ``--batch``, a timed run takes the cell's BATCHES entry - warm ones too.

    The timed path used to special-case any cell with ``warm`` in its name and run one
    group, which gave the decision cell two samples per arm and meant the batch sizes
    calibrated against the block budget never applied to the cells chosen for them.  A
    correctness run is not a sample of anything, so it stays at one group.
    """
    asked: dict[str, int] = {}

    def fake_run_block(cell: str, batch: int, want_correctness: bool,
                       block: int = 0) -> dict[str, Any]:
        asked["batch"] = batch
        return {"cell": cell, "status": "ok"}

    monkeypatch.setattr(bench_c1_latency, "run_block", fake_run_block)
    for cell in ("R-p50-warm", "R-p90-warm", "R-p99-warm"):
        asked.clear()
        assert main(["--pass", "latency", "--cell", cell]) == 0
        assert asked["batch"] == BATCHES[cell] > 1
    asked.clear()
    assert main(["--pass", "correctness", "--cell", "R-p99-warm"]) == 0
    assert asked["batch"] == 1


def test_batch_resolution_prefers_the_caller() -> None:
    """What the caller asked for wins; what it did not ask for is the table's."""
    assert resolve_batch(2, _SMALL) == 2
    assert resolve_batch(0, _SMALL) == BATCHES[_SMALL]
    assert resolve_batch(0, "R-p99-warm") == BATCHES["R-p99-warm"]
    assert resolve_batch(-1, "R-p99-warm") == BATCHES["R-p99-warm"]


def test_garbage_is_collected_before_the_timer_starts(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """A preparation's garbage is reaped outside the timed call, in both timed passes.

    ``prepare`` builds a stage, a tracker, a context and a package - and for a warm cell
    replays a conversation through them - all of which stops being referenced the moment
    the preparation ends.  Left to itself a generation gets collected inside the *next*
    invocation, which charges one sample for the leftovers of another one.  The collector
    is not switched off anywhere; it is only asked to work between the two.
    """
    events: list[str] = []
    monkeypatch.setattr(gc, "collect", lambda: events.append("collect"))
    prepare, timed = Arm.prepare, Arm.timed

    def mark_prepare(self: Arm) -> None:
        events.append("prepare")
        prepare(self)

    def mark_timed(self: Arm) -> None:
        events.append("timed")
        timed(self)

    monkeypatch.setattr(Arm, "prepare", mark_prepare)
    monkeypatch.setattr(Arm, "timed", mark_timed)
    for run, invocations in ((lambda: run_block(_SMALL, 1, False), 4),
                             (lambda: run_diag(_SMALL, 1), 2)):
        events.clear()
        run()
        assert events.count("timed") == invocations
        assert all(events[index - 1] == "collect"
                   for index, event in enumerate(events) if event == "timed")


def test_a_filler_sits_between_turns_and_never_inside_one() -> None:
    """Padding keeps a turn's calls and its replies together, the way traffic does.

    A client that announced a batch of calls answers it with tool results and with
    nothing between them; the fixture used to drop its follow-up messages into that gap.
    They are still user messages, and the newest assistant turn is still the newest thing
    before the answers, so the fingerprint boundary that makes the cell warm did not move.
    """
    fixture = build_fixture("R-p50-warm")
    messages = fixture["messages"]
    fillers = [message for message in messages if message.get("content") == FILLER_TEXT]
    assert len(fillers) == fixture["spec"]["fillers"] > 0
    assert all(message["role"] == "user" for message in fillers)
    for index, message in enumerate(messages):
        if "tool_calls" not in message:
            continue
        announced = len(message["tool_calls"])
        following = messages[index + 1:index + 1 + announced]
        assert [reply["role"] for reply in following] == ["tool"] * announced
    assert warm_gate(fixture) == (True, "matched")


def test_the_hand_built_table_holds_only_rows_a_cell_is_graded_against() -> None:
    """No row of :data:`CELL_SHAPES` is dead, and no cell reads a row it was not built from.

    The table used to carry measured conversations under names no cell has - ``N-count-50``,
    ``T-p99``, ``X-malformed-200`` - beside four empty placeholders.  Nothing looked at any
    of them: a claim from this table is consulted for a hand-built cell only, keyed by that
    cell's own name, so a row under a name no cell carries decides nothing, and a row a
    generated cell could fall back to would grade it against a conversation it merely
    resembles.
    """
    assert set(CELL_SHAPES) <= set(CELLS)
    consulted = set()
    for cell, spec in CELLS.items():
        expanded = expand_shape(dict(spec, cell=cell))
        if not expanded.get("observed_shape") and _claim_row(expanded):
            consulted.add(cell)
    assert consulted == set(CELL_SHAPES)


def test_the_cells_targets_are_the_repositorys_own_files() -> None:
    """The fixtures really do point at tracked files, which is what their cost claims rest on.

    A path that exists resolves about twice as fast as one that does not, so a transcript
    made of invented names would overstate what C1 costs - and the listing is only that
    listing while ``git`` can name the files.
    """
    targets = real_targets()
    assert targets, "git named no tracked file, so the fallback pattern is in use"
    assert targets == sorted(set(targets))
    assert all(target.endswith(".py") and "\\" not in target for target in targets)
