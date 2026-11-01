"""Tests for the conversation file-activity section of scripts/analyze_sessions.py.

The section reports what the transcripts the gateway was sent show the agent
reading and modifying.  Two properties carry the whole design.

The first is that every counter is a *snapshot*.  ``packages.pipeline.file_activity``
recomputes all fifteen numbers from the complete transcript a request carried, and
a Cline client re-sends its whole conversation on every turn, so a read done once
on turn one is stated by every later record.  Summing the column across records
would count that one read many times over - the exact bug the snapshot model
replaced - so this section offers median and maximum per record and must never
offer a cross-record total.

The second is that an absent reading is not a zero.  A record that predates roadmap
C1, one whose section is incomplete or unreadably typed, one whose measurement
could not run, and one whose supplied-context lineage has a gap must each stay
distinguishable from a conversation in which the agent genuinely touched nothing.
"""

from __future__ import annotations

import io
import json
import re
from contextlib import redirect_stdout
from typing import Any

from packages.pipeline.stages.repository_context import SIGNAL_OFF
from scripts.analyze_sessions import (
    _FILE_ACTIVITY_COUNTERS,
    _FILE_ACTIVITY_FIELDS,
    _preview_text,
    _print_file_activity,
    analyze,
    file_activity_summary,
)

#: The documented schema, as ``INERT_FILE_ACTIVITY`` states it: two tokens and
#: fifteen counters.
_INERT: dict[str, Any] = {
    "state": "measured",
    "correlation": "measured",
    "files_read": 0,
    "files_modified": 0,
    "files_touched": 0,
    "read_attempts": 0,
    "reads_failed": 0,
    "reads_unknown": 0,
    "modification_attempts": 0,
    "modifications_not_modified": 0,
    "modifications_unknown": 0,
    "context_files_touched": 0,
    "touched_without_context": 0,
    "changed_files_touched": 0,
    "paths_rejected": 0,
    "other_events": 0,
    "events_beyond_bound": 0,
}


def _activity(**overrides: Any) -> dict[str, Any]:
    """One complete activity section, with the given fields replaced."""
    section = dict(_INERT)
    section.update(overrides)
    return section


def _record(**overrides: Any) -> dict[str, Any]:
    """One session record stating a complete ``context.file_activity`` section."""
    context: dict[str, Any] = {"status": "assembled", "file_activity": _activity(**overrides)}
    return {"status": "ok", "context": context}


def _section(value: Any) -> dict[str, Any]:
    """One session record whose activity section is exactly ``value``."""
    return {"status": "ok", "context": {"status": "assembled", "file_activity": value}}


def _pre_c1() -> dict[str, Any]:
    """One session record written before roadmap C1 existed."""
    return {"status": "ok", "context": {"status": "assembled", "symbols_selected": 3}}


