"""Read Cline tool-result envelopes and normalize the files they name.

Cline reports every tool result back to the model as a user-role message whose
first line is an anchored header naming the tool and its target::

    [read_file for 'apps/gateway/session_log.py'] Result:
    <the result body - never examined here>

This module turns that one header into a bounded, deduplicated, repository-
relative *activity* statement: which file the agent read, and which file it
modified.  It is the parsing half of roadmap item C1; the counting half is
``packages.pipeline.file_activity``.

Grammar accepted
----------------

An envelope is recognized only when, after leading whitespace, the message
begins with ``"[<tool> for "`` where ``<tool>`` is a member of
:data:`packages.pipeline.user_messages.CLINE_FILE_ACTIVITY_TOOLS`, and the header
is then closed within :data:`MAX_ENVELOPE_HEADER_CHARS` by either ``"] Result:"``
(the form Cline sends) or a trailing ``"]"`` (the form left behind when the
gateway's own history cap truncates the body).  The tool table decides the
activity: ``read_file`` reads, ``write_to_file`` and ``replace_in_file`` modify,
and ``search_files``, ``list_files`` and ``execute_command`` are recognized
without naming any file - their target is a search pattern, a directory or a
command line, and the files inside their output belong to the result body.

Anything else is not an envelope: no header, an unknown tool name, a header that
never closes, or an envelope that does not start the message.  A header found
*inside* a result body - which is exactly what a prompt-injected file, commit
message or model answer can produce - is never seen, because nothing after the
terminator is examined at all.

Result status
-------------

A header says only that an operation was *attempted*.  The same
``[replace_in_file for x.py]`` arrives whether or not anything was written, and
the same ``[read_file for x.py]`` arrives when the read failed.  So one further,
separate read exists - :data:`MAX_RESULT_HEAD_CHARS` characters of the body that
follows the header's ``Result:`` marker - and it is consulted for nothing except
a status token, on a reader's envelope exactly as on a writer's:

- a writer's head is matched against two closed tables and classified
  ``"confirmed"``, ``"not_modified"`` or ``"unknown"``;
- a reader's head has no success grammar to match, because the body of a
  successful read is the file's own text.  The rule is therefore inverted and
  anchored: a head that *begins* with an entry of the closed read-failure table
  is ``"failed"``, a head that carries any other text is ``"confirmed"``, and a
  head with no text at all is ``"unknown"``.

An envelope whose tool names no file stays ``"not_applicable"``, and any body
with no marker inside the window is ``"unknown"``.  The head is never searched
for a path or a tool name, no marker's own text is ever returned, and the tables
are client-authored prose that a different version of Cline can reword: an
unknown status is the honest answer, and the tracker keeps attempted and
successful counts apart rather than guessing.  The tables hold only the wording
this repository's own sanitized envelope samples show; an unread result that
fails for a reason no sample demonstrates lands in ``"unknown"``, which is not
counted as a read.

Security boundary
-----------------

Envelope text is untrusted input, and path text doubly so.

- Only the anchored header is parsed.  No result body, source text, or command
  output is scanned for filenames, ever.  The one exception is the closed status
  read above, which can produce a token and no string.
- Every target is normalized before it is counted: slashes, redundant ``.``
  segments, relative spellings, absolute in-repository spellings, Windows drive
  spelling and case, and Unicode composition.
- Relative targets are resolved against the configured repository root, and both
  sides of the comparison are resolved with ``realpath`` first, so a symlink or a
  junction cannot smuggle a path out of the repository.
- Rejected: empty targets, NULs, control characters, over-long paths, malformed
  quoting, drive and UNC prefixes, NTFS alternate data streams, traversal that
  leaves the repository, and anything that resolves outside it.
- Modification targets may not exist yet, so containment is checked with
  ``strict=False``: nothing is created, opened, or tested for existence.  The only
  filesystem call is read-only path resolution.
- A rejection yields a token and a counter.  No path, target text or tool string
  is ever raised, logged, or returned in a value a caller could persist.  The one
  place a resolved target is kept is a local inside
  :func:`resolve_file_activity_events`, memoizing that request's own envelopes; it
  is not reachable from another request and does not outlive this one.

Public API
----------

.. code-block:: python

    from packages.pipeline.cline_activity import (
        RepositoryPathNormalizer,
        resolve_file_activity_events,
    )

    normalizer = RepositoryPathNormalizer(repo_root)
    batch = resolve_file_activity_events(request["messages"], normalizer)
    batch.events[0].activity  # "read" | "modified" | "none"
    batch.events[0].file      # "apps/gateway/session_log.py" - never persisted
    batch.events[0].outcome   # "confirmed" | "not_modified" | "unknown" | ...
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from packages.context.content import content_to_text
from packages.pipeline.user_messages import (
    ACTIVITY_MODIFIED,
    ACTIVITY_NONE,
    ACTIVITY_READ,
    CLINE_ENVELOPE_TOOLS,
    cline_envelope_tool,
)

__all__ = [
    "MAX_ENVELOPES_PER_REQUEST",
    "MAX_ENVELOPE_HEADER_CHARS",
    "MAX_PATH_CHARS",
    "MAX_RESULT_HEAD_CHARS",
    "ACTIVITY_NONE",
    "ACTIVITY_READ",
    "ACTIVITY_MODIFIED",
    "OUTCOME_CONFIRMED",
    "OUTCOME_NOT_MODIFIED",
    "OUTCOME_FAILED",
    "OUTCOME_NOT_APPLICABLE",
    "OUTCOME_UNKNOWN",
    "ActivityEvent",
    "Envelope",
    "RepositoryPathNormalizer",
    "ResolvedEnvelopes",
    "file_identity",
    "parse_envelopes",
    "parse_message_envelope",
    "resolve_file_activity_events",
]

#: How far past the ``"[<tool> for "`` marker the parser looks for the header's
#: terminator.  A Cline header is one short line; a target longer than this is an
#: attempt to make the gateway read a result body as if it were a header.
MAX_ENVELOPE_HEADER_CHARS: Final = 2048

#: Longest normalized target accepted.  Real repository paths are far shorter, and
#: an unbounded string reaching ``realpath`` is unbounded work on the request path.
MAX_PATH_CHARS: Final = 512

#: Recognized envelopes read from one request's messages.  History is
#: client-supplied, so a hostile client must not be able to make the gateway parse
#: or resolve an unbounded number of paths in a single request.  When a transcript
#: holds more than this, the *newest* ones are what is kept: a conversation that
#: has outgrown the bound still reports what it just did, and the envelopes that
#: fall out of the window are counted in :attr:`ResolvedEnvelopes.beyond_bound`
#: rather than silently setting the totals a turn backwards.
MAX_ENVELOPES_PER_REQUEST: Final = 256

#: The marker that closes a Cline envelope header and opens its result body.
#: Everything from here on is model output and is never examined, with the single
#: exception of the bounded status read documented under "Result status".
_ENVELOPE_TAIL: Final = "] Result:"

#: The marker that opens a result body, searched for when the header's tool either
#: reads or writes.  A body with no marker in the window yields ``OUTCOME_UNKNOWN``.
_RESULT_MARKER: Final = "Result:"

#: How far past the ``"Result:"`` marker the status read looks.  Cline states what
#: happened in the first line of a result, so a longer window would mean reading a
#: model-authored body as if the gateway had verified its grammar.
MAX_RESULT_HEAD_CHARS: Final = 200

#: The status a file-naming result reports.  ``OUTCOME_NOT_APPLICABLE`` marks an
#: envelope whose tool names no file, so no status was read at all; these are the
#: only outcome values that may leave this module, and no marker text does.
#: ``OUTCOME_FAILED`` is the reader's half of :data:`OUTCOME_NOT_MODIFIED`: the
#: client said this read did not happen.
OUTCOME_CONFIRMED: Final = "confirmed"
OUTCOME_NOT_MODIFIED: Final = "not_modified"
OUTCOME_FAILED: Final = "failed"
OUTCOME_UNKNOWN: Final = "unknown"
OUTCOME_NOT_APPLICABLE: Final = "not_applicable"

#: Client-authored status prose, matched case-insensitively inside the bounded
#: result head.  Both tables are deliberately short: they hold only what the
#: repository's own sanitized envelope samples show this client says, and anything
#: else is reported as :data:`OUTCOME_UNKNOWN` rather than guessed at.  A marker
#: may not contain a path, a tool name, or anything the tracker could read as a
#: file.
_RESULT_NOT_MODIFIED_MARKERS: Final = (
    "tool execution failed",
    "no changes were made",
)
_RESULT_CONFIRMED_MARKERS: Final = ("successfully saved",)

#: The reader's failure prefixes.  A successful read has no success grammar to
#: match - its result body is the file's own text - so the rule for a reader is
#: inverted and anchored: only a head that *begins* with one of these is treated as
#: a failed read, because a source file is free to contain the same words anywhere
#: in its first lines.  The table holds the one failure wording this repository's
#: sanitized samples show the client emit for any failed tool; a failure worded
#: differently is not recognized and reads as a successful read, which is why the
#: read total is an upper bound on reads and is stated as such wherever it is
#: documented.  Surveyed on this repository's own logged Cline traffic, 315 anchored
#: read results split 31 recognized failures to 284 that were not, and 72 of those 284
#: begin ``[DUPLICATE READ] You have already read ... N times``, a notice whose own text
#: says the content was not sent again.  It is not a failure of the rule above, so it
#: counts as a read; widening the table to cover it would change what ``files_read``
#: means, which is why it is recorded here rather than fixed on a survey.
_READ_FAILURE_PREFIXES: Final = ("the tool execution failed",)

#: The literal that separates a tool name from its target in the header.
_FOR_MARKER: Final = " for "

#: A Windows drive letter introducing an absolute path, after :func:`file_identity`
#: has folded case and slashes.
_DRIVE_PREFIX: Final = re.compile(r"^[a-z]:[\\/]")

#: Why a target was refused.  These tokens are the only description of a rejected
#: path that may leave this module, and none of them names a path: a rejection is
#: counted, never quoted.
REJECT_EMPTY: Final = "empty"
REJECT_QUOTING: Final = "quoting"
REJECT_NUL: Final = "nul"
REJECT_CONTROL: Final = "control"
REJECT_LENGTH: Final = "length"
REJECT_DRIVE: Final = "drive"
REJECT_STREAM: Final = "stream"
REJECT_OUTSIDE: Final = "outside"
REJECT_SELF: Final = "self"
REJECT_ROOT: Final = "root"

#: Control characters that cannot appear in a path the gateway will resolve.  A
#: newline would also be a second header smuggled inside the first.
_CONTROL_CHARS: Final = ("\r", "\n", "\t", "\x0b", "\x0c")


@dataclass(frozen=True, slots=True)
class Envelope:
    """One recognized envelope header, before its target is normalized.

    Attributes:
        tool: The Cline tool name read from the anchored header.
        activity: ``"read"``, ``"modified"``, or ``"none"`` for an envelope that
            names no single file.
        target: The text between the tool name and the header's terminator, with
            one layer of quoting removed.  Untrusted, and never logged or
            persisted.  Empty for a target that is absent or malformed.
        malformed: ``True`` when the header named a file but its quoting could not
            be read.  That is a rejected path event rather than an unrecognized
            envelope, so it must still be countable.
        outcome: The status token read from the bounded result head of a file-naming
            envelope - ``"confirmed"``, ``"not_modified"``, ``"failed"`` or
            ``"unknown"`` - or :data:`OUTCOME_NOT_APPLICABLE` for an envelope that
            names no file.  A closed token that never carries body text out of this
            module.  Whether an operation *happened* is a separate claim from whether
            it was *attempted*, so a caller can count both without reading one as the
            other.
    """

    tool: str
    activity: str
    target: str
    malformed: bool = False
    outcome: str = OUTCOME_NOT_APPLICABLE

    @property
    def names_file(self) -> bool:
        """Whether this envelope claims exactly one file."""
        return self.activity != ACTIVITY_NONE

    @property
    def successful(self) -> bool:
        """Whether this envelope's own result said the operation happened."""
        return self.outcome == OUTCOME_CONFIRMED


