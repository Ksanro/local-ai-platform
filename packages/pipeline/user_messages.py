"""Helpers for selecting user-authored task text from chat messages.

This module also owns the single Cline envelope registry the pipeline shares.
:data:`CLINE_ENVELOPE_SPECS` is the one place a Cline tool name is written down,
and every behavior that needs to ask "is this a Cline envelope?" derives its own
view of it instead of repeating a literal list:

* :data:`CLINE_FILE_ACTIVITY_TOOLS` - every registered tool - is what
  ``packages.pipeline.cline_activity`` may read an activity claim from;
* :data:`CLINE_TOOL_RESULT_PREFIXES` - the subset whose ``bookkeeping`` flag is
  set - is what planning text selection and the history cap compare against.

The two views are deliberately not the same set, and the difference is policy
rather than drift.  Roadmap C1 widened *recognition*, so that a write or a
replace now shows up in the file-activity counters; it must not have widened
*behavior*.  A ``[write_to_file for x.py]`` result is measured, and is still sent
to the model whole and still selectable as task text, exactly as it was before
C1 - see :attr:`ClineEnvelopeSpec.bookkeeping`.  One registry, two derived views,
no duplicated parsing rule anywhere: the literal tuple that used to exist twice
still exists exactly once, here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping

from packages.context.content import content_to_text

#: The activity a recognized Cline envelope implies for the file it names.
#: ``ACTIVITY_NONE`` marks an envelope that is recognized but must never be read
#: as touching one particular file: its target is a search pattern, a directory,
#: or a shell command line, and any file inside its result body belongs to the
#: model's output, not to a boundary the gateway can trust.
ACTIVITY_READ: Final = "read"
ACTIVITY_MODIFIED: Final = "modified"
ACTIVITY_NONE: Final = "none"


@dataclass(frozen=True, slots=True)
class ClineEnvelopeSpec:
    """One Cline tool whose result arrives as a user-role envelope.

    Attributes:
        tool: The name written in the header, ``"[<tool> for <target>]"``.
        activity: The file activity the gateway may attribute to the target -
            :data:`ACTIVITY_READ`, :data:`ACTIVITY_MODIFIED`, or
            :data:`ACTIVITY_NONE` when the envelope names no single file.
        bookkeeping: Whether planning text selection and the history cap treat
            this envelope as Cline bookkeeping rather than user-authored task
            text - that is, whether the message may be dropped from a retrieval
            query or truncated in place.  ``True`` holds for exactly the tools
            the gateway recognized before roadmap C1 introduced a file-activity
            reader.  The two writers are ``False`` on purpose: C1 needed to
            *see* a write result, not to start editing what the model receives
            because of it.  Widening file-activity recognition must never widen
            this flag as a side effect.
    """

    tool: str
    activity: str
    bookkeeping: bool


#: The canonical Cline envelope registry, in the order the gateway learned the
#: tools.  Every envelope view below is derived from this one table, and a tool
#: belongs to no behavior that is not spelled out here.
CLINE_ENVELOPE_SPECS: Final = (
    ClineEnvelopeSpec("read_file", ACTIVITY_READ, True),
    ClineEnvelopeSpec("write_to_file", ACTIVITY_MODIFIED, False),
    ClineEnvelopeSpec("replace_in_file", ACTIVITY_MODIFIED, False),
    ClineEnvelopeSpec("search_files", ACTIVITY_NONE, True),
    ClineEnvelopeSpec("list_files", ACTIVITY_NONE, True),
    ClineEnvelopeSpec("execute_command", ACTIVITY_NONE, True),
)

#: The file-activity view: every registered tool, and the activity the gateway
#: may attribute to its target.  Used by ``packages.pipeline.cline_activity``.
CLINE_ENVELOPE_TOOLS: Mapping[str, str] = MappingProxyType(
    {spec.tool: spec.activity for spec in CLINE_ENVELOPE_SPECS}
)

#: The recognition view of the same registry: a header naming any of these tools
#: is a Cline envelope, whether or not the pipeline's older consumers treat it as
#: one.  A tool outside this set - a client with its own vocabulary, or a Cline
#: tool the gateway has no verified grammar for - yields no event at all.
CLINE_FILE_ACTIVITY_TOOLS: frozenset[str] = frozenset(spec.tool for spec in CLINE_ENVELOPE_SPECS)

#: Envelope bodies that carry no tool header at all but are still Cline
#: bookkeeping rather than a user-authored task.
CLINE_NON_TOOL_PREFIXES: tuple[str, ...] = (
    "[attempt_completion]",
    "[ERROR] You did not use a tool",
)

#: The planning/history compatibility view: the prefixes text selection and the
#: history cap compare against, derived from the registry entries flagged as
#: bookkeeping.  This is the set those two consumers used before roadmap C1, and
#: it is not the file-activity set - see :attr:`ClineEnvelopeSpec.bookkeeping`.
CLINE_TOOL_RESULT_PREFIXES: tuple[str, ...] = (
    *tuple(f"[{spec.tool} for " for spec in CLINE_ENVELOPE_SPECS if spec.bookkeeping),
    *CLINE_NON_TOOL_PREFIXES,
)

#: How much of a message :func:`cline_envelope_tool` looks at.  A tool name is
#: short, and a header that starts later than this is not an envelope header -
#: reading further would mean scanning result bodies for structure, which the
#: boundary must never do.
_ENVELOPE_HEAD_WINDOW: Final = 96

#: The anchored envelope header prefix: a bracketed lowercase tool name plus the
#: literal ``" for "`` that separates it from its target.
_ENVELOPE_HEAD: Final = re.compile(r"\[([a-z_]+) for ")


def user_message_texts(messages: object) -> list[str]:
    """Return normalized text from user-role chat messages."""
    if not isinstance(messages, list):
        return []

    texts: list[str] = []
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "user":
            text = content_to_text(message.get("content", "")).strip()
            if text:
                texts.append(text)
    return texts


def select_task_texts(messages: list[str]) -> list[str]:
    """Select user-authored task text, ignoring Cline tool-result envelopes."""
    filtered = [
        message
        for message in messages
        if not looks_like_tool_result_message(message)
    ]

    task_messages: list[str] = []
    for message in filtered:
        task_messages.extend(
            match.strip()
            for match in re.findall(r"<task>\s*(.*?)\s*</task>", message, re.DOTALL)
            if match.strip()
        )
    if task_messages:
        return task_messages

    return filtered or messages


def select_last_task_text(messages: object) -> str:
    """Return the last clean user task text from a chat ``messages`` list."""
    selected = select_task_texts(user_message_texts(messages))
    return selected[-1].strip() if selected else ""


def select_context_query_text(messages: object) -> str:
    """Return retrieval query text, including prior task text for follow-ups."""
    selected = select_task_texts(user_message_texts(messages))
    if not selected:
        return ""

    last = selected[-1].strip()
    if len(selected) < 2 or not _looks_like_followup(last):
        return last

    previous = selected[-2].strip()
    return f"{previous}\n\n{last}" if previous else last


def looks_like_tool_result_message(message: str) -> bool:
    """Return True for the Cline envelopes this pipeline treats as bookkeeping.

    This is the compatibility view of the registry, ``CLINE_TOOL_RESULT_PREFIXES``,
    and not the file-activity view, so a ``write_to_file`` or ``replace_in_file``
    result reads as ordinary user text here exactly as it did before roadmap C1,
    and remains selectable as task text.

    Args:
        message: One user-role message, already flattened to text.

    Returns:
        ``True`` when the message starts with a recognized bookkeeping prefix.
    """
    return message.lstrip().startswith(CLINE_TOOL_RESULT_PREFIXES)


def cline_envelope_tool(message: str) -> str:
    """Return the Cline tool named by an anchored envelope header, or ``""``.

    Only the very start of the message is examined: a header is
    ``"[<tool> for <target>]"``, so the tool name is read from the anchored
    prefix and nothing after it is ever consulted.  A tool that is not in
    :data:`CLINE_FILE_ACTIVITY_TOOLS` - a client with its own envelope
    vocabulary, or a Cline tool the gateway has no verified grammar for - returns
    ``""``, which keeps an unrecognized header from being read as activity.

    This is the widest of the registry's views on purpose: roadmap C1 measures
    what the conversation's agent did, and a write is something it did.  Whether
    the same envelope is also *bookkeeping* for planning and the history cap is a
    separate flag, decided per tool in :data:`CLINE_ENVELOPE_SPECS`.

    Args:
        message: One user-role message, already flattened to text.

    Returns:
        The recognized tool name, or ``""`` when the message is not a
        recognized Cline tool-result envelope.
    """
    head = message.lstrip()[:_ENVELOPE_HEAD_WINDOW]
    match = _ENVELOPE_HEAD.match(head)
    if match is None:
        return ""
    tool = match.group(1)
    return tool if tool in CLINE_FILE_ACTIVITY_TOOLS else ""


def _looks_like_followup(message: str) -> bool:
    """Return True when a user turn depends on recent conversation context."""
    lowered = message.lower().strip()
    return lowered.startswith(
        (
            "for that ",
            "given that ",
            "with that ",
            "using that ",
            "for the same ",
            "given the same ",
            "same ",
        )
    ) or any(
        marker in lowered
        for marker in (
            " that split",
            " that capping logic",
            " the same ",
            " above ",
            " previous ",
        )
    )