def _printed(records: list[dict[str, Any]]) -> str:
    """The FILE ACTIVITY section these records produce, as printed text."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        _print_file_activity(records)
    return buffer.getvalue()


def test_the_allowlist_is_the_documented_seventeen_fields() -> None:
    """The section reads two tokens and fifteen counters, and nothing else."""
    assert len(_FILE_ACTIVITY_FIELDS) == 17
    assert _FILE_ACTIVITY_FIELDS[:2] == ("state", "correlation")
    assert len(_FILE_ACTIVITY_COUNTERS) == 15
    assert set(_FILE_ACTIVITY_COUNTERS) == set(_INERT) - {"state", "correlation"}


def test_records_predating_c1_are_separated_from_records_that_saw_nothing() -> None:
    """An absent section and a section reporting zero are different facts.

    A record written before C1 never measured anything, while a record that states
    ``state=none`` did measure and found nothing recognizable.  Both read as zeros
    in the JSON and only the token tells them apart, so the summary keeps the two
    counts in separate keys and lets neither reach a distribution.
    """
    records = [_pre_c1(), _record(state="none", correlation="no_prior_context")]

    summary = file_activity_summary(records)

    assert summary["records"] == 2
    assert summary["with_fields"] == 1
    assert summary["before_fields"] == 1
    assert summary["valid_fields"] == 1
    assert summary["by_state"]["none"] == 1
    assert sum(summary["by_state"].values()) == 1
    assert sum(summary["by_correlation"].values()) == 1


def test_measured_activity_is_tallied_per_record() -> None:
    """A measured record's counters are read, and read as one record's snapshot."""
    records = [_record(files_read=4, files_touched=4, read_attempts=5, reads_failed=1)]

    snapshots = file_activity_summary(records)["snapshots"]

    assert snapshots["files_read"]["eligible_records"] == 1
    assert snapshots["files_read"]["nonzero_records"] == 1
    assert snapshots["files_read"]["median"] == 4.0
    assert snapshots["files_read"]["max"] == 4
    assert snapshots["reads_failed"]["max"] == 1
    assert snapshots["files_read"]["kind"] == "activity"


def test_state_none_is_a_measured_zero_not_an_unavailable_measurement() -> None:
    """A client that sends no envelopes was looked at, and said nothing.

    ``state=none`` is the shape a non-Cline client produces: the transcript was
    read and held nothing recognizable, so its zeros are findings.
    ``state=unavailable`` is where the measurement could not run at all, and
    contributes nothing to any statistic.
    """
    records = [_record(state="none", correlation="no_prior_context"), _record(state="unavailable")]

    summary = file_activity_summary(records)

    assert summary["by_state"]["none"] == 1
    assert summary["by_state"]["unavailable"] == 1
    assert summary["snapshots"]["files_read"]["eligible_records"] == 1
    assert summary["snapshots"]["files_read"]["nonzero_records"] == 0


def test_the_feature_off_note_names_the_real_changed_file_signal_token() -> None:
    """The note contrasting ``state=none`` must quote the token the stage writes.

    The changed-file signal reports a disabled feature as ``off``, never
    ``none``; a note that named ``none`` would send a reader grepping logs for a
    value that cannot occur.
    """
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        _print_file_activity([_record()])
    printed = buffer.getvalue()

    assert SIGNAL_OFF == "off"
    assert f"changed_files_signal={SIGNAL_OFF}," in printed
    assert "changed_files_signal=none" not in printed


def test_state_unavailable_values_cannot_reach_the_activity_statistics() -> None:
    """A request whose measurement never ran cannot report touching anything."""
    records = [_record(state="unavailable", files_read=9, files_touched=9)]

    snapshots = file_activity_summary(records)["snapshots"]

    assert snapshots["files_read"]["eligible_records"] == 0
    assert snapshots["files_read"]["nonzero_records"] == 0
    assert snapshots["files_read"]["median"] is None
    assert snapshots["files_read"]["max"] is None


def test_state_partial_is_kept_and_is_a_floor() -> None:
    """A bound kept events unread, so the number is a minimum rather than a count."""
    records = [_record(state="partial", files_read=2, events_beyond_bound=31)]

    summary = file_activity_summary(records)

    assert summary["by_state"]["partial"] == 1
    assert summary["snapshots"]["files_read"]["eligible_records"] == 1
    assert summary["snapshots"]["files_read"]["max"] == 2
    assert summary["snapshots"]["events_beyond_bound"]["max"] == 31
    assert "state=partial values are floors" in _printed(records)


def test_correlation_no_prior_context_is_a_real_zero() -> None:
    """Nothing had been supplied earlier, so the correlation zero is the answer."""
    records = [_record(correlation="no_prior_context", files_touched=3, touched_without_context=3)]

    snapshots = file_activity_summary(records)["snapshots"]

    assert snapshots["context_files_touched"]["kind"] == "correlation"
    assert snapshots["context_files_touched"]["eligible_records"] == 1
    assert snapshots["touched_without_context"]["eligible_records"] == 1
    assert snapshots["touched_without_context"]["max"] == 3


def test_correlation_tracker_miss_is_excluded_from_correlation_statistics() -> None:
    """A lineage gap is not a measurement that nothing was supplied earlier.

    An evicted conversation, a restarted gateway and a rewritten history all
    report the correlation pair as zero under ``tracker_miss``.  Reading those
    zeros beside the real ones would turn a lost history into a confident finding
    that context never reached the agent, so the two correlation counters drop the
    record while the thirteen transcript-only counters keep it.
    """
    records = [_record(correlation="tracker_miss", files_touched=2, events_beyond_bound=7)]

    summary = file_activity_summary(records)

    assert summary["by_correlation"]["tracker_miss"] == 1
    assert summary["snapshots"]["context_files_touched"]["eligible_records"] == 0
    assert summary["snapshots"]["touched_without_context"]["eligible_records"] == 0
    assert summary["snapshots"]["files_touched"]["eligible_records"] == 1
    assert "excluded from the two corr counters" in _printed(records)


def test_correlation_unavailable_is_excluded_from_correlation_statistics() -> None:
    """Where the measurement did not run, neither half of the pair is a reading."""
    records = [_record(state="unavailable", correlation="unavailable")]

    summary = file_activity_summary(records)

    assert summary["by_correlation"]["unavailable"] == 1
    assert summary["snapshots"]["context_files_touched"]["eligible_records"] == 0


def test_a_correlation_reading_still_needs_a_read_transcript() -> None:
    """A usable lineage token on an unread transcript is not a correlation either."""
    records = [_record(state="unavailable", correlation="measured", context_files_touched=6)]

    snapshots = file_activity_summary(records)["snapshots"]

    assert snapshots["context_files_touched"]["eligible_records"] == 0


def test_unknown_state_and_correlation_tokens_are_tallied_as_unknown() -> None:
    """A token this script has never seen is a fact about the writer, not noise."""
    records = [_record(state="surveyed", correlation="reconstructed")]

    summary = file_activity_summary(records)

    assert summary["by_state"]["unknown"] == 1
    assert summary["by_correlation"]["unknown"] == 1
    # An unknown token measured nothing, so no counter may read it as a zero.
    assert summary["valid_fields"] == 1
    assert summary["snapshots"]["files_read"]["eligible_records"] == 0
    printed = _printed(records)
    assert "unknown" in printed
    assert "surveyed" not in printed
    assert "reconstructed" not in printed


def test_incomplete_section_is_not_a_record_that_predates_c1() -> None:
    """A half-deployed writer states an object with a key missing.

    Reading that as a pre-C1 record would file a partially instrumented gateway as
    an old log, and reading its present keys as the whole section would invent a
    zero for the key it never stated.
    """
    partial = _activity(files_read=3)
    del partial["paths_rejected"]
    records = [_section(partial), _pre_c1()]

    summary = file_activity_summary(records)

    assert summary["with_fields"] == 1
    assert summary["incomplete_fields"] == 1
    assert summary["before_fields"] == 1
    assert summary["valid_fields"] == 0
    assert sum(summary["by_state"].values()) == 0
    assert summary["snapshots"]["files_read"]["eligible_records"] == 0
    assert "missing a field" in _printed(records)


def test_a_section_that_is_not_an_object_is_malformed_not_absent() -> None:
    """A string or a list under the key is a broken writer, not an old record."""
    records = [
        _section("packages/pipeline/file_activity.py"),
        _section([3, 1, 0]),
        _section(None),
        _section(_INERT),
    ]

    summary = file_activity_summary(records)

    assert summary["malformed_fields"] == 3
    assert summary["before_fields"] == 0
    assert summary["valid_fields"] == 1
    assert "unusable field types" in _printed(records)


def test_malformed_counter_values_are_tallied_apart_from_zeros() -> None:
    """A counter that is not a count cannot be coerced into being one.

    A float, a bool, a negative, a string and ``None`` are each unreadable here,
    and ``int()``-ing them - which is what a careless aggregation would do - turns a
    ``1.5`` into a ``1``, ``True`` into a legitimate-looking ``1`` and ``None`` into
    an error or a zero.  The whole record is set aside instead.
    """
    records = [
        _record(files_read=1.5),
        _record(files_modified=True),
        _record(files_touched=-1),
        _record(read_attempts="3"),
        _record(reads_failed=None),
        _record(),
    ]

    summary = file_activity_summary(records)

    assert summary["malformed_fields"] == 5
    assert summary["valid_fields"] == 1
    assert summary["snapshots"]["files_read"]["eligible_records"] == 1
    assert summary["snapshots"]["files_read"]["max"] == 0
    assert summary["by_state"]["measured"] == 1


def test_a_malformed_state_token_does_not_become_predating_c1() -> None:
    """The distinction the audit asked for, in the awkward direction.

    A record that states a section whose token is not even a string is a C1 record
    that has gone wrong, not a record from before C1, and it must be counted where
    a reader looking for partially deployed writers will look.
    """
    records = [_record(state=7), _pre_c1()]

    summary = file_activity_summary(records)

    assert summary["malformed_fields"] == 1
    assert summary["before_fields"] == 1
    assert summary["with_fields"] == 1


def test_replayed_snapshots_are_not_summed_into_a_larger_number() -> None:
    """The same transcript replayed four times is one snapshot, not four reads.

    This is the case the whole section exists to get right.  A Cline client resends
    its conversation on every turn, so a session that read two files and then ran
    thirteen more turns states ``files_read=2`` fourteen times.  A tally would
    report twenty-eight files read; the truth is that the largest single record
    claimed two.
    """
    replayed = [_record(files_read=2, files_touched=2) for _ in range(14)]
    records = [_record(files_read=2, files_touched=2)] + replayed

    summary = file_activity_summary(records)
    stats = summary["snapshots"]["files_read"]

    assert stats["eligible_records"] == 15
    assert stats["nonzero_records"] == 15
    assert stats["median"] == 2.0
    assert stats["max"] == 2
    assert "total" not in stats
    assert "sum" not in stats
    printed = _printed(records)
    assert "28" not in printed
    assert "never summed across records" in printed


def test_the_summary_contains_no_cross_record_total_for_any_counter() -> None:
    """Not one field of the schema is additive, so not one gets a sum.

    Checking every counter rather than one: a single ``total_files_read`` anywhere
    in the output is the mistake, whichever field carries it.
    """
    records = [
        _record(files_read=3, other_events=9),
        _record(files_read=1, other_events=4, paths_rejected=2),
    ]

    summary = file_activity_summary(records)

    for field in _FILE_ACTIVITY_COUNTERS:
        stats = summary["snapshots"][field]
        assert set(stats) == {"kind", "eligible_records", "nonzero_records", "median", "max"}
        assert "total" not in field
    assert not re.search(r"(?i)\btotal (files|reads|events|attempts)\b", _printed(records))


def test_changed_files_touched_is_a_snapshot_and_gets_no_rate() -> None:
    """Touched-and-changed files are counted per record, never as a working-tree set.

    The same modified file can be touched by every turn of one conversation and by
    every conversation in a session, so a union of unique files or a percentage
    built on it would be a number this record set cannot support.
    """
    records = [
        _record(changed_files_touched=1),
        _record(changed_files_touched=1),
        _record(changed_files_touched=0, state="none", correlation="no_prior_context"),
    ]

    stats = file_activity_summary(records)["snapshots"]["changed_files_touched"]

    assert stats["eligible_records"] == 3
    assert stats["nonzero_records"] == 2
    assert stats["median"] == 1.0
    assert stats["max"] == 1
    assert not any(key.startswith("rate_") for key in stats)



def test_no_path_module_symbol_body_or_envelope_reaches_the_output() -> None:
    """Count-only means a hostile or sloppy writer cannot make the report leak.

    Everything below is planted under a key the allowlist does not name, plus one in
    a token position, which is the case that matters: a future field carrying a path,
    a module, a symbol, a result body or raw envelope text must not be reachable by
    printing whatever happens to sit inside ``context.file_activity``.
    """
    planted = [
        "packages/pipeline/file_activity.py",
        "C:\\Users\\someone\\secret\\notes.md",
        "FileActivityTracker.observe",
        "Result: 42 lines read from the file",
        "<environment_details>cwd=/tmp/repo</environment_details>",
    ]
    records: list[dict[str, Any]] = []
    for index, value in enumerate(planted):
        section = _activity(files_read=index)
        section[f"detail_{index}"] = value
        records.append(_section(section))
    records.append(_section(_activity(state="measured /tmp/repo/apps/gateway/main.py")))

    printed = "\n".join(_printed(records).split("FILE ACTIVITY")[1:])

    for value in planted:
        assert value not in printed
    assert "apps/gateway" not in printed
    assert "environment_details" not in printed
    assert "cwd=" not in printed
    # A token carrying content is bucketed as "unknown" and never printed itself.
    summary = file_activity_summary(records)
    assert summary["by_state"]["unknown"] == 1
    assert "/tmp/repo" not in printed


def test_unknown_keys_do_not_change_the_summary_in_any_order() -> None:
    """Determinism does not depend on how a record happened to be serialized.

    JSON object key order is not meaningful, and a summary that enumerated the
    section it was reading would make the report depend on it.  Two records that
    differ only in the order of their unknown keys must summarize identically,
    including as serialized text.
    """
    left = _activity(files_read=2)
    left["alpha"] = "packages/pipeline/file_activity.py"
    left["zeta"] = "FileActivityTracker.observe"
    right = _activity(files_read=2)
    right["zeta"] = "FileActivityTracker.observe"
    right["alpha"] = "packages/pipeline/file_activity.py"
    assert list(left) != list(right)

    first = file_activity_summary([_section(left)])
    second = file_activity_summary([_section(right)])

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert json.loads(json.dumps(first)) == first


def test_empty_input_and_an_all_pre_c1_log_are_both_safe_to_print() -> None:
    """A log with nothing to say prints a sentence, not a traceback or a zero.

    The all-pre-C1 case is what a real old log produces: every record predates
    roadmap C1, so the section must say so rather than report a session in which the
    agent touched nothing at all.
    """
    empty = _printed([])
    old_log = _printed([_pre_c1(), _pre_c1()])

    assert "No record states the file-activity fields." in empty
    assert "predating C1" in empty
    assert all(
        stats["eligible_records"] == 0 and stats["median"] is None and stats["max"] is None
        for stats in file_activity_summary([])["snapshots"].values()
    )
    assert "No record states the file-activity fields." in old_log
    assert "predating C1" in old_log
    assert "stating file_activity:  0" in old_log
    for line in old_log.splitlines():
        assert "measured" not in line


def test_the_section_is_part_of_the_full_analysis_output() -> None:
    """The report a reader gets from a real log path includes the new section.

    Calling :func:`analyze` rather than the printer is the point: a section that
    exists but is never invoked would pass every other test in this file.
    """
    records = [
        _record(files_read=2, files_touched=2, context_files_touched=1),
        _record(state="none", correlation="no_prior_context"),
        _pre_c1(),
    ]
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        analyze(records)
    printed = buffer.getvalue()

    assert "FILE ACTIVITY" in printed
    assert printed.index("CHANGED-FILE PROMOTION") < printed.index("FILE ACTIVITY")
    assert printed.index("FILE ACTIVITY") < printed.index("5 SLOWEST REQUESTS")
    assert "predating C1" in printed
    assert "packages/pipeline" not in printed


# ---------------------------------------------------------------------------
# Rendering the report past this section cannot depend on a field being there.
#
# These cases live in this file because the retained-log validation that proves
# the section above works runs the *whole* CLI, and a crash in any later section
# means the milestone cannot claim it validated the log.  The failure mode was
# real: `logs/implement_budget_A_4096_20260801.jsonl` holds 33 records with
# `status=error`, and those whose response carried no parseable error store
# `error: null`, which the old `r.get("error", "unknown")[:120]` sliced.
# ---------------------------------------------------------------------------


def _error_record(**fields: Any) -> dict[str, Any]:
    """One failed request that also states a complete activity section.

    Keyword arguments replace top-level record fields, which is what the report's
    later sections read.  Use :func:`_error_activity` to change what the activity
    section itself says.
    """
    record: dict[str, Any] = {
        "status": "error",
        "request_id": "e1e1e1e1-e1e1-41e1-91e1-e1e1e1e1e1e1",
        "error": "provider connection reset",
        "last_user_message": "Which function caps the chat history?",
        "timing": {"total_ms": 0},
        "context": {"status": "assembled", "file_activity": _activity()},
    }
    record.update(fields)
    return record


def _warmup(count: int = 6) -> list[dict[str, Any]]:
    """Ordinary successful requests that occupy the five-slowest list.

    ``analyze`` prints the five slowest requests *before* the error section and
    reads ``request_id`` and ``last_user_message`` there too.  That section is not
    part of this milestone, so the records a test is really about carry
    ``total_ms=0`` and are outranked by these, which keeps each assertion aimed at
    the section it names rather than at an unrelated one.
    """
    records: list[dict[str, Any]] = []
    for index in range(count):
        record = _record()
        record["request_id"] = f"0000000{index}-0000-4000-8000-000000000000"
        record["last_user_message"] = f"warm-up request {index}"
        record["timing"] = {"total_ms": 1000 + index}
        records.append(record)
    return records


def _error_activity(**overrides: Any) -> dict[str, Any]:
    """One failed request whose activity section carries these counters."""
    record = _error_record()
    record["context"]["file_activity"] = _activity(**overrides)
    return record


def _full_report(records: list[dict[str, Any]]) -> str:
    """The entire analysis of these records, as printed text."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        analyze(records)
    return buffer.getvalue()


