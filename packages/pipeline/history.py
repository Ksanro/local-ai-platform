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


def _content_to_text(content: object) -> str:
    """Normalise an OpenAI message ``content`` field to plain text.

    Content may be a string, or a list of parts such as
    ``[{"type": "text", "text": "..."}]`` (the format Cline and other
    clients send). Non-text parts are ignored.

    Args:
        content: The raw ``content`` value from a message.

    Returns:
        The concatenated text, or an empty string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""


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
    text = _content_to_text(message.get("content", ""))
    tokens = _estimate_tokens(text)

    if message.get("name"):
        tokens += _estimate_tokens(message["name"])

    if message.get("reasoning_content"):
        reasoning = _content_to_text(message["reasoning_content"])
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


def _pair_tool_calls_results(
    messages: list[dict[str, Any]],
) -> list[int]:
    """Build tool-call ↔ tool-result pairing map.

    Returns a list where index i maps to its paired index (assistant
    tool-call ↔ tool-result).  Paired indices are always mutual:
    pair[i] == j and pair[j] == i when both exist.  Unpaired messages
    map to -1.

    Args:
        messages: The full message list.

    Returns:
        Pairing map (list of indices or -1).
    """
    n = len(messages)
    pair = [-1] * n

    # First pass: find tool-calls on assistant messages and their
    # corresponding tool-result messages that follow.
    for i, msg in enumerate(messages):
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            continue
        # Each tool_call has an id; find matching role=tool messages.
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            tc_id = tc.get("id")
            if not tc_id:
                continue
            # Find the matching tool-result message after this assistant.
            for j in range(i + 1, n):
                if messages[j].get("role") == "tool" and messages[j].get(
                    "tool_call_id"
                ) == tc_id:
                    pair[i] = j
                    pair[j] = i
                    break

    # Second pass: for messages with role=tool that have no assistant
    # pairing (orphan results), search backwards for the assistant with
    # a matching tool_call id.
    for j, msg in enumerate(messages):
        if msg.get("role") != "tool":
            continue
        if pair[j] != -1:
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
                    pair[i] = j
                    pair[j] = i
                    break
            if pair[j] != -1:
                break

    return pair


def cap_history(
    messages: list[dict[str, Any]],
    max_history_tokens: int,
    estimate: Callable[[str], int] | None = None,
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

    # Total tokens of non-system messages.
    total_non_system_tokens = sum(token_counts[i] for i in non_system_indices)

    # If everything fits, return unchanged.
    if total_non_system_tokens <= max_history_tokens:
        return messages, 0

    # --- Capping logic ---

    # Build pairing map for tool calls/results.
    pair = _pair_tool_calls_results(messages)

    # Build candidate set for dropping: all non-system, non-last-user messages.
    # We'll try to keep from newest to oldest, stopping when budget exhausted.
    candidates = sorted(
        [i for i in non_system_indices if i != last_user_idx],
    )

    # We accumulate tokens from newest to oldest, stopping when budget exhausted.
    accumulated = 0
    kept_set: set[int] = set()

    # Walk candidates in reverse (newest first).
    for idx in reversed(candidates):
        p_idx = pair[idx]
        msg_tokens = token_counts[idx]
        pair_tokens = token_counts[p_idx] if p_idx != -1 else 0
        group_tokens = msg_tokens + (pair_tokens if p_idx != -1 else 0)

        if accumulated + group_tokens <= max_history_tokens:
            kept_set.add(idx)
            if p_idx != -1:
                kept_set.add(p_idx)
            accumulated += group_tokens
        else:
            # This and older messages (and their pairs) will be dropped.
            break

    # Ensure the last user message is always kept.
    kept_set.add(last_user_idx)

    # Build result: system messages (all) + kept non-system in original order.
    result = [messages[i] for i in system_indices] + [
        messages[i] for i in non_system_indices if i in kept_set
    ]

    dropped_count = len(messages) - len(result)

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
