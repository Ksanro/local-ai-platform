"""Focused tests for roadmap C1's file-activity measurement.

Nothing here decides what a request sends.  What these tests hold the code to is
the shape of the record that comes out the other side: that an activity total is a
property of the transcript rather than of how many times the transcript has been
re-sent, that a file counts as read or modified only when the client's own result
said it was, that no file name survives the trip to the session record, and that
the states meaning "this was not measured" - including a conversation whose history
this tracker cannot reconstruct - can always be told apart from the zeroes that
mean "nothing was touched".
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from packages.context.context_package import ModuleDescription, SymbolContext
from packages.pipeline import cline_activity as activity_module
from packages.pipeline.cline_activity import (
    MAX_PATH_CHARS,
    OUTCOME_CONFIRMED,
    OUTCOME_FAILED,
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_NOT_MODIFIED,
    OUTCOME_UNKNOWN,
    REJECT_CONTROL,
    REJECT_DRIVE,
    REJECT_EMPTY,
    REJECT_LENGTH,
    REJECT_NUL,
    REJECT_OUTSIDE,
    REJECT_QUOTING,
    REJECT_SELF,
    REJECT_STREAM,
    RepositoryPathNormalizer,
    file_identity,
    resolve_file_activity_events,
)
from packages.pipeline.context import PipelineContext
from packages.pipeline.file_activity import (
    CORRELATION_MEASURED,
    CORRELATION_NO_PRIOR_CONTEXT,
    CORRELATION_TRACKER_MISS,
    CORRELATION_UNAVAILABLE,
    INERT_FILE_ACTIVITY,
    NEW_CONVERSATION_KEY,
    STATE_MEASURED,
    STATE_PARTIAL,
    STATE_UNAVAILABLE,
    FileActivityCounts,
    FileActivityTracker,
    module_files_of,
    sanitize_file_activity,
    supplied_files_of,
    supplied_module_keys,
    transcript_fingerprints,
)
from packages.pipeline.stages.repository_context import RepositoryContextStage

WIDGET = "packages/demo/widget.py"
DELTA = "packages/context/delta.py"
OTHER = "packages/demo/__init__.py"
FIXTURE_FILES = (WIDGET, DELTA, OTHER)

#: What the assistant says between two requests.  The words are irrelevant to the
#: measurement and relevant to the identity: file activity fingerprints the whole
#: transcript, assistant turns included, so a test that wants two requests to be
#: one conversation has to send the reply that separates them.
REPLY = {"role": "assistant", "content": "Let me open that."}


def _repo(tmp_path: Path) -> Path:
    """Create a small repository-shaped tree and return its root.

    Args:
        tmp_path: The pytest temporary directory to build inside.

    Returns:
        The root, so callers can join onto it or pass it to a normalizer.
    """
    for relative in FIXTURE_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixture\n", encoding="utf-8")
    return tmp_path


def _envelope(
    target: str, tool: str = "read_file", body: str = "the file contents"
) -> dict[str, Any]:
    """Build one message shaped like a Cline tool-result envelope.

    Args:
        target: The path text the client claims to have used, untrusted by design.
        tool: The Cline tool named in the header.
        body: The result body that follows the header, read only for one closed
            status token and never for its text.

    Returns:
        A user-role message dict of the shape the request path carries.
    """
    return {"role": "user", "content": f"[{tool} for {target}] Result: {body}"}


def _saved(target: str, tool: str = "write_to_file") -> dict[str, Any]:
    """Build a modification envelope whose result says the write landed."""
    return _envelope(target, tool=tool, body="The file was successfully saved.")


def _refused(target: str, tool: str = "replace_in_file") -> dict[str, Any]:
    """Build a modification envelope whose result says nothing was written."""
    return _envelope(target, tool=tool, body="The tool execution failed with error: no match.")


def _read_failed(target: str) -> dict[str, Any]:
    """Build a read envelope whose result says the read did not happen."""
    return _envelope(target, body="The tool execution failed with error: no such file or directory")


def _context(messages: list[dict[str, Any]], request_id: str = "req") -> PipelineContext:
    """Build the minimal context a stage execution reads.

    Args:
        messages: The provider-request messages.
        request_id: The request identifier to carry.

    Returns:
        A context with ``request`` populated and no plan metadata.
    """
    context = PipelineContext(request_id=request_id)
    context.request = {"messages": messages}
    return context


def _events(messages: list[dict[str, Any]], root: Path) -> Any:
    """Resolve a message list into events with a normalizer bound to ``root``.

    Args:
        messages: The messages to parse.
        root: The repository root to contain targets against.

    Returns:
        The ``ResolvedEnvelopes`` batch for the request.
    """
    return resolve_file_activity_events(messages, RepositoryPathNormalizer(root))


def _observe(
    tracker: FileActivityTracker,
    messages: list[dict[str, Any]],
    root: Path,
    *,
    supplied: list[str] | None = None,
    changed: list[str] | None = None,
) -> FileActivityCounts:
    """Measure one request the way the stage measures it, and return its counts.

    Args:
        tracker: The store the conversation's correlation state lives in.
        messages: The transcript this request carries.
        root: The repository root targets are contained against.
        supplied: The files the context package this request sends.
        changed: The files the working-tree signal reports as modified.

    Returns:
        The counts for this request.
    """
    lookup_key, store_key = transcript_fingerprints(messages)
    batch = _events(messages, root)
    return tracker.observe(
        lookup_key=lookup_key,
        store_key=store_key,
        events=batch.events,
        beyond_bound=batch.beyond_bound,
        supplied_files=supplied or (),
        changed_files=changed,
    )


# ---------------------------------------------------------------------------
# The envelope grammar, and what it refuses to read
# ---------------------------------------------------------------------------


def test_read_header_yields_one_confirmed_read(tmp_path: Path) -> None:
    """A ``read_file`` result is a read of the path its header names."""
    root = _repo(tmp_path)

    batch = _events([_envelope(WIDGET)], root)

    assert len(batch.events) == 1
    assert batch.events[0].activity == "read"
    assert batch.events[0].file == WIDGET
    assert batch.events[0].outcome == OUTCOME_CONFIRMED
    assert batch.events[0].successful is True


def test_modification_header_yields_a_confirmed_modification(tmp_path: Path) -> None:
    """A writer's header plus a result that says the file landed is a modification."""
    root = _repo(tmp_path)

    batch = _events([_saved(WIDGET, tool="replace_in_file")], root)

    assert batch.events[0].activity == "modified"
    assert batch.events[0].outcome == OUTCOME_CONFIRMED


@pytest.mark.parametrize("tool", ("write_to_file", "replace_in_file"))
def test_both_writers_are_still_recognized_by_the_activity_boundary(
    tmp_path: Path, tool: str
) -> None:
    """Restoring the history-cap behavior restored nothing here - it never left.

    Recognizing a writer's envelope is the whole point of roadmap C1, and the
    registry view that decides it stays wide even though the planning/history view
    was pulled back to its pre-C1 set.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
        tool: The Cline writing tool under test.
    """
    root = _repo(tmp_path)

    batch = _events([_saved(WIDGET, tool=tool)], root)

    assert batch.events[0].tool == tool
    assert batch.events[0].activity == "modified"
    assert batch.events[0].file == WIDGET


@pytest.mark.parametrize("tool", ("write_to_file", "replace_in_file"))
def test_a_writer_result_reaches_the_record_as_numbers_only(tmp_path: Path, tool: str) -> None:
    """The write is measured and named by nothing: a modified file and no prose.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
        tool: The Cline writing tool under test.
    """
    root = _repo(tmp_path)

    counts = _observe(FileActivityTracker(), [_saved(WIDGET, tool=tool)], root)
    record = counts.as_dict()

    assert counts.files_modified == 1
    assert counts.modification_attempts == 1
    assert counts.state == STATE_MEASURED
    # The record is already exactly the shape a session log may write: two closed
    # tokens and fifteen integers, so sanitizing it cannot change a byte of it and
    # there is nowhere in it for a tool name to live.
    assert sanitize_file_activity(record) == record
    assert tool not in json.dumps(record)


def test_a_failed_read_is_a_failed_read(tmp_path: Path) -> None:
    """A read result beginning with the client's failure prose did not read anything.

    The body of a successful read is the file's own text, so there is no success
    grammar to match and the failure rule is anchored instead: only a head that
    *begins* with the recognized prose counts as a failure.
    """
    root = _repo(tmp_path)

    batch = _events([_read_failed(WIDGET)], root)

    assert batch.events[0].outcome == OUTCOME_FAILED
    assert batch.events[0].file == WIDGET
    assert batch.events[0].successful is False