def _error_block(printed: str) -> str:
    """The ERROR REQUESTS section of a completed report."""
    return printed.split("ERROR REQUESTS", 1)[1].split("END OF REPORT", 1)[0]


def test_a_null_error_field_cannot_abort_the_report() -> None:
    """A failed request that logged no error text still reaches the report's end.

    This is the exact shape found in a retained log.  The section must print the
    record with a stated fallback and carry on to ``END OF REPORT``; dying on the
    last field of the last section would leave the file-activity validation above
    unproven even though that section had printed correctly.
    """
    printed = _full_report(
        [_record(), _error_record(error=None), _error_activity(files_read=1)]
    )

    assert "END OF REPORT" in printed
    assert "error=unknown" in _error_block(printed)
    assert "NoneType" not in printed
    assert " error=None" not in printed


def test_a_null_or_absent_request_id_falls_back_to_the_same_text() -> None:
    """Missing and null are the same absence, and neither prints as ``None``."""
    null_id = _error_record(request_id=None)
    absent_id = _error_record()
    del absent_id["request_id"]

    first = _error_block(_full_report([*_warmup(), null_id]))
    second = _error_block(_full_report([*_warmup(), absent_id]))

    assert "id=unknown" in first
    assert "id=unknown" in second
    assert "id=None" not in first
    assert "id=None" not in second
    assert first == second


