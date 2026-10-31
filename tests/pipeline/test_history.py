"""Tests for history capping (packages/pipeline/history.py).

Covers all capping rules:
- history under budget → returned unchanged
- history over budget → oldest dropped
- system messages never dropped
- last user message never dropped
- tool call/result pairing preserved
- order preserved
- list-form content counted correctly
- history_cap_enabled=False path
- budget derivation from the resolved model's definition.context_window
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from packages.context.budget import CHARS_PER_TOKEN
from packages.context.content import content_to_text
from packages.pipeline.context import PipelineContext
from packages.pipeline.engine import (
    _apply_history_cap,
    _resolve_history_chars_per_token,
)
from packages.pipeline.history import RATIO_MAX, RATIO_MIN, cap_history
from packages.pipeline.normalized import NormalizedRequest
from packages.providers.models import ModelDefinition, ResolvedModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg(
    role: str,
    content: str = "",
    tool_calls: list[dict[str, Any]] | None = None,
    tool_call_id: str | None = None,
) -> dict[str, Any]:
    """Build a message dict for tests."""
    m: dict[str, Any] = {"role": role, "content": content}
    if tool_calls:
        m["tool_calls"] = tool_calls
    if tool_call_id:
        m["tool_call_id"] = tool_call_id
    return m


def _estimate(text: str) -> int:
    """Token estimator using CHARS_PER_TOKEN (4.0)."""
    from packages.context.budget import CHARS_PER_TOKEN
    return int(len(text) / CHARS_PER_TOKEN)


# --- Roadmap A3 helpers ----------------------------------------------------
#
# These build payloads and read what the production cap did with them.  None of
# them decides a boundary: every "how much history survives" question in this
# file is answered by packages/pipeline/history.py and
# packages/pipeline/engine._apply_history_cap.

TRUNCATION_MARKER = "\n\n[... truncated by gateway history cap ...]"
CLINE_QUESTION = (
    "Which function applies the cap, in which file, and which APP_ environment "
    "variable forces the budget?"
)
_NULL_PROVIDER = object()


def _envelope(tool: str, target: str, chars: int) -> str:
    """Return a Cline tool-result envelope exactly ``chars`` characters long."""
    header = f"[{tool} for '{target}'] Result:\n"
    return header + ("x" * (chars - len(header)))


def _boundary_transcript() -> list[dict[str, Any]]:
    """A Cline-like history whose size lands between 4.0 and 3.5.

    Two short turns and three 3,600-character tool results - 10,960 characters
    of cappable text.  The platform estimate reads that as 2,707 tokens, inside
    the 3,000-token budget this file caps at, while a 3.5 calibration reads the
    same characters as 3,092 and the oldest result no longer fits.  So one
    transcript, one budget, and the only thing that moves the answer is the
    ratio.
    """
    return [
        _msg("system", "System."),
        _msg("user", "Earlier question"),
        _msg("assistant", "Earlier answer"),
        _msg("user", _envelope("read_file", "packages/pipeline/history.py", 3600)),
        _msg("user", _envelope("search_files", "cap_history", 3600)),
        _msg("user", _envelope("list_files", "packages/pipeline", 3600)),
        _msg("user", CLINE_QUESTION),
    ]


def _contents(messages: list[dict[str, Any]]) -> list[Any]:
    """Return the content of each message, for byte-for-byte comparisons."""
    return [m.get("content") for m in messages]


def _tokens_at(messages: list[dict[str, Any]], chars_per_token: float) -> int:
    """The size ``history_tokens_after`` claims, read off the forwarded payload.

    Deliberately written out here rather than imported: it is the oracle the
    recorded number is checked against, not the code under test.
    """
    return sum(
        int(len(content_to_text(m.get("content", ""))) / chars_per_token)
        if m.get("content")
        else 0
        for m in messages
    )


def _context_with(messages: list[dict[str, Any]]) -> PipelineContext:
    """A context holding one request, as the engine sees it after normalization."""
    context = PipelineContext(request={"messages": messages, "model": "qwen38-27b"})
    context.normalized_request = NormalizedRequest.from_client(context.request)
    return context


def _definition(**overrides: Any) -> ModelDefinition:
    """A model definition carrying only what a calibration test needs."""
    return ModelDefinition(
        model="qwen38-27b",
        provider="openai",
        base_url="http://127.0.0.1:18300/v1",
        **overrides,
    )


def _resolved(**overrides: Any) -> ResolvedModel:
    """A resolved model in the shape ``ModelResolutionStage`` stores."""
    return ResolvedModel(definition=_definition(**overrides), provider=_NULL_PROVIDER)


class _WindowModel:
    """A resolved model whose context window sits on the object itself."""

    def __init__(self, context_window: int) -> None:
        self.context_window = context_window


class _TwoShapeModel:
    """A resolved model carrying a window on its definition and on itself."""

    def __init__(self, definition: ModelDefinition, context_window: Any) -> None:
        self.definition = definition
        self.context_window = context_window


class _BareResolvedModel:
    """A resolved model carrying no definition at all."""


def _derived_budget(
    resolved_model: Any, max_tokens_override: int | None = 2048
) -> dict[str, Any]:
    """Run the production derivation with no ``APP_HISTORY_CAP_TOKENS`` forced.

    Args:
        resolved_model: The model the request supposedly routed to.
        max_tokens_override: The generation reserve subtracted from the window.

    Returns:
        What ``_cap_run`` reports, whose ``budget`` is 0 when the derivation
        found no room and capping stayed off.
    """
    return _cap_run(resolved_model, cap_tokens=0, max_tokens_override=max_tokens_override)


def _cap_run(
    resolved_model: Any,
    cap_tokens: int = 3000,
    messages: list[dict[str, Any]] | None = None,
    max_tokens_override: int | None = None,
) -> dict[str, Any]:
    """Send one transcript through the production cap and report what came out.

    Args:
        resolved_model: Whatever the request supposedly routed to - a real
            ``ResolvedModel``, a stand-in, or ``None``.
        cap_tokens: The value ``APP_HISTORY_CAP_TOKENS`` would have supplied;
            0 leaves no forced budget and selects the derived branch.
        messages: The transcript to cap; the calibrated boundary transcript if
            none is given.
        max_tokens_override: The generation reserve the derivation subtracts,
            ``None`` standing for the request not setting ``max_tokens``.

    Returns:
        The forwarded messages and the four metadata fields a session record
        turns into ``history.*``.
    """
    transcript = messages if messages is not None else _boundary_transcript()
    context = _context_with(transcript)
    context.set_metadata("history_cap_tokens", cap_tokens)
    sent = list(context.normalized_request.messages)

    _apply_history_cap(
        context,
        resolved_model=resolved_model,
        max_tokens_override=max_tokens_override,
    )

    forwarded = context.normalized_request.messages
    return {
        "context": context,
        "sent": sent,
        "messages": forwarded,
        "dropped_count": context.get_metadata("history_dropped_count", 0),
        "tokens_after": context.get_metadata("history_tokens_after", 0),
        "budget": context.get_metadata("history_cap_budget", 0),
        "applied": context.get_metadata("history_cap_applied", False),
        "ratio": _resolve_history_chars_per_token(resolved_model),
    }


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------


class TestHistoryUnderBudget:
    """History that already fits the budget is returned unchanged."""

    def test_returns_unchanged_when_under_budget(self) -> None:
        msgs = [
            _msg("system", "You are helpful."),
            _msg("user", "Hello"),
            _msg("assistant", "Hi there"),
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=10000, estimate=_estimate)
        assert dropped == 0
        assert capped == msgs

    def test_empty_history(self) -> None:
        capped, dropped = cap_history([], max_history_tokens=10000, estimate=_estimate)
        assert dropped == 0
        assert capped == []


class TestHistoryOverBudget:
    """When history exceeds budget, oldest messages are dropped first."""

    def test_oldest_messages_dropped(self) -> None:
        # Create messages where total non-system tokens exceed budget.
        # System message is free; last user is always kept.
        msgs = [
            _msg("system", "System prompt."),
            _msg("user", "A" * 40),        # ~10 tokens — dropped
            _msg("assistant", "B" * 40),    # ~10 tokens — dropped
            _msg("user", "C" * 40),         # ~10 tokens — kept (budget fits)
            _msg("assistant", "D" * 40),    # ~10 tokens — kept
            _msg("user", "E" * 40),         # ~10 tokens — kept (last user)
        ]
        # Budget = 25 tokens → fits C(10) + D(10) + E(10) = 30 > 25.
        # So fits C(10) + D(10) = 20 + E(10) = 30 > 25 → only D(10) + E(10) = 20 ≤ 25.
        # Actually: candidates=[A,B,C,D], walked reversed [D,C,B,A].
        # D(10) ≤ 25 → kept, acc=10. C(10): 10+10=20 ≤ 25 → kept, acc=20.
        # B(10): 20+10=30 > 25 → break.
        # kept = {C,D} + {E} = C,D,E. dropped = A,B = 2.
        capped, dropped = cap_history(msgs, max_history_tokens=25, estimate=_estimate)
        assert dropped == 2  # A, B dropped
        # Keep: system + C + D + E
        assert len(capped) == 4
        assert capped[0]["role"] == "system"
        assert capped[1]["role"] == "user"  # C
        assert capped[2]["role"] == "assistant"  # D
        assert capped[3]["role"] == "user"  # E

    def test_order_preserved(self) -> None:
        msgs = [
            _msg("system", "System."),
            _msg("user", "A" * 40),
            _msg("user", "B" * 40),
            _msg("user", "C" * 40),
        ]
        # Budget = 10 tokens → fits only last user (C, ~10 tokens).
        # candidates=[A,B], walked reversed [B,A].
        # B(10) ≤ 10 → kept, acc=10. A(10): 10+10=20 > 10 → break.
        # kept = {B} + {C} = B,C. dropped = A = 1.
        capped, dropped = cap_history(msgs, max_history_tokens=10, estimate=_estimate)
        assert dropped == 1
        assert capped[0]["role"] == "system"
        assert capped[1]["role"] == "user"
        assert capped[1]["content"] == "B" * 40
        assert capped[2]["role"] == "user"
        assert capped[2]["content"] == "C" * 40


# ---------------------------------------------------------------------------
# System messages never dropped
# ---------------------------------------------------------------------------


class TestSystemMessagesPreserved:
    """System messages are never dropped, even when over budget."""

    def test_multiple_system_messages_kept(self) -> None:
        msgs = [
            _msg("system", "SYS1"),
            _msg("system", "SYS2"),
            _msg("user", "A" * 40),
            _msg("assistant", "B" * 40),
            _msg("user", "C" * 40),
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=0, estimate=_estimate)
        # Budget 0 → only system and last user kept.
        assert len(capped) == 3  # SYS1, SYS2, user C
        assert dropped == 2
        assert all(m["role"] == "system" for m in capped[:2])
        assert capped[2]["role"] == "user"


# ---------------------------------------------------------------------------
# Last user message never dropped
# ---------------------------------------------------------------------------


class TestLastUserMessagePreserved:
    """Last user message is always kept."""

    def test_last_user_never_dropped(self) -> None:
        msgs = [
            _msg("system", "System."),
            _msg("user", "Old query"),
            _msg("assistant", "Old answer"),
            _msg("user", "Current query"),
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=0, estimate=_estimate)
        # Only system + last user should remain.
        assert capped[-1]["role"] == "user"
        assert capped[-1]["content"] == "Current query"


# ---------------------------------------------------------------------------
# Tool-call / tool-result pairing
# ---------------------------------------------------------------------------


class TestToolCallPairing:
    """Tool calls and their results are kept or dropped together."""

    def test_tool_call_dropped_with_result(self) -> None:
        """Assistant tool call + its tool result are both dropped."""
        msgs = [
            _msg("system", "System."),
            _msg("user", "A" * 80),
            _msg("assistant", "Thinking...", tool_calls=[{
                "id": "tc1",
                "function": {"name": "read_file", "arguments": '{"path": "a.py"}'},
            }]),
            _msg("tool", "Content: file contents", tool_call_id="tc1"),
            _msg("assistant", "Done", tool_calls=[{
                "id": "tc2",
                "function": {"name": "write_file", "arguments": '{"path": "b.py"}'},
            }]),
            _msg("tool", "Content: written", tool_call_id="tc2"),
            _msg("user", "Current"),
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=20, estimate=_estimate)
        # Both tool call + result pairs should be kept or dropped together.
        # No orphaned tool calls or results.
        tool_call_ids: set[str] = set()
        tool_result_ids: set[str] = set()
        for m in capped:
            for tc in m.get("tool_calls", []) or []:
                if isinstance(tc, dict) and tc.get("id"):
                    tool_call_ids.add(tc["id"])
            if m.get("role") == "tool" and m.get("tool_call_id"):
                tool_result_ids.add(m["tool_call_id"])
        # Every tool result must have a matching call.
        assert tool_result_ids - tool_call_ids == set(), "Orphaned tool result found"

    def test_tool_result_dropped_with_call(self) -> None:
        """Tool call/result pair dropped together when budget exhausted."""
        msgs = [
            _msg("system", "System."),
            _msg("user", "A" * 80),       # ~20 tokens — dropped
            _msg("assistant", "X" * 40, tool_calls=[{
                "id": "tc1",
                "function": {"name": "tool", "arguments": "{}"},
            }]),                         # ~10 tokens — dropped (paired with result)
            _msg("tool", "Result", tool_call_id="tc1"),  # ~1 token — dropped (paired with call)
            _msg("user", "Current"),      # ~1 token — kept
        ]
        # Budget = 0. The tool-result(1)+assistant(10) group: 0+11=11 > 0.
        # So even Current(1) can't fit with anything. Only Current stays.
        capped, dropped = cap_history(msgs, max_history_tokens=0, estimate=_estimate)
        assert dropped == 3  # A, assistant(tc1), tool(tc1)
        # tc1 pair should be dropped; only system + user Current remain.
        assert len(capped) == 2
        assert capped[0]["role"] == "system"
        assert capped[1]["role"] == "user"
        for m in capped:
            tc_list = m.get("tool_calls", []) or []
            for tc in tc_list:
                if isinstance(tc, dict) and tc.get("id") == "tc1":
                    pytest.fail("tc1 should have been dropped")
            if m.get("tool_call_id") == "tc1":
                pytest.fail("tc1 result should have been dropped")


# ---------------------------------------------------------------------------
# List-form content counted correctly
# ---------------------------------------------------------------------------


class TestListContentCounting:
    """List-form content is counted correctly."""

    def test_list_content_estimated(self) -> None:
        msgs = [
            _msg("system", "System."),
            _msg("user", [{"type": "text", "text": "A" * 80}]),
            _msg("assistant", [{"type": "text", "text": "B" * 80}]),
            _msg("user", [{"type": "text", "text": "Current"}]),
        ]
        # A=20, B=20, Current=1. Budget=20.
        # candidates=[A,B], walked reversed [B,A].
        # B(20) ≤ 20 → kept, acc=20. A(20): 20+20=40 > 20 → break.
        # kept = {B} + {Current}. dropped = A = 1.
        capped, dropped = cap_history(msgs, max_history_tokens=20, estimate=_estimate)
        assert dropped == 1
        assert len(capped) == 3  # system + B + current user
        assert capped[0]["role"] == "system"
        assert capped[1]["role"] == "assistant"  # B kept (processed first, newest)
        assert isinstance(capped[1]["content"], list)
        assert capped[2]["role"] == "user"  # Current (last user, always kept)
        assert isinstance(capped[2]["content"], list)

    def test_string_content_still_works(self) -> None:
        """String content also counted correctly."""
        msgs = [
            _msg("system", "System."),
            _msg("user", "A" * 80),
            _msg("assistant", "B" * 80),
            _msg("user", "Current"),
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=20, estimate=_estimate)
        assert dropped == 1
        assert len(capped) == 3


# ---------------------------------------------------------------------------
# Budget derivation and settings
# ---------------------------------------------------------------------------


class TestBudgetDerivation:
    """Budget derivation from context_window."""

    def test_budget_zero_means_minimal_capping(self) -> None:
        """max_history_tokens=0 → budget 0 means drop all candidates.
        Only system + last user remain."""
        msgs = [
            _msg("system", "System."),
            _msg("user", "Hello"),      # ~1 token
            _msg("assistant", "Hi there"),  # ~2 tokens
            _msg("user", "Current"),     # ~1 token
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=0, estimate=_estimate)
        # Budget 0 → no candidates fit (both Hello=1 and Hi=1 > 0).
        # dropped = 2 (Hello, Hi there).
        assert dropped == 2
        assert len(capped) == 2
        assert capped[0]["role"] == "system"
        assert capped[1]["role"] == "user"
        assert capped[1]["content"] == "Current"


class TestNoOpUnderBudget:
    """When nothing needs dropping, returned unchanged."""

    def test_noop_returns_identical(self) -> None:
        msgs = [
            _msg("system", "System."),
            _msg("user", "Hi"),
            _msg("assistant", "Hello"),
            _msg("user", "How are you?"),
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=10000, estimate=_estimate)
        assert dropped == 0
        assert capped is msgs  # Should return the original list (no-op).


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases for history capping."""

    def test_only_system_messages(self) -> None:
        msgs = [
            _msg("system", "SYS1"),
            _msg("system", "SYS2"),
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=0, estimate=_estimate)
        assert dropped == 0
        assert len(capped) == 2

    def test_single_user_message(self) -> None:
        msgs = [_msg("user", "Hello")]
        capped, dropped = cap_history(msgs, max_history_tokens=0, estimate=_estimate)
        assert dropped == 0
        assert len(capped) == 1
        assert capped[0]["role"] == "user"

    def test_no_system_messages(self) -> None:
        # Use large content so tokens exceed budget.
        msgs = [
            _msg("user", "O" * 40),       # ~10 tokens
            _msg("assistant", "A" * 40),  # ~10 tokens
            _msg("user", "Current"),      # ~2 tokens
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=5, estimate=_estimate)
        # Budget 5 fits only Current (2 tokens).
        assert len(capped) == 1
        assert capped[0]["role"] == "user"
        assert capped[0]["content"] == "Current"