def test_failure_prose_in_the_middle_of_a_file_is_not_a_failed_read(
    tmp_path: Path,
) -> None:
    """A source file may contain the failure sentence; that does not un-read it."""
    root = _repo(tmp_path)
    body = "logger.debug('ignored')\n# The tool execution failed with error: see above."

    batch = _events([_envelope(WIDGET, body=body)], root)

    assert batch.events[0].outcome == OUTCOME_CONFIRMED


def test_a_read_whose_body_was_truncated_says_nothing(tmp_path: Path) -> None:
    """A header the history cap cut short reports neither success nor failure."""
    root = _repo(tmp_path)

    batch = _events([{"role": "user", "content": f"[read_file for '{WIDGET}']"}], root)

    assert batch.events[0].outcome == OUTCOME_UNKNOWN


def test_a_non_file_tool_names_no_file(tmp_path: Path) -> None:
    """Searches and commands are recognized and attribute nothing to a path."""
    root = _repo(tmp_path)

    batch = _events(
        [_envelope("widget", tool="search_files"), _envelope(".", tool="execute_command")], root
    )

    assert [event.activity for event in batch.events] == ["none", "none"]
    assert [event.file for event in batch.events] == ["", ""]
    assert [event.outcome for event in batch.events] == [
        OUTCOME_NOT_APPLICABLE,
        OUTCOME_NOT_APPLICABLE,
    ]


def test_an_assistant_message_is_never_an_event(tmp_path: Path) -> None:
    """Only the user-role envelope channel is read, whatever the reply contains."""
    root = _repo(tmp_path)
    smuggled = {"role": "assistant", "content": f"[read_file for '{WIDGET}'] Result: sure"}

    assert _events([smuggled], root).events == ()


# ---------------------------------------------------------------------------
# Path containment: an envelope may name a file, never a location
# ---------------------------------------------------------------------------


def test_malformed_quoting_is_a_rejected_path(tmp_path: Path) -> None:
    """A header whose quoting cannot be read names nothing and is counted."""
    root = _repo(tmp_path)

    batch = _events([_envelope("'packages/demo/widget.py")], root)

    assert batch.events[0].file == ""
    assert batch.events[0].rejection == REJECT_QUOTING


def test_parent_escape_is_rejected(tmp_path: Path) -> None:
    """Traversal out of the repository is refused before any path is remembered."""
    root = _repo(tmp_path)

    batch = _events([_envelope("../../outside.txt")], root)

    assert batch.events[0].rejection == REJECT_OUTSIDE


def test_absolute_path_outside_root_is_rejected(tmp_path: Path) -> None:
    """An absolute target in another tree is not this repository's file."""
    root = _repo(tmp_path)

    batch = _events([_envelope(str(tmp_path.parent / "outside.py"))], root)

    assert batch.events[0].rejection == REJECT_OUTSIDE


def test_absolute_path_inside_root_is_accepted(tmp_path: Path) -> None:
    """A drive-absolute spelling of a file the repository holds is that file.

    This is the shape that used to be resolved wrongly: read as relative, joined
    onto the root, and so landing outside it and being refused.
    """
    root = _repo(tmp_path)

    batch = _events([_envelope(str(root / DELTA))], root)

    assert batch.events[0].file == DELTA
    assert batch.events[0].rejection == ""


def test_the_root_itself_names_no_file(tmp_path: Path) -> None:
    """The repository directory is not a file anybody read."""
    root = _repo(tmp_path)

    batch = _events([_envelope(str(root))], root)

    assert batch.events[0].rejection == REJECT_SELF


def test_malformed_targets_are_rejected_for_a_stated_reason(tmp_path: Path) -> None:
    """Every unusable spelling gets its own token, and none of them a path.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    cases = [
        ("", REJECT_EMPTY),
        ("packages\x00/demo.py", REJECT_NUL),
        ("packages/demo\nwidget.py", REJECT_CONTROL),
        ("a" * (MAX_PATH_CHARS + 1) + ".py", REJECT_LENGTH),
        ("//server/share/x.py", REJECT_DRIVE),
        ("C:ads:x.py", REJECT_STREAM),
    ]

    for target, reason in cases:
        batch = _events([_envelope(target)], root)
        assert batch.events[0].rejection == reason, target
        assert batch.events[0].file == "", target


def test_an_absent_root_still_measures(tmp_path: Path) -> None:
    """Containment is decided lexically, so a missing directory is not a broken one."""
    missing = tmp_path / "not-a-repository"

    normalizer = RepositoryPathNormalizer(missing)
    batch = resolve_file_activity_events([_envelope("x.py")], normalizer)

    assert normalizer.root_ok is True
    assert batch.events[0].file == "x.py"


#: Whether this filesystem folds case, decided the way ``file_identity`` decides it.
_CASE_INSENSITIVE_FS = os.path.normcase("A") == "a"


def test_file_identity_is_idempotent() -> None:
    """Normalizing an identity that is already normalized changes nothing."""
    once = file_identity("Apps\\Gateway\\x.py")

    assert file_identity(once) == once


def test_file_identity_folds_case_only_where_the_filesystem_does() -> None:
    """Two spellings differing only in case are one file on Windows, two on Linux."""
    mixed = file_identity("Apps\\Gateway\\x.py")
    lower = file_identity("apps/gateway/x.py")

    if _CASE_INSENSITIVE_FS:
        assert mixed == lower
    else:
        assert mixed == "Apps/Gateway/x.py"
        assert mixed != lower


# ---------------------------------------------------------------------------
# Module keys become the file identities the transcript uses
# ---------------------------------------------------------------------------


def test_module_keys_become_the_envelope_identity(tmp_path: Path) -> None:
    """The index's key for a file and a client's name for it must compare equal."""
    root = _repo(tmp_path)

    derived = module_files_of(["packages/demo/widget"])
    # A case-folding filesystem lets the client's spelling differ in case too;
    # a case-sensitive one names a different file if it does.
    spelling = "Packages\\Demo\\Widget.py" if _CASE_INSENSITIVE_FS else "packages\\demo\\widget.py"
    batch = _events([_envelope(spelling)], root)

    assert derived == (WIDGET,)
    assert batch.events[0].file == derived[0]


def test_module_key_derivation_is_guarded() -> None:
    """Keys that are not strings, and shapes that are not sequences, yield nothing."""
    assert module_files_of(None) == ()
    assert module_files_of("packages/demo/widget") == ()
    assert module_files_of([None, 3, "", "packages/context/delta"]) == (DELTA,)
    assert module_files_of(["packages/demo", "packages\\demo"]) == ("packages/demo.py",)


def test_supplied_keys_come_from_every_place_a_package_names_modules() -> None:
    """A package may name its modules in three places, and all three are read.

    ``supplied_module_keys`` walks ``related_modules``, each
    ``module_descriptions`` entry's ``module_path``, and the module element of each
    ``SymbolContext.location``, in that order, first-seen.  A ``location`` is the
    real three-element shape - ``(module_path, start_line, end_line)`` - because the
    derivation is compared against what the composer actually builds, not against a
    stand-in of convenience.
    """
    package = SimpleNamespace(
        related_modules=[DELTA[:-3]],
        module_descriptions=[ModuleDescription(module_path=WIDGET[:-3], purpose="the widget")],
        primary_symbol_context=SymbolContext(
            qualified_name="demo.Widget",
            location=(OTHER[: -len(".__init__.py")], 12, 40),
        ),
        supporting_symbol_contexts=[],
    )

    assert supplied_module_keys(package) == (DELTA[:-3], WIDGET[:-3], "packages/demo")
    assert supplied_files_of(package) == (DELTA, WIDGET, "packages/demo.py")


def test_supplied_keys_are_empty_for_a_package_that_names_nothing() -> None:
    """No composed modules is a real answer, and it must not read as a mismatch."""
    assert supplied_module_keys(None) == ()
    assert supplied_files_of(None) == ()
    assert supplied_files_of(SimpleNamespace(related_modules="packages")) == ()


# ---------------------------------------------------------------------------
# Activity totals are a snapshot of the transcript
# ---------------------------------------------------------------------------


def test_replaying_the_same_transcript_returns_the_same_dictionary(
    tmp_path: Path,
) -> None:
    """The invariant the whole model rests on: same transcript, same record.

    A Cline client re-sends its entire prior conversation on every request.  Under
    the tally this replaces, each re-send added the same envelope again, so a file
    read on turn one was fifteen reads by turn fifteen and the only number that
    moved honestly was a suppression counter.  Nothing is incremented per request
    here, so the second answer is the same dictionary as the first, field for field.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    messages = [_envelope(WIDGET), _saved(DELTA), _envelope("widget", tool="search_files")]

    first = _observe(tracker, messages, root)
    second = _observe(tracker, messages, root)
    third = _observe(tracker, messages, root)

    assert first.as_dict() == second.as_dict() == third.as_dict()
    assert first.files_read == 1
    assert first.files_modified == 1
    assert first.files_touched == 2
    assert first.other_events == 1


