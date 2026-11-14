"""A Cline follow-up turn must retrieve for the task, not for the client's notice.

``logs/cline_sessions.jsonl`` recorded 200 requests on 2026-11-14 whose newest
user-role message was the ``ask_question`` answer notice Cline injects, and every
one of them was answered out of ``packages/tasks`` - a dormant package - because
the selection treated that notice as the user's task.  The fixture below rebuilds
the two things a real request carries: the task, named by file path, and the
envelope that continues it, plus a decoy module whose symbols are the only thing
the envelope's own words could point at.

Both stage-level halves are checked here rather than only the selection rule:
what a follow-up turn sends, which must be what the same task sends on its own
turn, and what a turn with nothing but bookkeeping in it records - no context,
and a reason that says why.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from packages.pipeline.context import PipelineContext
from packages.pipeline.stages.planning_stage import PlanningStage
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.repository.index.builder import RepositoryIndexBuilder
from packages.repository.index.models import RepositoryIndex

#: The file the user's task names, and the symbol it asks about.
PARSER_MODULE = '''"""Splits the rows a reader hands in."""
from __future__ import annotations


def parse_report_row(line: str) -> dict[str, str]:
    """Split one report line into its two fields."""
    key, _, value = line.partition("=")
    return {key: value}
'''

#: The decoy: symbols whose only claim on this request is that the client's
#: notice says "task", "answered" and "continue working".
DECOY_MODULE = '''"""What the client continues after a question is answered."""
from __future__ import annotations


class AnsweredTask:
    """A task continued by an answer rather than by a request."""

    @property
    def name(self) -> str:
        """The name shown for the continued task."""
        return "answered"
'''

TASK_TEXT = (
    "In pkg/parser.py, which function splits one report line into its two "
    "fields? Name the function and its file."
)

#: The notice as the client sends it.  Attribute values are opaque ids; the
#: length of the opening tag is the client's, not a size this gateway chose.
HOOK_CONTEXT = (
    '<hook_context source="ToolSuccess" tool_name="ask__question" '
    'tool_call_id="chatcmpl-tool-b22a65e7a73d6439">\n'
    "The user has answered the question. Continue working on their task using "
    "that answer.\n"
    "</hook_context>"
)

CONTEXT_TOKENS = 4096


def _index(tmp_path: Path) -> RepositoryIndex:
    """Index the named file and the decoy, the way the gateway indexes a repository."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "parser.py").write_text(PARSER_MODULE, encoding="utf-8")
    (tmp_path / "pkg" / "tasks").mkdir()
    (tmp_path / "pkg" / "tasks" / "answering.py").write_text(DECOY_MODULE, encoding="utf-8")
    return RepositoryIndexBuilder().build(tmp_path)


def _run(index: RepositoryIndex, messages: list[dict[str, str]]) -> tuple[object, dict]:
    """Send one request through PlanningStage and RepositoryContextStage."""
    context = PipelineContext(
        request_id="client-bookkeeping-context",
        request={
            "messages": [{"role": "system", "content": "You answer from context."}, *messages]
        },
    )
    asyncio.run(PlanningStage().execute(context))
    stage = RepositoryContextStage(index=index, max_context_tokens=CONTEXT_TOKENS)
    result = asyncio.run(stage.execute(context))
    return context, dict(result.data or {})


def _sent(data: dict) -> list[str]:
    """The symbols one request was sent, primary first, or nothing."""
    package = data.get("package")
    if package is None:
        return []
    return [name for name in (package.primary_symbol, *package.supporting_symbols) if name]


def _followup_messages() -> list[dict[str, str]]:
    """The request as the client sends it: task, report, answer, notice."""
    return [
        {"role": "user", "content": TASK_TEXT},
        {"role": "assistant", "content": "Step 1 diagnosis: the named file's rule decides it."},
        {
            "role": "tool",
            "tool_call_id": "chatcmpl-tool-b22a65e7a73d6439",
            "content": "Continue with the named-module breadth only.",
        },
        {"role": "user", "content": HOOK_CONTEXT},
    ]



def test_the_task_alone_retrieves_the_function_it_names(tmp_path: Path) -> None:
    """The control: what the task sends while it is still the newest message."""
    _, data = _run(_index(tmp_path), [{"role": "user", "content": TASK_TEXT}])
    sent = _sent(data)

    assert sent[0].startswith("pkg/parser"), sent


def test_the_followup_turn_sends_what_the_task_alone_sends(tmp_path: Path) -> None:
    """The rule in one sentence: a bookkeeping message changes nothing that is sent.

    Comparing the two requests instead of naming an expected symbol keeps this
    honest if ranking ever moves: what matters is that the notice arriving after
    the task is invisible to retrieval.
    """
    index = _index(tmp_path)

    _, plain = _run(index, [{"role": "user", "content": TASK_TEXT}])
    context, followup = _run(index, _followup_messages())

    assert _sent(followup) == _sent(plain)
    assert _sent(followup)[0].startswith("pkg/parser"), _sent(followup)
    assert "hook_context" not in RepositoryContextStage._extract_query(context)


def test_a_turn_of_pure_bookkeeping_sends_nothing_and_says_why(tmp_path: Path) -> None:
    """No task text means no context, and a reason that says which empty path it was."""
    context, data = _run(_index(tmp_path), [{"role": "user", "content": HOOK_CONTEXT}])

    assert "package" not in data
    assert context.context_package is None
    assert data["symbols_selected"] == 0
    assert data["empty_reason"] == "client_bookkeeping_only"


def test_a_request_without_any_user_text_says_something_different(tmp_path: Path) -> None:
    """Nothing was set aside where nothing was offered; the two must not read alike."""
    _, data = _run(_index(tmp_path), [{"role": "assistant", "content": "ok"}])

    assert data["empty_reason"] == "no_relevant_symbols"


def test_a_greeting_under_an_envelope_stays_on_the_greeting_path(tmp_path: Path) -> None:
    """``is_conversational_only`` is untouched: the filter leaves ``hi``, not nothing."""
    _, data = _run(
        _index(tmp_path),
        [
            {"role": "user", "content": "hi"},
            {"role": "user", "content": HOOK_CONTEXT},
        ],
    )

    assert data["empty_reason"] == "non_task"


def test_the_bookkeeping_reason_reaches_the_log_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """What the record carries, the log line states beside it."""
    with caplog.at_level(logging.INFO):
        _run(_index(tmp_path), [{"role": "user", "content": HOOK_CONTEXT}])

    assert "context_status=empty reason=client_bookkeeping_only" in caplog.text