# ---------------------------------------------------------------------------
# Fix 2: Multi-tool-call grouping
# ---------------------------------------------------------------------------


class TestMultiToolCallGrouping:
    """Multi-tool-call messages keep ALL their results together."""

    def test_two_tool_calls_both_results_kept(self) -> None:
        """Assistant with TWO tool calls: both results kept together."""
        msgs = [
            _msg("system", "System."),
            _msg("user", "Do both" * 20),        # ~10 tokens
            _msg("assistant", "Processing...", tool_calls=[
                {"id": "tc1", "function": {"name": "tool_a", "arguments": '{"x":1}'}},
                {"id": "tc2", "function": {"name": "tool_b", "arguments": '{"y":2}'}},
            ]),
            _msg("tool", "Result A", tool_call_id="tc1"),
            _msg("tool", "Result B", tool_call_id="tc2"),
            _msg("user", "Current"),
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=1000, estimate=_estimate)
        # Under budget → nothing dropped.
        assert dropped == 0
        assert len(capped) == len(msgs)

    def test_two_tool_calls_both_results_dropped_together(self) -> None:
        """When budget exhausted, BOTH results are dropped with the assistant."""
        msgs = [
            _msg("system", "System."),
            _msg("user", "A" * 80),        # ~20 tokens — dropped
            _msg("assistant", "Work...", tool_calls=[
                {"id": "tc1", "function": {"name": "tool_a", "arguments": '{"x":1}'}},
                {"id": "tc2", "function": {"name": "tool_b", "arguments": '{"y":2}'}},
            ]),
            _msg("tool", "Result A", tool_call_id="tc1"),
            _msg("tool", "Result B", tool_call_id="tc2"),
            _msg("user", "Current"),
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=0, estimate=_estimate)
        # Budget 0 → only system + current user kept.
        assert dropped == 4  # A, assistant, tc1 result, tc2 result
        assert len(capped) == 2
        assert capped[0]["role"] == "system"
        assert capped[1]["role"] == "user"
        assert capped[1]["content"] == "Current"
        # No orphaned tool ids.
        for m in capped:
            for tc in m.get("tool_calls", []) or []:
                assert tc.get("id") not in ("tc1", "tc2")
            assert m.get("tool_call_id") not in ("tc1", "tc2")

    def test_no_orphan_single_result(self) -> None:
        """Never keep one result without the other for a 2-call assistant."""
        msgs = [
            _msg("system", "System."),
            _msg("user", "A" * 80),
            _msg("assistant", "Work...", tool_calls=[
                {"id": "tc1", "function": {"name": "tool_a", "arguments": '{"x":1}'}},
                {"id": "tc2", "function": {"name": "tool_b", "arguments": '{"y":2}'}},
            ]),
            _msg("tool", "Result A", tool_call_id="tc1"),
            _msg("tool", "Result B", tool_call_id="tc2"),
            _msg("assistant", "Done"),
            _msg("user", "Current"),
        ]
        # Tight budget that fits only system + last user + the "Done" assistant.
        capped, dropped = cap_history(msgs, max_history_tokens=5, estimate=_estimate)
        # The 2-call group (assistant+2 results) is a single atomic unit.
        # Check no orphans: every tc id must have its result and vice versa.
        call_ids: set[str] = set()
        result_ids: set[str] = set()
        for m in capped:
            for tc in m.get("tool_calls", []) or []:
                if isinstance(tc, dict) and tc.get("id"):
                    call_ids.add(tc["id"])
            if m.get("role") == "tool" and m.get("tool_call_id"):
                result_ids.add(m["tool_call_id"])
        assert result_ids - call_ids == set(), "Orphaned tool result found"
        assert call_ids - result_ids == set(), "Orphaned tool call found"


