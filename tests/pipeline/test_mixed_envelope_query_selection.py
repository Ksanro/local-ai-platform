"""A turn that carries both task text and a ``hook_context`` envelope stays whole.

Query selection sets a Cline ``<hook_context>`` envelope aside when the message is
*nothing but* envelopes (`288cb8d`, `6f7bebf`).  The shape this module pins is the
one right next to it: a single message with user text **and** an envelope in it.
There the markup is deliberately kept, and that is a measured decision rather than
an oversight:

* The client observed here composes no such message.  Cline 3.0.74's
  ``@cline/agents`` ``flushPendingHookContexts`` joins the pending envelopes with
  ``"\\n\\n"`` and emits them as their **own** user message
  (``displayRole: "system"``); it does not concatenate one with what the user typed.
  The mixed shape as an *injection* has therefore not occurred in this deployment -
  a statement about the observed client, not a promise about a future one.
* In the real traffic the tag appears inside 10 of the 193 user-role text blocks
  under ``~/.cline/data/sessions``: 7 are nothing-but-envelope messages, 1 quotes a
  whole envelope inside a 3,825-character task, 2 name the tag in prose.  Those
  last three are a user writing *about* the markup, and position is the only thing
  that tells that apart from an injection.
* Removing spans anyway is not a tidy-up.  On this repository's own index,
  stripping whole-envelope spans out of that real quoting turn drops 169
  characters and changes what it retrieves (``select_last_task_text`` out,
  ``looks_like_tool_result_message`` in).  What attached markup does to a symbol
  list is ranking's to decide, and it was measured rather than assumed: nothing
  moved for a 2,043-character task, and two symbols were added for a 122-character
  one.  Selection neither promises nor forbids either outcome - a mixed message is
  not treated as bookkeeping, and its text is not rewritten.

So the boundary is recognition at the two ends of a message and nothing inside
them, and these tests hold it there.  A rule that rewrites the inside of a user
message - which is what "extract the task text" means - has to beat this evidence
first, and it re-opens the bug `19dc0f6` closed for ``<task>``: a prompt that
quotes the tags loses its own words to its own quotation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from packages.pipeline.context import PipelineContext
from packages.pipeline.stages.planning_stage import PlanningStage
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.pipeline.user_messages import (
    client_bookkeeping_only,
    looks_like_client_envelope_message,
    select_context_query_text,
    select_task_texts,
)
from packages.repository.index.builder import RepositoryIndexBuilder
from packages.repository.index.models import RepositoryIndex

#: What the user's task names, and the decoy the envelope's own words point at.
PARSER_MODULE = '''"""Splits the rows a reader hands in."""
from __future__ import annotations


def parse_report_row(line: str) -> dict[str, str]:
    """Split one report line into its two fields."""
    key, _, value = line.partition("=")
    return {key: value}
'''

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

#: The notice exactly as ``ask_question`` sends it (session log, 2026-11-14).
ENVELOPE = (
    '<hook_context source="ToolSuccess" tool_name="ask__question" '
    'tool_call_id="chatcmpl-tool-b22a65e7a73d6439">\n'
    "The user has answered the question. Continue working on their task using "
    "that answer.\n"
    "</hook_context>"
)

#: Another source the client's composer emits: a hook attached to a run rather
#: than to a tool call, so the opening tag carries one attribute and no id.
RUN_START_ENVELOPE = (
    '<hook_context source="RunStart">\n'
    "Reminder: re-read the project docs before editing.\n"
    "</hook_context>"
)

#: A body may only ever mention the tag escaped (``<\\hook_context>``) - the client
#: rewrites it that way while composing.  Recognition must not trip over it.
ESCAPED_BODY_ENVELOPE = (
    '<hook_context source="PostToolUse">\n'
    "See <\\hook_context> for the earlier notice.\n"
    "</hook_context>"
)
#: The one mixed shape the transcripts really do contain: a task that quotes a
#: whole envelope as its evidence.  Transcribed from session
#: ``1794660611277_z01hk``, shortened, with the absolute paths taken out.
QUOTING_TASK = (
    "Task: Cline follow-up turns retrieve context for the hook_context envelope "
    "instead of the user's task.\r"
    "Evidence (verified):\r"
    "- logs/cline_sessions.jsonl: 200 requests have last_user_message =\r"
    "  '" + ENVELOPE + "'\r"
    "  All 200 got primary_symbol packages/tasks/context_builder.ContextBuilder\r"
    "Work measurement-first and STOP after Step 1."
)

#: The same turn as a span-removal rule would have selected it: the quote is gone,
#: and nothing about the remaining text says a sentence used to sit there.
QUOTING_TASK_WITH_SPAN_REMOVED = QUOTING_TASK.replace(ENVELOPE, "")

WRAPPED_TASK = "<task>fix the parser</task>\n# task_progress RECOMMENDED"

CONTEXT_TOKENS = 4096


def _index(tmp_path: Path) -> RepositoryIndex:
    """Index the named file and the decoy, the way the gateway indexes a repository."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "parser.py").write_text(PARSER_MODULE, encoding="utf-8")
    (tmp_path / "pkg" / "tasks").mkdir()
    (tmp_path / "pkg" / "tasks" / "answering.py").write_text(DECOY_MODULE, encoding="utf-8")
    return RepositoryIndexBuilder().build(tmp_path)