def test_a_longer_transcript_measures_the_work_and_not_the_replay(
    tmp_path: Path,
) -> None:
    """Growing the conversation grows the totals by what is new in it."""
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    first_turn = [_envelope(WIDGET)]
    second_turn = first_turn + [REPLY, _envelope(DELTA)]

    before = _observe(tracker, first_turn, root)
    after = _observe(tracker, second_turn, root)

    assert (before.files_read, before.files_touched) == (1, 1)
    assert (after.files_read, after.files_touched) == (2, 2)


def test_read_then_modified_unions_to_one_touched_file(tmp_path: Path) -> None:
    """A file read and then edited is one touched file and one of each action."""
    root = _repo(tmp_path)

    counts = _observe(FileActivityTracker(), [_envelope(WIDGET), _saved(WIDGET)], root)

    assert counts.files_read == 1
    assert counts.files_modified == 1
    assert counts.files_touched == 1


def test_conversations_are_kept_apart(tmp_path: Path) -> None:
    """One conversation's transcript does not appear in another's totals."""
    root = _repo(tmp_path)
    tracker = FileActivityTracker()

    _observe(tracker, [_envelope(WIDGET)], root)
    other = _observe(tracker, [_envelope(DELTA)], root)

    assert other.files_read == 1
    assert other.files_touched == 1
    assert other.files_modified == 0


# ---------------------------------------------------------------------------
# Attempts, successes and failures are three different claims
# ---------------------------------------------------------------------------


def test_a_failed_write_is_an_attempt_and_not_a_modification(tmp_path: Path) -> None:
    """A header that names a file says the agent tried, not that anything landed."""
    root = _repo(tmp_path)

    counts = _observe(FileActivityTracker(), [_refused(WIDGET)], root)

    assert counts.modification_attempts == 1
    assert counts.modifications_not_modified == 1
    assert counts.files_modified == 0
    assert counts.files_touched == 0


def test_an_unclassified_write_is_an_attempt_and_an_unknown(tmp_path: Path) -> None:
    """A client that words its results differently confirms nothing."""
    root = _repo(tmp_path)
    odd = _envelope(WIDGET, tool="write_to_file", body="All done! The file is updated.")

    counts = _observe(FileActivityTracker(), [odd], root)

    assert counts.modification_attempts == 1
    assert counts.modifications_unknown == 1
    assert counts.files_modified == 0


def test_a_failed_read_is_an_attempt_and_not_a_read(tmp_path: Path) -> None:
    """The read total counts results, not headers."""
    root = _repo(tmp_path)

    counts = _observe(FileActivityTracker(), [_read_failed(WIDGET)], root)

    assert counts.read_attempts == 1
    assert counts.reads_failed == 1
    assert counts.files_read == 0
    assert counts.files_touched == 0


def test_failure_then_success_on_one_file_is_a_modified_file(tmp_path: Path) -> None:
    """Precedence, not first-come: any confirmed result for a file settles it."""
    root = _repo(tmp_path)

    counts = _observe(FileActivityTracker(), [_refused(WIDGET), _saved(WIDGET)], root)

    assert counts.files_modified == 1
    assert counts.modifications_not_modified == 0
    assert counts.modification_attempts == 1


def test_success_then_failure_on_one_file_stays_modified(tmp_path: Path) -> None:
    """A later failure cannot un-write a file an earlier result said was saved."""
    root = _repo(tmp_path)

    counts = _observe(FileActivityTracker(), [_saved(WIDGET), _refused(WIDGET)], root)

    assert counts.files_modified == 1
    assert counts.modifications_not_modified == 0


def test_replay_moves_no_outcome_counter(tmp_path: Path) -> None:
    """Outcomes are decided per file, so re-sending a transcript cannot shift one."""
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    first = [_refused(WIDGET)]
    second = first + [REPLY, _saved(WIDGET)]

    before = _observe(tracker, first, root)
    after = _observe(tracker, second, root)
    again = _observe(tracker, second, root)

    assert (before.files_modified, before.modifications_not_modified) == (0, 1)
    assert (after.files_modified, after.modifications_not_modified) == (1, 0)
    assert again.as_dict() == after.as_dict()


def test_the_outcome_fields_partition_every_attempt(tmp_path: Path) -> None:
    """Nothing a header named can go unreported by the outcome fields."""
    root = _repo(tmp_path)
    messages = [
        _saved(WIDGET),
        _refused(DELTA),
        _envelope(OTHER, tool="write_to_file", body="I have updated the file."),
        _read_failed("packages/demo/gone.py"),
    ]

    counts = _observe(FileActivityTracker(), messages, root)

    assert counts.modification_attempts == 3
    assert (
        counts.files_modified + counts.modifications_not_modified + counts.modifications_unknown
        == counts.modification_attempts
    )
    assert counts.read_attempts == counts.files_read + counts.reads_failed + counts.reads_unknown


def test_a_rejected_path_is_counted_and_names_no_file(tmp_path: Path) -> None:
    """An envelope whose target cannot be contained is a refusal, not a touch.

    It lands in ``paths_rejected`` and in neither attempt field, because there is no
    file in the repository for an outcome to belong to.
    """
    root = _repo(tmp_path)

    counts = _observe(FileActivityTracker(), [_envelope("../../outside.txt")], root)

    assert counts.paths_rejected == 1
    assert counts.files_touched == 0
    assert counts.modification_attempts == 0
    assert counts.state == STATE_MEASURED


def test_a_repeated_shape_of_refusal_is_two_refusals(tmp_path: Path) -> None:
    """Two refused targets are two events, even of the same shape.

    What stays unrecoverable is *which* paths were refused: the counter names no
    file, and a replay of the transcript returns the same two.  This replaces the
    per-shape count, which reported a conversation refused fifty times as having met
    one refusal.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    messages = [_envelope("../../outside.txt"), _envelope("../../elsewhere.txt")]

    counts = _observe(tracker, messages, root)
    again = _observe(tracker, messages, root)

    assert counts.paths_rejected == 2 == again.paths_rejected
    assert counts.files_touched == 0


# ---------------------------------------------------------------------------
# Correlation: the one number that needs memory, and when memory is missing
# ---------------------------------------------------------------------------


def test_context_supplied_on_one_request_is_credited_on_the_next(tmp_path: Path) -> None:
    """A file the gateway sent earlier and the agent opens later is the measurement.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    first = [{"role": "user", "content": "explain the widget"}]

    supplied = _observe(tracker, first, root, supplied=[WIDGET])
    touching = _observe(tracker, first + [REPLY, _envelope(WIDGET)], root)

    assert supplied.context_files_touched == 0
    assert touching.files_touched == 1
    assert touching.context_files_touched == 1
    assert touching.touched_without_context == 0
    assert touching.correlation == CORRELATION_MEASURED


def test_a_same_turn_access_is_never_credited_on_a_later_request(tmp_path: Path) -> None:
    """The exact regression: a file sent and touched on one request stays uncredited.

    Request 1 contains a successful read of that file and supplies it on the same
    request, so the touch cannot have followed the supply.  Request 2 re-sends that
    history and adds no new access to it.  Correlating the historical read against
    the context request 1 added was the original bug: the transcript never changed,
    only the gateway's memory did.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    first = [_envelope(WIDGET)]

    one = _observe(tracker, first, root, supplied=[WIDGET])
    two = _observe(
        tracker, first + [REPLY, _envelope("nothing", tool="search_files")], root, supplied=[WIDGET]
    )

    assert one.context_files_touched == 0
    assert two.context_files_touched == 0
    assert two.files_read == 1
    assert two.correlation == CORRELATION_MEASURED


def test_a_replayed_credit_stays_credited(tmp_path: Path) -> None:
    """Re-sending the request that earned a credit neither repeats nor loses it."""
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    first = [{"role": "user", "content": "explain the widget"}]
    second = first + [REPLY, _envelope(WIDGET)]

    _observe(tracker, first, root, supplied=[WIDGET])
    earned = _observe(tracker, second, root)
    again = _observe(tracker, second, root)

    assert earned.context_files_touched == 1
    assert again.as_dict() == earned.as_dict()


def test_a_touched_file_that_was_never_supplied_is_counted_apart(
    tmp_path: Path,
) -> None:
    """The two correlation counters partition the touched set and cannot overlap."""
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    first = [{"role": "user", "content": "explain the widget"}]

    _observe(tracker, first, root, supplied=[WIDGET])
    counts = _observe(tracker, first + [REPLY, _envelope(WIDGET), _envelope(DELTA)], root)

    assert counts.files_touched == 2
    assert counts.context_files_touched == 1
    assert counts.touched_without_context == 1


def test_a_first_request_reports_no_prior_context(tmp_path: Path) -> None:
    """Nothing was supplied before the conversation's first request: a real zero."""
    root = _repo(tmp_path)

    counts = _observe(FileActivityTracker(), [_envelope(WIDGET)], root)

    assert counts.correlation == CORRELATION_NO_PRIOR_CONTEXT
    assert counts.context_files_touched == 0
    assert counts.touched_without_context == counts.files_touched