# ---------------------------------------------------------------------------
# Fix 3: Large current user message doesn't trip capping of fitting history
# ---------------------------------------------------------------------------


class TestFix3LargeCurrentMessage:
    """History that fits budget should NOT be dropped just because current
    user message is very large."""

    def test_large_current_does_not_drop_fitting_history(self) -> None:
        """Old history fits budget, large current message is kept outside budget.
        History should NOT be dropped."""
        # Old history = 10 tokens total. Budget = 20 tokens.
        # Current user message = 100 tokens (25 tokens).
        # Total non-system = 10 + 25 = 35 > 20, but the old history (10)
        # alone fits the budget (20). So nothing should be dropped.
        msgs = [
            _msg("system", "System."),
            _msg("user", "A" * 40),       # ~10 tokens — old history
            _msg("assistant", "B" * 40),  # ~10 tokens — old history
            # Total old history = 20 tokens ≤ budget = 20 → fits exactly.
            _msg("user", "C" * 400),      # ~100 tokens — large current user
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=20, estimate=_estimate)
        # The old history (A + B = 20 tokens) fits exactly within budget (20).
        # The large current user is always kept outside the budget.
        # Therefore, nothing should be dropped.
        assert dropped == 0
        assert len(capped) == len(msgs)

    def test_old_history_over_budget_still_drops(self) -> None:
        """Old history that itself exceeds budget SHOULD be dropped."""
        msgs = [
            _msg("system", "System."),
            _msg("user", "A" * 200),      # ~50 tokens — old history
            _msg("assistant", "B" * 200), # ~50 tokens — old history
            # Total old history = 100 tokens > budget = 20
            _msg("user", "Current"),      # ~1 token — large current user
        ]
        capped, dropped = cap_history(msgs, max_history_tokens=20, estimate=_estimate)
        # Old history (100 tokens) > budget (20). Capping should engage.
        assert dropped > 0
        # Last user message always present.
        assert capped[-1]["role"] == "user"
        assert capped[-1]["content"] == "Current"


