"""History capping to a token budget.

Provides ``cap_history`` — a pure function that trims old conversation
history to fit within a token budget while preserving protocol invariants
(system messages, last user message, tool-call/result pairing).

This reduces prefill latency by forwarding fewer tokens to vLLM every turn.

Constraints
-----------

- No repository access.
- No filesystem access.
- No provider calls.
- No HTTP.

Public API
----------

.. code-block:: python

    from packages.pipeline.history import cap_history
    from packages.context.budget import CHARS_PER_TOKEN

    capped, dropped = cap_history(
        messages,
        max_history_tokens=16384,
        estimate=lambda text: int(len(text) / CHARS_PER_TOKEN),
    )
"""

from __future__ import annotations

from typing import Any, Callable

from packages.context.budget import CHARS_PER_TOKEN
from packages.context.content import content_to_text


def _estimate_tokens(content: str) -> int:
    """Estimate token count from text using CHARS_PER_TOKEN.

    Args:
        content: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    return int(len(content) / CHARS_PER_TOKEN) if content else 0


def _message_token_count(message: dict[str, Any]) -> int:
    """Estimate the token count of a single message.

    Counts the ``content``, ``name``, and ``reasoning_content`` fields.
    For assistant messages with ``tool_calls``, also counts the tool call
    JSON representation.

    Args:
        message: A single message dict.

    Returns:
        Estimated token count.
    """
    text = content_to_text(message.get("content", ""))
    tokens = _estimate_tokens(text)

    if message.get("name"):
        tokens += _estimate_tokens(message["name"])

    if message.get("reasoning_content"):
        reasoning = content_to_text(message["reasoning_content"])
        tokens += _estimate_tokens(reasoning)

    # Count tool_calls content for assistant messages.
    tool_calls = message.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            if isinstance(tc, dict):
                fn = tc.get("function", {})
                if isinstance(fn, dict):
                    name = fn.get("name", "")
                    args = fn.get("arguments", "")
                    tokens += _estimate_tokens(name)
                    tokens += _estimate_tokens(args)

    return tokens


def _looks_like_cline_tool_result_message(message: dict[str, Any]) -> bool:
    """Return True for Cline tool-result envelopes sent as user text."""
    if message.get("role") != "user":
        return False

    content = content_to_text(message.get("content", ""))
    stripped = content.lstrip()
    prefixes = (
        "[read_file for ",
        "[search_files for ",
        "[list_files for ",
        "[execute_command for ",
        "[attempt_completion]",
        "[ERROR] You did not use a tool",
    )
    return stripped.startswith(prefixes)


def _truncate_message_content(
    message: dict[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    """Return a shallow copy with text content truncated."""
    if max_tokens <= 0:
        return message

    max_chars = int(max_tokens * CHARS_PER_TOKEN)
    content = message.get("content", "")
    text = content_to_text(content)
    if len(text) <= max_chars:
        return message

    marker = "\n\n[... truncated by gateway history cap ...]"
    keep_chars = max(0, max_chars - len(marker))
    updated = dict(message)
    updated["content"] = f"{text[:keep_chars]}{marker}"
    return updated


def _cap_current_tool_result(
    messages: list[dict[str, Any]],
    max_current_tool_result_tokens: int | None,
) -> list[dict[str, Any]]:
    """Cap the current Cline tool-result message without dropping it."""
    if max_current_tool_result_tokens is None or max_current_tool_result_tokens <= 0:
        return messages

    last_user_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break

    if last_user_idx is None:
        return messages

    message = messages[last_user_idx]
    if not _looks_like_cline_tool_result_message(message):
        return messages

    capped_message = _truncate_message_content(
        message,
        max_tokens=max_current_tool_result_tokens,
    )
    if capped_message is message:
        return messages

    capped_messages = list(messages)
    capped_messages[last_user_idx] = capped_message
    return capped_messages


def _build_cap_groups(
    messages: list[dict[str, Any]],
) -> list[set[int]]:
    """Build atomic grouping sets for history capping.

    Each assistant message with tool calls is grouped together with ALL
    its tool-result messages.  Standalone messages (no tool calls, no
    paired results) form their own singleton groups.  This prevents
    splitting a multi-result group during capping — either the entire
    assistant+results unit is kept or dropped as one.

    Args:
        messages: The full message list.

    Returns:
        A list of sets, each set containing indices that must be kept
        or dropped together.
    """
    n = len(messages)
    # Union-Find for collapsing tool-call ↔ tool-result links into groups.
    parent = list(range(n))
    rank = [0] * n

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1

    # First pass: link each assistant tool-call message to its tool results.
    for i, msg in enumerate(messages):
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            continue
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            tc_id = tc.get("id")
            if not tc_id:
                continue
            for j in range(i + 1, n):
                if (
                    messages[j].get("role") == "tool"
                    and messages[j].get("tool_call_id") == tc_id
                ):
                    union(i, j)
                    break

    # Second pass: orphan tool results → link to nearest preceding
    # assistant with a matching tool_call id.
    for j, msg in enumerate(messages):
        if msg.get("role") != "tool":
            continue
        tc_id = msg.get("tool_call_id")
        if not tc_id:
            continue
        for i in range(j - 1, -1, -1):
            if messages[i].get("role") != "assistant":
                continue
            tc_list = messages[i].get("tool_calls", [])
            for tc in tc_list:
                if isinstance(tc, dict) and tc.get("id") == tc_id:
                    union(i, j)
                    break

    # Collapse into groups.
    groups_map: dict[int, set[int]] = {}
    for idx in range(n):
        root = find(idx)
        groups_map.setdefault(root, set()).add(idx)

    return list(groups_map.values())


def cap_history(
    messages: list[dict[str, Any]],
    max_history_tokens: int,
    estimate: Callable[[str], int] | None = None,
    max_current_tool_result_tokens: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return (capped_messages, dropped_count).

    Keeps the conversation valid while fitting recent history into a
    token budget.  Older messages are dropped first.

    Rules (in priority order):

    1. **Never drop system messages.** All system messages are kept
       regardless of budget. They are not counted against
       ``max_history_tokens``.
    2. **Never drop the last user message.** The current turn is always
       kept in full.
    3. **Keep the most recent messages that fit** ``max_history_tokens``,
       walking backward from the newest.  Older messages are dropped
       first.
    4. **Preserve tool-call / tool-result pairing.** If a message is an
       assistant tool call and its matching tool result would be dropped
       (or vice versa), drop or keep them **together**.  Never leave a
       tool call without its result or a result without its call.
    5. **Preserve order.** The kept messages stay in their original
       relative order.
    6. **When nothing needs dropping** (history already fits), return the
       messages unchanged and ``dropped_count=0``.  The transform is a
       no-op under the budget.

    Args:
        messages: Full message list including system messages.
        max_history_tokens: Token budget for non-system messages (excluding
            the last user message).
        estimate: A callable that estimates token count from text.  If not
            provided, uses ``int(len(text) / CHARS_PER_TOKEN)``.
        max_current_tool_result_tokens: Optional cap for the final user
            message when it is a Cline-style tool-result envelope.

    Returns:
        A tuple of (capped_messages, dropped_count).
    """
    if not messages:
        return messages, 0

    # Count tokens for each message.
    token_counts: list[int] = [_message_token_count(m) for m in messages]

    # Separate system messages (never counted, never dropped).
    system_indices = [i for i, m in enumerate(messages) if m.get("role") == "system"]
    non_system_indices = [i for i, m in enumerate(messages) if m.get("role") != "system"]

    if not non_system_indices:
        return messages, 0

    # Find the last user message index (among all messages, including system).
    last_user_idx = len(messages) - 1 - _trailing_assistant_count(messages)
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break

    # FIX 3: Total tokens of non-system messages EXCLUDING the last user message.
    # The last user message is always kept outside the budget.
    non_last_user_indices = [i for i in non_system_indices if i != last_user_idx]
    total_non_last_user_tokens = sum(token_counts[i] for i in non_last_user_indices)

    # If everything fits, return unchanged.
    if total_non_last_user_tokens <= max_history_tokens:
        return (
            _cap_current_tool_result(messages, max_current_tool_result_tokens),
            0,
        )

    # --- Capping logic ---

    # Build atomic groups for tool-call/result pairing.
    groups = _build_cap_groups(messages)

    # Build candidate groups for dropping: exclude system messages and the
    # last user message's group, and only include groups that have at least
    # one non-system, non-last-user member.
    # Each group is a set of indices.
    candidate_groups: list[set[int]] = []
    for group in groups:
        # Skip groups that are entirely system or last-user.
        has_capable_member = any(
            i not in system_indices and i != last_user_idx
            for i in group
        )
        if has_capable_member:
            candidate_groups.append(group)

    # If no candidate groups, nothing to cap.
    if not candidate_groups:
        return (
            _cap_current_tool_result(messages, max_current_tool_result_tokens),
            0,
        )

    # Sort groups by their maximum index (newest-first ordering).
    candidate_groups.sort(key=lambda g: max(g), reverse=True)

    # Accumulate tokens from newest groups until budget exhausted.
    accumulated = 0
    kept_groups: list[set[int]] = []

    for group in candidate_groups:
        group_tokens = sum(token_counts[i] for i in group)
        if accumulated + group_tokens <= max_history_tokens:
            kept_groups.append(group)
            accumulated += group_tokens
        else:
            # This and older groups will be dropped.
            break

    # Build kept set: all system indices + last user index + kept group members.
    kept_set: set[int] = set(system_indices)
    kept_set.add(last_user_idx)
    for group in kept_groups:
        kept_set.update(group)

    # Build result: all kept messages in original order.
    result = [messages[i] for i in sorted(kept_set)]

    dropped_count = len(messages) - len(result)

    result = _cap_current_tool_result(result, max_current_tool_result_tokens)
    return result, dropped_count


def _get_last_user_message(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the last user message, or None if no user message exists.

    Args:
        messages: The full message list.

    Returns:
        The last user message dict, or None.
    """
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg
    return None


def _trailing_assistant_count(
    messages: list[dict[str, Any]],
) -> int:
    """Count trailing assistant messages after the last user message.

    These are typically the response being streamed and should not be
    considered part of the "history" to cap.

    Args:
        messages: The full message list.

    Returns:
        Number of trailing assistant messages.
    """
    count = 0
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            count += 1
        else:
            break
    return count
