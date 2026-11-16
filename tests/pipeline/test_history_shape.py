"""Tests for the opt-in history-shape summary (packages/pipeline/history_shape.py).

The summary is observability over the *real* inbound message list - native
OpenAI chat-form messages with assistant ``tool_calls`` and ``role: "tool"``
results, which is the shape :func:`packages.pipeline.history.cap_history`
consumes - so that a history-cap policy can be simulated offline afterwards.
Every fixture here is written that way on purpose: stored Cline transcripts carry
Anthropic ``tool_use`` / ``tool_result`` blocks, and converting them into this
shape would have introduced exactly the unverified independent variable the
offline measurement declined.

Sentinels are planted in each field the summary is forbidden to state -
message content, a system prompt, reasoning text, a tool name, tool arguments,
a tool-call id, a result body, a file path - and then searched for in the
serialized output.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from packages.context.budget import CHARS_PER_TOKEN
from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.engine import PipelineEngine, _record_history_shape
from packages.pipeline.history import _message_token_count
from packages.pipeline.history_shape import (
    MAX_SHAPE_DETAIL_TOKENS,
    MAX_SHAPE_GROUPS,
    SHAPE_SCHEMA_VERSION,
    summarize_history_shape,
)
from packages.pipeline.normalized import NormalizedRequest
from packages.pipeline.request import PipelineRequest
from packages.pipeline.result import PipelineStageResult
from packages.providers.models import ModelDefinition, ResolvedModel

# --- Sentinels: one per field the summary must never state -------------------

USER_SECRET = "SENTINEL-IN-USER-CONTENT"
SYSTEM_SECRET = "SENTINEL-IN-SYSTEM-PROMPT"
ASSISTANT_SECRET = "SENTINEL-IN-ASSISTANT-CONTENT"
REASONING_SECRET = "SENTINEL-IN-REASONING-CONTENT"
TOOL_NAME_SECRET = "SENTINEL-IN-TOOL-NAME"
ARGUMENT_SECRET = "SENTINEL-IN-TOOL-ARGUMENTS"
CALL_ID_SECRET = "SENTINEL-IN-TOOL-CALL-ID"
RESULT_SECRET = "SENTINEL-IN-TOOL-RESULT-CONTENT"
PATH_SECRET = "packages/SENTINEL-IN-module.py"
SECOND_CALL_ID_SECRET = "SENTINEL-IN-SECOND-CALL-ID"

ALL_SECRETS = (
    USER_SECRET,
    SYSTEM_SECRET,
    ASSISTANT_SECRET,
    REASONING_SECRET,
    TOOL_NAME_SECRET,
    ARGUMENT_SECRET,
    CALL_ID_SECRET,
    RESULT_SECRET,
    PATH_SECRET,
    SECOND_CALL_ID_SECRET,
)

_TOP_LEVEL_FIELDS = {
    "schema",
    "status",
    "chars_per_token",
    "message_count",
    "system_message_count",
    "non_system_message_count",
    "history_tokens",
    "cap_eligible_tokens",
    "group_count",
    "recorded_groups",
    "omitted_groups",
    "recorded_tokens",
    "omitted_tokens",
    "recorded_cap_eligible_tokens",
    "omitted_cap_eligible_tokens",
    "omitted_messages",
    "detail_complete",
    "last_message_role",
    "last_user_distance",
    "last_user_group",
    "assistant_with_tool_calls",
    "tool_result_count",
    "complete_tool_groups",
    "orphan_tool_calls",
    "orphan_tool_results",
    "groups",
}

_GROUP_FIELDS = {
    "ordinal",
    "message_count",
    "tokens",
    "cap_eligible_tokens",
    "roles",
    "has_system",
    "has_last_user",
    "has_tool_calls",
    "has_tool_results",
    "pairing_complete",
    "orphan_tool_calls",
    "orphan_tool_results",
}

_ROLE_TOKENS = {"assistant", "developer", "function", "system", "tool", "user", "other"}


# --- Message builders: native chat form only ---------------------------------


def _system(text: str) -> dict[str, Any]:
    """A system message."""
    return {"role": "system", "content": text}


def _user(text: Any) -> dict[str, Any]:
    """A user message."""
    return {"role": "user", "content": text}


def _assistant(
    text: Any = "",
    tool_calls: list[dict[str, Any]] | None = None,
    reasoning: str | None = None,
) -> dict[str, Any]:
    """An assistant message, optionally with native tool calls."""
    message: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return message


def _tool_result(call_id: str, content: str) -> dict[str, Any]:
    """A native tool result."""
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _call(
    call_id: str,
    name: str = TOOL_NAME_SECRET,
    arguments: str = ARGUMENT_SECRET,
) -> dict[str, Any]:
    """One native tool call."""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _one_exchange() -> list[dict[str, Any]]:
    """System prompt, a question, one native tool call and its result, an answer."""
    return [
        _system(SYSTEM_SECRET),
        _user(USER_SECRET),
        _assistant(
            "",
            tool_calls=[_call(CALL_ID_SECRET, arguments=json.dumps({"path": PATH_SECRET}))],
            reasoning=REASONING_SECRET,
        ),
        _tool_result(CALL_ID_SECRET, RESULT_SECRET),
        _assistant(ASSISTANT_SECRET),
    ]


# --- Assertion helpers -------------------------------------------------------


def _assert_no_secrets(value: Any) -> None:
    """Fail if any sentinel appears anywhere in the serialized summary."""
    blob = json.dumps(value, sort_keys=True)
    assert not any(secret in blob for secret in ALL_SECRETS), blob


def _strings(value: Any, found: set[str] | None = None) -> set[str]:
    """Every string value a summary actually contains, keys excluded."""
    collected: set[str] = set() if found is None else found
    if isinstance(value, str):
        collected.add(value)
    elif isinstance(value, dict):
        for item in value.values():
            _strings(item, collected)
    elif isinstance(value, list):
        for item in value:
            _strings(item, collected)
    return collected


def _context_with(messages: list[dict[str, Any]]) -> PipelineContext:
    """A context holding one request, as the engine sees it after normalization."""
    context = PipelineContext(request={"messages": messages, "model": "qwen38-27b"})
    context.normalized_request = NormalizedRequest.from_client(context.request)
    return context


def _resolved(**overrides: Any) -> ResolvedModel:
    """A resolved model in the shape ``ModelResolutionStage`` stores."""
    return ResolvedModel(
        definition=ModelDefinition(
            model="qwen38-27b",
            provider="openai",
            base_url="http://127.0.0.1:18300/v1",
            **overrides,
        ),
        provider=object(),
    )


def _summed(messages: list[dict[str, Any]], chars_per_token: float) -> int:
    """What the real estimator charges for every non-system message."""
    return sum(
        _message_token_count(message, chars_per_token)
        for message in messages
        if message.get("role") != "system"
    )


class TestSchemaAndPrivacy:
    """The summary is a fixed set of numbers, booleans and three token kinds."""

    def test_field_set_is_the_documented_one(self) -> None:
        """Top-level, per-group and reserved-group fields are exactly the schema."""
        summary = summarize_history_shape(_one_exchange())

        assert set(summary) == _TOP_LEVEL_FIELDS
        assert summary["schema"] == SHAPE_SCHEMA_VERSION
        assert summary["status"] == "measured"
        assert summary["groups"]
        for group in summary["groups"]:
            assert set(group) == _GROUP_FIELDS
        # The protected turn's reservation is stated in the same shape as an entry,
        # so a reader never has to learn a second schema to use it.
        assert set(summary["last_user_group"]) == _GROUP_FIELDS

    def test_no_string_is_caller_authored(self) -> None:
        """The only strings are the schema, the status, and known role tokens."""
        summary = summarize_history_shape(_one_exchange())

        assert _strings(summary) <= {SHAPE_SCHEMA_VERSION, "measured"} | _ROLE_TOKENS

    def test_no_sentinel_survives_serialization(self) -> None:
        """Nothing planted in content, reasoning, names, arguments, ids or paths logs."""
        _assert_no_secrets(summarize_history_shape(_one_exchange()))

    def test_messages_are_not_modified(self) -> None:
        """Summarizing is a read: the list, its members and their order are untouched."""
        messages = _one_exchange()
        before = copy.deepcopy(messages)

        summarize_history_shape(messages, chars_per_token=3.5)

        assert messages == before

    def test_empty_history(self) -> None:
        """An empty message list summarizes as zeros rather than raising."""
        summary = summarize_history_shape([])

        assert summary["message_count"] == 0
        assert summary["group_count"] == 0
        assert summary["groups"] == []
        assert summary["detail_complete"] is True
        assert summary["last_message_role"] == ""
        assert summary["last_user_distance"] is None
        assert summary["last_user_group"] is None
        assert summary["history_tokens"] == 0
        assert (
            summary["recorded_cap_eligible_tokens"] + summary["omitted_cap_eligible_tokens"]
            == summary["cap_eligible_tokens"]
        )

    def test_unknown_role_is_not_echoed(self) -> None:
        """A role outside the protocol is stated as ``other``, never echoed."""
        messages = [{"role": f"SYSTEM LEAK {USER_SECRET}", "content": USER_SECRET}]

        summary = summarize_history_shape(messages)

        assert summary["last_message_role"] == "other"
        assert summary["groups"][0]["roles"] == {"other": 1}
        _assert_no_secrets(summary)


class TestOrdinaryConversation:
    """Plain system/user/assistant turns count, order and price themselves."""

    def test_counts_roles_and_newest_first_order(self) -> None:
        """Four messages make four groups, walked newest first."""
        messages = [_system("sys"), _user("q1"), _assistant("a1"), _user("q2")]

        summary = summarize_history_shape(messages)

        assert summary["message_count"] == 4
        assert summary["system_message_count"] == 1
        assert summary["non_system_message_count"] == 3
        assert summary["group_count"] == 4
        assert summary["detail_complete"] is True
        assert [group["ordinal"] for group in summary["groups"]] == [0, 1, 2, 3]
        assert [group["roles"] for group in summary["groups"]] == [
            {"user": 1},
            {"assistant": 1},
            {"user": 1},
            {"system": 1},
        ]
        assert summary["last_message_role"] == "user"
        assert summary["last_user_distance"] == 0
        assert summary["assistant_with_tool_calls"] == 0
        assert summary["tool_result_count"] == 0
        assert summary["complete_tool_groups"] == 0
        assert summary["orphan_tool_calls"] == 0
        assert summary["orphan_tool_results"] == 0

    def test_system_messages_are_not_counted_against_a_budget(self) -> None:
        """The protected-turn split matches what ``_message_token_count`` charges."""
        messages = [_system("sys"), _user("q1"), _assistant("a1"), _user("q2")]

        summary = summarize_history_shape(messages)

        assert summary["history_tokens"] == _summed(messages, 4.0)
        assert summary["cap_eligible_tokens"] == (
            summary["history_tokens"] - _message_token_count(messages[-1], 4.0)
        )

    def test_a_system_only_list_is_all_system_and_nothing_to_cap(self) -> None:
        """System messages are reported and never counted as history."""
        summary = summarize_history_shape([_system("only a system prompt")])

        assert summary["system_message_count"] == 1
        assert summary["non_system_message_count"] == 0
        assert summary["history_tokens"] == 0
        assert summary["cap_eligible_tokens"] == 0
        assert summary["groups"][0]["has_system"] is True
        assert summary["last_message_role"] == "system"


class TestNativeToolExchange:
    """One assistant call and its result are one atomic group."""

    def test_call_and_result_form_one_complete_group(self) -> None:
        """Indices 2 and 3 are one group; the list carves into four."""
        messages = _one_exchange()

        summary = summarize_history_shape(messages, chars_per_token=3.5)

        assert summary["group_count"] == 4
        assert [group["message_count"] for group in summary["groups"]] == [1, 2, 1, 1]
        exchange = summary["groups"][1]
        assert exchange["roles"] == {"assistant": 1, "tool": 1}
        assert exchange["has_tool_calls"] is True
        assert exchange["has_tool_results"] is True
        assert exchange["pairing_complete"] is True
        assert exchange["orphan_tool_calls"] == 0
        assert exchange["orphan_tool_results"] == 0
        assert summary["assistant_with_tool_calls"] == 1
        assert summary["tool_result_count"] == 1
        assert summary["complete_tool_groups"] == 1

    def test_group_tokens_are_the_real_estimator_over_both_members(self) -> None:
        """The group figure is ``_message_token_count`` of the call and the result."""
        messages = _one_exchange()

        summary = summarize_history_shape(messages, chars_per_token=3.5)

        assert summary["groups"][1]["tokens"] == (
            _message_token_count(messages[2], 3.5) + _message_token_count(messages[3], 3.5)
        )

    def test_ids_names_and_arguments_are_not_logged(self) -> None:
        """The exchange's tool-call id, tool name and arguments stay out."""
        blob = json.dumps(summarize_history_shape(_one_exchange()), sort_keys=True)

        for secret in (CALL_ID_SECRET, TOOL_NAME_SECRET, ARGUMENT_SECRET, PATH_SECRET):
            assert secret not in blob