def _run(
    index: RepositoryIndex,
    messages: list[dict[str, str]],
    intent: str | None = None,
) -> tuple[PipelineContext, dict]:
    """Send one request through PlanningStage and RepositoryContextStage."""
    context = PipelineContext(
        request_id="mixed-envelope-query-selection",
        request={
            "messages": [{"role": "system", "content": "You answer from context."}, *messages]
        },
    )
    if intent is not None:
        context.set_metadata("context_intent", intent)
    asyncio.run(PlanningStage().execute(context))
    stage = RepositoryContextStage(index=index, max_context_tokens=CONTEXT_TOKENS)
    result = asyncio.run(stage.execute(context))
    return context, dict(result.data or {})


def _query(context: PipelineContext) -> str:
    """The text the retrieval path actually queried with."""
    return RepositoryContextStage._extract_query(context)


def _sent(data: dict) -> list[str]:
    """The symbols one request was sent, primary first, or nothing."""
    package = data.get("package")
    if package is None:
        return []
    return [name for name in (package.primary_symbol, *package.supporting_symbols) if name]


def _user(text: str) -> dict[str, str]:
    """One user-role message, the shape the request carries."""
    return {"role": "user", "content": text}


# ------------------------------------------------------------ a mixed message


def test_a_task_with_an_attached_envelope_is_selected_whole(tmp_path: Path) -> None:
    """The issue in one line: the markup is in the query, and that is the decision.

    Nothing inside a message that carries user text is parsed as structure, so the
    envelope rides along.  Stated here so the next reader finds it as a rule and not
    as a gap.
    """
    mixed = TASK_TEXT + "\n" + ENVELOPE
    context, data = _run(_index(tmp_path), [_user(mixed)])

    assert looks_like_client_envelope_message(mixed) is False
    assert select_task_texts([mixed]) == [mixed]
    assert _query(context) == mixed
    assert "<hook_context" in _query(context)
    assert data["symbols_selected"] > 0
    assert client_bookkeeping_only([_user(mixed)]) is False


def test_an_attached_envelope_reaches_the_query_unedited(tmp_path: Path) -> None:
    """What this two-module fixture proves is about the query, not the symbol list.

    The same task is sent twice, with and without an envelope attached, and the
    invariant is the text selection: the markup is neither parsed as structure nor
    stripped from the query, so the mixed query is the task plus exactly that
    envelope, and neither turn is set aside as bookkeeping.  Whether attached markup
    then moves what ranking returns is ranking's to decide and is not claimed here -
    the real-index run recorded in ``docs/live-gateway-runbook.md`` measured it change
    the symbols for a short task and not for a long one, so a fixture-level symbol
    comparison would be a snapshot, not a rule.
    """
    index = _index(tmp_path)

    plain_context, plain = _run(index, [_user(TASK_TEXT)])
    mixed_text = TASK_TEXT + "\n" + ENVELOPE
    mixed_context, mixed = _run(index, [_user(mixed_text)])

    assert _query(plain_context) == TASK_TEXT
    assert _query(mixed_context) == mixed_text
    assert _query(mixed_context)[len(TASK_TEXT) :] == "\n" + ENVELOPE
    assert client_bookkeeping_only([_user(mixed_text)]) is False
    assert _sent(plain) and _sent(mixed)
    assert _sent(mixed)[0].startswith("pkg/parser")


def test_an_envelope_attached_in_front_of_the_task_is_kept_with_it(tmp_path: Path) -> None:
    """Recognition reads both ends and finds user text, so order cannot matter."""
    mixed = ENVELOPE + "\n" + TASK_TEXT
    context, _ = _run(_index(tmp_path), [_user(mixed)])

    assert looks_like_client_envelope_message(mixed) is False
    assert select_task_texts([mixed]) == [mixed]
    assert _query(context) == mixed