def file_identity(text: str) -> str:
    """Return the comparison identity of one repository-relative path.

    This is the lexical half of normalization, and it is idempotent: separators
    become slashes, leading ``./`` segments and a trailing slash are dropped, the
    string is composed with Unicode NFC so two spellings of one name become one
    identity, and the result is folded through :func:`os.path.normcase` -
    lowercase on a case-insensitive filesystem and untouched on a case-sensitive
    one, which is what makes ``Apps/Gateway/x.py`` and ``apps/gateway/x.py`` the
    same file on Windows and different files on Linux.

    Args:
        text: A path in any spelling.  Trusted or untrusted: this function only
            reshapes text and never touches the filesystem.

    Returns:
        The normalized path, or ``""`` for blank input.
    """
    path = unicodedata.normalize("NFC", text.replace("\\", "/").strip())
    while path.startswith("./"):
        path = path[2:]
    path = path.rstrip("/")
    if not path:
        return ""
    return os.path.normcase(path).replace("\\", "/")


class RepositoryPathNormalizer:
    """Turn untrusted path text into a repository-relative file identity.

    Containment is decided by resolving both the configured root and the candidate
    with ``realpath`` before comparing them, so a symlink, a junction, a ``subst``
    drive or an 8.3 short name inside the repository cannot point the gateway at a
    file outside it.  Existence is never required: a modification target may name a
    file that is about to be created, so resolution runs with ``strict=False`` and
    nothing is created, opened, or tested for existence.

    Attributes:
        root_ok: Whether the configured root could be resolved at all.  When it
            could not, every target is rejected as ``"root"``: an unusable
            configuration is stated, not guessed at.
    """

    __slots__ = ("_root", "root_ok")

    def __init__(self, root: Path | str) -> None:
        """Bind the normalizer to one repository root.

        Args:
            root: The configured repository root, as the gateway received it.  Only
                its canonical form is kept; it is never returned.
        """
        self._root = _canonical_root(root)
        self.root_ok = self._root != ""

    def normalize(self, target: str) -> tuple[str, str]:
        """Return the ``(file identity, rejection token)`` pair for one target.

        Exactly one side of the pair is non-empty, and neither ever contains the
        caller's text: the rejection token is one of the ``REJECT_*`` constants.

        Args:
            target: The header's target text.  Untrusted.

        Returns:
            ``(identity, "")`` when the target names a file inside the repository,
            and ``("", token)`` when it does not.
        """
        identity = file_identity(target)
        if not identity:
            return "", REJECT_EMPTY
        if "\x00" in identity:
            return "", REJECT_NUL
        if any(char in identity for char in _CONTROL_CHARS):
            return "", REJECT_CONTROL
        if len(identity) > MAX_PATH_CHARS:
            return "", REJECT_LENGTH
        if ":" in identity and not _DRIVE_PREFIX.match(identity):
            # A colon anywhere other than a leading drive letter is an NTFS
            # alternate data stream, a URL scheme, or a stray fragment.  None of
            # them is ever a file the index holds.
            return "", REJECT_STREAM
        if identity.startswith("//"):
            return "", REJECT_DRIVE  # a UNC share is not this repository
        if not self.root_ok:
            return "", REJECT_ROOT

        # A target that is already an absolute path is not joined onto the root; a
        # Windows drive-absolute target reads as ``c:/...`` once normalized, and
        # treating it as relative would look for ``<root>/c:/...``, which is never
        # the file the envelope meant.
        absolute = identity.startswith("/") or _DRIVE_PREFIX.match(identity) is not None
        candidate = identity if absolute else f"{self._root}/{identity}"
        try:
            resolved = os.path.realpath(candidate, strict=False)
        except (OSError, ValueError):
            return "", REJECT_OUTSIDE
        try:
            relative = os.path.relpath(resolved, self._root)
        except ValueError:
            return "", REJECT_DRIVE  # different drives - no shared mapping exists
        relative = file_identity(relative)
        if relative == ".":
            return "", REJECT_SELF  # the repository root itself is not a file
        if not relative or relative.startswith("../"):
            return "", REJECT_OUTSIDE
        return relative, ""


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    """One recognized envelope reduced to what the tracker may record.

    Attributes:
        tool: The Cline tool name, kept only so a caller can tell one writer from
            another.  Never logged and never persisted.
        activity: ``"read"``, ``"modified"``, or ``"none"`` for an envelope that
            names no file.
        file: The normalized identity of the file touched, or ``""``.
        rejection: The token naming why a file-naming target was refused, or
            ``""``.  A non-empty rejection means the event counts as rejected and
            contributes no file.
        outcome: The result status token - ``"confirmed"``, ``"not_modified"``,
            ``"failed"``, ``"unknown"`` - or ``"not_applicable"`` for an envelope
            that names no file.  Whether an operation happened is a separate claim
            from whether it was attempted, so the tracker can count the attempts,
            the successes and the failures apart without reading one as another.
    """

    tool: str
    activity: str
    file: str
    rejection: str = ""
    outcome: str = OUTCOME_NOT_APPLICABLE

    @property
    def successful(self) -> bool:
        """Whether the operation named in this event's header reported success.

        Returns:
            ``True`` only for an accepted file whose own result head confirmed the
            operation.  A rejected path never confirms anything: the repository
            does not hold the file it names.
        """
        return bool(self.file) and self.outcome == OUTCOME_CONFIRMED

    @property
    def attempted(self) -> bool:
        """Whether this event names a repository file an operation was aimed at."""
        return bool(self.file)