def test_an_evicted_conversation_reports_a_tracker_miss_not_a_zero(
    tmp_path: Path,
) -> None:
    """A conversation the tracker lost must not read as one that saw no context.

    The activity half of the record is untouched by the loss - it came from the
    transcript in front of the gateway - and the correlation half is stated as
    unavailable instead of as the confident zero it would otherwise look like.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker(maxsize=1)
    first = [{"role": "user", "content": "explain the widget"}]

    _observe(tracker, first, root, supplied=[WIDGET])
    _observe(tracker, [{"role": "user", "content": "an unrelated task"}], root, supplied=[DELTA])
    lost = _observe(tracker, first + [REPLY, _envelope(WIDGET)], root)

    assert lost.correlation == CORRELATION_TRACKER_MISS
    assert lost.context_files_touched == 0
    assert lost.touched_without_context == 0
    assert lost.files_read == 1
    assert lost.state == STATE_MEASURED


def test_a_rewritten_history_reports_a_tracker_miss(tmp_path: Path) -> None:
    """History that does not extend what was remembered is not correlatable.

    The client or the gateway can drop or rewrite older messages, and then whatever
    the tracker holds belongs to a transcript that is not this one's prefix.  The
    correlation is reported as unavailable rather than as a number, because every
    operation in front of the gateway may be historical and nothing here can tell
    which.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    first = [{"role": "user", "content": "explain the widget"}]

    _observe(tracker, first, root, supplied=[WIDGET])
    rewritten = _observe(
        tracker,
        [{"role": "user", "content": "explain the widget again"}] + [REPLY, _envelope(WIDGET)],
        root,
    )

    assert rewritten.correlation == CORRELATION_TRACKER_MISS
    assert rewritten.context_files_touched == 0


def test_a_tracker_miss_is_sticky_for_every_descendant(tmp_path: Path) -> None:
    """The request that finds a gap is not the only one that should say so.

    Without a continuity flag a miss lasts exactly one record: the state rebuilt
    after the gap is stored as though nothing were missing, so the request that
    extends it finds that state and reports ``correlation=measured`` while
    partitioning a touched set whose supplied half it cannot see.  Turn 1 supplies
    ``WIDGET``; the tracker is restarted; turn 2 reports the miss; turn 3 extends
    turn 2 and must still report it.  Replaying turn 3 must not move a field.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    turn1 = [{"role": "user", "content": "explain the widget"}]
    _observe(FileActivityTracker(), turn1, root, supplied=[WIDGET])

    restarted = FileActivityTracker()
    turn2 = turn1 + [REPLY, _envelope(WIDGET)]
    second = _observe(restarted, turn2, root)
    turn3 = turn2 + [REPLY, _saved(DELTA)]
    third = _observe(restarted, turn3, root, supplied=[DELTA])
    replay = _observe(restarted, turn3, root, supplied=[DELTA])

    assert second.correlation == CORRELATION_TRACKER_MISS
    assert third.correlation == CORRELATION_TRACKER_MISS
    assert third.files_touched == 2
    assert third.state == STATE_MEASURED
    # What turn 1 was shown is unknown from here on, so neither half of the
    # partition is claimed - and in particular ``WIDGET`` is not reported as a file
    # touched without context, which is the claim a healed-over miss would make.
    assert third.context_files_touched == 0
    assert third.touched_without_context == 0
    assert replay.as_dict() == third.as_dict()


def test_a_miss_found_by_eviction_stays_missed_after_the_gap(tmp_path: Path) -> None:
    """An eviction and a restart break a lineage the same way.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker(maxsize=1)
    turn1 = [{"role": "user", "content": "explain the widget"}]

    _observe(tracker, turn1, root, supplied=[WIDGET])
    _observe(tracker, [{"role": "user", "content": "an unrelated task"}], root, supplied=[DELTA])
    turn2 = turn1 + [REPLY, _envelope(WIDGET)]
    second = _observe(tracker, turn2, root, supplied=[DELTA])

    assert second.correlation == CORRELATION_TRACKER_MISS

    turn3 = turn2 + [REPLY, _saved(DELTA)]
    third = _observe(tracker, turn3, root, supplied=[DELTA])

    assert third.correlation == CORRELATION_TRACKER_MISS
    assert third.context_files_touched == 0
    assert third.touched_without_context == 0
    assert third.files_modified == 1


def test_a_rewritten_history_keeps_its_gap_forward(tmp_path: Path) -> None:
    """A history the client rewrote is unknown forever, not unknown for one turn."""
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    turn1 = [{"role": "user", "content": "explain the widget"}]

    _observe(tracker, turn1, root, supplied=[WIDGET])
    rewritten = [{"role": "user", "content": "explain the widget again"}]
    second = _observe(tracker, rewritten + [REPLY, _envelope(WIDGET)], root)
    third_turn = rewritten + [REPLY, _envelope(WIDGET), REPLY, _saved(DELTA)]
    third = _observe(tracker, third_turn, root, supplied=[DELTA])

    assert second.correlation == CORRELATION_TRACKER_MISS
    assert third.correlation == CORRELATION_TRACKER_MISS
    assert third.touched_without_context == 0


def test_an_unbroken_lineage_is_still_reported_as_measured(tmp_path: Path) -> None:
    """Stickiness must not cost the honest answer to the conversations it did not lose.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    first = [{"role": "user", "content": "explain the widget"}]

    supplied = _observe(tracker, first, root, supplied=[WIDGET])
    credited = _observe(tracker, first + [REPLY, _envelope(WIDGET)], root, supplied=[DELTA])
    later = _observe(
        tracker, first + [REPLY, _envelope(WIDGET), REPLY, _saved(DELTA)], root, supplied=[DELTA]
    )

    assert supplied.correlation == CORRELATION_NO_PRIOR_CONTEXT
    assert credited.correlation == CORRELATION_MEASURED
    assert credited.context_files_touched == 1
    assert later.correlation == CORRELATION_MEASURED
    assert later.files_touched == 2


def test_rejected_targets_are_counted_one_per_envelope(tmp_path: Path) -> None:
    """Fifty refusals are fifty, not one refusal shape.

    The totals are rebuilt from the transcript in hand, so a count of them can be a
    count of the envelopes themselves: no rejected string has to be remembered, and
    no conversation that hit the same wall fifty times has to report hitting it once.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    messages = [_refused(f"../../outside{index}.txt") for index in range(50)]

    counts = _observe(tracker, messages, root)
    again = _observe(tracker, messages, root)

    assert counts.paths_rejected == 50
    assert again.paths_rejected == 50
    assert counts.modification_attempts == 0
    assert counts.files_touched == 0
    assert counts.events_beyond_bound == 0


def test_non_file_envelopes_count_as_events_not_as_tool_kinds(tmp_path: Path) -> None:
    """Nine searches, listings and commands are nine events, not three tool kinds.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    tools = ("search_files", "list_files", "execute_command")
    messages = [_envelope(f"pattern-{index}", tool=tools[index % 3]) for index in range(9)]

    counts = _observe(tracker, messages, root)
    again = _observe(tracker, messages, root)

    assert counts.other_events == 9
    assert again.other_events == 9
    assert counts.files_touched == 0
    assert again.as_dict() == counts.as_dict()


def test_changed_files_are_counted_from_the_transcript_alone(tmp_path: Path) -> None:
    """The working-tree overlap needs no memory, so a tracker miss cannot hide it."""
    root = _repo(tmp_path)
    tracker = FileActivityTracker(maxsize=1)
    messages = [_envelope(WIDGET)]

    counted = _observe(tracker, messages, root, changed=[WIDGET])
    _observe(tracker, [{"role": "user", "content": "another conversation"}], root)
    blind = _observe(tracker, messages, root, changed=None)

    assert counted.changed_files_touched == 1
    assert blind.changed_files_touched == 0


def test_a_failed_operation_never_enters_the_changed_overlap(tmp_path: Path) -> None:
    """A write that did not land cannot be a file the tree shows as modified."""
    root = _repo(tmp_path)

    counts = _observe(FileActivityTracker(), [_refused(WIDGET)], root, changed=[WIDGET])

    assert counts.files_touched == 0
    assert counts.changed_files_touched == 0


# ---------------------------------------------------------------------------
# Bounds, and what a bound does to a state
# ---------------------------------------------------------------------------


def test_a_bound_that_drops_envelopes_says_partial_and_keeps_the_newest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a bound cannot read is a floor on the totals, and it is stated.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
        monkeypatch: Pytest fixture used to shrink the envelope bound.
    """
    root = _repo(tmp_path)
    monkeypatch.setattr(activity_module, "MAX_ENVELOPES_PER_REQUEST", 2)

    counts = _observe(
        FileActivityTracker(), [_envelope(OTHER), _envelope("gone.py"), _envelope(WIDGET)], root
    )

    assert counts.events_beyond_bound == 1
    assert counts.state == STATE_PARTIAL
    assert counts.files_touched == 2