class TestMultipleToolCalls:
    """One assistant message with several calls stays one group with all results."""

    def test_parallel_calls_and_results_are_one_group(self) -> None:
        """Two calls and both results are atomic, and complete."""
        messages = [
            _system("sys"),
            _user("list two files"),
            _assistant(
                "",
                tool_calls=[
                    _call(CALL_ID_SECRET, name="read_file", arguments=ARGUMENT_SECRET),
                    _call(SECOND_CALL_ID_SECRET, name="list_files", arguments="{}"),
                ],
            ),
            _tool_result(CALL_ID_SECRET, RESULT_SECRET),
            _tool_result(SECOND_CALL_ID_SECRET, "second body"),
            _user("thanks"),
        ]

        summary = summarize_history_shape(messages)

        assert summary["group_count"] == 4
        exchange = summary["groups"][1]
        assert exchange["message_count"] == 3
        assert exchange["roles"] == {"assistant": 1, "tool": 2}
        assert exchange["pairing_complete"] is True
        assert summary["assistant_with_tool_calls"] == 1
        assert summary["tool_result_count"] == 2
        assert summary["complete_tool_groups"] == 1
        assert summary["orphan_tool_calls"] == 0
        assert summary["orphan_tool_results"] == 0
        _assert_no_secrets(summary)