def test_a_task_and_its_envelope_in_two_messages_select_the_task_alone(
    tmp_path: Path,
) -> None:
    """The shape this client really sends, and the guarantee that shape carries.

    ``flushPendingHookContexts`` gives the envelope a message of its own, so a
    follow-up turn selects the older task and carries no markup at all - and the
    bookkeeping turn is invisible to retrieval, which is what `288cb8d` promised and
    is checked here against the same task sent without it, not against a mixed turn.
    """
    index = _index(tmp_path)

    _, alone = _run(index, [_user(TASK_TEXT)])
    context, followup = _run(
        index,
        [
            _user(TASK_TEXT),
            {"role": "assistant", "content": "Step 1 report: the named rule decides."},
            _user(ENVELOPE),
        ],
    )

    assert _query(context) == TASK_TEXT
    assert "<hook_context" not in _query(context)
    assert _sent(followup) == _sent(alone)


# --------------------------------------------- several envelopes in one message


def test_envelopes_joined_behind_task_text_are_kept_with_it(tmp_path: Path) -> None:
    """The composer can join several envelopes into one message with ``"\\n\\n"``.

    With the user's text in front of them the message is not nothing-but-envelopes,
    so recognition fails and every one of them stays in the query.
    """
    mixed = TASK_TEXT + "\n\n" + ENVELOPE + "\n\n" + RUN_START_ENVELOPE
    context, _ = _run(_index(tmp_path), [_user(mixed)])

    assert looks_like_client_envelope_message(mixed) is False
    assert _query(context) == mixed


def test_the_same_envelopes_alone_are_still_bookkeeping(tmp_path: Path) -> None:
    """Preserved: nothing-but-envelopes gives no context and names which empty path."""
    joined = ENVELOPE + "\n\n" + RUN_START_ENVELOPE
    context, data = _run(_index(tmp_path), [_user(joined)])

    assert _query(context) == ""
    assert "package" not in data
    assert data["empty_reason"] == "client_bookkeeping_only"


def test_an_envelope_whose_body_holds_the_clients_escape_is_bookkeeping() -> None:
    """The body is never parsed, so an escaped nested mention cannot widen the rule.

    The composer escapes a body's own ``<hook_context`` as ``<\\hook_context``; the
    span rule only looks for the closing tag, which such a message holds exactly one
    of, and that one closes the envelope.
    """
    assert looks_like_client_envelope_message(ESCAPED_BODY_ENVELOPE) is True
    assert select_task_texts([ESCAPED_BODY_ENVELOPE]) == []


def test_the_same_escaped_envelope_beside_a_task_is_kept_with_it() -> None:
    """One message, two claims: recognition fails, so its body stays in the text."""
    mixed = TASK_TEXT + "\n" + ESCAPED_BODY_ENVELOPE

    assert looks_like_client_envelope_message(mixed) is False
    assert select_task_texts([mixed]) == [mixed]


# -------------------------------------------------------- quoted, not injected


def test_a_task_that_quotes_an_envelope_keeps_its_own_quotation(tmp_path: Path) -> None:
    """The mixed shape that really occurs, and why removal would eat the evidence.

    Transcribed from a turn the gateway served: the task quotes the envelope it is
    about, so the quote is task text.  This is the same rule that keeps a
    ``<task>...</task>`` mention whole (`19dc0f6`) - the fix for that bug is why a
    quote cannot be told from an injection by its contents.
    """
    context, data = _run(_index(tmp_path), [_user(QUOTING_TASK)])

    assert looks_like_client_envelope_message(QUOTING_TASK) is False
    assert select_task_texts([QUOTING_TASK]) == [QUOTING_TASK]
    assert _query(context) == QUOTING_TASK
    assert "last_user_message" in _query(context)
    assert "package" in data
    assert data["symbols_selected"] > 0


def test_the_quote_and_an_injection_are_indistinguishable_to_the_boundary() -> None:
    """The guard: both forms are user text, so no rule here can choose between them.

    The stripped variant is what a span-removal rule would have retrieved for on the
    real turn above.  It is shorter by exactly one envelope and it selects as
    ordinary text, which is the point - by then the user's sentence about the
    envelope is already gone, and the measured cost of that on this repository's own
    index was two symbols moving.
    """
    assert QUOTING_TASK_WITH_SPAN_REMOVED != QUOTING_TASK
    assert len(QUOTING_TASK_WITH_SPAN_REMOVED) == len(QUOTING_TASK) - len(ENVELOPE)
    assert select_task_texts([QUOTING_TASK]) == [QUOTING_TASK]
    assert select_task_texts([QUOTING_TASK_WITH_SPAN_REMOVED]) == [
        QUOTING_TASK_WITH_SPAN_REMOVED
    ], "the stripped form must select as ordinary text"