def test_a_correlation_bound_leaves_a_count(tmp_path: Path) -> None:
    """A file the remembered set would not hold is reported as bounded-away."""
    root = _repo(tmp_path)
    tracker = FileActivityTracker(max_unique_files=1)
    first = [{"role": "user", "content": "explain the widget"}]

    _observe(tracker, first, root, supplied=[WIDGET])
    counts = _observe(tracker, first + [REPLY, _envelope(WIDGET), _envelope(DELTA)], root)

    assert counts.events_beyond_bound >= 1
    assert counts.correlation == CORRELATION_MEASURED


def test_a_request_whose_file_sets_are_full_still_measures(tmp_path: Path) -> None:
    """The remembered sets are bounded; the transcript measurement is not starved."""
    root = _repo(tmp_path)

    counts = _observe(FileActivityTracker(max_unique_files=1), [_envelope(WIDGET)], root)

    assert counts.files_read == 1
    assert counts.state == STATE_MEASURED


def test_dropping_a_conversation_changes_nothing_in_a_transcript(tmp_path: Path) -> None:
    """The same transcript measures the same with or without remembered state.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    kept = FileActivityTracker()
    thrashed = FileActivityTracker(maxsize=1)
    messages = [_envelope(WIDGET), _saved(DELTA)]

    mine = _observe(kept, messages, root)
    _observe(thrashed, messages, root)
    _observe(thrashed, [{"role": "user", "content": "other task"}], root)
    back = _observe(thrashed, messages, root)

    assert back.files_read == mine.files_read == 1
    assert back.files_modified == mine.files_modified == 1


def test_one_long_conversation_consumes_many_states(tmp_path: Path) -> None:
    """The bound counts transcript-prefix states, and one conversation needs many.

    Four requests of one conversation are four entries, not one: every request
    stores what it derived under the fingerprint of the transcript it saw, which is
    what lets a retry or a branch find the state that was current when it was sent.
    A tracker sized for four *conversations* therefore runs out of room after four
    turns of a single one, and the turn that arrives after its prefix was dropped
    reports the gap and keeps reporting it.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker(maxsize=4)
    first = [{"role": "user", "content": "explain the widget"}]

    _observe(tracker, first, root, supplied=[WIDGET])
    second = first + [REPLY, _envelope(WIDGET)]
    _observe(tracker, second, root, supplied=[DELTA])
    third = second + [REPLY, _saved(DELTA)]
    _observe(tracker, third, root, supplied=[DELTA])
    fourth = third + [REPLY, _envelope(OTHER)]
    counts = _observe(tracker, fourth, root, supplied=[OTHER])

    assert counts.correlation == CORRELATION_MEASURED
    assert tracker.state_count() == 4  # one conversation, four entries

    _observe(tracker, fourth + [REPLY, _envelope(WIDGET)], root)

    assert tracker.state_count() == 4  # the bound held; the oldest prefix is gone
    dropped = _observe(tracker, second, root)
    assert dropped.correlation == CORRELATION_TRACKER_MISS


# ---------------------------------------------------------------------------
# Path resolution: memoized per request, and its filesystem answers kept across them
# ---------------------------------------------------------------------------


class _CountingNormalizer(RepositoryPathNormalizer):
    """A normalizer that records every target it was asked to resolve.

    Attributes:
        calls: The target text handed to :meth:`normalize`, in order.  A memoized
            resolve hands one spelling here once per request, which is the whole
            point: each call below costs a ``realpath``.
    """

    __slots__ = ("calls",)

    def __init__(self, root: Path | str) -> None:
        """Bind the normalizer to ``root`` and start an empty call list."""
        super().__init__(root)
        self.calls: list[str] = []

    def normalize(self, target: str) -> tuple[str, str]:
        """Record ``target``, then resolve it exactly as the normalizer would."""
        self.calls.append(target)
        return super().normalize(target)


def test_a_repeated_target_is_resolved_once_per_request(tmp_path: Path) -> None:
    """Forty copies of one envelope are forty parses and one resolution.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    normalizer = _CountingNormalizer(root)
    messages = [_envelope(WIDGET) for _ in range(40)]

    batch = resolve_file_activity_events(messages, normalizer)

    assert len(batch.events) == 40
    assert normalizer.calls == [WIDGET]
    assert {event.file for event in batch.events} == {WIDGET}


def test_distinct_targets_still_resolve_on_their_own(tmp_path: Path) -> None:
    """Memoizing a spelling must not memoize the file it names.

    Two ways of writing one path are two keys here, and each is resolved; the
    per-request map is keyed by the client's spelling, not by the file.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    normalizer = _CountingNormalizer(root)
    spellings = (WIDGET, f"./{WIDGET}", f"{root.as_posix()}/{WIDGET}")

    batch = resolve_file_activity_events([_envelope(target) for target in spellings], normalizer)

    assert normalizer.calls == list(spellings)
    assert len({event.file for event in batch.events}) == 1


def test_the_request_cache_does_not_survive_into_the_next_request(tmp_path: Path) -> None:
    """A second request walks its envelopes again: the per-request map dies with it.

    What crosses requests is only the normalizer's map of filesystem answers, which
    sits below :meth:`normalize` - see the ``realpath`` tests that follow.
    """
    root = _repo(tmp_path)
    normalizer = _CountingNormalizer(root)
    messages = [_envelope(WIDGET), _saved(DELTA)]

    first = resolve_file_activity_events(messages, normalizer)
    second = resolve_file_activity_events(messages, normalizer)

    assert len(first.events) == len(second.events) == 2
    assert normalizer.calls == [WIDGET, DELTA, WIDGET, DELTA]


def test_memoizing_changes_no_answer_and_no_rejection_count(tmp_path: Path) -> None:
    """The cache may only remove work, never change which file a target named."""
    root = _repo(tmp_path)
    messages = [
        _envelope(WIDGET),
        _envelope(WIDGET),
        _envelope("../../outside.txt"),
        _envelope("../../outside.txt"),
        _envelope("pattern", tool="search_files"),
        _saved(DELTA),
    ]

    plain = resolve_file_activity_events(messages, RepositoryPathNormalizer(root))
    counter = _CountingNormalizer(root)
    counted = resolve_file_activity_events(messages, counter)

    assert counted.events == plain.events
    assert sum(1 for event in plain.events if event.rejection) == 2
    assert sum(1 for event in counted.events if event.rejection) == 2
    assert len(counter.calls) == 3  # WIDGET, the escaped target, DELTA - once each


# ---------------------------------------------------------------------------
# The boundary every one of these numbers has to cross
# ---------------------------------------------------------------------------


def test_sanitize_coerces_every_untrusted_shape() -> None:
    """Whatever a metadata dict holds, the record is counts and two tokens."""
    assert sanitize_file_activity(None) == INERT_FILE_ACTIVITY
    assert sanitize_file_activity("measured") == INERT_FILE_ACTIVITY
    assert sanitize_file_activity({"files_read": 3}) == {**INERT_FILE_ACTIVITY, "files_read": 3}
    assert sanitize_file_activity({"state": "measured", "correlation": "measured"}) == {
        **INERT_FILE_ACTIVITY,
        "state": STATE_MEASURED,
        "correlation": CORRELATION_MEASURED,
    }


def test_sanitize_drops_a_leaked_path_or_state() -> None:
    """Even metadata that leaked a path yields counts and two words.

    ``sanitize_file_activity`` walks the fixed field list only, so path text on a
    count field becomes ``0``, an unlisted key is never read, and a token outside a
    closed set becomes ``unavailable``.  No input shape can put a string other than
    a state token into the record.
    """
    leaked = {
        **INERT_FILE_ACTIVITY,
        "state": "definitely-not-a-state",
        "correlation": "confident",
        "files_read": "packages/demo/widget.py",
        "file_paths": ["packages/demo/widget.py"],
        "modifications_confirmed": "/etc/passwd",
    }

    cleaned = sanitize_file_activity(leaked)

    assert set(cleaned) == set(INERT_FILE_ACTIVITY)
    assert cleaned["state"] == STATE_UNAVAILABLE
    assert cleaned["correlation"] == CORRELATION_UNAVAILABLE
    assert cleaned["files_read"] == 0
    assert [value for value in cleaned.values() if isinstance(value, str)] == [
        STATE_UNAVAILABLE,
        CORRELATION_UNAVAILABLE,
    ]