class TestOrphanedToolTraffic:
    """A call without a result, or a result without a call, is counted not quoted."""

    def test_orphan_assistant_call(self) -> None:
        """One dangling call: counted as an orphan, id absent from the output."""
        messages = [
            _system("sys"),
            _user("read it"),
            _assistant("", tool_calls=[_call(CALL_ID_SECRET)]),
            _user("still there?"),
        ]

        summary = summarize_history_shape(messages)

        assert summary["orphan_tool_calls"] == 1
        assert summary["orphan_tool_results"] == 0
        assert summary["complete_tool_groups"] == 0
        dangling = summary["groups"][1]
        assert dangling["message_count"] == 1
        assert dangling["has_tool_calls"] is True
        assert dangling["has_tool_results"] is False
        assert dangling["pairing_complete"] is False
        assert dangling["orphan_tool_calls"] == 1
        blob = json.dumps(summary, sort_keys=True)
        assert CALL_ID_SECRET not in blob
        assert TOOL_NAME_SECRET not in blob

    def test_orphan_tool_result(self) -> None:
        """One result whose call never arrived: counted, id absent from the output."""
        messages = [
            _system("sys"),
            _user("read it"),
            _tool_result(SECOND_CALL_ID_SECRET, RESULT_SECRET),
            _user("and now?"),
        ]

        summary = summarize_history_shape(messages)

        assert summary["orphan_tool_results"] == 1
        assert summary["orphan_tool_calls"] == 0
        assert summary["complete_tool_groups"] == 0
        stranded = summary["groups"][1]
        assert stranded["message_count"] == 1
        assert stranded["has_tool_results"] is True
        assert stranded["has_tool_calls"] is False
        assert stranded["pairing_complete"] is False
        assert stranded["orphan_tool_results"] == 1
        assert SECOND_CALL_ID_SECRET not in json.dumps(summary, sort_keys=True)