@dataclass(frozen=True, slots=True)
class ResolvedEnvelopes:
    """The activity claims of one request, and what a bound left out.

    Attributes:
        events: Events in message order.
        beyond_bound: How many further recognized envelopes were not recorded
            because :data:`MAX_ENVELOPES_PER_REQUEST` was reached.  It is a count,
            and it is the reason a capped conversation cannot read as a quiet one.
    """

    events: tuple[ActivityEvent, ...] = ()
    beyond_bound: int = 0


def parse_envelopes(messages: object) -> tuple[list[Envelope], int]:
    """Read the anchored envelope headers of the user-role messages.

    When a transcript holds more recognized envelopes than
    :data:`MAX_ENVELOPES_PER_REQUEST`, it is the *oldest* that are dropped: the
    newest envelopes are the work this conversation just did, and a bound may
    never make a live session look idle by keeping only a stale prefix.

    Args:
        messages: A chat ``messages`` list.  Anything that is not a list of message
            dicts yields no envelope, so a malformed request is simply a client
            that showed the gateway no activity.

    Returns:
        A ``(envelopes in message order, recognized envelopes beyond the bound)``
        pair.
    """
    if not isinstance(messages, list):
        return [], 0

    found: deque[Envelope] = deque(maxlen=MAX_ENVELOPES_PER_REQUEST)
    recognized = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        envelope = parse_message_envelope(content_to_text(message.get("content", "")))
        if envelope is None:
            continue
        recognized += 1
        found.append(envelope)
    return list(found), max(recognized - MAX_ENVELOPES_PER_REQUEST, 0)