def test_a_mention_of_the_tag_with_no_closing_tag_is_ordinary_text(tmp_path: Path) -> None:
    """Prose that only names the envelope carries no structure to read."""
    text = "Why does the <hook_context envelope keep showing up in the query?"
    context, _ = _run(_index(tmp_path), [_user(text)])

    assert looks_like_client_envelope_message(text) is False
    assert _query(context) == text


def test_an_unclosed_envelope_beside_the_task_is_user_text(tmp_path: Path) -> None:
    """Recognition needs both ends; an open span is not a reason to cut text."""
    mixed = TASK_TEXT + "\n" + ENVELOPE.replace("\n</hook_context>", "")
    context, _ = _run(_index(tmp_path), [_user(mixed)])

    assert looks_like_client_envelope_message(mixed) is False
    assert _query(context) == mixed


# -------------------------------------- markers, follow-ups, and other consumers


def test_a_trailing_envelope_after_a_wrapped_task_stays_out_of_the_query(
    tmp_path: Path,
) -> None:
    """Preserved: the explicit task marker decides, and it runs to the last ``</task>``.

    Anything attached after that closing tag - Cline's own guidance, or an envelope
    hypothetically glued on - is outside the extracted task.
    """
    message = WRAPPED_TASK + "\n" + ENVELOPE
    context, _ = _run(_index(tmp_path), [_user(message)])

    assert _query(context) == "fix the parser"
    assert "<hook_context" not in _query(context)


def test_a_leading_envelope_before_a_wrapped_task_is_kept(tmp_path: Path) -> None:
    """The asymmetry, stated rather than fixed: the wrapper counts only when it
    *opens* the message, so an envelope in front of it lands inside the selection.

    This is the one mixed shape with a plausible argument for extraction.  It is
    pinned instead of patched because the client does not produce it - an envelope is
    always flushed as its own message - and because an end-anchored rule is exactly
    the rule that eats a quoted envelope, which the corpus does contain.
    """
    message = ENVELOPE + "\n" + WRAPPED_TASK
    context, _ = _run(_index(tmp_path), [_user(message)])

    assert _query(context) == message
    assert select_task_texts([message]) == [message]


def test_a_followup_under_an_envelope_still_carries_the_previous_task(tmp_path: Path) -> None:
    """Preserved: the anaphoric join is untouched by anything on this boundary."""
    followup = "and the same in the serializer"
    context, _ = _run(
        _index(tmp_path),
        [
            _user(TASK_TEXT),
            {"role": "assistant", "content": "By the shared writer rule."},
            _user(followup),
            _user(ENVELOPE),
        ],
    )

    assert _query(context) == f"{TASK_TEXT}\n\n{followup}"
    assert "<hook_context" not in _query(context)


def test_planning_sees_the_mixed_turn_whole_and_a_separate_envelope_not_at_all(
    tmp_path: Path,
) -> None:
    """The same selection feeds intent detection, in both directions.

    A mixed turn is one string to the planner, markup and all; an envelope that
    arrived as its own message contributes nothing, which is what keeps a follow-up
    turn classified by the task it continues.
    """
    mixed = TASK_TEXT + "\n" + ENVELOPE
    index = _index(tmp_path)

    combined, _ = _run(index, [_user(mixed)])
    followup, _ = _run(
        index,
        [_user(TASK_TEXT), {"role": "assistant", "content": "Step 1 report."}, _user(ENVELOPE)],
    )

    assert PlanningStage._extract_messages(combined) == [mixed]
    assert PlanningStage._extract_messages(followup) == [TASK_TEXT]


def test_an_explicit_intent_still_decides_a_turn_that_carries_an_envelope(
    tmp_path: Path,
) -> None:
    """Preserved: ``context_intent`` outranks detection, markup or no markup."""
    context, _ = _run(
        _index(tmp_path),
        [_user(TASK_TEXT + "\n" + ENVELOPE)],
        intent="REFACTOR",
    )
    plan = context.get_metadata("context_plan")

    assert plan is not None
    assert plan.intent == "REFACTOR"


def test_an_ordinary_message_is_selected_exactly_as_it_arrived(tmp_path: Path) -> None:
    """Preserved: a message with no envelope in it is never rewritten."""
    text = "Which function in pkg/parser.py splits a report line, and what does it return?"
    context, _ = _run(_index(tmp_path), [_user(text)])

    assert select_context_query_text([_user(text)]) == text
    assert _query(context) == text
