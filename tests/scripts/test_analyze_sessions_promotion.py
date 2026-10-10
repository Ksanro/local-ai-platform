"""Tests for the changed-file promotion section of scripts/analyze_sessions.py.

The section answers one question per record: did the working-tree bonus change
the context that was sent?  Records written before the promotion fields existed
must not be able to answer "no", because that would turn missing data into a
measured zero and drag every rate down.  The same applies to a record whose
comparison itself failed: an unmeasurable request is neither a proved change nor
a measured "nothing happened", so it gets its own tally and stays out of both.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from typing import Any

from scripts.analyze_sessions import _print_changed_file_promotion, changed_file_promotion_summary


def _record(**overrides: Any) -> dict[str, Any]:
    """One session record with the inert promotion fields filled in."""
    base: dict[str, Any] = {
        "status": "assembled",
        "symbols_selected": 3,
        "changed_files_count": 0,
        "changed_symbols_selected": 0,
        "changed_primary_promoted": False,
        "changed_symbols_promoted": 0,
        "changed_context_differs": False,
        "changed_baseline_status": "none",
        "changed_files_signal": "off",
    }
    base.update(overrides)
    return {"context": base}


def test_records_without_the_fields_are_counted_separately() -> None:
    """A pre-field record is neither a promotion nor a measured zero."""
    records = [
        {"context": {"status": "assembled", "symbols_selected": 2}},
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_promoted=1,
            changed_context_differs=True,
            changed_baseline_status="built",
        ),
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["records"] == 2
    assert summary["before_fields"] == 1
    assert summary["with_fields"] == 1
    assert summary["symbols_promoted"] == 1
    assert summary["proved"] == 1
    assert summary["unmeasured"] == 0
    # The rate divides by the one record that can answer, not by both.
    assert summary["rate_with_changed_files"] == 1.0


def test_signal_states_are_tallied_apart() -> None:
    """Clean, disabled, and failed sources are three different readings."""
    records = [
        _record(changed_files_signal="ok"),
        _record(changed_files_signal="ok"),
        _record(changed_files_signal="off"),
        _record(changed_files_signal="unavailable"),
        _record(changed_files_signal="corrupted"),
    ]

    by_signal = changed_file_promotion_summary(records)["by_signal"]

    assert by_signal == {"ok": 2, "off": 1, "unavailable": 1, "unknown": 1}


def test_a_dirty_tree_that_changed_nothing_is_not_counted_as_promotion() -> None:
    """The counterfactual pays for itself here: selected above zero, no change."""
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=2,
            changed_symbols_selected=3,
            changed_primary_promoted=False,
            changed_symbols_promoted=0,
            changed_context_differs=False,
            changed_baseline_status="built",
        )
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["with_changed_files"] == 1
    assert summary["proved"] == 0
    assert summary["present_but_inert"] == 1
    assert summary["unmeasured"] == 0
    assert summary["symbols_selected"] == 3
    assert summary["symbols_promoted"] == 0


def test_promotion_is_proved_by_a_symbol_or_the_primary() -> None:
    """Either counter moving proves the effect; a signal of ``ok`` is required."""
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=1,
            changed_symbols_promoted=1,
            changed_context_differs=True,
            changed_baseline_status="built",
        ),
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_primary_promoted=True,
            changed_context_differs=True,
            changed_baseline_status="built",
        ),
        # The same numbers with no usable source prove nothing.
        _record(
            changed_files_signal="unavailable",
            changed_files_count=1,
            changed_symbols_selected=1,
            changed_symbols_promoted=1,
            changed_context_differs=True,
            changed_baseline_status="built",
        ),
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["proved"] == 2
    assert summary["primary_promoted"] == 1
    assert summary["proved_primary"] == 1
    assert summary["proved_membership"] == 1
    assert summary["proved_reorder_only"] == 0
    assert summary["unmeasured"] == 0
    assert summary["present_but_inert"] == 0


def test_unusable_numbers_read_as_zero_instead_of_crashing() -> None:
    """A counter that arrived as text cannot invent a promotion."""
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count="three",
            changed_symbols_promoted=None,
        )
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["with_changed_files"] == 0
    assert summary["symbols_promoted"] == 0
    assert summary["proved"] == 0
    assert summary["unmeasured"] == 0


def test_a_partially_fielded_record_is_reported() -> None:
    """A half-written record is visible rather than silently zero."""
    records = [{"context": {"changed_files_signal": "ok", "changed_files_count": 1}}]

    summary = changed_file_promotion_summary(records)

    assert summary["with_fields"] == 1
    assert summary["incomplete_fields"] == 1
    # A record that never states the comparison cannot answer either way.
    assert summary["unmeasured"] == 1
    assert summary["proved"] == 0
    assert summary["present_but_inert"] == 0


def test_a_reorder_only_change_is_a_proved_change() -> None:
    """The case the earlier fields could not express: nothing added, order moved.

    The bonus is a reordering signal, so this is the common proved record, not a
    corner of one.  It has to be separable from a primary or membership change.
    """
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_primary_promoted=False,
            changed_symbols_promoted=0,
            changed_context_differs=True,
            changed_baseline_status="built",
        )
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["proved"] == 1
    assert summary["proved_reorder_only"] == 1
    assert summary["proved_primary"] == 0
    assert summary["proved_membership"] == 0
    assert summary["present_but_inert"] == 0


def test_a_failed_comparison_is_unmeasured_and_excluded() -> None:
    """A comparison that never ran must not be counted as inert."""
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=2,
            changed_symbols_selected=3,
            changed_context_differs=False,
            changed_baseline_status="failed",
        ),
        _record(
            changed_files_signal="ok",
            changed_files_count=2,
            changed_symbols_selected=3,
            changed_context_differs=True,
            changed_baseline_status="failed",
        ),
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["unmeasured"] == 2
    assert summary["proved"] == 0
    assert summary["present_but_inert"] == 0
    assert summary["by_baseline_status"]["failed"] == 2


def test_a_skipped_comparison_with_the_bonus_selected_is_inert() -> None:
    """``skipped_no_bonus`` says the two contexts were identical by construction."""
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_context_differs=False,
            changed_baseline_status="skipped_no_bonus",
        )
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["present_but_inert"] == 1
    assert summary["proved"] == 0
    assert summary["unmeasured"] == 0


def test_section_names_every_field_and_carries_no_name() -> None:
    """The printed section is counts, and never a path or a symbol."""
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_primary_promoted=True,
            changed_context_differs=True,
            changed_baseline_status="built",
        ),
        {"context": {"status": "assembled"}},
    ]
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        _print_changed_file_promotion(records)
    printed = buffer.getvalue()

    for label in (
        "CHANGED-FILE PROMOTION",
        "changed_files_signal",
        "changed_baseline_status",
        "changed_files_count > 0",
        "changed_primary_promoted",
        "sum changed_symbols_promoted",
        "sum changed_symbols_selected",
        "proves a change",
        "primary changed",
        "membership changed",
        "reorder only",
        "present but inert",
        "unmeasured",
        "predating the fields",
    ):
        assert label in printed, label
    for forbidden in ("modules/", ".py", "C:\\", "/home/"):
        assert forbidden not in printed, forbidden


def test_section_without_any_field_is_honest() -> None:
    """An old log says there is no data rather than reporting clean zeros."""
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        _print_changed_file_promotion([{"context": {"status": "assembled"}}])
    printed = buffer.getvalue()

    assert "No record states the promotion fields." in printed
    assert "proves a change" not in printed
    assert "present but inert" not in printed