def parse_message_envelope(text: str) -> Envelope | None:
    """Parse one message's anchored envelope header, if it has one.

    Args:
        text: The flattened text of a single message.

    Returns:
        The :class:`Envelope`, or ``None`` when the message is not a recognized
        envelope header.  ``None`` means "no event": a result body, a different
        client's marker, or an unclosed header is never guessed at.
    """
    head = text.lstrip()
    tool = cline_envelope_tool(head)
    if not tool:
        return None
    activity = CLINE_ENVELOPE_TOOLS.get(tool, ACTIVITY_NONE)

    rest = head[len(f"[{tool}{_FOR_MARKER}") :]
    if not rest:
        return None

    window = rest[: MAX_ENVELOPE_HEADER_CHARS + 1]
    cut = window.find(_ENVELOPE_TAIL)
    if cut >= 0:
        target = window[:cut]
    elif len(rest) <= MAX_ENVELOPE_HEADER_CHARS and rest.endswith("]"):
        # The gateway's own history cap can truncate the body away; a header that
        # still closed remains an unambiguous header.
        target = rest[:-1]
    else:
        return None

    value, malformed = _unquote(target)
    # The status read is the one place a result body is consulted, and only for a
    # tool that names one file.  A read's body is the file's own text, so the reader
    # gets the anchored failure rule in :func:`_read_status` rather than a search
    # through whatever the file happened to contain.
    outcome = OUTCOME_NOT_APPLICABLE
    if activity == ACTIVITY_MODIFIED:
        outcome = _result_status(head)
    elif activity == ACTIVITY_READ:
        outcome = _read_status(head)
    return Envelope(
        tool=tool,
        activity=activity,
        target=value,
        malformed=malformed,
        outcome=outcome,
    )