def _long_turns(count: int, chars: int) -> list[dict[str, Any]]:
    """``count`` alternating user/assistant messages, each ``chars`` characters long."""
    cycle = ("user", "assistant")
    return [{"role": cycle[i % 2], "content": "x" * chars} for i in range(count)]


class TestProtectedLastUser:
    """The turn capping never drops is marked without being read."""

    def test_the_group_holding_the_newest_user_message_is_marked(self) -> None:
        """Exactly one group carries ``has_last_user``, and it holds no text."""
        messages = [
            _system(SYSTEM_SECRET),
            _user("old question"),
            _assistant("", tool_calls=[_call(CALL_ID_SECRET, name="read_file", arguments="{}")]),
            _tool_result(CALL_ID_SECRET, RESULT_SECRET),
            _user(USER_SECRET),
        ]

        summary = summarize_history_shape(messages, chars_per_token=3.5)

        assert [group["ordinal"] for group in summary["groups"] if group["has_last_user"]] == [0]
        assert summary["groups"][0]["roles"] == {"user": 1}
        assert summary["last_user_distance"] == 0
        _assert_no_secrets(summary)

    def test_distance_from_the_end_when_an_assistant_replies_last(self) -> None:
        """A trailing assistant answer puts the protected turn further back."""
        summary = summarize_history_shape(_one_exchange())

        assert summary["last_message_role"] == "assistant"
        assert summary["last_user_distance"] == 3
        assert [group["has_last_user"] for group in summary["groups"]] == [
            False,
            False,
            True,
            False,
        ]


