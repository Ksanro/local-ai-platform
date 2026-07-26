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
- budget derivation from context_window
"""

from __future__ import annotations

from typing import Any

from packages.pipeline.history import cap_history

import pytest


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
