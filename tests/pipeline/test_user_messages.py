"""Focused tests for the planning/history compatibility view of the envelope registry.

Roadmap C1 taught the gateway to *measure* Cline's ``write_to_file`` and
``replace_in_file`` results.  These tests hold the line that it must not have
taught the gateway to *react* to them: the messages task-text selection and the
history cap treat as Cline bookkeeping are still exactly the ones it treated that
way before C1 existed, and both consumers still read that set from one place
instead of keeping their own copy of it.
"""

from __future__ import annotations

import pytest

from packages.pipeline.user_messages import (
    ACTIVITY_MODIFIED,
    ACTIVITY_NONE,
    ACTIVITY_READ,
    CLINE_ENVELOPE_SPECS,
    CLINE_ENVELOPE_TOOLS,
    CLINE_FILE_ACTIVITY_TOOLS,
    CLINE_NON_TOOL_PREFIXES,
    CLINE_TOOL_RESULT_PREFIXES,
    cline_envelope_tool,
    looks_like_tool_result_message,
    select_context_query_text,
    select_task_texts,
)

#: The set the pipeline compared against before roadmap C1, in the order it
#: compared it.  Written out here on purpose: if a future change widens file-activity
#: recognition and the derived view follows it, this is the line that fails.
PRE_C1_PREFIXES: tuple[str, ...] = (
    "[read_file for ",
    "[search_files for ",
    "[list_files for ",
    "[execute_command for ",
    "[attempt_completion]",
    "[ERROR] You did not use a tool",
)

#: The tools a write or a replace result may name; both are measured activity and
#: neither is bookkeeping.
WRITERS = ("write_to_file", "replace_in_file")

READERS_AND_PROBE_TOOLS = ("read_file", "search_files", "list_files", "execute_command")


def _envelope(tool: str, target: str = "packages/demo/widget.py") -> dict[str, str]:
    """Return one user-role message carrying a Cline tool-result envelope.

    Args:
        tool: The Cline tool named in the anchored header.
        target: The text between the tool name and the header's terminator.

    Returns:
        A message dict of the shape the request path carries.
    """
    return {"role": "user", "content": f"[{tool} for '{target}'] Result:\nsome result body"}


def _task(text: str) -> dict[str, str]:
    """Return one user-role message carrying a real Cline task block."""
    return {"role": "user", "content": f"<task>{text}</task>\n# task_progress RECOMMENDED"}


def test_the_compatibility_prefixes_are_exactly_the_pre_c1_set() -> None:
    """Widening recognition must not widen what planning and capping react to."""
    assert CLINE_TOOL_RESULT_PREFIXES == PRE_C1_PREFIXES


@pytest.mark.parametrize("tool", WRITERS)
def test_a_writer_result_is_not_bookkeeping(tool: str) -> None:
    """A write or replace result reads as user text, as it always did."""
    message = f"[{tool} for 'packages/demo/widget.py'] Result:\nThe file was saved."

    assert looks_like_tool_result_message(message) is False


@pytest.mark.parametrize("tool", READERS_AND_PROBE_TOOLS)
def test_the_pre_c1_tools_are_still_bookkeeping(tool: str) -> None:
    """The four tools that were recognized before C1 still are."""
    assert looks_like_tool_result_message(_envelope(tool)["content"]) is True


def test_the_reminder_bodies_are_still_bookkeeping() -> None:
    """The two prefixes that carry no tool header are untouched by this registry."""
    assert looks_like_tool_result_message("[attempt_completion] Result:\ndone") is True
    assert looks_like_tool_result_message("[ERROR] You did not use a tool in this step") is True
    assert set(CLINE_NON_TOOL_PREFIXES) == {
        prefix for prefix in CLINE_TOOL_RESULT_PREFIXES if not prefix.endswith(" for ")
    }