class TestBoundedDetail:
    """The detail keeps the newest groups and states what it left out."""

    def test_group_bound_keeps_the_newest_and_counts_the_rest(self) -> None:
        """Six groups, two recorded: the ordinals are the newest and the totals are whole."""
        messages = [_system("sys")] + _long_turns(5, 40)

        summary = summarize_history_shape(messages, max_groups=2)

        assert summary["group_count"] == 6
        assert [group["ordinal"] for group in summary["groups"]] == [0, 1]
        assert summary["recorded_groups"] == 2
        assert summary["omitted_groups"] == 4
        assert summary["detail_complete"] is False
        assert summary["omitted_messages"] == 4
        assert summary["groups"][0]["tokens"] == _message_token_count(messages[-1], 4.0)
        assert summary["recorded_tokens"] + summary["omitted_tokens"] == sum(
            _message_token_count(message, 4.0) for message in messages
        )

    def test_top_level_totals_describe_the_whole_list(self) -> None:
        """A truncated detail is still a summary of everything, not of what was kept."""
        messages = [_system("sys")] + _long_turns(5, 40)

        whole = summarize_history_shape(messages)
        bounded = summarize_history_shape(messages, max_groups=2)

        for field in (
            "message_count",
            "system_message_count",
            "non_system_message_count",
            "history_tokens",
            "cap_eligible_tokens",
            "group_count",
            "assistant_with_tool_calls",
            "tool_result_count",
            "complete_tool_groups",
            "orphan_tool_calls",
            "orphan_tool_results",
            "last_message_role",
            "last_user_distance",
            "last_user_group",
        ):
            assert bounded[field] == whole[field]
        assert whole["detail_complete"] is True
        assert bounded["groups"] == whole["groups"][:2]

    def test_ordering_is_deterministic(self) -> None:
        """The same list summarizes to the same bytes twice running."""
        messages = _one_exchange() + _long_turns(4, 200)

        first = json.dumps(summarize_history_shape(messages), sort_keys=True)
        second = json.dumps(summarize_history_shape(messages), sort_keys=True)

        assert first == second

    def test_token_bound_reaches_the_largest_budget_simulated(self) -> None:
        """Recording stops once the detail carries a full sweep of eligible budget.

        300 turns of 1,000 tokens each, newest-first, of which exactly one - the
        protected current turn at ordinal 1 - charges nothing.  So coverage crosses
        the 131,072-token floor one group later than a counter that ignored
        eligibility would: the group recorded "for free" is the one capping always
        keeps anyway, and it is recorded because the count bound, not the coverage
        bound, is what had not been reached yet.
        """
        messages = _long_turns(300, 4000)  # 1,000 tokens each at the platform ratio

        summary = summarize_history_shape(messages)

        assert summary["group_count"] == 300
        assert summary["recorded_groups"] == 133
        assert summary["omitted_groups"] == 167
        # Enough cap-eligible coverage for the whole 16k/32k/64k/96k/128k sweep.
        assert summary["recorded_cap_eligible_tokens"] >= 128 * 1024
        assert summary["recorded_cap_eligible_tokens"] == 132_000
        assert summary["cap_eligible_tokens"] == 299_000  # 300,000 less the protected turn
        assert summary["recorded_tokens"] == 133_000
        assert (
            summary["recorded_cap_eligible_tokens"] + summary["omitted_cap_eligible_tokens"]
            == summary["cap_eligible_tokens"]
        )
        assert summary["history_tokens"] == 300_000

    def test_documented_bounds(self) -> None:
        """The bound is the one the schema section states, not an accident."""
        assert MAX_SHAPE_GROUPS == 256
        assert MAX_SHAPE_DETAIL_TOKENS == 128 * 1024


def _tool_pairs(count: int) -> list[dict[str, Any]]:
    """``count`` native call/result exchanges - one atomic group each."""
    messages: list[dict[str, Any]] = []
    for index in range(count):
        call_id = f"call-{index}"
        messages.append(
            _assistant(
                "",
                tool_calls=[_call(call_id, name="read_file", arguments='{"path":"a.py"}')],
            )
        )
        messages.append(_tool_result(call_id, "result body"))
    return messages


#: Text worth well over ``MAX_SHAPE_DETAIL_TOKENS`` at the platform ratio - the size
#: a current turn or a system message really does reach in agent traffic.
OVER_FLOOR_CHARS = 600_000


