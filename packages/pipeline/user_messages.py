"""Helpers for selecting user-authored task text from chat messages.

This module also owns the single Cline tool-result envelope boundary the whole
pipeline shares: :data:`CLINE_ENVELOPE_TOOLS` names every Cline tool whose
result arrives as a user-role message, and :data:`CLINE_TOOL_RESULT_PREFIXES`
is generated from it.  Planning text selection, history capping and file-activity
extraction all read that one table, so the three cannot drift into recognizing
different envelopes.  The value each tool maps to is the file activity the
gateway may attribute to it - see ``packages.pipeline.cline_activity`` - and
``ACTIVITY_NONE`` means the envelope is recognized without naming a file it
touched.
"""

from __future__ import annotations

import re
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

#: The Cline tools whose result arrives as a user-role envelope, and the activity
#: each one carries.  The three that name exactly one file are the file-activity
#: tools; ``read_file`` is a read and both writers are modifications.  The
#: remaining entries are recognized envelopes that touch no identifiable file.
CLINE_ENVELOPE_TOOLS: Mapping[str, str] = MappingProxyType(
    {
        "read_file": ACTIVITY_READ,
        "write_to_file": ACTIVITY_MODIFIED,
        "replace_in_file": ACTIVITY_MODIFIED,
        "search_files": ACTIVITY_NONE,
        "list_files": ACTIVITY_NONE,
        "execute_command": ACTIVITY_NONE,
    }
)

#: Envelope bodies that carry no tool header at all but are still Cline
#: bookkeeping rather than a user-authored task.
CLINE_NON_TOOL_PREFIXES: tuple[str, ...] = (
    "[attempt_completion]",
    "[ERROR] You did not use a tool",
)

CLINE_TOOL_RESULT_PREFIXES: tuple[str, ...] = (
    *tuple(f"[{tool} for " for tool in CLINE_ENVELOPE_TOOLS),
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
    """Return True for Cline tool-result/user-reminder messages."""
    return message.lstrip().startswith(CLINE_TOOL_RESULT_PREFIXES)


def cline_envelope_tool(message: str) -> str:
    """Return the Cline tool named by an anchored envelope header, or ``""``.

    Only the very start of the message is examined: a header is
    ``"[<tool> for <target>]"``, so the tool name is read from the anchored
    prefix and nothing after it is ever consulted.  A tool that is not in
    :data:`CLINE_ENVELOPE_TOOLS` - a client with its own envelope vocabulary, or
    a Cline tool the gateway has no verified grammar for - returns ``""``, which
    keeps an unrecognized header from being read as activity.

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
    return tool if tool in CLINE_ENVELOPE_TOOLS else ""


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
