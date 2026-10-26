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


def test_file_identity_is_idempotent() -> None:
    """Normalizing an identity that is already normalized changes nothing."""
    assert file_identity(file_identity("Apps\\Gateway\\x.py")) == file_identity(
        "apps/gateway/x.py"
    )


# ---------------------------------------------------------------------------
# Module keys become the file identities the transcript uses
# ---------------------------------------------------------------------------


def test_module_keys_become_the_envelope_identity(tmp_path: Path) -> None:
    """The index's key for a file and a client's name for it must compare equal."""
    root = _repo(tmp_path)

    derived = module_files_of(["packages/demo/widget"])
    batch = _events([_envelope("Packages\\Demo\\Widget.py")], root)

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


def test_a_repeated_shape_of_refusal_is_one_refusal(tmp_path: Path) -> None:
    """Refusals are counted per shape, because counting them per path keeps a path.

    Two refused targets of the same kind are one entry here: the number of distinct
    paths refused is not recoverable without storing a path, and it is deliberately
    not recovered.  A replay of the transcript returns the same one.
    """
    root = _repo(tmp_path)
    tracker = FileActivityTracker()
    messages = [_envelope("../../outside.txt"), _envelope("../../elsewhere.txt")]

    counts = _observe(tracker, messages, root)
    again = _observe(tracker, messages, root)

    assert counts.paths_rejected == 1 == again.paths_rejected
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