class TestEligibilityDrivenDetailBound:
    """Only cap-eligible tokens may buy the detail's coverage.

    ``cap_history`` charges neither a system message nor the protected current turn
    against a budget, so neither may end the ordered detail either.  v1 counted them,
    which let the largest always-kept message in a transcript buy the summary out of
    the history the summary exists to record: a protected turn over 128k tokens
    produced one recorded group (itself), ``omitted_tokens`` holding every token a
    simulation would need.  These are that bug's regressions.
    """

    def test_protected_turn_bigger_than_the_floor_still_records_history(self) -> None:
        """A giant current turn is recorded, and advances coverage by nothing."""
        messages = [
            _system(SYSTEM_SECRET),
            _user("older question"),
            _assistant("older answer"),
            _user("u" * OVER_FLOOR_CHARS),
        ]

        summary = summarize_history_shape(messages)

        assert summary["last_user_distance"] == 0
        assert summary["group_count"] == 4
        assert summary["recorded_groups"] == 4
        assert summary["omitted_groups"] == 0
        assert summary["detail_complete"] is True
        # The older history a cap would actually drop is in the detail, not omitted.
        assert summary["omitted_cap_eligible_tokens"] == 0
        assert summary["recorded_cap_eligible_tokens"] == summary["cap_eligible_tokens"] > 0

        giant = next(group for group in summary["groups"] if group["has_last_user"])
        assert giant["tokens"] > MAX_SHAPE_DETAIL_TOKENS
        assert giant["cap_eligible_tokens"] == 0
        assert summary["last_user_group"] == giant

        older = [
            group
            for group in summary["groups"]
            if not group["has_last_user"] and not group["has_system"]
        ]
        assert len(older) == 2
        assert summary["recorded_cap_eligible_tokens"] == sum(
            group["cap_eligible_tokens"] for group in older
        )
        _assert_no_secrets(summary)
        assert _strings(summary) <= {SHAPE_SCHEMA_VERSION, "measured"} | _ROLE_TOKENS

    def test_system_message_bigger_than_the_floor_still_records_history(self) -> None:
        """A giant system message is uncharged too, wherever the client put it.

        Index 0 is a convention rather than a rule, so the oversized always-kept
        group is placed where the newest-first walk meets it first - which is exactly
        when counting it did the most damage.
        """
        messages = [
            _user("older question"),
            _assistant("older answer"),
            _user("and now?"),
            _system("s" * OVER_FLOOR_CHARS),
        ]

        summary = summarize_history_shape(messages)

        assert summary["group_count"] == 4
        assert summary["recorded_groups"] == 4
        assert summary["omitted_cap_eligible_tokens"] == 0
        assert summary["detail_complete"] is True
        system_group = next(group for group in summary["groups"] if group["has_system"])
        assert system_group["ordinal"] == 0
        assert system_group["tokens"] > MAX_SHAPE_DETAIL_TOKENS
        assert system_group["cap_eligible_tokens"] == 0

    def test_eligible_partition_holds_at_every_bound(self) -> None:
        """However the detail is cut, the eligible tokens are all accounted for."""
        messages = _one_exchange() + _long_turns(9, 4000)

        bounds_cases: tuple[dict[str, Any], ...] = (
            {},
            {"max_groups": 2},
            {"max_groups": 0},
            {"max_detail_tokens": 1},
            {"max_detail_tokens": 0},
            {"max_groups": 3, "max_detail_tokens": 5},
        )
        for bounds in bounds_cases:
            summary = summarize_history_shape(messages, **bounds)

            assert (
                summary["recorded_cap_eligible_tokens"]
                + summary["omitted_cap_eligible_tokens"]
                == summary["cap_eligible_tokens"]
            ), bounds
            assert summary["recorded_cap_eligible_tokens"] == sum(
                group["cap_eligible_tokens"] for group in summary["groups"]
            ), bounds
            assert (
                summary["recorded_groups"] + summary["omitted_groups"]
                == summary["group_count"]
            ), bounds
            assert summary["recorded_tokens"] + summary["omitted_tokens"] == sum(
                _message_token_count(message, 4.0) for message in messages
            ), bounds
            # The protected turn is never something a reader has to infer.
            assert summary["last_user_group"] is not None, bounds
            assert summary["last_user_group"]["has_last_user"] is True, bounds

    def test_protected_turn_stays_explicit_beyond_the_group_bound(self) -> None:
        """More groups than the bound than the protected turn is not allowed to hide.

        260 native exchanges trail the last user message, so the count bound is
        exhausted long before the walk reaches it.  ``groups`` therefore stays the
        contiguous newest-first prefix - which is what makes it walkable as a budget
        - and the protected group's own detail is reserved alongside it.
        """
        messages = [_system("sys"), _user("the protected turn"), *_tool_pairs(260)]

        summary = summarize_history_shape(messages)

        assert summary["group_count"] == 262
        assert summary["recorded_groups"] == MAX_SHAPE_GROUPS
        assert summary["omitted_groups"] == 262 - MAX_SHAPE_GROUPS
        assert summary["detail_complete"] is False
        assert [group["ordinal"] for group in summary["groups"]] == list(
            range(MAX_SHAPE_GROUPS)
        )
        assert not any(group["has_last_user"] for group in summary["groups"])

        reserved = summary["last_user_group"]
        assert reserved is not None
        assert reserved["has_last_user"] is True
        assert reserved["roles"] == {"user": 1}
        assert reserved["cap_eligible_tokens"] == 0
        # Beyond the prefix rather than inside it, so no reader mistakes the
        # reservation for another member of the contiguous walk.
        assert reserved["ordinal"] > summary["groups"][-1]["ordinal"]
        assert (
            summary["recorded_cap_eligible_tokens"] + summary["omitted_cap_eligible_tokens"]
            == summary["cap_eligible_tokens"]
        )
        assert summary["last_user_distance"] == 520

    def test_the_reservation_repeats_the_prefix_entry_when_both_hold_it(self) -> None:
        """One group, one description: the reservation never disagrees with the list."""
        summary = summarize_history_shape(_one_exchange())

        entry = next(group for group in summary["groups"] if group["has_last_user"])

        assert summary["last_user_group"] == entry

    def test_no_user_message_reserves_the_turn_capping_protects(self) -> None:
        """With no user turn, the reservation follows capping's own fallback.

        ``cap_history`` protects a *position* when a transcript holds no user
        message - the one after the trailing assistant messages - so the summary
        reserves that same group rather than inventing a case the cap does not have.
        ``has_last_user`` has meant "the group holds the turn capping never drops"
        since v1, and ``last_user_distance`` is the field that says whether that turn
        was a user message at all.
        """
        summary = summarize_history_shape([_system("only a system prompt")])

        assert summary["last_user_distance"] is None
        assert summary["cap_eligible_tokens"] == 0
        reserved = summary["last_user_group"]
        assert reserved is not None
        assert reserved["has_last_user"] is True
        assert reserved["has_system"] is True
        assert reserved["cap_eligible_tokens"] == 0




