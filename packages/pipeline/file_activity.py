"""Snapshot-scoped, count-only file-activity measurement (roadmap C1).

:class:`FileActivityTracker` answers one question per request: which files does
the transcript this client just sent show the agent actually reading or writing,
and how did that meet the repository context the gateway has been sending it?
The answer leaves this module as counts and two state tokens - never a path,
filename, module name, envelope, or byte of file content.

A snapshot, not a tally
-----------------------

Cline's conversation endpoint re-sends the whole prior conversation inside every
request, so the transcript *is* the conversation's history and there is nothing
for a counter to accumulate.  Every number describing what the client reported -
``files_read``, ``files_modified``, ``files_touched``, the attempt and outcome
counters, ``paths_rejected``, ``other_events`` - is therefore recomputed from the
events of the current request and nothing else:

    same transcript + same supplied-context state = exactly the same output.

The bug this replaces counted on every ``observe()``, so a file read on turn one
was fifteen reads by turn fifteen, and a repeated request only hid the doubling
in the per-file totals it did not touch.  There is no ``replay_suppressed``
counter any more because there is nothing left to suppress: a re-sent transcript
re-reads the same events and arrives at the same numbers.  What a transcript
*cannot* answer on its own is the one genuinely temporal question - was this file
already in front of the agent when it opened it? - and that is the only thing
this module still remembers between requests.

Conversation isolation
----------------------

The remembered half is keyed by a file-activity-specific fingerprint of the
request's **complete message prefix, assistant turns included**, and each request
stores its state under the fingerprint of the prefix it saw, which is what the
next request looks up.  Assistant turns matter here because the activity being
measured is the agent's, and a key that cannot see them treats two conversations
whose user turns happen to match as one conversation.

The honest limitation is that the fingerprint is content, not identity: two
independent conversations whose transcripts are byte-identical are, to this
module, the same conversation.  Nothing in a chat-completions request carries a
conversation ID that could tell them apart; a client that wants its conversations
counted separately must send them with transcripts that differ.  Nothing is
process-global and nothing crosses between conversations otherwise, and the
tracker never mutates the state it looked up - it derives a new one and stores
that - so a request whose transcript is empty cannot bleed into a conversation.

The cache is an LRU of ``maxsize`` *transcript-prefix states*, and each state
holds at most ``max_unique_files`` files per set.  An entry is not a conversation:
a conversation contributes one new state per request that answers an earlier
prefix, so a five-turn Cline session occupies five entries and a conversation that
has fallen out of the window comes back as a lineage gap rather than as a
reconstruction.  Both bounds exist because history is client-supplied: a hostile
client must not be able to turn a request into unbounded work or memory.  What a
bound forces out is counted (``events_beyond_bound``) rather than silently lost,
and it is the *oldest* envelopes that fall out of a bounded parse, so what the
conversation just did remains visible.

Correlation and ordering
------------------------

``context_files_touched`` is the one number a single transcript cannot answer,
because it asks what the gateway supplied *before* this request arrived.  It is
therefore the only quantity that consults remembered state, and the rules that
keep it honest are temporal ones:

* a file is credited only when the successful operation on it is **new** to this
  conversation - an operation an earlier transcript already showed the tracker is
  history being re-sent, not an agent acting on what it was just given;
* the current request's supplied files join the remembered set *after*
  correlation, so a context package that introduces a file on the same request
  that reports touching it proves only that the context arrived;
* correlation never reconsiders a historical event against context supplied
  later, which is the retroactive-attribution bug this ordering exists to stop;
* a lineage that broke stays broken.  A request whose prefix the tracker cannot
  find - an eviction, a restart, a rewritten history - marks the state it stores
  discontinuous, and every descendant of that state inherits the mark, so the
  correlation pair is reported as ``tracker_miss`` from then on rather than
  quietly resuming as ``measured`` on the turn after the gap.  What was supplied
  before the gap is permanently unknown here, and a number that forgot that would
  be the most misleading thing this module could print.

``touched_without_context`` is ``files_touched`` minus ``context_files_touched``,
so the two partition the touched set and cannot disagree - and both are zero, with
``correlation`` saying so, while a lineage is discontinuous.

Outcome is not attempt
----------------------

A header names a file whether or not the operation on it worked: the same
``[replace_in_file for x.py]`` arrives when nothing was written, and the same
``[read_file for x.py]`` arrives when the read failed.  So each file gets one
outcome per operation kind, by deterministic precedence over every envelope the
current transcript holds - **confirmed** when any successful result for that file
exists, otherwise **failed** when any known failure or no-change result exists,
otherwise **unknown**:

* a failure followed by a success is a confirmed operation;
* a success followed by a failure stays confirmed;
* replaying the transcript changes neither, because the same precedence is
  applied to the same events again.

The precedence decides which counter a file lands in, never how many times it is
counted.  ``files_modified`` and ``files_read`` hold only files whose outcome is
confirmed, and ``files_touched`` is the union of those two; failed and unknown
operations are kept apart from them in ``read_attempts``/``reads_failed`` and
``modification_attempts``/``modifications_not_modified``/``modifications_unknown``.  An
attempt field is a set size, not an event count, so
``read_attempts == files_read + reads_failed + reads_unknown`` and
``modification_attempts == files_modified + modifications_not_modified +
modifications_unknown`` hold on every transcript.  None of it is filesystem
truth: confirmed means the client's own bounded result line said the operation
happened, and a client that words its results differently lands in an unknown
counter rather than in either claim.  An envelope whose target was refused names
no file at all, so it enters none of these counters - it is ``paths_rejected``.

Public API
----------

.. code-block:: python

    from packages.pipeline.file_activity import FileActivityTracker

    tracker = FileActivityTracker(maxsize=settings.context_delta_cache_size)
    lookup_key, store_key = transcript_fingerprints(request["messages"])
    counts = tracker.observe(
        lookup_key,
        store_key,
        events=batch.events,
        beyond_bound=batch.beyond_bound,
        supplied_files=supplied_files,
        changed_files=changed_files,
    )
    counts.as_dict()  # the file_activity section, count-only

``transcript_fingerprints`` is file-activity's own conversation identity: a
fingerprint of the **complete message prefix, assistant turns included**, and not
``packages.context.delta``'s user-only key.  A conversation is stored under the
fingerprint of the transcript it saw, which is what the next request looks up
after dropping the newest assistant turn and everything behind it.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, cast

from packages.context.content import content_to_text
from packages.pipeline.cline_activity import (
    OUTCOME_CONFIRMED,
    OUTCOME_FAILED,
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_NOT_MODIFIED,
    OUTCOME_UNKNOWN,
    ActivityEvent,
    file_identity,
)
from packages.pipeline.user_messages import (
    ACTIVITY_MODIFIED,
    ACTIVITY_NONE,
    ACTIVITY_READ,
)
from packages.repository.module_paths import module_key_to_path

__all__ = [
    "CORRELATION_MEASURED",
    "CORRELATION_NO_PRIOR_CONTEXT",
    "CORRELATION_TRACKER_MISS",
    "CORRELATION_UNAVAILABLE",
    "FILE_ACTIVITY_CORRELATION_STATES",
    "FILE_ACTIVITY_STATES",
    "MAX_ACTIVITY_STATES",
    "MAX_UNIQUE_FILES_PER_STATE",
    "NEW_CONVERSATION_KEY",
    "FileActivityCounts",
    "FileActivityTracker",
    "INERT_FILE_ACTIVITY",
    "module_files_of",
    "sanitize_file_activity",
    "STATE_MEASURED",
    "STATE_NONE",
    "STATE_PARTIAL",
    "STATE_UNAVAILABLE",
    "supplied_files_of",
    "supplied_module_keys",
    "transcript_fingerprints",
]

#: The activity-availability states a record can carry.  ``none`` and
#: ``unavailable`` both report zeroes, and only one of them means the gateway
#: looked.  ``partial`` says the transcript held more than a bound could read:
#: the totals are then a floor, and what fell outside the window is counted in
#: ``events_beyond_bound`` rather than presented as the whole conversation.
STATE_MEASURED: Final = "measured"
STATE_NONE: Final = "none"
STATE_PARTIAL: Final = "partial"
STATE_UNAVAILABLE: Final = "unavailable"

#: The correlation states, reported apart from the activity states because they
#: answer a different question.  ``state`` asks whether the transcript was read;
#: ``correlation`` asks whether the gateway was in a position to know whether a
#: touched file had been supplied earlier.  A tracker miss is not a zero: an
#: evicted conversation, a rewritten history and a conversation the gateway has
#: only just met all produce ``context_files_touched == 0``, and only the token
#: says that the zero is not a measurement.  A miss is also sticky: the request
#: that notices the gap marks the whole lineage discontinuous, so each of its
#: descendants keeps reporting ``tracker_miss`` instead of resuming a claim to
#: know what was supplied before a prefix nothing remembered.
CORRELATION_MEASURED: Final = "measured"
CORRELATION_NO_PRIOR_CONTEXT: Final = "no_prior_context"
CORRELATION_TRACKER_MISS: Final = "tracker_miss"
CORRELATION_UNAVAILABLE: Final = "unavailable"

#: The conversation identity a first request looks up.  No transcript can
#: produce it, because :func:`transcript_fingerprint` returns a hex digest for
#: any message list it is given - including an empty one, which hashes to its own
#: digest and so cannot collide with the sentinel.
NEW_CONVERSATION_KEY: Final = "__new__"

#: Unique files held per set within one stored state.  A real session reads tens of
#: files; a client that sends ten thousand envelopes must not be able to grow the
#: tracker past this.  Overflow is counted, not hidden.
MAX_UNIQUE_FILES_PER_STATE: Final = 256

#: Transcript-prefix states held by a tracker built without a configured size -
#: entries, not conversations, because one conversation stores a state per request
#: that answered an earlier prefix.  The gateway passes its
#: ``context_delta_cache_size`` instead, so the two caches cannot drift apart in
#: size; this bound is what keeps a standalone tracker bounded all the same.
MAX_ACTIVITY_STATES: Final = 256

#: How much of each message takes part in the fingerprint.  A transcript that
#: repeats a tool result verbatim beyond this window still fingerprints the same,
#: and a client cannot make the gateway hash an unbounded body per request.
MAX_FINGERPRINT_CHARS: Final = 2048

#: How many of the newest messages a fingerprint reads.  Work per request stays
#: bounded however long a client's transcript is; the total message count is folded
#: into the digest as well, so a history that slides older messages out cannot
#: fingerprint the same as the history it replaced.
MAX_FINGERPRINT_MESSAGES: Final = 256

#: The three outcomes one file can have for one kind of operation, ranked so that a
#: confirmation outranks a known failure and a known failure outranks a result the
#: parser could not read.  :func:`_file_outcomes` takes the maximum over every
#: envelope in the transcript, which is what makes a failure followed by a success -
#: or a success followed by a failure - land in the same counter either way.
_UNREPORTED: Final = 0
_FAILED: Final = 1
_CONFIRMED: Final = 2

#: Below every rank, so the first outcome seen for a file always takes.
_BELOW_ANY: Final = -1

#: Where each closed outcome token from ``packages.pipeline.cline_activity`` ranks.
#: ``OUTCOME_NOT_APPLICABLE`` is the name an envelope that reads no result carries,
#: and an unknown token means the client said something the grammar does not cover;
#: neither is a failure and neither is a confirmation.
_OUTCOME_RANK: Mapping[str, int] = MappingProxyType(
    {
        OUTCOME_CONFIRMED: _CONFIRMED,
        OUTCOME_NOT_MODIFIED: _FAILED,
        OUTCOME_FAILED: _FAILED,
        OUTCOME_UNKNOWN: _UNREPORTED,
        OUTCOME_NOT_APPLICABLE: _UNREPORTED,
    }
)


#: The activity section as a record states it when nothing was measured.  This is
#: the single source of truth for the schema: the stage, the gateway mapping and
#: the session record all start here, so no caller can invent a field and none can
#: guess a default.  ``STATE_UNAVAILABLE`` is the inert state because an inert
#: section describes a request whose transcript was never read, and
#: ``CORRELATION_UNAVAILABLE`` accompanies it for the same reason.
INERT_FILE_ACTIVITY: Final[Mapping[str, Any]] = {
    "state": STATE_UNAVAILABLE,
    "correlation": CORRELATION_UNAVAILABLE,
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

#: The states a record may carry, as a tuple so a caller can test against it
#: without naming the four constants one by one.
FILE_ACTIVITY_STATES: Final = (
    STATE_MEASURED,
    STATE_NONE,
    STATE_PARTIAL,
    STATE_UNAVAILABLE,
)

#: The correlation states a record may carry.
FILE_ACTIVITY_CORRELATION_STATES: Final = (
    CORRELATION_MEASURED,
    CORRELATION_NO_PRIOR_CONTEXT,
    CORRELATION_TRACKER_MISS,
    CORRELATION_UNAVAILABLE,
)


def sanitize_file_activity(value: object) -> dict[str, int | str]:
    """Coerce anything read back from a boundary into the recorded shape.

    A gateway hands the counts across the pipeline boundary as a plain dict and then
    writes them to disk, and it must be able to do that without trusting what it
    finds.  A value that is not a mapping, a counter that is not a non-negative
    integer, and a state token outside :data:`FILE_ACTIVITY_STATES` or
    :data:`FILE_ACTIVITY_CORRELATION_STATES` each collapse to the inert record: a
    half-formed activity section reads worse than none at all, because a missing
    field and a zero are different claims.

    Args:
        value: The object to coerce, normally a :meth:`FileActivityCounts.as_dict`.

    Returns:
        Every key of :data:`INERT_FILE_ACTIVITY` at its contracted value, in the
        order the schema documents them, and nothing else - never a path.
    """
    source = value if isinstance(value, dict) else {}
    clean: dict[str, int] = {}
    for key, inert in INERT_FILE_ACTIVITY.items():
        if key in ("state", "correlation"):
            continue
        raw = source.get(key, inert)
        clean[key] = (
            raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0 else inert
        )
    tokens: dict[str, str] = {}
    for key, known in (
        ("state", FILE_ACTIVITY_STATES),
        ("correlation", FILE_ACTIVITY_CORRELATION_STATES),
    ):
        value_in = source.get(key, "")
        tokens[key] = (
            value_in
            if isinstance(value_in, str) and value_in in known
            else INERT_FILE_ACTIVITY[key]
        )
    return {**tokens, **clean}


@dataclass(frozen=True, slots=True)
class FileActivityCounts:
    """What the current transcript says, plus the one number that needs memory.

    Every field is an integer or a state token, every file count is a count of
    *unique normalized files* rather than of events, and every total except the
    correlation pair is recomputed from the transcript of the request being
    answered.  Sending the same transcript twice therefore returns the same
    dictionary twice; nothing here accumulates per request.

    Attributes:
        state: ``"measured"`` when the transcript held envelopes and a bound kept
            none of them out, ``"partial"`` when a bound kept some out - which
            makes every total a floor rather than a count - ``"none"`` when the
            transcript showed the gateway nothing to recognize, which is what a
            client that does not send Cline envelopes reports, and
            ``"unavailable"`` when the measurement could not run at all.
        correlation: Whether the correlation pair below is a measurement.
            ``"measured"`` when this conversation's earlier requests are
            remembered; ``"no_prior_context"`` when they are remembered and none
            of them supplied a file, so the zero is a real answer;
            ``"tracker_miss"`` when an earlier request existed that this tracker
            cannot reconstruct - eviction, a restart, or a history the client or
            the gateway rewrote - and ``"unavailable"`` when the measurement did
            not run.  The two correlation counters are reported as zero under the
            last two tokens, so a lost history never reads as a confident zero
            correlation.  A miss is sticky: once a conversation's lineage has a
            gap in it, every later request in that conversation reports the miss,
            because what was supplied before the gap stays unknown forever.
        files_read: Unique files whose read result reported a successful read.
            A read whose result begins with a recognized failure is in
            ``reads_failed`` instead, and one that reported nothing the gateway
            can read is in ``reads_unknown``.
        files_modified: Unique files whose modification result reported that the
            write landed.  A file modified once and then failed on is still here:
            the outcome is decided per file by precedence, not by whichever
            envelope arrived first.
        files_touched: The union of the two above, so a file read and then edited
            counts once here and once in each of them.
        read_attempts: Unique files a read header named, whatever the result said.
            ``files_read + reads_failed + reads_unknown`` equals this.
        reads_failed: Files read-attempted whose every result said the read failed.
        reads_unknown: Files read-attempted whose results said nothing the gateway
            could classify - including a result body the history cap truncated away.
        modification_attempts: Unique files a modification header named, whatever
            the result said.  ``files_modified + modifications_not_modified +
            modifications_unknown`` equals this.
        modifications_not_modified: Files whose modification was attempted and
            whose results said nothing was written, with no later result saying a
            write landed for that file.
        modifications_unknown: Files whose modification was attempted and whose
            results the parser could not classify.  A client that words its
            results differently lands here rather than in either claim.
        context_files_touched: Successfully touched files this conversation had
            already been supplied as repository context on an *earlier* request.
        touched_without_context: The rest of the touched set, reported as
            ``files_touched`` minus ``context_files_touched`` so the two partition
            it instead of double-counting it.
        changed_files_touched: Touched files the cached working-tree signal reports
            as modified too.  Zero whenever the signal is off or unavailable.
        paths_rejected: File-naming envelopes in the retained transcript window
            whose target the repository refused - outside it, malformed, or
            unresolvable.  One per envelope, not one per distinct refusal shape:
            counting shapes would understate a conversation that hit the same wall
            fifty times, and counting paths is impossible without keeping one.
        other_events: Recognized envelopes in that window that name no file -
            ``search_files``, ``list_files``, ``execute_command`` - counted once
            each.
        events_beyond_bound: Recognized envelopes a bound kept out of this
            request's window, plus files a per-state bound would not hold.
            It is what separates "this session touched nothing" from "this session
            was not counted".
    """

    state: str
    correlation: str
    files_read: int
    files_modified: int
    files_touched: int
    read_attempts: int
    reads_failed: int
    reads_unknown: int
    modification_attempts: int
    modifications_not_modified: int
    modifications_unknown: int
    context_files_touched: int
    touched_without_context: int
    changed_files_touched: int
    paths_rejected: int
    other_events: int
    events_beyond_bound: int

    def as_dict(self) -> dict[str, Any]:
        """Return the section a session record carries.

        Returns:
            The fields exactly as ``INERT_FILE_ACTIVITY`` orders them, so every
            request writes a record with the same shape.
        """
        return {key: getattr(self, key) for key in INERT_FILE_ACTIVITY}


class _Transcript:
    """The file operations one transcript reports, and nothing else.

    A request's whole conversation reduces to this one object, and every activity
    total in a record is a property of it.  It is built by a single pass over the
    events, so re-reading a re-sent transcript rebuilds an equal object and moves no
    counter: replay cannot inflate a total that is derived here rather than
    accumulated somewhere else.

    Attributes:
        reads_attempted: Files a read header named.
        reads_confirmed: Files with at least one read result that reported success.
        reads_failed: Files read-attempted with a known failure and no success.
        reads_unknown: Files read-attempted with no result the parser could read.
        modifications_attempted: Files a modification header named.
        modifications_confirmed: Files with at least one result that reported the
            write landed - which is what ``files_modified`` counts.
        modifications_failed: Files with a known failure or no-change result and no
            confirmation anywhere in the transcript.
        modifications_unknown: Files modification was attempted on with neither.
        succeeded: How many successful operations each file appears in, so a later
            request can tell an operation it has already examined from a new one.
        rejection_events: How many file-naming envelopes in this window named a
            target the repository refused.  Envelopes, not refusal shapes: the
            totals are rebuilt from the transcript every request, so a count of
            them can be a count of the events themselves, and no refused text needs
            to be remembered to produce one.
        other_envelopes: How many recognized envelopes that name no file -
            ``search_files``, ``list_files``, ``execute_command`` - this window
            holds.  Again events rather than the distinct tools among them, which
            is what makes the number comparable to the others here.
        beyond_bound: Envelopes a bound left out of this transcript's window.
    """

    __slots__ = (
        "beyond_bound",
        "modifications_attempted",
        "modifications_confirmed",
        "modifications_failed",
        "modifications_unknown",
        "other_envelopes",
        "reads_attempted",
        "reads_confirmed",
        "reads_failed",
        "reads_unknown",
        "recognized",
        "rejection_events",
        "succeeded",
    )

    def __init__(self, events: Sequence[ActivityEvent], beyond_bound: int) -> None:
        """Reduce one request's events to the files they name and what they did.

        Args:
            events: The request's normalized events, in message order.  Order does
                not matter: each file's outcome is decided by precedence, so a
                failure followed by a success and a success followed by a failure
                both come out confirmed.
            beyond_bound: Recognized envelopes a bound kept out of ``events``.
        """
        rank = _file_outcomes(events)
        succeeded: dict[str, int] = {}
        for event in events:
            if event.file and event.outcome == OUTCOME_CONFIRMED:
                succeeded[event.file] = succeeded.get(event.file, 0) + 1
        self.succeeded = succeeded
        self.reads_attempted, self.reads_confirmed, self.reads_failed, self.reads_unknown = (
            _partition(rank, ACTIVITY_READ)
        )
        (
            self.modifications_attempted,
            self.modifications_confirmed,
            self.modifications_failed,
            self.modifications_unknown,
        ) = _partition(rank, ACTIVITY_MODIFIED)
        self.rejection_events = sum(1 for event in events if event.rejection)
        self.other_envelopes = sum(
            1
            for event in events
            if not event.file and not event.rejection and event.activity == ACTIVITY_NONE
        )
        self.beyond_bound = max(beyond_bound, 0)
        self.recognized = bool(events)

    @property
    def touched(self) -> frozenset[str]:
        """The files this transcript reports being successfully used.

        Returns:
            The union of the confirmed reads and the confirmed modifications.  A
            failed or unread operation is in neither, so it cannot reach
            ``files_touched`` or either correlation counter.
        """
        return frozenset(self.reads_confirmed) | frozenset(self.modifications_confirmed)

    def new_operations(self, examined: Mapping[str, int]) -> tuple[tuple[str, int], ...]:
        """Return the successful operations this transcript adds to ``examined``.

        Args:
            examined: How many successful operations per file the tracker already
                examined for this conversation.  An empty mapping - a conversation
                nothing has been remembered for - makes every operation in the
                transcript new, which is the honest reading: this is the first time
                the gateway has seen this history.

        Returns:
            ``(file, count)`` pairs for the files whose successful operation count
            here exceeds what was already examined.  A replayed transcript returns
            nothing, because its counts are the counts already remembered.
        """
        return tuple(
            (file, count) for file, count in self.succeeded.items() if count > examined.get(file, 0)
        )


class _ConversationActivity:
    """What one conversation's earlier requests remembered.

    This holds no counters at all.  Every number a record reports comes from the
    transcript being answered; what lives here exists only to say what the gateway
    had already shown this conversation, and which of the operations in front of it
    the tracker has already examined.

    Attributes:
        supplied: Files supplied by requests already answered.  This request's own
            supplied files join it *after* correlation, which is what keeps a file
            introduced and reported touched on one request from reading as a
            context hit.
        operations: How many successful operations on each file the tracker has
            already examined.  A transcript whose counts match these numbers is
            history being re-sent, so it is new nothing to correlate; a file with
            more operations in hand than recorded here did something this
            conversation has not been shown before.
        credited: Files already credited as supplied-then-touched.  Carried forward
            so a later request reports the same correlation the one that earned it
            reported, and a replayed transcript cannot move it.
        lineage_complete: Whether every request of this conversation's remembered
            lineage was seen.  ``False`` once any request in the chain arrived on a
            prefix this tracker could not find - an eviction, a restart, a rewritten
            history - which means the files supplied before that gap are permanently
            unknown and stay unknown for every descendant of this state.
    """

    __slots__ = ("credited", "lineage_complete", "operations", "supplied")

    def __init__(self) -> None:
        """Start an empty, unbroken conversation state."""
        self.supplied: set[str] = set()
        self.operations: dict[str, int] = {}
        self.credited: set[str] = set()
        self.lineage_complete = True

    def copy(self) -> "_ConversationActivity":
        """Return an independent copy of this state.

        Returns:
            A state with the same contents in fresh containers, so recording a
            request never mutates the object another conversation is still holding
            - which is what keeps a shared bucket from bleeding into a different
            conversation.  The continuity flag comes along, because a descendant of
            a broken lineage is as blind to what preceded the gap as the request
            that found it.
        """
        clone = _ConversationActivity()
        clone.supplied = set(self.supplied)
        clone.operations = dict(self.operations)
        clone.credited = set(self.credited)
        clone.lineage_complete = self.lineage_complete
        return clone

    def correlate(self, seen: "_Transcript", limit: int) -> int:
        """Credit the files in ``seen`` that this conversation was shown earlier.

        Args:
            seen: The transcript being answered, already reduced to its file
                operations.  Only the operations it holds *now* are considered;
                nothing here reconsiders an operation the tracker examined on an
                earlier request, which is the retroactive attribution this exists
                to prevent.
            limit: The largest ``credited`` and ``operations`` may become.

        Returns:
            ``1`` for each file a bound refused to remember, so correlation the
            tracker could not hold is reported as bounded-away rather than as a
            zero.
        """
        dropped = 0
        for file, count in seen.new_operations(self.operations):
            if file in self.supplied:
                dropped += _add(self.credited, file, limit)
            if file in self.operations or len(self.operations) < limit:
                self.operations[file] = count
            else:
                dropped += 1
        return dropped

    def counts(
        self, seen: _Transcript, correlation: str, changed: frozenset[str]
    ) -> FileActivityCounts:
        """Return the count-only view of this transcript and this conversation.

        Args:
            seen: The transcript's own file operations.
            correlation: The correlation availability token, decided by the caller
                because it depends on whether a prior state was found at all.  A
                confident token is corrected to ``tracker_miss`` here when this
                state's own lineage is discontinuous: a partition of what was
                supplied before a gap nothing remembered is not a measurement, and
                no caller gets to claim one by forgetting to ask.
            changed: The files the cached working-tree signal reports as modified.

        Returns:
            A :class:`FileActivityCounts` whose activity totals depend on nothing
            but ``seen``, and whose correlation pair depends on ``seen`` and this
            state.
        """
        touched = seen.touched
        total = len(touched)
        beyond = seen.beyond_bound
        if not self.lineage_complete and correlation in (
            CORRELATION_MEASURED,
            CORRELATION_NO_PRIOR_CONTEXT,
        ):
            correlation = CORRELATION_TRACKER_MISS
        if correlation == CORRELATION_MEASURED:
            credited = len(self.credited & touched)
            without = total - credited
        elif correlation == CORRELATION_NO_PRIOR_CONTEXT:
            # Nothing was supplied by an earlier request, so nothing that was
            # touched had been.  That is a real answer, and the token says so.
            credited, without = 0, total
        else:
            # A conversation this tracker cannot reconstruct knows neither half of
            # the partition, so neither is claimed; a measurement that never ran
            # claims nothing at all.
            credited = without = 0
        if seen.recognized:
            state = STATE_PARTIAL if beyond else STATE_MEASURED
        else:
            state = STATE_PARTIAL if beyond else STATE_NONE
        return FileActivityCounts(
            state=state,
            correlation=correlation,
            files_read=len(seen.reads_confirmed),
            files_modified=len(seen.modifications_confirmed),
            files_touched=total,
            read_attempts=len(seen.reads_attempted),
            reads_failed=len(seen.reads_failed),
            reads_unknown=len(seen.reads_unknown),
            modification_attempts=len(seen.modifications_attempted),
            modifications_not_modified=len(seen.modifications_failed),
            modifications_unknown=len(seen.modifications_unknown),
            context_files_touched=credited,
            touched_without_context=without,
            changed_files_touched=len(touched & changed),
            paths_rejected=seen.rejection_events,
            other_events=seen.other_envelopes,
            events_beyond_bound=beyond,
        )


class FileActivityTracker:
    """Bounded store for the correlation half of file-activity state.

    The tracker holds what a transcript cannot tell you: which files earlier
    requests of this conversation had put in front of the model, and which of the
    operations in the transcript it had already examined.  It holds no counters -
    the totals are recomputed from the transcript by :class:`_Transcript` on every
    request - and nothing else: no paths from a client, no symbols, no envelope
    text.

    An entry is a *transcript-prefix state*, not a conversation.  Each request
    stores the state it derived under the fingerprint of the transcript it saw, so
    a conversation that has run five requests occupies five entries and shares one
    lineage between them; that is what lets a retry or a branch of an older prefix
    find the state that was current when it was sent.  A long conversation
    therefore consumes the bound faster than the number of conversations suggests,
    and the request that arrives after its own prefix has been evicted reports the
    gap - and every request descended from it keeps reporting it.

    Attributes:
        maxsize: Transcript-prefix states held before the least recently used one
            is dropped.
        max_unique_files: Files held per set within one stored state.
    """

    __slots__ = ("_cache", "max_unique_files", "maxsize")

    def __init__(
        self,
        maxsize: int = MAX_ACTIVITY_STATES,
        max_unique_files: int = MAX_UNIQUE_FILES_PER_STATE,
    ) -> None:
        """Create a bounded tracker.

        Args:
            maxsize: Transcript-prefix states to retain, normally the gateway's
                ``context_delta_cache_size`` so the two client-history caches
                cannot drift apart in size.  One conversation needs several of them,
                one per request that answered an earlier prefix.  A non-positive
                value is read as one.
            max_unique_files: Files retained per set within a stored state.  A
                non-positive value is read as one.
        """
        self.maxsize = maxsize if maxsize > 0 else 1
        self.max_unique_files = max_unique_files if max_unique_files > 0 else 1
        self._cache: OrderedDict[str, _ConversationActivity] = OrderedDict()

    def observe(
        self,
        lookup_key: str,
        store_key: str,
        events: Sequence[ActivityEvent],
        beyond_bound: int,
        supplied_files: Iterable[str] | None = None,
        changed_files: Iterable[str] | None = None,
    ) -> FileActivityCounts:
        """Measure one request's transcript and return its counts.

        Nothing here is cumulative.  Sending the same transcript twice recomputes
        the same totals from the same events and returns the same dictionary, which
        is the property a re-sending client needs: a Cline conversation endpoint
        re-submits the whole prior conversation on every request, so a counter that
        moved on ``observe()`` was measuring how many times the history had been
        re-read.

        Args:
            lookup_key: The conversation identity of the transcript *before* this
                request's own turn - what the correlation compares against.
                :data:`NEW_CONVERSATION_KEY` says the client had no earlier turn at
                all, which is a confident ``no_prior_context`` rather than a miss.
            store_key: The identity including this turn, under which the new state
                is saved for the next one.
            events: The transcript's normalized events, in message order.  This is
                the whole re-sent conversation, and it is the only source of the
                activity totals.
            beyond_bound: Events of this transcript that a parse bound left out.
            supplied_files: Normalized files the context package this request sends,
                which join the remembered set *after* the correlations are computed.
            changed_files: Normalized files the cached working-tree signal reports as
                modified.  ``None`` or empty - off, clean, or unavailable - can only
                ever produce a zero changed-signal correlation.

        Returns:
            The :class:`FileActivityCounts` of this transcript and this conversation.
        """
        prior = self._cache.get(lookup_key)
        state = prior.copy() if prior is not None else _ConversationActivity()
        seen = _Transcript(events, beyond_bound)

        # A miss on a transcript that shows earlier turns is a conversation the
        # tracker lost - eviction, a restart, a history someone rewrote - and its
        # correlation would otherwise read as a confident zero.  The mark belongs to
        # the state, not to this request: it is copied forward into what is stored
        # under ``store_key``, so the descendant of a broken lineage keeps reporting
        # the gap instead of resuming a measurement of the half it can see.
        if prior is None and lookup_key != NEW_CONVERSATION_KEY:
            state.lineage_complete = False
        if not state.lineage_complete:
            correlation = CORRELATION_TRACKER_MISS
        elif not state.supplied:
            correlation = CORRELATION_NO_PRIOR_CONTEXT
        else:
            correlation = CORRELATION_MEASURED

        # Correlation first, and only over operations this conversation has not
        # already examined: this request's own supplied files may not be in yet.
        dropped = state.correlate(seen, self.max_unique_files)
        dropped += _merge(state.supplied, supplied_files or (), self.max_unique_files)
        seen.beyond_bound += dropped

        counts = state.counts(seen, correlation, frozenset(changed_files or ()))
        self._cache[store_key] = state
        self._cache.move_to_end(store_key)
        while len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)
        return counts

    def snapshot(self, lookup_key: str) -> FileActivityCounts:
        """Return what one stored prefix remembers, having measured no transcript.

        Args:
            lookup_key: The conversation identity to look up.

        Returns:
            A record whose activity totals are all zero - no transcript was read, so
            nothing about the client's file operations is being claimed - and whose
            ``correlation`` says whether this tracker can reconstruct the
            conversation at all.  A miss is reported as a tracker miss, never as a
            zero that looks like a measurement, and so is a found state whose own
            lineage carries a gap.
        """
        state = self._cache.get(lookup_key)
        if state is not None:
            self._cache.move_to_end(lookup_key)
            correlation = (
                CORRELATION_MEASURED if state.lineage_complete else CORRELATION_TRACKER_MISS
            )
            return state.counts(_Transcript((), 0), correlation, frozenset())
        return _ConversationActivity().counts(
            _Transcript((), 0), CORRELATION_TRACKER_MISS, frozenset()
        )

    def state_count(self) -> int:
        """Return how many transcript-prefix states the tracker currently holds.

        Returns:
            The live entry count, which tests use to confirm the LRU bound.  It is
            not a count of conversations: one conversation contributes an entry per
            request that answered one of its earlier prefixes.
        """
        return len(self._cache)


def transcript_fingerprints(messages: object) -> tuple[str, str]:
    """Return the ``(lookup_key, store_key)`` identities of one transcript.

    File activity keeps its own conversation identity rather than borrowing
    ``packages.context.delta``'s.  The delta key hashes user messages only, so two
    conversations whose client text happens to match while the agent said different
    things look like one conversation; here every message contributes its role, the
    head of its text and its length, assistant turns included.

    The pair chains the way the delta pair does.  ``store_key`` fingerprints the
    transcript this request saw.  ``lookup_key`` fingerprints everything *before*
    the newest assistant turn - the transcript of the request that produced that
    turn, which is the previous request in this conversation - and a transcript with
    no assistant turn at all has no earlier request to look up, so it reads
    :data:`NEW_CONVERSATION_KEY`, a sentinel no message list can hash to.

    Args:
        messages: The request's ``messages`` list.  Anything that is not a list is
            read as an empty transcript, which is how the parser reads it too.

    Returns:
        The ``(lookup_key, store_key)`` pair.  Both are digests or the sentinel;
        neither can be turned back into message text, and neither is ever reported.

    Limitations, stated rather than hidden: the identity is content, not a
    conversation ID.  Two independent conversations with byte-identical transcripts
    are indistinguishable here and share correlation state, and only a client that
    supplied its own conversation identifier could tell them apart - which a
    chat-completions request does not.  And because a fingerprint reads the newest
    :data:`MAX_FINGERPRINT_MESSAGES` messages plus the message count, a client that
    rewrote history *inside* that window is detected only if the rewrite changed a
    role, a message head, or a length.
    """
    roles: list[str] = []
    texts: list[str] = []
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            roles.append(str(message.get("role", "")))
            texts.append(content_to_text(message.get("content", "")))
    boundary = len(roles)
    for index in range(len(roles) - 1, -1, -1):
        # The newest assistant turn is the reply the previous request produced;
        # everything from it onward is new here.
        if roles[index] == "assistant":
            boundary = index
            break
    store_key = _fingerprint(roles, texts, len(roles))
    lookup_key = (
        _fingerprint(roles, texts, boundary) if boundary < len(roles) else NEW_CONVERSATION_KEY
    )
    return lookup_key, store_key


def _fingerprint(roles: Sequence[str], texts: Sequence[str], stop: int) -> str:
    """Return the digest of the transcript's messages up to ``stop``.

    Args:
        roles: The role of every message, in order.
        texts: The flattened text of every message, index-matched to ``roles``.
        stop: One past the last message to include.

    Returns:
        A lowercase hex digest over the message count and the newest
        :data:`MAX_FINGERPRINT_MESSAGES` roles and text heads.  An empty range
        digests to a value that no earlier non-empty transcript can produce, and
        never to :data:`NEW_CONVERSATION_KEY`.
    """
    digest = hashlib.sha256()
    digest.update(f"file-activity/v1/{stop}".encode())
    for index in range(max(0, stop - MAX_FINGERPRINT_MESSAGES), stop):
        text = texts[index]
        digest.update(b"\0")
        digest.update(roles[index].encode())
        digest.update(b"\0")
        digest.update(text[:MAX_FINGERPRINT_CHARS].encode("utf-8", "replace"))
        digest.update(f"\0{len(text)}".encode())
    return digest.hexdigest()


def _file_outcomes(events: Sequence[ActivityEvent]) -> dict[tuple[str, str], int]:
    """Return the strongest outcome each file saw for each kind of operation.

    Args:
        events: The transcript's events, in any order.  Order cannot matter: a
            confirmation anywhere in the transcript outranks a failure anywhere
            else, which is what makes a failure followed by a success - and a
            success followed by a failure - both read as confirmed.

    Returns:
        ``{(activity, file): best outcome rank}`` for every event that named a
        repository file.  An event whose target was refused is absent, because
        there is no file in the repository to attribute an outcome to.
    """
    ranks: dict[tuple[str, str], int] = {}
    for event in events:
        if not event.file:
            continue
        key = (event.activity, event.file)
        rank = _OUTCOME_RANK.get(event.outcome, _UNREPORTED)
        if rank > ranks.get(key, _BELOW_ANY):
            ranks[key] = rank
    return ranks


def _partition(
    outcomes: Mapping[tuple[str, str], int], activity: str
) -> tuple[set[str], set[str], set[str], set[str]]:
    """Split the files of one activity into the four counters that describe it.

    Args:
        outcomes: The per-file outcome ranks from :func:`_file_outcomes`.
        activity: :data:`~packages.pipeline.user_messages.ACTIVITY_READ` or
            ``ACTIVITY_MODIFIED``, deciding which half of the split to take.

    Returns:
        ``(attempted, confirmed, failed, unknown)`` - a partition of the files this
        activity named, so the last three sum to the first and a file appears in
        exactly one of them.  Precedence decides which: confirmation beats failure,
        failure beats an unread result.
    """
    confirmed: set[str] = set()
    failed: set[str] = set()
    unreported: set[str] = set()
    for (kind, file), outcome in outcomes.items():
        if kind != activity:
            continue
        if outcome == _CONFIRMED:
            confirmed.add(file)
        elif outcome == _FAILED:
            failed.add(file)
        else:
            unreported.add(file)
    failed -= confirmed
    unreported -= confirmed | failed
    return confirmed | failed | unreported, confirmed, failed, unreported


def _add(target: set[str], file: str, limit: int) -> int:
    """Add one file to a bounded set.

    Args:
        target: The set to grow.
        file: The normalized identity to add; empty is ignored.
        limit: The largest the set may become.

    Returns:
        ``1`` when the bound refused the file, else ``0`` - so a file that could not
        be remembered is reported as bounded-away work instead of disappearing.
    """
    if not file or file in target:
        return 0
    if len(target) >= limit:
        return 1
    target.add(file)
    return 0


def _merge(target: set[str], files: Iterable[str], limit: int) -> int:
    """Add every file of an iterable to a bounded set.

    Args:
        target: The set to grow.
        files: Normalized file identities, in the caller's order.
        limit: The largest the set may become.

    Returns:
        How many files the bound refused to hold.
    """
    dropped = 0
    for file in files:
        dropped += _add(target, file, limit)
    return dropped


def module_files_of(module_keys: object) -> tuple[str, ...]:
    """Return the normalized file identities that index module keys name.

    The index and the rest of the repository name the same file differently -
    ``packages/context/delta`` to the index, ``packages/context/delta.py`` to Git,
    the filesystem, and a Cline envelope - and ``module_key_to_path`` is the only
    place allowed to cross that boundary.  This function adds the second half: the
    same case-and-separator identity the parser gives an envelope target, without
    which the two sides of a correlation would never compare equal.

    Args:
        module_keys: An iterable of index module keys, or anything that is not a
            sequence of strings - a ``frozenset``, a ``tuple``, a list, or ``None``.
            Non-strings and empty keys are skipped, not rejected.

    Returns:
        Repository-relative normalized paths in iteration order, each exactly once.
        Order from a set is unspecified, so callers that report a sequence should
        sort the keys first; callers that only test membership will not notice.
    """
    if module_keys is None or isinstance(module_keys, str):
        return ()
    files: list[str] = []
    seen: set[str] = set()
    try:
        candidates = list(cast("Iterable[object]", module_keys))
    except TypeError:
        return ()
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        path = module_key_to_path(candidate)
        identity = file_identity(path) if path else ""
        if identity and identity not in seen:
            seen.add(identity)
            files.append(identity)
    return tuple(files)


def supplied_module_keys(package: object) -> tuple[str, ...]:
    """Return the index module keys one context package carries.

    This is the trusted side of the C1 correlation: the repository files the
    gateway itself is putting in front of the model on this turn.  The values come
    from the gateway's own index rather than from a client, so they need no
    containment check - only the identity mapping the parser applies to an envelope
    target, which is what makes the two sets comparable at all.

    A composed :class:`~packages.context.context_package.ContextPackage` names the
    modules it sends in three places, and every one of them holds index module keys
    - repository-relative, forward-slashed, ``.py``-less - never filesystem paths:

    - ``related_modules``, which the composer builds from the primary, the
      supporting symbols and the callers and callees, so it is the package's full
      module set;
    - ``module_descriptions[*].module_path``, the modules it describes;
    - the module element of each ``SymbolContext.location``.

    Reading all three costs nothing and keeps the derivation correct for a package
    assembled by a capability rather than by the composer, which may fill only one
    of them.  Qualified symbol names are deliberately *not* split for a module
    prefix: the module-key boundary inside ``packages/demo/widget.Widget.spin`` is
    a property of the index, not something a string rule can recover.

    Args:
        package: The ``ContextPackage`` a request sends, or ``None`` when the
            context stage assembled nothing.  Attribute access is guarded, because
            this reads an object another package built.

    Returns:
        The module keys in first-seen order, each exactly once.  A package that
        names no module, or a context with no index, yields ``()``.
    """
    if package is None:
        return ()
    ordered: list[str] = []

    def _collect(value: object) -> None:
        if isinstance(value, str) and value and value not in ordered:
            ordered.append(value)

    _collect_strings(package, "related_modules", _collect)
    for description in _attr_sequence(package, "module_descriptions"):
        _collect(getattr(description, "module_path", None))
    _collect_location(getattr(package, "primary_symbol_context", None), _collect)
    for context in _attr_sequence(package, "supporting_symbol_contexts"):
        _collect_location(context, _collect)
    return tuple(ordered)


def supplied_files_of(package: object) -> tuple[str, ...]:
    """Return the normalized file identities one context package supplies.

    :func:`supplied_module_keys` says where the keys come from and why a package's
    module set is the trusted half of the C1 correlation; this adds the one step
    that makes the result comparable with an envelope target.

    Args:
        package: The ``ContextPackage`` a request sends, or ``None``.

    Returns:
        Repository-relative normalized paths in first-seen order, each once.  A
        package that names no module yields ``()``, which the tracker reports as
        "nothing was supplied" - never as a mismatch.
    """
    return module_files_of(supplied_module_keys(package))


def _collect_location(context: object, emit: Any) -> None:
    """Pass the module element of one ``SymbolContext.location`` to ``emit``.

    Args:
        context: A ``SymbolContext``, or ``None`` when the package carries no
            source-aware context for that symbol.
        emit: Called once when the location holds a string module.
    """
    location = getattr(context, "location", None)
    if isinstance(location, tuple) and location and isinstance(location[0], str):
        emit(location[0])


def _collect_strings(package: object, attribute: str, emit: Any) -> None:
    """Pass every string of one sequence-valued package attribute to ``emit``.

    Args:
        package: The object to read.
        attribute: The attribute name, which may be absent or of any type.
        emit: Called once per string element, in order.
    """
    for item in _attr_sequence(package, attribute):
        if isinstance(item, str):
            emit(item)


def _attr_sequence(package: object, attribute: str) -> Sequence[Any]:
    """Return one package attribute as a sequence, or empty when it is not one.

    Args:
        package: The object to read.
        attribute: The attribute name.

    Returns:
        The value when it is a real sequence - a string excluded, since iterating a
        module path one character at a time would supply nonsense - else ``()``.
    """
    value = getattr(package, attribute, ())
    if isinstance(value, str) or not isinstance(value, Sequence):
        return ()
    return value