def test_a_null_user_message_renders_empty_rather_than_as_the_word_none() -> None:
    """The message preview's fallback is the empty string, not a placeholder."""
    null_message = _error_record(last_user_message=None)
    absent_message = _error_record()
    del absent_message["last_user_message"]

    first = _error_block(_full_report([*_warmup(), null_message]))
    second = _error_block(_full_report([*_warmup(), absent_message]))

    assert "     msg: \n" in first
    assert "msg: None" not in first
    assert "msg: unknown" not in first
    assert first == second


def test_non_string_field_values_are_converted_to_text_and_truncated() -> None:
    """A number, a bool or a container in a text field is printed, not crashed on.

    The log writer is not this script's to control, so the report converts rather
    than assumes.  What it must not do is raise, or invent a value the record did
    not carry.
    """
    printed = _full_report(
        [
            *_warmup(),
            _error_record(
                request_id=12345678901234567890,
                error={"code": 500},
                last_user_message=42,
            ),
            _error_record(request_id=True, error=1.5, last_user_message=False),
        ]
    )

    block = _error_block(printed)
    assert "END OF REPORT" in printed
    assert "id=123456789012" in block  # str() of the int, then the 12-character cut
    assert "error={'code': 500}" in block
    assert "msg: 42" in block
    assert "id=True" in block
    assert "error=1.5" in block
    assert "msg: False" in block