def resolve_file_activity_events(
    messages: object,
    normalizer: RepositoryPathNormalizer,
) -> ResolvedEnvelopes:
    """Normalize every recognized envelope of one request into events.

    Args:
        messages: The request's ``messages`` list.
        normalizer: Path normalizer bound to the configured repository root.

    Returns:
        The :class:`ResolvedEnvelopes` for the request, in message order.

    A target spelling is resolved by the normalizer at most once per call: a Cline
    transcript re-sends the same envelope text inside every request, so the same
    handful of targets would otherwise reach ``realpath`` again for every copy of
    itself.  That cache is a local of this function, not state on the normalizer -
    it dies with the request, holds nothing a client could have written to poison a
    later one, and is bounded by :data:`MAX_ENVELOPES_PER_REQUEST` because it can
    only ever gain one entry per envelope parsed here.  Distinct spellings of the
    same file are distinct keys, and each still resolves on its own.
    """
    envelopes, beyond = parse_envelopes(messages)
    resolved_targets: dict[str, tuple[str, str]] = {}
    events: list[ActivityEvent] = []
    for envelope in envelopes:
        if not envelope.names_file:
            events.append(ActivityEvent(tool=envelope.tool, activity=ACTIVITY_NONE, file=""))
            continue
        if envelope.malformed:
            events.append(
                ActivityEvent(
                    tool=envelope.tool,
                    activity=envelope.activity,
                    file="",
                    rejection=REJECT_QUOTING,
                    outcome=envelope.outcome,
                )
            )
            continue
        cached = resolved_targets.get(envelope.target)
        if cached is None:
            cached = normalizer.normalize(envelope.target)
            resolved_targets[envelope.target] = cached
        identity, rejection = cached
        events.append(
            ActivityEvent(
                tool=envelope.tool,
                activity=envelope.activity,
                file=identity,
                rejection=rejection,
                outcome=envelope.outcome,
            )
        )
    return ResolvedEnvelopes(events=tuple(events), beyond_bound=beyond)