# ---------------------------------------------------------------------------
# Current Cline tool result compression
# ---------------------------------------------------------------------------


class TestCurrentClineToolResultCompression:
    """Oversized Cline tool-result envelopes are capped in place."""

    def test_current_cline_tool_result_is_truncated(self) -> None:
        msgs = [
            _msg("system", "System."),
            _msg("user", "Original task"),
            _msg(
                "user",
                "[search_files for 'answer_preview'] Result:\n" + ("X" * 1000),
            ),
        ]

        capped, dropped = cap_history(
            msgs,
            max_history_tokens=1000,
            estimate=_estimate,
            max_current_tool_result_tokens=20,
        )

        assert dropped == 0
        assert capped[-1]["role"] == "user"
        assert len(capped[-1]["content"]) <= 80
        assert "truncated by gateway history cap" in capped[-1]["content"]

    def test_current_regular_user_prompt_is_not_truncated(self) -> None:
        current = "Please inspect this deliberately long prompt: " + ("X" * 1000)
        msgs = [
            _msg("system", "System."),
            _msg("user", "Original task"),
            _msg("user", current),
        ]

        capped, dropped = cap_history(
            msgs,
            max_history_tokens=1000,
            estimate=_estimate,
            max_current_tool_result_tokens=20,
        )

        assert dropped == 0
        assert capped[-1]["content"] == current

    @pytest.mark.parametrize("tool", ("write_to_file", "replace_in_file"))
    def test_current_writer_result_is_not_truncated(self, tool: str) -> None:
        """Roadmap C1 measures a writer's result; it does not shorten what the model sees.

        A Cline write or replace result carries the file's whole new content, and the
        activity path needs nothing from it but one status token out of the first line.
        Capping it would change the prompt, which is outside C1's observability scope,
        so it stays byte-identical even though the envelope is now recognized.
        """
        current = (
            f"[{tool} for 'packages/demo/widget.py'] Result:\n"
            "The file was successfully saved.\n" + ("X" * 1000)
        )
        msgs = [
            _msg("system", "System."),
            _msg("user", "Original task"),
            _msg("user", current),
        ]

        capped, dropped = cap_history(
            msgs,
            max_history_tokens=1000,
            estimate=_estimate,
            max_current_tool_result_tokens=20,
        )

        assert dropped == 0
        assert capped[-1]["content"] == current
        assert "truncated by gateway history cap" not in capped[-1]["content"]

    @pytest.mark.parametrize(
        "tool", ("read_file", "search_files", "list_files", "execute_command")
    )
    def test_pre_c1_tool_results_are_capped_exactly_as_before(self, tool: str) -> None:
        """The four envelopes the gateway has always capped are still capped.

        Args:
            tool: A Cline tool whose result was bookkeeping before roadmap C1 and is
                bookkeeping after it - the derived compatibility view must not have
                narrowed while it was being prevented from widening.
        """
        current = f"[{tool} for 'packages/demo/widget.py'] Result:\n" + ("X" * 1000)
        msgs = [
            _msg("system", "System."),
            _msg("user", "Original task"),
            _msg("user", current),
        ]

        capped, dropped = cap_history(
            msgs,
            max_history_tokens=1000,
            estimate=_estimate,
            max_current_tool_result_tokens=20,
        )

        assert dropped == 0
        assert len(capped[-1]["content"]) <= 80
        assert "truncated by gateway history cap" in capped[-1]["content"]

    def test_capping_reads_the_shared_table_instead_of_its_own_copy(self) -> None:
        """One prefix table, two consumers: this module holds no literal list any more."""
        from packages.pipeline import history as history_module
        from packages.pipeline import user_messages

        assert (
            history_module.CLINE_TOOL_RESULT_PREFIXES
            is user_messages.CLINE_TOOL_RESULT_PREFIXES
        )