def test_the_truncation_widths_are_the_ones_the_section_always_used() -> None:
    """Hardening these fields must not quietly re-width the report.

    Twelve characters of id, one hundred and twenty of error, eighty of message: a
    reader comparing two reports of one log should see no difference in shape.
    """
    long_id = "a" * 40
    long_error = "e" * 400
    long_message = "m" * 300

    block = _error_block(
        _full_report(
            [
                _record(),
                _error_record(
                    request_id=long_id,
                    error=long_error,
                    last_user_message=long_message,
                ),
            ]
        )
    )

    assert "id=" + "a" * 12 + "  error=" + "e" * 120 + "\n" in block
    assert "msg: " + "m" * 80 + "\n" in block
    assert "a" * 13 not in block
    assert "e" * 121 not in block
    assert "m" * 81 not in block


def test_the_fallbacks_and_conversions_are_the_documented_ones() -> None:
    """State the three fallbacks and the conversion rule without a report around them."""
    assert _preview_text(None, fallback="unknown", limit=12) == "unknown"
    assert _preview_text(None, fallback="", limit=80) == ""
    assert _preview_text("plain", fallback="unknown", limit=12) == "plain"
    # A fallback is text too, so it is held to the same width as a real value.
    assert _preview_text(None, fallback="z" * 20, limit=5) == "z" * 5
    # Equal text forms print equally, so a report never depends on a field's type.
    assert _preview_text(1, fallback="", limit=12) == _preview_text("1", fallback="", limit=12)
    assert _preview_text(True, fallback="", limit=12) == _preview_text(
        "True", fallback="", limit=12
    )