@pytest.mark.asyncio
async def test_rejected_targets_reach_the_record_as_a_count(tmp_path: Path) -> None:
    """Fifty refusals produce fifty of them and no trace of what was refused.

    Args:
        tmp_path: The pytest temporary directory to build a repository in.
    """
    root = _repo(tmp_path)
    stage = RepositoryContextStage(
        index=None, file_activity=FileActivityTracker(), repository_root=root
    )
    messages = [_refused(f"../../outside{index}.txt") for index in range(50)]
    context = _context(messages, request_id="refusals")

    await stage.execute(context)

    record = context.get_metadata("file_activity")

    assert record["paths_rejected"] == 50
    assert record["files_touched"] == 0
    assert sanitize_file_activity(record) == record
    assert "outside" not in json.dumps(record)


def test_the_record_carries_no_field_a_replay_could_inflate() -> None:
    """The schema has no cumulative counter left to grow on a second delivery."""
    counters = [key for key in INERT_FILE_ACTIVITY if key not in ("state", "correlation")]

    assert "replay_suppressed" not in INERT_FILE_ACTIVITY
    assert "file_events" not in INERT_FILE_ACTIVITY
    assert sorted(counters) == sorted(counters)
    assert len(counters) == len(INERT_FILE_ACTIVITY) - 2


# ---------------------------------------------------------------------------
# The transcript is the conversation's identity
# ---------------------------------------------------------------------------


def test_the_fingerprint_sees_the_assistant_turns_a_user_only_key_would_miss() -> None:
    """Two conversations with the same user text and different replies differ.

    ``packages.context.delta`` keys on user messages, which is the right question for
    a symbol filter and the wrong one here: the activity being measured is the
    agent's, so what it said is part of what identifies the conversation.
    """
    task = {"role": "user", "content": "explain the widget"}

    lookup_one, store_one = transcript_fingerprints([task, {"role": "assistant", "content": "a"}])
    lookup_two, store_two = transcript_fingerprints([task, {"role": "assistant", "content": "b"}])

    assert store_one != store_two
    assert lookup_one == transcript_fingerprints([task])[1]
    assert lookup_one != NEW_CONVERSATION_KEY


def test_the_first_request_of_a_conversation_looks_up_nothing(tmp_path: Path) -> None:
    """A transcript with no reply in it has no earlier request to compare with."""
    lookup_key, store_key = transcript_fingerprints(
        [{"role": "user", "content": "explain the widget"}]
    )

    assert lookup_key == NEW_CONVERSATION_KEY
    assert store_key != NEW_CONVERSATION_KEY
    assert transcript_fingerprints([])[1] != NEW_CONVERSATION_KEY


def test_an_identical_replay_looks_up_the_state_it_just_wrote(tmp_path: Path) -> None:
    """The next request's prefix is this one's whole transcript, by construction."""
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    first = [{"role": "user", "content": "explain the widget"}]
    second = first + [REPLY, _envelope(WIDGET)]

    _observe(tracker, first, root, supplied=[WIDGET])
    counts = _observe(tracker, second, root)
    replay = _observe(tracker, second, root)

    assert replay.correlation == CORRELATION_MEASURED == counts.correlation
    assert replay.as_dict() == counts.as_dict()


# ---------------------------------------------------------------------------
# The stage, and the fact that measurement never costs a request
# ---------------------------------------------------------------------------


class _RecordingTracker:
    """A tracker stand-in that reports what the stage decided to hand it."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def observe(self, **kwargs: Any) -> Any:
        """Record the request and answer with an inert measured record.

        Args:
            **kwargs: Everything the stage resolved for the request.

        Returns:
            A counts object with both states measured and no tallies of its own.
        """
        self.calls.append(kwargs)
        return FileActivityCounts(
            **{
                **INERT_FILE_ACTIVITY,
                "state": STATE_MEASURED,
                "correlation": CORRELATION_MEASURED,
            }
        )


class _RaisingTracker:
    """A tracker whose measurement fails, which must not fail the request."""

    def observe(self, **kwargs: Any) -> Any:
        """Refuse to count anything.

        Args:
            **kwargs: Ignored; the call is what raises.

        Raises:
            RuntimeError: Always, to stand in for any measurement failure.
        """
        raise RuntimeError("the measurement is not allowed to matter")


def test_observation_reads_both_halves_of_the_correlation(tmp_path: Path) -> None:
    """The client's envelopes, the request's context, and the tree all arrive together."""
    root = _repo(tmp_path)
    tracker = _RecordingTracker()
    stage = RepositoryContextStage(file_activity=tracker, repository_root=root)
    messages = [_envelope(WIDGET)]

    stage._observe_file_activity(
        _context(messages),
        messages,
        SimpleNamespace(related_modules=[DELTA[:-3]]),
        frozenset({"packages/demo/widget"}),
    )

    call = tracker.calls[0]
    assert [event.file for event in call["events"]] == [WIDGET]
    assert call["supplied_files"] == (DELTA,)
    assert call["changed_files"] == (WIDGET,)
    assert call["lookup_key"] == NEW_CONVERSATION_KEY
    assert call["store_key"] == transcript_fingerprints(messages)[1]


def test_the_record_has_no_field_a_replay_can_move() -> None:
    """The schema holds no cumulative counter left to grow on a second delivery."""
    assert "replay_suppressed" not in INERT_FILE_ACTIVITY
    assert "file_events" not in INERT_FILE_ACTIVITY
    assert "modifications_confirmed" not in INERT_FILE_ACTIVITY
    tokens = {"state", "correlation"}
    counters = set(INERT_FILE_ACTIVITY) - tokens
    assert all(isinstance(INERT_FILE_ACTIVITY[key], int) for key in counters)
    assert all(key not in counters for key in tokens)


@pytest.mark.asyncio
async def test_a_request_is_counted_even_with_no_index(tmp_path: Path) -> None:
    """An agent that read files on a gateway that sent no context is still measured."""
    root = _repo(tmp_path)
    stage = RepositoryContextStage(
        index=None, file_activity=FileActivityTracker(), repository_root=root
    )
    context = _context([_envelope(WIDGET)])

    result = await stage.execute(context)

    record = context.get_metadata("file_activity")
    assert result.success is True
    assert record["state"] == STATE_MEASURED
    assert record["correlation"] == CORRELATION_NO_PRIOR_CONTEXT
    assert record["files_read"] == 1


@pytest.mark.asyncio
async def test_a_failed_measurement_states_unavailable_and_keeps_the_request(
    tmp_path: Path,
) -> None:
    """Nothing the request was going to say depends on the observation succeeding."""
    stage = RepositoryContextStage(
        index=None, file_activity=_RaisingTracker(), repository_root=_repo(tmp_path)
    )
    context = _context([_envelope(WIDGET)])

    result = await stage.execute(context)

    assert result.success is True
    assert context.get_metadata("file_activity") == {
        **INERT_FILE_ACTIVITY,
        "state": STATE_UNAVAILABLE,
        "correlation": CORRELATION_UNAVAILABLE,
    }


@pytest.mark.asyncio
async def test_a_tracker_without_a_root_is_stated_as_unavailable() -> None:
    """A tracker cannot guess which directory it is containing paths against.

    :class:`FileActivityTracker` holds no filesystem path - containment belongs to
    the normalizer the stage is built with - so a stage configured with a tracker and
    no root cannot measure anything.  That is reported as ``unavailable`` on both
    tokens, never as a confident zero.
    """
    stage = RepositoryContextStage(index=None, file_activity=FileActivityTracker())
    context = _context([_envelope(WIDGET)])

    await stage.execute(context)

    assert context.get_metadata("file_activity") == INERT_FILE_ACTIVITY


# ---------------------------------------------------------------------------
# Native tool calls (Cline 4.x): tool_calls plus role "tool" results
#
# Shapes follow a 2026-11-02 wire capture of Cline 4.1.26; every result body here
# is a placeholder, and none of the captured conversation text is used.
# ---------------------------------------------------------------------------


def _call(call_id: str, name: str, arguments: Any) -> dict[str, Any]:
    """Build an assistant turn that makes one native tool call."""
    text = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": text}}
        ],
    }


def _result(call_id: str, payload: Any) -> dict[str, Any]:
    """Build the ``role: "tool"`` message answering one call."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"role": "tool", "tool_call_id": call_id, "content": text}


def _ok(query: str) -> dict[str, Any]:
    """One successful result entry, with a placeholder body."""
    return {"query": query, "result": "placeholder", "success": True}


_REJECTED = {"error": "This tool call was rejected by the user and not executed."}
_DENIED_EDIT = {"error": "The user denied this edit. The file was NOT modified."}