class TestCalibratedEstimator:
    """The ratio changes what a group is worth, never how the list carves up."""

    def test_ratio_moves_every_number_the_way_the_cap_path_does(self) -> None:
        """The summary prices a transcript exactly as ``_message_token_count`` does."""
        messages = _one_exchange()

        platform = summarize_history_shape(messages)
        calibrated = summarize_history_shape(messages, chars_per_token=3.5)

        assert platform["chars_per_token"] == CHARS_PER_TOKEN
        assert calibrated["chars_per_token"] == 3.5
        assert platform["history_tokens"] == _summed(messages, 4.0)
        assert calibrated["history_tokens"] == _summed(messages, 3.5)
        assert calibrated["history_tokens"] >= platform["history_tokens"]
        # Structure is the ratio's indifference: same groups, same counts, same marks.
        assert calibrated["group_count"] == platform["group_count"]
        assert calibrated["message_count"] == platform["message_count"]
        assert [
            group["ordinal"] for group in calibrated["groups"] if group["has_last_user"]
        ] == [group["ordinal"] for group in platform["groups"] if group["has_last_user"]]

    def test_an_unusable_ratio_falls_back_to_the_platform_estimate(self) -> None:
        """A nonsense ratio is refused, exactly as ``cap_history`` refuses one."""
        messages = _one_exchange()

        for unusable in (0, 0.0, -4.0, float("nan"), True, 1000.0, None):
            assert summarize_history_shape(messages, chars_per_token=unusable)[
                "chars_per_token"
            ] == CHARS_PER_TOKEN


class _ContextStage(PipelineStage):
    """A stage in the ``repository_context`` slot the engine measures beside."""

    def __init__(self, resolved_model: Any = None) -> None:
        self._resolved_model = resolved_model

    @property
    def name(self) -> str:
        """The stage name the engine's measurement boundary keys on."""
        return "repository_context"

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Stand in for context assembly, and resolve the model if asked to."""
        if self._resolved_model is not None:
            context.resolved_model = self._resolved_model
        return PipelineStageResult(stage_name=self.name, success=True, data={})


class _ProviderStage(PipelineStage):
    """A stage that records what would have been forwarded."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        """The stage name."""
        return "provider"

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Capture the message list the provider would receive."""
        nr = context.normalized_request
        self.sent = list(nr.messages) if nr is not None else []
        return PipelineStageResult(stage_name=self.name, success=True, data={"choices": []})


async def _run(
    messages: list[dict[str, Any]],
    *,
    shape_log_enabled: bool = True,
    cap_enabled: bool = False,
    cap_tokens: int = 0,
    resolved_model: Any = None,
) -> tuple[Any, _ProviderStage]:
    """Send one transcript through the real engine and report the response.

    Args:
        messages: The inbound chat-form transcript.
        shape_log_enabled: What ``APP_HISTORY_SHAPE_LOG_ENABLED`` would say.
        cap_enabled: What ``APP_HISTORY_CAP_ENABLED`` would say.
        cap_tokens: What ``APP_HISTORY_CAP_TOKENS`` would say; 0 derives it.
        resolved_model: The model the request supposedly routed to.

    Returns:
        The pipeline response and the provider stub that saw the payload.
    """
    engine = PipelineEngine()
    engine.register(_ContextStage(resolved_model))
    provider = _ProviderStage()
    engine.register(provider)
    response = await engine.execute(
        PipelineRequest(
            provider_name="openai",
            model="qwen38-27b",
            messages=messages,
            metadata={
                "history_shape_log_enabled": shape_log_enabled,
                "history_cap_enabled": cap_enabled,
                "history_cap_tokens": cap_tokens,
            },
        )
    )
    return response, provider