def test_the_error_rendering_is_deterministic_across_repeats() -> None:
    """The same records print the same report, twice, in one process or out of it."""
    records = [
        *_warmup(),
        _error_record(error=None),
        _error_record(request_id=None, last_user_message=None),
        _error_record(error=["reset", "refused"], last_user_message=7),
    ]

    once = _full_report(records)
    twice = _full_report(records)

    assert once == twice
    assert "END OF REPORT" in once
    assert _error_block(once) == _error_block(twice)
    # Absence and a container both become text; neither becomes a traceback.
    assert "error=unknown" in once
    assert "error=['reset', 'refused']" in once


def test_rendering_errors_keeps_the_file_activity_section_count_only() -> None:
    """Fixing a later section must not open a privacy hole in this one.

    The records below are failed requests that also carry the activity section, and
    that section is planted with the same content-like values the privacy test
    above uses.  Error rendering reads top-level record fields, so it cannot reach
    them; the report still has to finish, and the activity block must still be
    clean.
    """
    planted = [
        "packages/pipeline/file_activity.py",
        "C:\\Users\\someone\\secret\\notes.md",
        "FileActivityTracker.observe",
        "Result: 42 lines read from the file",
        "<environment_details>cwd=/tmp/repo</environment_details>",
    ]
    records: list[dict[str, Any]] = []
    for index, value in enumerate(planted):
        section = _activity(files_read=index, files_touched=index)
        section[f"detail_{index}"] = value
        record = _error_record(error=None)
        record["context"]["file_activity"] = section
        records.append(record)

    printed = _full_report(records)
    activity = printed.split("FILE ACTIVITY", 1)[1].split("HISTORY CAPPING", 1)[0]

    assert "END OF REPORT" in printed
    assert "error=unknown" in _error_block(printed)
    assert "records:" in activity
    for value in planted:
        assert value not in activity
    assert "/tmp/repo" not in activity
    assert "environment_details" not in activity
    assert "apps/gateway" not in activity