# ---------------------------------------------------------------------------
# Fix 1: Engine integration - resolved_model typed field drives budget
# ---------------------------------------------------------------------------


class TestFix1ResolvedModelBudget:
    """History capping derives its budget from the resolved model's real window."""

    def test_apply_history_cap_docstring_mentions_env_override(self) -> None:
        """Context docs for the promoted helper should name the env override."""
        docstring = inspect.getdoc(_apply_history_cap) or ""

        assert "APP_HISTORY_CAP_TOKENS" in docstring
        assert "history_cap_tokens" in docstring
        assert "max_tokens_override" in docstring
        assert "not the forced" in docstring

    def test_apply_history_cap_updates_request_when_only_current_tool_result_truncates(
        self,
    ) -> None:
        """Current tool-result truncation updates the provider-bound request."""
        context = PipelineContext(
            request={
                "messages": [
                    _msg("system", "System."),
                    _msg("user", "Original task"),
                    _msg(
                        "user",
                        "[search_files for 'answer_preview'] Result:\n" + ("X" * 1000),
                    ),
                ],
                "model": "qwen36",
            }
        )
        context.normalized_request = NormalizedRequest.from_client(context.request)
        context.set_metadata("history_cap_tokens", 20)

        _apply_history_cap(context, resolved_model=None, max_tokens_override=None)

        assert context.normalized_request is not None
        capped = context.normalized_request.messages
        assert len(capped) == 3
        assert context.get_metadata("history_dropped_count") == 0
        assert "truncated by gateway history cap" in capped[-1]["content"]

    def test_engine_derives_budget_from_resolved_model_context_window(self) -> None:
        """The derived budget is built from the window the routed model really has.

        ``ModelResolutionStage`` stores the router's ``ResolvedModel``, and that
        type carries no ``context_window`` of its own - the configuration lives
        one level down on ``definition`` (`packages/providers/models.py`).  The
        derivation read the resolved object first, so ``getattr`` answered 8192
        for every request in the registry and the ``definition`` fallback below it
        could never run: the budget was derived from a window no model has.  The
        claim is made against the real type, on a window chosen so the model's
        answer and the old 8192 answer cannot agree.
        """
        window = 128000  # anything but the 8192 the fallback answers with

        def budget_with(max_tokens_override: int | None) -> Any:
            run = _derived_budget(_resolved(context_window=window), max_tokens_override)
            assert run["applied"] is True
            return run["budget"]

        # window - generation reserve - repo-context reserve - safety margin,
        # the three reserves this path has always subtracted.
        assert budget_with(2048) == window - 2048 - 1024 - 512
        # The generation reserve is subtracted, and nothing else moved it.
        assert budget_with(2048) - budget_with(4096) == 4096 - 2048
        # A request that sets no max_tokens is priced at the 2048 it always was.
        assert budget_with(None) == budget_with(2048)
        # It is the routed model's window that produced the number, not the
        # default the broken read returned for every model in the registry.
        assert budget_with(2048) != 8192 - 2048 - 1024 - 512

    def test_derived_budget_estimates_with_the_models_ratio(self) -> None:
        """Calibration reaches the derived branch, not only the forced one.

        One window, chosen so the budget it derives is the 3,000 tokens this
        file's boundary transcript straddles: 6,584 less the 2,048 generation,
        1,024 repo-context and 512 safety reserves.  Same window, same derived
        budget, same payload; the only difference between the runs is what the
        model's definition says a character is worth.
        """
        platform = _derived_budget(_resolved(context_window=6584))
        calibrated = _derived_budget(_resolved(context_window=6584, chars_per_token=3.5))

        assert platform["budget"] == calibrated["budget"] == 3000
        assert platform["ratio"] == 4.0
        assert calibrated["ratio"] == 3.5
        assert platform["dropped_count"] == 0
        assert calibrated["dropped_count"] == 3
        assert calibrated["tokens_after"] == _tokens_at(calibrated["messages"], 3.5)

    def test_derived_budget_reads_every_supported_model_shape(self) -> None:
        """The definition shape, the legacy shape, and which one wins.

        A real ``ResolvedModel`` is what production passes and what the
        correction is for.  A window on the resolved object itself is the older
        shape this code was written against and keeps working, so when an object
        offers both, the definition is the one believed - it is the configuration
        the request actually routed to.
        """
        # The shape ModelResolutionStage stores.
        assert _derived_budget(_resolved(context_window=128000))["budget"] == 128000 - 3584
        # A real model that names no window still has one: the definition's own
        # default, not the derivation's 8192.
        assert _derived_budget(_resolved())["budget"] == 131072 - 3584
        # The legacy object whose window sits on the object itself.
        assert _derived_budget(_WindowModel(128000))["budget"] == 128000 - 3584
        # Both shapes at once - the definition is believed.
        both = _TwoShapeModel(_definition(context_window=128000), 65536)
        assert _derived_budget(both)["budget"] == 128000 - 3584
        # A definition carrying nothing usable hands the derivation to a window
        # on the object rather than to the default.
        rescued = _TwoShapeModel(_definition(context_window=None), 65536)
        assert _derived_budget(rescued)["budget"] == 65536 - 3584

    @pytest.mark.parametrize(
        "bad_window",
        (None, 0, 0.0, -1, "131072", True, float("nan"), float("inf")),
    )
    def test_unusable_context_window_keeps_the_default(
        self, bad_window: Any
    ) -> None:
        """A window that is not a window leaves the 8192 this path used before.

        Args:
            bad_window: A value a model definition might carry that cannot be a
                context window - absent, empty, negative, a string, a boolean, or
                not a finite number.
        """
        run = _derived_budget(_resolved(context_window=bad_window))

        assert run["budget"] == 8192 - 3584
        assert run["applied"] is True
        # The calibration is a separate read, and it still comes from the model.
        assert run["ratio"] == 4.0

    def test_derived_budget_that_leaves_no_room_caps_nothing(self) -> None:
        """A window the reserves eat up does not cap, and does not pretend to.

        Nothing is recorded and the request bound for the provider is the object
        that came in - on the production shape and on the legacy one alike.
        """
        starved = _context_with(_boundary_transcript())
        starved.set_metadata("history_cap_tokens", 0)
        before_starved = starved.normalized_request

        _apply_history_cap(starved, _resolved(context_window=3000), max_tokens_override=2048)

        assert not starved.get_metadata("history_cap_applied", False)
        assert not starved.get_metadata("history_cap_budget", 0)
        assert starved.normalized_request is before_starved
        assert _contents(starved.normalized_request.messages) == _contents(
            _boundary_transcript()
        )
        assert _derived_budget(_WindowModel(3000))["applied"] is False

    def test_engine_falls_back_when_resolved_model_is_none(self) -> None:
        """No resolved model and no explicit budget leaves the request alone.

        Capping enabled with neither a budget to force nor a model to derive one
        from is not an instruction to drop anything, so nothing is applied,
        nothing is recorded, and the request bound for the provider is untouched.
        """
        context = _context_with(_boundary_transcript())
        untouched = context.normalized_request

        _apply_history_cap(context, resolved_model=None, max_tokens_override=None)

        assert context.normalized_request is untouched
        assert _contents(context.normalized_request.messages) == _contents(
            _boundary_transcript()
        )
        assert not context.get_metadata("history_cap_applied", False)
        assert not context.get_metadata("history_tokens_after", 0)

    def test_engine_caps_at_the_default_ratio_without_a_definition(self) -> None:
        """A resolved model with no definition still caps, at 4.0.

        The ratio is absent rather than wrong here, which is the case the safe
        fallback exists for: an explicit budget was given, so capping still
        runs, and the estimate it runs on is the platform's.
        """
        run = _cap_run(_BareResolvedModel())

        assert run["ratio"] == 4.0
        assert run["budget"] == 3000
        assert run["applied"] is True
        assert run["dropped_count"] == 0
        assert len(run["messages"]) == 7

    def test_explicit_history_cap_tokens_bypasses_resolved_model(self) -> None:
        """An explicit token budget wins for the budget, on every model shape.

        This model's window would derive no capping at all once the reserves are
        taken off it, and ``APP_HISTORY_CAP_TOKENS`` says 3000 - so 3000 is what
        the pass runs on, and the request is capped.  The real ``ResolvedModel``
        and the legacy window-on-the-object stand-in are both checked because the
        correction touched how this function reads a model at all.
        """
        for model in (_resolved(context_window=1024), _WindowModel(1024)):
            run = _cap_run(model)

            assert run["budget"] == 3000
            assert run["applied"] is True
            # Take the forced budget away and the same model derives nothing.
            assert not _cap_run(model, cap_tokens=0)["applied"]

    def test_explicit_budget_forwarding_ignores_the_context_window(self) -> None:
        """The window correction cannot move what the live A/B measured.

        Both arms of roadmap A3's controlled Cline run set
        ``APP_HISTORY_CAP_TOKENS=3000``, which selects the explicit branch before
        any window is consulted, and both ran on the model's calibrated 3.5.  So
        the routed model's window is what varies here: the 262,144 the live alias
        really carries, the 8192 the broken read returned for every model, and a
        window too small to derive a budget at all.  One transcript, one forced
        budget, one answer - which is the claim the recorded live evidence rests
        on, and the reason it does not have to be re-run.
        """
        arms = [
            _cap_run(_resolved(chars_per_token=3.5, context_window=window))
            for window in (262144, 8192, 1024)
        ]

        assert {run["budget"] for run in arms} == {3000}
        assert {run["applied"] for run in arms} == {True}
        assert {run["dropped_count"] for run in arms} == {3}
        assert {len(run["messages"]) for run in arms} == {4}
        assert _contents(arms[0]["messages"]) == _contents(arms[1]["messages"])
        assert _contents(arms[1]["messages"]) == _contents(arms[2]["messages"])
        assert {run["tokens_after"] for run in arms} == {arms[0]["tokens_after"]}