@pytest.mark.parametrize("tool", WRITERS)
def test_a_writer_result_survives_task_text_selection(tool: str) -> None:
    """A writer's result is never dropped from the text a follow-up query is built of."""
    messages = [f"[{tool} for 'packages/demo/widget.py'] Result:\nThe file was saved."]

    assert select_task_texts(messages) == messages


def test_a_reader_result_is_still_filtered_from_task_text() -> None:
    """The bookkeeping half of the registry still filters as it did before C1."""
    task = _task("explain the widget")
    messages = [task["content"], _envelope("read_file")["content"]]

    assert select_task_texts(messages) == ["explain the widget"]


def test_a_writer_result_can_be_the_query_a_follow_up_retrieves_with() -> None:
    """Pre-C1 behavior kept a writer's result selectable as query text; it still does.

    This is the observable consequence of the compatibility set on the live path:
    :func:`select_context_query_text` decides the retrieval query, so a turn whose
    only user message was a write result must query with that result, exactly as it
    did before the activity measurement existed.
    """
    messages = [_envelope("write_to_file")]

    assert select_context_query_text(messages) == messages[0]["content"]


def test_the_writer_query_text_matches_the_pre_c1_selection() -> None:
    """Selecting from a task plus a write result returns the task, not nothing."""
    task = _task("refactor the widget")
    messages = [task, _envelope("replace_in_file")]

    assert select_context_query_text(messages) == "refactor the widget"


# ---------------------------------------------------------------------------
# One registry, two views
# ---------------------------------------------------------------------------


def test_the_registry_is_the_single_source_of_both_views() -> None:
    """No behavior names a tool that the registry does not.

    The literal lists this module used to duplicate are gone: every tool prefix is
    a registry entry, and the only prefixes that are not are the two reminder bodies
    that name no tool at all.
    """
    tools = [spec.tool for spec in CLINE_ENVELOPE_SPECS]

    assert len(tools) == len(set(tools))
    assert set(CLINE_ENVELOPE_TOOLS) == set(tools)
    assert CLINE_FILE_ACTIVITY_TOOLS == frozenset(tools)
    for prefix in CLINE_TOOL_RESULT_PREFIXES:
        if not prefix.endswith(" for "):
            assert prefix in CLINE_NON_TOOL_PREFIXES
            continue
        named = prefix[1 : -len(" for ")]
        assert named in tools, f"{prefix!r} names a tool the registry does not hold"


def test_the_file_activity_view_includes_the_writers() -> None:
    """What C1 came to measure is still measured: six tools, three of them files."""
    assert CLINE_FILE_ACTIVITY_TOOLS == frozenset({*READERS_AND_PROBE_TOOLS, *WRITERS})
    assert CLINE_ENVELOPE_TOOLS["read_file"] == ACTIVITY_READ
    assert CLINE_ENVELOPE_TOOLS["write_to_file"] == ACTIVITY_MODIFIED
    assert CLINE_ENVELOPE_TOOLS["replace_in_file"] == ACTIVITY_MODIFIED
    assert CLINE_ENVELOPE_TOOLS["search_files"] == ACTIVITY_NONE


@pytest.mark.parametrize("tool", [*READERS_AND_PROBE_TOOLS, *WRITERS])
def test_every_registered_tool_is_recognized_for_activity(tool: str) -> None:
    """Recognition is the wide view, so a writer's header yields a tool here."""
    assert cline_envelope_tool(_envelope(tool)["content"]) == tool


def test_recognition_is_wider_than_the_compatibility_view_by_the_writers_only() -> None:
    """The gap between the two derived views is exactly the writers, and nothing else."""
    recognized = {spec.tool for spec in CLINE_ENVELOPE_SPECS}
    bookkeeping = {spec.tool for spec in CLINE_ENVELOPE_SPECS if spec.bookkeeping}

    assert recognized - bookkeeping == set(WRITERS)
    assert bookkeeping == set(READERS_AND_PROBE_TOOLS)
