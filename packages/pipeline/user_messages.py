"""Helpers for selecting user-authored task text from chat messages."""

from __future__ import annotations

import re

from packages.context.content import content_to_text

CLINE_TOOL_RESULT_PREFIXES: tuple[str, ...] = (
    "[read_file for ",
    "[search_files for ",
    "[list_files for ",
    "[execute_command for ",
    "[attempt_completion]",
    "[ERROR] You did not use a tool",
)


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
