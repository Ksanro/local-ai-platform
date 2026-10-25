"""Tests for the changed-file promotion section of scripts/analyze_sessions.py.

The section answers one question per record: did the working-tree bonus change
the context that was sent?  Records written before the promotion fields existed
must not be able to answer "no", because that would turn missing data into a
measured zero and drag every rate down.  The same applies to a record whose
comparison itself failed, or - since roadmap B4 made the second context build
opt-in - to one whose comparison was never sampled: an unmeasured request is
neither a proved change nor a measured
"nothing happened", so it gets its own tally and stays out of both.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from typing import Any

import pytest

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


def test_a_comparison_that_was_never_sampled_is_unmeasured_not_inert() -> None:
    """Roadmap B4: a request nobody compared answers neither question.

    An enabled request no longer builds the no-bonus context unless the run asks
    for it, so its record carries the same numbers a measured no-change would -
    and a tally that read ``changed_symbols_selected`` alone would file it under
    "present but inert" and report a finding nobody made.  ``not_sampled`` keeps
    it out of both verdicts, where ``failed`` already lives.
    """
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=2,
            changed_symbols_selected=3,
            changed_context_differs=False,
            changed_baseline_status="not_sampled",
        ),
        _record(
            changed_files_signal="ok",
            changed_files_count=2,
            changed_symbols_selected=3,
            changed_context_differs=False,
            changed_baseline_status="built",
        ),
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["unmeasured"] == 1
    assert summary["present_but_inert"] == 1
    assert summary["proved"] == 0
    assert summary["by_baseline_status"]["not_sampled"] == 1
    assert summary["by_baseline_status"]["built"] == 1


def test_the_unsampled_state_is_named_in_the_report() -> None:
    """A reader of the printed section can see how many records were not compared."""
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_baseline_status="not_sampled",
        )
    ]
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        _print_changed_file_promotion(records)
    printed = buffer.getvalue()

    assert "not_sampled" in printed
    assert "unmeasured (comparison failed, not sampled, or fields absent): " in printed


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


# ---------------------------------------------------------------------------
# Roadmap B4: the counterfactual aggregates read from measured records only.
#
# ``changed_primary_promoted`` and ``changed_symbols_promoted`` are answers a
# request can only give when the stage actually built the no-bonus context.  On
# a ``not_sampled`` or ``failed`` record those fields exist and say ``False``
# and ``0``, so averaging them into a rate alongside real measurements turns a
# request nobody compared into a measured "nothing changed" and pulls the rate
# below what the compared records said.  The directly observable counters -
# changed-file count, changed symbols selected, the signal and status tallies -
# stay across every fielded record, because a request states those whichever way
# the comparison setting went.
# ---------------------------------------------------------------------------


def test_an_unsampled_record_does_not_dilute_the_measured_promotion_rate() -> None:
    """One measured promotion plus one not-sampled record is 100%, not 50%.

    This is the pair roadmap B4 put into production: the first record built the
    counterfactual and found the primary moved; the second is the same request
    in a gateway that was never asked to compare, so it states the placeholder
    ``changed_primary_promoted=false``.  The rate belongs to the records that
    answered the question.
    """
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_primary_promoted=True,
            changed_context_differs=True,
            changed_baseline_status="built",
        ),
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_baseline_status="not_sampled",
        ),
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["with_fields"] == 2
    assert summary["measured"] == 1
    assert summary["primary_promoted"] == 1
    assert summary["rate_primary_promoted"] == 1.0
    # The not-sampled record is unmeasured, and it is not a measured zero either.
    assert summary["unmeasured"] == 1
    assert summary["proved"] == 1
    assert summary["present_but_inert"] == 0
    # What it does state directly is still counted, over all fielded records.
    assert summary["with_changed_files"] == 2
    assert summary["rate_with_changed_files"] == 1.0
    assert summary["symbols_selected"] == 4
    assert summary["by_baseline_status"]["not_sampled"] == 1


def test_a_promotion_stated_on_an_unmeasured_record_is_not_a_measurement() -> None:
    """A placeholder that arrived as a promotion is still not a promotion.

    ``not_sampled`` and ``failed`` never carry these values in production - the
    stage writes inert placeholders whenever it has no baseline - but the
    counterfactual aggregates must not depend on that: a record whose comparison
    was not made cannot be what teaches a reader what the bonus did, however
    confident its fields look.
    """
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_primary_promoted=True,
            changed_symbols_promoted=3,
            changed_context_differs=True,
            changed_baseline_status="not_sampled",
        ),
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_primary_promoted=True,
            changed_symbols_promoted=3,
            changed_context_differs=True,
            changed_baseline_status="failed",
        ),
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["measured"] == 0
    assert summary["primary_promoted"] == 0
    assert summary["symbols_promoted"] == 0
    assert summary["proved"] == 0
    assert summary["present_but_inert"] == 0
    assert summary["unmeasured"] == 2
    # No denominator to divide by, and no ZeroDivisionError for trying.
    assert summary["rate_primary_promoted"] == 0.0
    # The direct counters still see both records.
    assert summary["with_changed_files"] == 2
    assert summary["symbols_selected"] == 4


def test_a_mixed_log_separates_measured_from_direct_counts() -> None:
    """Every bucket of one mixed log holds exactly the records it should.

    Six records covering all five baseline states: the measured denominator is
    the three that were compared or proved comparison unnecessary, the two that
    could not answer are unmeasured and in neither verdict, and the direct counts
    still cover all six records that state the fields.
    """
    records = [
        # 1. Compared, and the bonus moved both the primary and a symbol.
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_primary_promoted=True,
            changed_symbols_promoted=1,
            changed_context_differs=True,
            changed_baseline_status="built",
        ),
        # 2. Compared, and nothing moved.
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_baseline_status="built",
        ),
        # 3. Not compared because the bonus touched no candidate: the two arms
        #    are identical by proof, so this answers without a second build.
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=0,
            changed_baseline_status="skipped_no_bonus",
        ),
        # 4. The ordinary enabled request after roadmap B4.
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_baseline_status="not_sampled",
        ),
        # 5. Asked for a comparison and could not build one.
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_baseline_status="failed",
        ),
        # 6. A clean tree: nothing there to compare.
        _record(changed_files_signal="ok", changed_baseline_status="none"),
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["records"] == 6
    assert summary["with_fields"] == 6
    assert summary["before_fields"] == 0
    # Measured: records 1, 2 and 3.
    assert summary["measured"] == 3
    assert summary["primary_promoted"] == 1
    assert summary["symbols_promoted"] == 1
    assert summary["rate_primary_promoted"] == pytest.approx(1 / 3)
    assert summary["proved"] == 1
    assert summary["proved_primary"] == 1
    assert summary["proved_membership"] == 1
    assert summary["proved_reorder_only"] == 0
    assert summary["present_but_inert"] == 1
    # Unmeasured: records 4 and 5.
    assert summary["unmeasured"] == 2
    assert summary["by_baseline_status"] == {
        "none": 1,
        "built": 2,
        "skipped_no_bonus": 1,
        "not_sampled": 1,
        "failed": 1,
        "unknown": 0,
    }
    # Direct: records 1-5 all state a changed file, and four state a selection.
    assert summary["with_changed_files"] == 5
    assert summary["rate_with_changed_files"] == pytest.approx(5 / 6)
    assert summary["symbols_selected"] == 8


def test_a_log_of_only_unmeasured_records_reports_a_zero_rate() -> None:
    """Normal production traffic says nothing, and must not divide by nothing.

    A gateway started without the comparison opt-in writes ``not_sampled``,
    ``failed`` and ``none`` records only.  The summary reports a zero rate rather
    than an arithmetic error, and keeps every such record out of both verdicts.
    """
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=2,
            changed_symbols_selected=3,
            changed_baseline_status="not_sampled",
        ),
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=1,
            changed_baseline_status="failed",
        ),
        _record(changed_files_signal="ok", changed_baseline_status="none"),
        _record(),
        {"context": {"status": "assembled", "symbols_selected": 4}},
    ]

    summary = changed_file_promotion_summary(records)

    assert summary["measured"] == 0
    assert summary["primary_promoted"] == 0
    assert summary["symbols_promoted"] == 0
    assert summary["rate_primary_promoted"] == 0.0
    assert summary["proved"] == 0
    assert summary["present_but_inert"] == 0
    assert summary["unmeasured"] == 2
    assert summary["with_fields"] == 4
    assert summary["before_fields"] == 1
    assert summary["with_changed_files"] == 2
    assert summary["symbols_selected"] == 4


def test_the_reported_rate_names_the_measured_denominator() -> None:
    """The printed section says which denominator each rate was taken over.

    A reader comparing the two rates must be able to see that one covers every
    record stating the fields and the other only the records that were compared:
    "of fielded" on the promotion line would imply the placeholder zeros were in
    it, which is the mistake this wording used to invite.
    """
    records = [
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_primary_promoted=True,
            changed_context_differs=True,
            changed_baseline_status="built",
        ),
        _record(
            changed_files_signal="ok",
            changed_files_count=1,
            changed_symbols_selected=2,
            changed_baseline_status="not_sampled",
        ),
    ]
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        _print_changed_file_promotion(records)
    printed = buffer.getvalue()

    promotion_line = next(
        line for line in printed.splitlines() if "changed_primary_promoted" in line
    )
    assert "100.0%" in promotion_line
    assert "of 1 measured" in promotion_line
    assert "of fielded" not in promotion_line
    # The directly observable line keeps its own, larger denominator.
    files_line = next(line for line in printed.splitlines() if "changed_files_count" in line)
    assert "of fielded" in files_line
    assert "sum changed_symbols_promoted" in printed
    assert "measured = comparison built or provably unnecessary" in printed