# ---------------------------------------------------------------------------
# The five-slowest list reads the same two fields, one section earlier.
#
# `5 SLOWEST REQUESTS` sliced `request_id` and `last_user_message` directly, so a
# record with either one null aborted the report before the error section was ever
# reached.  Repairing ERROR REQUESTS therefore did not finish the job for a log
# whose *slow* records carry the null: the two sections had the same defect, and a
# record slow enough belongs in the list, so these cases put the tested record in
# the section rather than parking it out of it.
# ---------------------------------------------------------------------------


def _slow_record(**fields: Any) -> dict[str, Any]:
    """One request certain to appear first in the five-slowest list.

    The section sorts on ``timing.total_ms`` and every other record these tests
    build sorts at zero, so this latency ranks the record under test into the list
    on its own merits instead of behind a screen of faster filler.  Keyword
    arguments replace top-level record fields, which is what both preview sections
    read.
    """
    record = _record()
    record["request_id"] = "5e5e5e5e-5e5e-4e5e-8e5e-5e5e5e5e5e5e"
    record["last_user_message"] = "Which section sorts by total latency?"
    record["timing"] = {"total_ms": 9000}
    record.update(fields)
    return record


def _slowest_block(printed: str) -> str:
    """The 5 SLOWEST REQUESTS section of a completed report.

    The list ends where the error section begins; when no request failed the
    report's own end bounds it, since that branch prints a sentence and no header.
    """
    tail = printed.split("5 SLOWEST REQUESTS", 1)[1]
    return tail.split("ERROR REQUESTS", 1)[0]