def _result_head(text: str) -> str:
    """Return the bounded, case-folded head of one envelope's result body.

    Args:
        text: The full message text, whose header has already been recognized as a
            file-naming envelope.  Untrusted.

    Returns:
        At most :data:`MAX_RESULT_HEAD_CHARS` of what follows the ``Result:`` marker,
        lowercased for marker matching, or ``""`` when the message carries no marker
        at all - which is what a body the gateway's own history cap truncated away
        looks like.
    """
    start = text.find(_RESULT_MARKER)
    if start < 0:
        return ""
    body = start + len(_RESULT_MARKER)
    return text[body : body + MAX_RESULT_HEAD_CHARS].lower()


def _result_status(text: str) -> str:
    """Return the closed status token a writer's result body reports.

    Args:
        text: The full message text, whose header has already been recognized as a
            modification envelope.  Untrusted.

    Returns:
        :data:`OUTCOME_NOT_MODIFIED` when a failure marker appears in the bounded
        head - checked first, so a body that states a write and then fails cannot
        read as a success - :data:`OUTCOME_CONFIRMED` when a success marker
        appears and no failure marker does, and :data:`OUTCOME_UNKNOWN` when the
        head holds no marker at all.  Never the matched text: nothing here may
        carry a client's prose out of this module.
    """
    head = _result_head(text)
    if not head.strip():
        return OUTCOME_UNKNOWN
    if any(marker in head for marker in _RESULT_NOT_MODIFIED_MARKERS):
        return OUTCOME_NOT_MODIFIED
    if any(marker in head for marker in _RESULT_CONFIRMED_MARKERS):
        return OUTCOME_CONFIRMED
    return OUTCOME_UNKNOWN