def test_native_read_files_is_a_confirmed_read_of_each_file(tmp_path: Path) -> None:
    """``read_files`` reads every file it names, absolute spellings included."""
    root = _repo(tmp_path)
    absolute = str(root / "packages" / "demo" / "widget.py")
    files = [{"path": absolute}, {"path": DELTA, "start_line": 1}]
    messages = [
        {"role": "user", "content": "read two files"},
        _call("c1", "read_files", {"files": files}),
        _result("c1", [_ok(absolute), _ok(DELTA)]),
    ]

    batch = _events(messages, root)

    assert [(e.activity, e.file, e.outcome) for e in batch.events] == [
        ("read", WIDGET, OUTCOME_CONFIRMED),
        ("read", DELTA, OUTCOME_CONFIRMED),
    ]


def test_native_read_entries_carry_their_own_status(tmp_path: Path) -> None:
    """Each entry of a multi-file result decides its own file's outcome."""
    root = _repo(tmp_path)
    files = [{"path": WIDGET}, {"path": DELTA}, {"path": OTHER}]
    messages = [
        _call("c1", "read_files", {"files": files}),
        _result(
            "c1",
            [
                _ok(WIDGET),
                {"query": DELTA, "error": "placeholder"},
                {"query": OTHER, "result": "placeholder"},
            ],
        ),
    ]

    outcomes = [e.outcome for e in _events(messages, root).events]

    assert outcomes == [OUTCOME_CONFIRMED, OUTCOME_FAILED, OUTCOME_UNKNOWN]


def test_native_editor_success_and_denial(tmp_path: Path) -> None:
    """``editor`` modifies its ``path``; a denied edit is not a modification."""
    root = _repo(tmp_path)
    messages = [
        _call("c1", "editor", {"path": WIDGET, "new_text": "x"}),
        _result("c1", {"query": f"edit:{WIDGET}", "result": "placeholder", "success": True}),
        _call("c2", "editor", {"path": DELTA, "old_text": "a", "new_text": "b"}),
        _result("c2", _DENIED_EDIT),
    ]

    events = _events(messages, root).events

    assert [(e.activity, e.file, e.outcome) for e in events] == [
        ("modified", WIDGET, OUTCOME_CONFIRMED),
        ("modified", DELTA, OUTCOME_NOT_MODIFIED),
    ]


def test_a_rejected_native_read_is_a_failed_read(tmp_path: Path) -> None:
    """A call the user rejected before it ran read nothing."""
    root = _repo(tmp_path)
    messages = [
        _call("c1", "read_files", {"files": [{"path": WIDGET}]}),
        _result("c1", _REJECTED),
    ]

    counts = _observe(FileActivityTracker(maxsize=4), messages, root)

    assert counts.files_read == 0
    assert counts.read_attempts == 1
    assert counts.reads_failed == 1


def test_native_search_and_commands_name_no_file(tmp_path: Path) -> None:
    """``search_codebase`` and ``run_commands`` are activity without a file."""
    root = _repo(tmp_path)
    messages = [
        _call("c1", "search_codebase", {"queries": ["pattern"]}),
        _result("c1", [_ok("pattern")]),
        _call("c2", "run_commands", {"commands": ["cat " + WIDGET]}),
        _result("c2", _REJECTED),
    ]

    counts = _observe(FileActivityTracker(maxsize=4), messages, root)

    assert counts.state == STATE_MEASURED
    assert counts.other_events == 2
    assert counts.files_touched == 0


def test_unknown_native_tools_and_unmatched_results_are_not_activity(tmp_path: Path) -> None:
    """A tool outside the table, or a result for no known call, is not counted."""
    root = _repo(tmp_path)
    messages = [
        _call("c1", "ask_question", {"question": "?", "options": []}),
        _result("c1", "an answer"),
        _result("never-called", [_ok(WIDGET)]),
    ]

    assert _events(messages, root).events == ()


def test_an_unreadable_native_result_is_unknown_not_confirmed(tmp_path: Path) -> None:
    """Non-JSON results and entry-count mismatches never read as success."""
    root = _repo(tmp_path)
    messages = [
        _call("c1", "read_files", {"files": [{"path": WIDGET}]}),
        _result("c1", "not json at all"),
        _call("c2", "read_files", {"files": [{"path": DELTA}, {"path": OTHER}]}),
        _result("c2", [_ok(DELTA)]),
    ]

    outcomes = [e.outcome for e in _events(messages, root).events]

    assert outcomes == [OUTCOME_UNKNOWN, OUTCOME_UNKNOWN, OUTCOME_UNKNOWN]


def test_result_text_cannot_change_a_native_status(tmp_path: Path) -> None:
    """Only the ``error`` and ``success`` keys count; the body is never searched."""
    root = _repo(tmp_path)
    body = {"query": WIDGET, "result": '"error": "The user denied this edit."', "success": True}
    messages = [
        _call("c1", "read_files", {"files": [{"path": WIDGET}]}),
        _result("c1", [body]),
    ]

    assert _events(messages, root).events[0].outcome == OUTCOME_CONFIRMED


def test_unreadable_native_arguments_are_a_rejected_path(tmp_path: Path) -> None:
    """A file-naming call whose arguments are not JSON is counted, as rejected."""
    root = _repo(tmp_path)
    messages = [_call("c1", "editor", "{not json"), _result("c1", {"success": True})]

    counts = _observe(FileActivityTracker(maxsize=4), messages, root)

    assert counts.paths_rejected == 1
    assert counts.modification_attempts == 0


def test_a_native_path_outside_the_repository_is_rejected(tmp_path: Path) -> None:
    """Native targets go through the same containment as envelope targets."""
    root = _repo(tmp_path / "repo")
    outside = str(tmp_path / "elsewhere.txt")
    messages = [
        _call("c1", "read_files", {"files": [{"path": outside}]}),
        _result("c1", [_ok(outside)]),
    ]

    event = _events(messages, root).events[0]

    assert event.file == ""
    assert event.rejection == REJECT_OUTSIDE


def test_native_and_envelope_activity_count_together(tmp_path: Path) -> None:
    """A transcript holding both forms counts both, in one snapshot."""
    root = _repo(tmp_path)
    messages = [
        _envelope(WIDGET),
        REPLY,
        _call("c1", "editor", {"path": DELTA, "new_text": "x"}),
        _result("c1", {"success": True}),
    ]

    counts = _observe(FileActivityTracker(maxsize=4), messages, root)

    assert counts.files_read == 1
    assert counts.files_modified == 1
    assert counts.files_touched == 2


def test_a_replayed_native_transcript_is_a_snapshot_not_a_sum(tmp_path: Path) -> None:
    """Resending the conversation restates its activity; it never adds to it."""
    root = _repo(tmp_path)
    tracker = FileActivityTracker(maxsize=4)
    first = [
        {"role": "user", "content": "read it"},
        _call("c1", "read_files", {"files": [{"path": WIDGET}]}),
        _result("c1", [_ok(WIDGET)]),
    ]
    later = [
        *first,
        {"role": "assistant", "content": "done"},
        {"role": "user", "content": "thanks"},
    ]

    one = _observe(tracker, first, root)
    two = _observe(tracker, later, root)
    again = _observe(tracker, later, root)

    assert one.files_read == two.files_read == again.files_read == 1
    assert two.as_dict() == again.as_dict()


# ---------------------------------------------------------------------------
# The bound is filled newest first, and what falls outside it is never decoded
# ---------------------------------------------------------------------------


def _reference_parse(messages: list[Any]) -> tuple[list[Any], int]:
    """The original oldest-first walk into a bounded queue, kept as the specification.

    Every result body is decoded and the queue then drops the oldest envelopes.  The
    production walk must return exactly this, envelope for envelope.
    """
    from collections import deque

    bound = activity_module.MAX_ENVELOPES_PER_REQUEST
    found: deque[Any] = deque(maxlen=bound)
    recognized = 0
    calls: dict[str, tuple[str, object]] = {}
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "assistant":
            activity_module._remember_native_calls(message.get("tool_calls"), calls)
            continue
        if role == "tool":
            call = calls.get(str(message.get("tool_call_id", "")))
            if call is None:
                continue
            for native in activity_module._native_envelopes(
                call[0], call[1], message.get("content", "")
            ):
                recognized += 1
                found.append(native)
            continue
        if role != "user":
            continue
        envelope = activity_module.parse_message_envelope(
            activity_module.content_to_text(message.get("content", ""))
        )
        if envelope is None:
            continue
        recognized += 1
        found.append(envelope)
    return list(found), max(recognized - bound, 0)