# ---------------------------------------------------------------------------
# Roadmap A3: calibrated history-cap estimation
# ---------------------------------------------------------------------------


class TestCalibratedCapBoundary:
    """``cap_history`` estimates at the ratio it is given, not at a constant.

    Each case pairs two runs of one transcript under one budget, so the only
    thing that can move the answer is the characters-per-token ratio.
    """

    def test_ratio_moves_the_cap_boundary(self) -> None:
        """The same transcript and budget keeps everything at 4.0, drops at 3.5."""
        msgs = _boundary_transcript()

        kept, dropped_default = cap_history(msgs, 3000, chars_per_token=4.0)
        capped, dropped_calibrated = cap_history(msgs, 3000, chars_per_token=3.5)

        assert dropped_default == 0
        assert kept == msgs
        assert len(capped) < len(msgs)
        assert dropped_calibrated == 3
        # What the boundary removed is the oldest tool result and the turns that
        # predate it - and nothing newer.
        assert msgs[3]["content"] not in [m["content"] for m in capped]
        assert msgs[4]["content"] in [m["content"] for m in capped]
        assert msgs[5]["content"] in [m["content"] for m in capped]
        assert capped[0]["role"] == "system"
        assert capped[-1] is msgs[-1]

    def test_ratio_is_counted_in_the_text_a_tool_call_carries(self) -> None:
        """A call whose only text is its name and arguments still moves.

        Before roadmap A3 this case could not move: `cap_history` has taken an
        ``estimate`` argument since it was written and never called it, counting
        every message through a module-level constant instead.
        """
        msgs = [
            _msg("system", "System."),
            _msg(
                "assistant",
                "",
                tool_calls=[
                    {
                        "id": "tc1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "a" * 3960},
                    }
                ],
            ),
            _msg("tool", "ok", tool_call_id="tc1"),
            _msg("user", "And now?"),
        ]

        kept, dropped_default = cap_history(msgs, 1000, chars_per_token=4.0)
        capped, dropped_calibrated = cap_history(msgs, 1000, chars_per_token=3.5)

        assert dropped_default == 0
        assert kept == msgs
        # 992 tokens of call at 4.0 fits a 1,000 budget; 1,133 at 3.5 does not,
        # and the call and its result go together.
        assert dropped_calibrated == 2
        assert [m["role"] for m in capped] == ["system", "user"]

    def test_estimate_callable_reaches_the_counting(self) -> None:
        """The estimator a caller supplies is the estimator that runs."""
        seen: list[str] = []

        def estimate(text: str) -> int:
            seen.append(text)
            return 1 if text else 0

        msgs = _boundary_transcript()

        capped, dropped = cap_history(msgs, 4, estimate=estimate, chars_per_token=3.5)
        assert dropped == 1
        assert len(capped) == 6
        assert any(text.startswith("[read_file for ") for text in seen)

        everything, kept_all = cap_history(msgs, 6, estimate=estimate)
        assert kept_all == 0
        assert everything == msgs

    def test_default_ratio_is_the_platform_estimate(self) -> None:
        """Leaving the ratio out is the same run as asking for 4.0."""
        msgs = _boundary_transcript()

        omitted, dropped_omitted = cap_history(msgs, 3000)
        explicit, dropped_explicit = cap_history(msgs, 3000, chars_per_token=4.0)
        by_estimate, dropped_by_estimate = cap_history(
            msgs, 3000, estimate=lambda text: int(len(text) / 4.0) if text else 0
        )

        assert dropped_omitted == dropped_explicit == dropped_by_estimate == 0
        assert _contents(omitted) == _contents(explicit) == _contents(by_estimate)

    @pytest.mark.parametrize("budget", (20, 200))
    def test_current_envelope_truncation_shares_the_ratio(self, budget: int) -> None:
        """The budget-to-characters conversion uses the ratio the counting used.

        Args:
            budget: Tokens the current Cline envelope is capped to.
        """
        msgs = [
            _msg("system", "System."),
            _msg("user", "Earlier task"),
            _msg("user", _envelope("search_files", "cap_history", 4000)),
        ]

        default_capped, _ = cap_history(
            msgs,
            3000,
            max_current_tool_result_tokens=budget,
            chars_per_token=4.0,
        )
        calibrated_capped, _ = cap_history(
            msgs,
            3000,
            max_current_tool_result_tokens=budget,
            chars_per_token=3.5,
        )

        default_text = default_capped[-1]["content"]
        calibrated_text = calibrated_capped[-1]["content"]
        assert default_text.endswith(TRUNCATION_MARKER)
        assert calibrated_text.endswith(TRUNCATION_MARKER)
        assert len(default_text) == int(budget * 4.0)
        assert len(calibrated_text) == int(budget * 3.5)
        assert len(calibrated_text) < len(default_text)

    @pytest.mark.parametrize(
        "ratio",
        (0, 0.0, -4.0, float("nan"), float("inf"), 1e9, 0.1, "3.5", True, None),
    )
    def test_unusable_ratio_cannot_break_the_math(self, ratio: Any) -> None:
        """Nothing a definition could carry makes the pass fail, invert, or stop.

        Zero would raise on the division, a negative ratio would make longer text
        look cheaper, and NaN compares false against every budget and so caps
        nothing at all.  All three deserve a case, because the number arrives
        from configuration.

        Args:
            ratio: A value that must never reach the arithmetic.
        """
        msgs = _boundary_transcript()

        capped, dropped = cap_history(msgs, 3000, chars_per_token=ratio)
        reference, dropped_reference = cap_history(msgs, 3000, chars_per_token=4.0)

        assert dropped == dropped_reference == 0
        assert _contents(capped) == _contents(reference)

    def test_ratio_bounds_match_the_provider_registry(self) -> None:
        """The range this honors is the range ``chars_per_token`` may be set to.

        A ratio at either documented bound is used for what it says; a value just
        outside either bound is not, and that run behaves like the platform
        estimate it fell back to.
        """
        msgs = _boundary_transcript()

        at_floor, dropped_floor = cap_history(msgs, 1000, chars_per_token=RATIO_MIN)
        below_floor, dropped_below = cap_history(
            msgs, 1000, chars_per_token=RATIO_MIN - 0.01
        )
        at_ceiling, dropped_ceiling = cap_history(msgs, 1000, chars_per_token=RATIO_MAX)
        above_ceiling, dropped_above = cap_history(
            msgs, 1000, chars_per_token=RATIO_MAX + 0.1
        )
        reference, dropped_reference = cap_history(msgs, 1000, chars_per_token=4.0)

        # Fewer characters per token makes the same text worth more, so it drops
        # more of it; the opposite at the ceiling.
        assert dropped_floor > dropped_reference > dropped_ceiling
        # Outside the range, both ways, is the platform estimate again - the same
        # forwarded messages, not merely the same count.
        assert dropped_below == dropped_above == dropped_reference
        assert _contents(below_floor) == _contents(reference)
        assert _contents(above_ceiling) == _contents(reference)
        assert CHARS_PER_TOKEN == 4.0