class TestEngineMeasurementPoint:
    """The summary is taken where the cap reads, and before the cap writes."""

    @pytest.mark.asyncio
    async def test_disabled_knob_records_nothing(self) -> None:
        """With the knob off the pipeline metadata carries no shape at all."""
        response, provider = await _run(_one_exchange(), shape_log_enabled=False)

        assert response.success is True
        assert "history_shape" not in response.metadata
        assert provider.sent == _one_exchange()

    @pytest.mark.asyncio
    async def test_records_when_history_capping_is_disabled(self) -> None:
        """A cap-off request still states its shape.

        This is the case the offline measurement could not reach - stored
        transcripts are a different dialect, so the shape of a real cap-off
        request had never been recorded by the code that would cap it.
        """
        messages = _one_exchange() + _long_turns(20, 4000)

        response, provider = await _run(messages, cap_enabled=False)

        shape = response.metadata["history_shape"]
        assert shape["status"] == "measured"
        assert shape["message_count"] == len(messages)
        assert response.metadata.get("history_cap_applied", False) is False
        assert provider.sent == messages

    @pytest.mark.asyncio
    async def test_records_the_pre_cap_list_when_capping_runs(self) -> None:
        """Capping drops messages; the summary still counts what came in."""
        messages = _long_turns(12, 4000)

        response, provider = await _run(
            messages, cap_enabled=True, cap_tokens=1000, resolved_model=_resolved()
        )

        shape = response.metadata["history_shape"]
        assert shape["message_count"] == 12
        assert shape["group_count"] == 12
        assert response.metadata["history_dropped_count"] > 0
        assert len(provider.sent) < 12

    @pytest.mark.asyncio
    async def test_resolved_model_ratio_is_the_cap_path_ratio(self) -> None:
        """The numbers are the ones ``_apply_history_cap`` would have priced with."""
        messages = _one_exchange() + _long_turns(3, 4000)

        calibrated = await _run(messages, resolved_model=_resolved(chars_per_token=3.5))
        platform = await _run(messages, resolved_model=_resolved())

        assert calibrated[0].metadata["history_shape"] == summarize_history_shape(
            messages, chars_per_token=3.5
        )
        assert platform[0].metadata["history_shape"] == summarize_history_shape(
            messages, chars_per_token=4.0
        )
        assert (
            calibrated[0].metadata["history_shape"]["history_tokens"]
            > platform[0].metadata["history_shape"]["history_tokens"]
        )

    @pytest.mark.asyncio
    async def test_never_mutates_the_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The list the provider receives is the list that arrived, unchanged."""
        messages = _one_exchange()
        before = copy.deepcopy(messages)

        def _boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
            """A summarizer that must not be able to break or rewrite the request."""
            raise RuntimeError(f"cannot summarize {messages[0]['content']}")

        monkeypatch.setattr("packages.pipeline.engine.summarize_history_shape", _boom)

        response, provider = await _run(messages)

        assert response.success is True
        assert messages == before
        assert provider.sent == before
        assert response.metadata["history_shape"] == {
            "schema": SHAPE_SCHEMA_VERSION,
            "status": "unavailable",
        }

    @pytest.mark.asyncio
    async def test_a_failing_summary_still_leaves_the_shape_privacy_intact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even the degraded marker states no text, though the failure had some."""
        messages = _one_exchange()

        def _boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
            """Raise with a sentinel in the message, the way a real fault might."""
            raise RuntimeError(f"cannot read {USER_SECRET} at {PATH_SECRET}")

        monkeypatch.setattr("packages.pipeline.engine.summarize_history_shape", _boom)

        response, _ = await _run(messages)

        _assert_no_secrets(response.metadata["history_shape"])


class TestDirectRecording:
    """The recording helper is a read of the context, nothing more."""

    def test_context_without_a_normalized_request_records_nothing(self) -> None:
        """Called before normalization, the helper states nothing and raises nothing."""
        context = PipelineContext(request={"messages": [], "model": "qwen38-27b"})

        _record_history_shape(context, None)

        assert "history_shape" not in context.metadata

    def test_messages_are_equal_before_and_after(self) -> None:
        """Deep equality, after the fact, on the very list that was summarized."""
        messages = _one_exchange()
        before = copy.deepcopy(messages)
        context = _context_with(messages)

        _record_history_shape(context, _resolved(chars_per_token=3.5))

        assert context.normalized_request is not None
        assert context.normalized_request.messages == before
        assert messages == before
        assert context.metadata["history_shape"]["message_count"] == len(before)