def _random_transcript(rng: Any, length: int) -> list[Any]:
    """Return a transcript mixing every shape the walk has to keep in order.

    Legacy envelopes, plain user text, native calls naming one or several files,
    calls whose arguments are not JSON, results answering no announced call, a call
    id announced twice, results that arrive before their call, and non-dict entries.
    """
    messages: list[Any] = []
    serial = 0
    for _ in range(length):
        roll = rng.random()
        if roll < 0.2:
            messages.append(_envelope(f"pkg/m{rng.randrange(40)}.py"))
        elif roll < 0.27:
            messages.append(_saved(f"pkg/m{rng.randrange(40)}.py"))
        elif roll < 0.32:
            messages.append({"role": "user", "content": "plain follow-up text"})
        elif roll < 0.34:
            messages.append("not a message")
        elif roll < 0.38:
            messages.append(_result(f"never_{serial}", [_ok("x")]))
        else:
            serial += 1
            call_id = f"c{serial % 30}"  # ids recur, so a later call rebinds one
            kind = rng.random()
            if kind < 0.45:
                count = rng.randrange(1, 6)
                files = [{"path": f"pkg/m{rng.randrange(40)}.py"} for _ in range(count)]
                call = _call(call_id, "read_files", {"files": files})
                payload: Any = [_ok("q") for _ in range(count)]
            elif kind < 0.7:
                call = _call(call_id, "editor", {"path": f"pkg/m{rng.randrange(40)}.py"})
                payload = _DENIED_EDIT if rng.random() < 0.3 else {"success": True}
            elif kind < 0.8:
                call = _call(call_id, "editor", "arguments that are not json")
                payload = {"success": True}
            elif kind < 0.9:
                call = _call(call_id, "read_files", {"query": "no target at all"})
                payload = _REJECTED
            else:
                call = _call(call_id, "search_codebase", {"query": "x"})
                payload = {"output": "matches"}
            result = _result(call_id, payload)
            if rng.random() < 0.05:
                messages.extend([result, call])  # a result before its call answers nothing
            else:
                messages.extend([call, result])
    return messages


@pytest.mark.parametrize("bound", [1, 3, 17, 256])
def test_the_newest_first_walk_matches_the_bounded_queue_it_replaced(
    monkeypatch: pytest.MonkeyPatch, bound: int
) -> None:
    """Same envelopes, same order, same overflow count, on transcripts of every size."""
    import random

    monkeypatch.setattr(activity_module, "MAX_ENVELOPES_PER_REQUEST", bound)
    rng = random.Random(20261103 + bound)
    for _ in range(60):
        messages = _random_transcript(rng, rng.randrange(0, 200))
        assert activity_module.parse_envelopes(messages) == _reference_parse(messages)


def test_a_call_straddling_the_bound_keeps_its_newest_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A read of three files with room for two keeps the last two and counts one out."""
    monkeypatch.setattr(activity_module, "MAX_ENVELOPES_PER_REQUEST", 3)
    files = [{"path": f"pkg/f{index}.py"} for index in range(3)]
    messages = [
        _call("a", "read_files", {"files": files}),
        _result("a", [_ok("q")] * 3),
        _envelope(WIDGET),
    ]

    envelopes, beyond = activity_module.parse_envelopes(messages)

    assert [envelope.target for envelope in envelopes] == ["pkg/f1.py", "pkg/f2.py", WIDGET]
    assert beyond == 1
    assert (envelopes, beyond) == _reference_parse(messages)


def test_a_result_outside_the_bound_is_counted_and_never_decoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the bodies the bound keeps reach the JSON decoder."""
    monkeypatch.setattr(activity_module, "MAX_ENVELOPES_PER_REQUEST", 2)
    decoded: list[str] = []
    real = activity_module._native_statuses

    def spy(content: object, count: int) -> list[str]:
        decoded.append(str(content))
        return real(content, count)

    monkeypatch.setattr(activity_module, "_native_statuses", spy)
    messages: list[Any] = []
    for index in range(6):
        messages.append(_call(f"c{index}", "editor", {"path": f"pkg/f{index}.py"}))
        messages.append(_result(f"c{index}", {"success": True, "result": f"body {index}"}))

    envelopes, beyond = activity_module.parse_envelopes(messages)

    assert [envelope.target for envelope in envelopes] == ["pkg/f4.py", "pkg/f5.py"]
    assert beyond == 4
    assert len(decoded) == 2
    assert all("body 4" in text or "body 5" in text for text in decoded)


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("read_files", {"files": [{"path": "a.py"}, {"path": "b.py"}, "c.py", {"x": 1}]}),
        ("read_files", {"files": []}),
        ("read_files", {"path": "a.py"}),
        ("read_files", {"query": "nothing named"}),
        ("editor", {"path": "a.py"}),
        ("editor", {"path": 42}),
        ("editor", "not json"),
        ("editor", '["a list", "not an object"]'),
        ("search_codebase", {"query": "x"}),
        ("run_commands", "anything at all"),
    ],
)
def test_the_overflow_count_mirrors_the_envelopes_a_call_builds(
    tool: str, arguments: Any
) -> None:
    """Counting a call from its arguments gives the number decoding it would build."""
    text = arguments if isinstance(arguments, str) else json.dumps(arguments)
    built = activity_module._native_envelopes(tool, text, json.dumps({"success": True}))
    assert activity_module._native_envelope_count(tool, text) == len(built)


# ---------------------------------------------------------------------------
# realpath answers are kept across requests, bounded, and never change an answer
# ---------------------------------------------------------------------------


def _count_realpath(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every ``realpath`` the module makes from now on, and return the record."""
    seen: list[str] = []
    real = os.path.realpath

    def spy(path: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(activity_module.os.path, "realpath", spy)
    return seen


def test_a_later_request_reuses_the_filesystem_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second request of a conversation reaches ``realpath`` for nothing it named before."""
    root = _repo(tmp_path)
    normalizer = RepositoryPathNormalizer(root)
    seen = _count_realpath(monkeypatch)
    first_request = [_envelope(WIDGET), _saved(DELTA)]
    second_request = [*first_request, _envelope(WIDGET), _envelope("packages/new.py")]

    first = resolve_file_activity_events(first_request, normalizer)
    resolved_first = len(seen)
    second = resolve_file_activity_events(second_request, normalizer)

    assert resolved_first == 2
    assert len(seen) == 3  # only the one file the second request named for the first time
    assert second.events[:2] == first.events


def test_the_cross_request_map_changes_no_answer(tmp_path: Path) -> None:
    """A warm normalizer answers every target exactly as a fresh one does, rejections included."""
    root = _repo(tmp_path)
    targets = [WIDGET, f"./{WIDGET}", DELTA, "../../outside.txt", f"{root.as_posix()}/{WIDGET}",
               "packages/demo/../demo/widget.py", "packages", "."]
    warm = RepositoryPathNormalizer(root)
    for target in targets:
        warm.normalize(target)

    for target in targets:
        assert warm.normalize(target) == RepositoryPathNormalizer(root).normalize(target)


def test_the_cross_request_map_is_bounded_and_evicts_the_oldest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The map never holds more than its bound, and an evicted target resolves again."""
    monkeypatch.setattr(activity_module, "MAX_RESOLVED_PATHS", 3)
    root = _repo(tmp_path)
    normalizer = RepositoryPathNormalizer(root)
    seen = _count_realpath(monkeypatch)

    for index in range(5):
        normalizer.normalize(f"pkg/f{index}.py")
    assert len(normalizer._resolved) == 3
    assert len(seen) == 5

    normalizer.normalize("pkg/f4.py")  # newest: still held
    assert len(seen) == 5
    normalizer.normalize("pkg/f0.py")  # oldest: evicted, so resolved again
    assert len(seen) == 6
    assert len(normalizer._resolved) == 3


def test_a_lexical_rejection_never_reaches_the_map(tmp_path: Path) -> None:
    """Only a candidate that passed every lexical check is remembered."""
    normalizer = RepositoryPathNormalizer(_repo(tmp_path))
    long_path = "x" * (MAX_PATH_CHARS + 1)
    for target in ("", "a\x00b", "a\tb", long_path, "docs:notes", "//server/share"):
        _identity, rejection = normalizer.normalize(target)
        assert rejection
    assert len(normalizer._resolved) == 0


def test_a_failed_resolution_is_not_remembered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``realpath`` that raised is reported as outside once, then asked again."""
    root = _repo(tmp_path)
    normalizer = RepositoryPathNormalizer(root)
    real = os.path.realpath
    failures = {"left": 1}

    def flaky(path: Any, *args: Any, **kwargs: Any) -> Any:
        if failures["left"]:
            failures["left"] -= 1
            raise OSError("transient")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(activity_module.os.path, "realpath", flaky)

    assert normalizer.normalize(WIDGET) == ("", REJECT_OUTSIDE)
    assert len(normalizer._resolved) == 0
    assert normalizer.normalize(WIDGET) == (WIDGET, "")