class TestCalibratedRatioThroughTheEngine:
    """The live path resolves the ratio off the model it actually routed to."""

    def test_resolved_model_ratio_moves_the_forwarded_history(self) -> None:
        """The request's resolved ``chars_per_token`` is what caps it."""
        calibrated = _cap_run(_resolved(chars_per_token=3.5))
        default = _cap_run(_resolved(chars_per_token=4.0))

        assert calibrated["ratio"] == 3.5
        assert default["ratio"] == 4.0
        assert calibrated["budget"] == default["budget"] == 3000
        assert calibrated["applied"] is True and default["applied"] is True
        assert default["dropped_count"] == 0
        assert _contents(default["messages"]) == _contents(default["sent"])
        assert calibrated["dropped_count"] == 3
        assert len(calibrated["messages"]) == len(default["messages"]) - 3
        # One ratio per run: the size recorded is the size of what is forwarded.
        assert calibrated["tokens_after"] == _tokens_at(calibrated["messages"], 3.5)
        assert default["tokens_after"] == _tokens_at(default["messages"], 4.0)
        assert calibrated["tokens_after"] < default["tokens_after"]

    def test_model_without_override_keeps_prior_behavior(self) -> None:
        """A definition that never mentioned the field caps exactly as before.

        ``ModelDefinition.chars_per_token`` defaults to 4.0, and the request that
        resolves it has to forward what the pre-roadmap-A3 engine forwarded: same
        messages, same dropped count, same recorded size.
        """
        definition = ModelDefinition(
            model="qwen-undertest",
            provider="openai",
            base_url="http://127.0.0.1:1/v1",
        )
        assert definition.chars_per_token == 4.0  # the default A3 had to preserve

        inherited = _cap_run(
            ResolvedModel(definition=definition, provider=_NULL_PROVIDER)
        )
        explicit = _cap_run(_resolved(chars_per_token=4.0))
        without_model = _cap_run(None)

        assert _contents(inherited["messages"]) == _contents(explicit["messages"])
        assert _contents(without_model["messages"]) == _contents(inherited["messages"])
        assert inherited["dropped_count"] == explicit["dropped_count"] == 0
        assert inherited["tokens_after"] == explicit["tokens_after"]
        assert inherited["ratio"] == without_model["ratio"] == 4.0

    @pytest.mark.parametrize("bad_ratio", (None, 0, "3.5", float("nan"), -2.0, True, 1e9))
    def test_engine_falls_back_to_the_safe_ratio(self, bad_ratio: Any) -> None:
        """An unusable calibration cannot reach the division through the engine.

        Args:
            bad_ratio: A value a model definition might carry that is not a
                characters-per-token ratio.
        """
        run = _cap_run(_resolved(chars_per_token=bad_ratio))
        reference = _cap_run(_resolved(chars_per_token=4.0))

        assert run["ratio"] == 4.0
        assert run["budget"] == 3000  # the explicit budget still applies
        assert run["applied"] is True
        assert run["dropped_count"] == reference["dropped_count"] == 0
        assert _contents(run["messages"]) == _contents(reference["messages"])
        assert run["tokens_after"] == reference["tokens_after"]

    def test_ratio_and_explicit_budget_are_separate_knobs(self) -> None:
        """The ratio changes what text is worth; the budget changes the budget.

        ``APP_HISTORY_CAP_TOKENS`` stays a token count whatever the calibration
        says: at 3.5 a tighter budget drops more of the same transcript, and the
        number recorded as the budget is the number that was asked for.
        """
        tight = _cap_run(_resolved(chars_per_token=3.5), cap_tokens=2000)
        wide = _cap_run(_resolved(chars_per_token=3.5), cap_tokens=3000)
        platform = _cap_run(_resolved(chars_per_token=4.0), cap_tokens=3000)

        assert tight["budget"] == 2000
        assert wide["budget"] == platform["budget"] == 3000
        assert tight["dropped_count"] > wide["dropped_count"] > platform["dropped_count"]



    def test_session_metadata_describes_the_forwarded_payload(self) -> None:
        """Budget, dropped count, applied state and size agree on one payload.

        These four fields are what a session record turns into
        ``history.{budget,dropped_count,cap_applied,tokens_after}``, and the
        claim they make is about the request that actually goes out.
        """
        for ratio, expected_dropped in ((4.0, 0), (3.5, 3)):
            context = _context_with(_boundary_transcript())
            context.set_metadata("history_cap_tokens", 3000)
            sent = list(context.normalized_request.messages)

            _apply_history_cap(
                context,
                resolved_model=_resolved(chars_per_token=ratio),
                max_tokens_override=None,
            )
            forwarded = context.normalized_request.messages

            assert context.get_metadata("history_cap_budget") == 3000
            assert context.get_metadata("history_cap_applied") is True
            assert context.get_metadata("history_dropped_count") == expected_dropped
            assert len(forwarded) == len(sent) - expected_dropped
            assert context.get_metadata("history_tokens_after") == _tokens_at(
                forwarded, ratio
            )

    def test_protected_messages_and_pairing_survive_the_boundary(self) -> None:
        """System, current turn and tool pairing hold at the calibrated boundary."""
        msgs = [
            _msg("system", "System."),
            _msg(
                "assistant",
                "",
                tool_calls=[
                    {
                        "id": "tc1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "a" * 1600},
                    }
                ],
            ),
            _msg("tool", "ok", tool_call_id="tc1"),
            _msg("user", _envelope("search_files", "cap_history", 1600)),
            _msg("user", CLINE_QUESTION),
        ]
        run = _cap_run(_resolved(chars_per_token=3.5), cap_tokens=500, messages=msgs)
        forwarded = run["messages"]

        assert run["dropped_count"] == 2
        assert [m["role"] for m in forwarded] == ["system", "user", "user"]
        assert forwarded[-1]["content"] == CLINE_QUESTION
        calls = {
            tc["id"]
            for m in forwarded
            for tc in (m.get("tool_calls") or [])
            if isinstance(tc, dict) and tc.get("id")
        }
        results = {m["tool_call_id"] for m in forwarded if m.get("role") == "tool"}
        assert calls == results  # never a call without its result, or the reverse

    @pytest.mark.parametrize("tool", ("write_to_file", "replace_in_file"))
    def test_writer_results_stay_whole_at_the_calibrated_ratio(self, tool: str) -> None:
        """C1 measures a writer's result; the calibrated cap still never shortens it.

        Args:
            tool: A Cline writer whose result carries the file's new content.
        """
        body = (
            f"[{tool} for 'packages/demo/widget.py'] Result:\n"
            "The file was successfully saved.\n" + ("x" * 4000)
        )
        msgs = [
            _msg("system", "System."),
            _msg("user", "Earlier task"),
            _msg("user", body),
        ]
        for ratio in (3.5, 4.0):
            run = _cap_run(_resolved(chars_per_token=ratio), cap_tokens=20, messages=msgs)
            assert run["messages"][-1]["content"] == body
            assert TRUNCATION_MARKER not in run["messages"][-1]["content"]

    def test_current_envelope_shortens_with_the_model_ratio(self) -> None:
        """A Cline envelope in the current turn is trimmed to the calibrated size."""
        body = _envelope("read_file", "packages/pipeline/history.py", 4000)
        msgs = [
            _msg("system", "System."),
            _msg("user", "Earlier task"),
            _msg("user", body),
        ]

        default = _cap_run(_resolved(chars_per_token=4.0), cap_tokens=20, messages=msgs)
        calibrated = _cap_run(_resolved(chars_per_token=3.5), cap_tokens=20, messages=msgs)

        assert len(default["messages"][-1]["content"]) == int(20 * 4.0)
        assert len(calibrated["messages"][-1]["content"]) == int(20 * 3.5)
        assert calibrated["dropped_count"] == default["dropped_count"] == 0
        assert calibrated["messages"][-1]["content"].endswith(TRUNCATION_MARKER)