def _read_status(text: str) -> str:
    """Return the closed status token a reader's result body reports.

    Args:
        text: The full message text, whose header has already been recognized as a
            read envelope.  Untrusted, and normally the contents of the file read.

    Returns:
        :data:`OUTCOME_FAILED` when the bounded head *begins* with a recognized
        failure prefix - anchored rather than searched, because a source file is
        free to contain those words as ordinary text - :data:`OUTCOME_UNKNOWN` when
        the head holds no text at all, and :data:`OUTCOME_CONFIRMED` otherwise.  A
        successful read has no success grammar to match, so this is the weakest of
        the three readings and the reason ``files_read`` is documented as counting
        only reads whose result did not report a failure.
    """
    head = _result_head(text)
    if not head.strip():
        return OUTCOME_UNKNOWN
    if head.lstrip().startswith(_READ_FAILURE_PREFIXES):
        return OUTCOME_FAILED
    return OUTCOME_CONFIRMED


def _unquote(target: str) -> tuple[str, bool]:
    """Strip one layer of Cline quoting from a header target.

    Args:
        target: The text between the tool name and the header's terminator.

    Returns:
        A ``(value, malformed)`` pair.  A blank target gives ``("", False)`` so the
        path layer can call it empty; an unbalanced, doubled or embedded quote gives
        ``("", True)``, because guessing where a quoted name ends would mean reading
        a client's punctuation as a rule the gateway never verified.
    """
    text = target.strip()
    if not text:
        return "", False
    quote = text[0]
    if quote in ("'", '"'):
        if len(text) >= 2 and text.endswith(quote) and text.count(quote) == 2:
            return text[1:-1].strip(), False
        return "", True
    if "'" in text or '"' in text:
        return "", True
    return text, False


def _canonical_root(root: Path | str) -> str:
    """Return the slash-separated, symlink-free form of a repository root.

    Args:
        root: The configured root, which need not exist.

    Returns:
        The canonical absolute form, or ``""`` when the filesystem refused to
        resolve it - an unusable configuration the caller reports as a state and
        never as a path.
    """
    text = str(root)
    try:
        return file_identity(os.path.realpath(text))
    except (OSError, ValueError):
        pass
    try:
        return file_identity(os.path.abspath(text))
    except (OSError, ValueError):
        return ""