def test_a_null_or_absent_request_id_falls_back_in_the_slowest_list_too() -> None:
    """The slowest list cannot outrank a log's own missing identifier.

    Same absence, same placeholder as the error section: a record whose writer left
    ``request_id`` out and one that stored null have to print alike, and neither may
    print the word ``None`` where an identifier belongs.
    """
    null_id = _slow_record(request_id=None)
    absent_id = _slow_record()
    del absent_id["request_id"]

    first = _slowest_block(_full_report([_record(), null_id]))
    second = _slowest_block(_full_report([_record(), absent_id]))

    assert "  1. id=unknown  latency=9000ms" in first
    assert "  1. id=unknown  latency=9000ms" in second
    assert "id=None" not in first
    assert "id=None" not in second
    assert first == second


def test_a_null_or_absent_user_message_renders_empty_in_the_slowest_list() -> None:
    """A slow request that logged no prompt still gets its line, with no text.

    The preview's fallback is the empty string here as it is in the error section,
    so the row prints and the line after the latency detail holds nothing.
    """
    null_message = _slow_record(last_user_message=None)
    absent_message = _slow_record()
    del absent_message["last_user_message"]

    first = _slowest_block(_full_report([_record(), null_message]))
    second = _slowest_block(_full_report([_record(), absent_message]))

    assert "     msg: \n" in first
    assert "msg: None" not in first
    assert "msg: unknown" not in first
    assert first == second


def test_non_string_values_are_converted_before_the_slowest_list_truncates() -> None:
    """Conversion happens first here too, so a typed field prints instead of raising.

    Slicing the number before converting it is the abort this test rules out: the
    twenty digits below have to become text and then be cut to twelve characters,
    exactly as a string of the same digits would be.
    """
    printed = _full_report(
        [
            _record(),
            _slow_record(
                request_id=12345678901234567890,
                last_user_message=["read", "the history capping stage"],
            ),
            _slow_record(request_id=True, last_user_message=42.5, timing={"total_ms": 8000}),
        ]
    )
    block = _slowest_block(printed)

    assert "END OF REPORT" in printed
    assert "  1. id=123456789012" in block
    assert "  2. id=True" in block
    assert "12345678901234567890" not in block
    assert "msg: ['read', 'the history capping stage']" in block
    assert "msg: 42.5" in block


def test_the_slowest_list_keeps_the_shape_and_widths_it_always_had() -> None:
    """Hardening two fields must not quietly re-width the report's slowest rows.

    Twelve characters of identifier, eighty of message, one detail line and one
    preview line per record, ranked by latency: a reader comparing two reports of
    one log should see no difference at all in the ordinary string-valued case.
    """
    block = _slowest_block(
        _full_report([_record(), _slow_record(request_id="a" * 40, last_user_message="m" * 300)])
    )
    expected = (
        "  1. id="
        + "a" * 12
        + "  latency=9000ms  "
        + "prompt_tokens=0  completion_tokens=0  "
        + "context=assembled"
    )

    assert expected + "\n" in block
    assert "     msg: " + "m" * 80 + "\n" in block
    assert "a" * 13 not in block
    assert "m" * 81 not in block
    assert block.count("     msg: ") == 2


def test_a_null_preview_record_reaches_the_top_five_and_the_end_of_the_report() -> None:
    """The report finishes when the record carrying the nulls is a headline one.

    This is the case the fix exists for: the slowest request in a log is the one
    with no identifier and no prompt, so it is the first line the section prints,
    and before the repair that line ended the run instead of the report.
    """
    records = [_record(), _slow_record(request_id=None, last_user_message=None), _record()]

    printed = _full_report(records)
    twice = _full_report(records)
    block = _slowest_block(printed)

    assert "END OF REPORT" in printed
    assert printed == twice
    assert "  1. id=unknown  latency=9000ms" in block
    assert "     msg: \n" in block
    assert "NoneType" not in printed
    assert printed.index("5 SLOWEST REQUESTS") < printed.index("END OF REPORT")
