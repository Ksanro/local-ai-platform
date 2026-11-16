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

    capped, dropped = cap_history(
        messages,
        max_history_tokens=16384,
        chars_per_token=3.5,  # the resolved model's calibration
    )

``chars_per_token`` is optional; left out, or given anything unusable, the
estimate is the platform's ``CHARS_PER_TOKEN`` (4.0) it has always been.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from packages.context.budget import CHARS_PER_TOKEN
from packages.context.content import content_to_text
from packages.pipeline.user_messages import CLINE_TOOL_RESULT_PREFIXES

#: Bounds a characters-per-token ratio may be used at.  This is the range
#: ``packages/providers/registry_models.py`` validates ``chars_per_token``
#: against, restated here because this module is where the ratio is used as a
#: divisor: a value that arrives by another path is checked before it divides.
#: Kept as constants rather than a helper function so this file's index symbols -
#: what the changed-file ranking sees when ``packages/pipeline/history`` is the
#: dirty module - stay the set every measurement of them recorded.
RATIO_MIN: float = 0.5
RATIO_MAX: float = 20.0


def _estimate_tokens(content: str, chars_per_token: float = CHARS_PER_TOKEN) -> int:
    """Estimate token count from text at a calibrated characters-per-token ratio.

    Args:
        content: The text to estimate tokens for.
        chars_per_token: The ratio to divide by.  Callers pass one already
            checked against ``RATIO_MIN``/``RATIO_MAX``, so it is never zero,
            negative or NaN; the default keeps this the platform estimate it was
            before roadmap A3.

    Returns:
        Estimated token count.
    """
    return int(len(content) / chars_per_token) if content else 0


def _message_token_count(
    message: dict[str, Any],
    chars_per_token: float = CHARS_PER_TOKEN,
    estimate: Callable[[str], int] | None = None,
) -> int:
    """Estimate the token count of a single message.

    Counts the ``content``, ``name``, and ``reasoning_content`` fields.
    For assistant messages with ``tool_calls``, also counts the tool call
    name and arguments.

    Args:
        message: A single message dict.
        chars_per_token: The calibrated ratio to divide by when the caller did
            not supply its own estimator.
        estimate: A caller's text-to-token estimator, applied to every text
            field counted.  Before roadmap A3 this parameter existed on
            ``cap_history`` and was never passed down here at all, so the
            counting always went through the global constant.

    Returns:
        Estimated token count.
    """
    texts: list[str] = [content_to_text(message.get("content", ""))]

    if message.get("name"):
        texts.append(message["name"])

    if message.get("reasoning_content"):
        texts.append(content_to_text(message["reasoning_content"]))

    # Count tool_calls content for assistant messages.
    tool_calls = message.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            if isinstance(tc, dict):
                fn = tc.get("function", {})
                if isinstance(fn, dict):
                    texts.append(fn.get("name", ""))
                    texts.append(fn.get("arguments", ""))

    if estimate is not None:
        return sum(estimate(text) for text in texts)
    return sum(_estimate_tokens(text, chars_per_token) for text in texts)


def _looks_like_cline_tool_result_message(message: dict[str, Any]) -> bool:
    """Return True for Cline tool-result envelopes sent as user text.

    The recognition is the pipeline's planning/history compatibility view,
    ``CLINE_TOOL_RESULT_PREFIXES`` from :mod:`packages.pipeline.user_messages`,
    which is derived from the one Cline envelope registry - so this module and
    task-text selection cannot drift apart.  It is deliberately *not* the set the
    file-activity boundary reads: roadmap C1 taught the gateway to measure
    ``write_to_file`` and ``replace_in_file`` results, and capping their text here
    would have changed what the model receives, which is outside C1's scope.  A
    writer's result is therefore still forwarded whole and is never truncated.
    """
    if message.get("role") != "user":
        return False

    content = content_to_text(message.get("content", ""))
    return content.lstrip().startswith(CLINE_TOOL_RESULT_PREFIXES)


def _truncate_message_content(
    message: dict[str, Any],
    max_tokens: int,
    chars_per_token: float = CHARS_PER_TOKEN,
) -> dict[str, Any]:
    """Return a shallow copy with text content truncated.

    Args:
        message: The message to truncate.
        max_tokens: The token budget the truncated text has to fit in.
        chars_per_token: The ratio that converts that budget back into
            characters - the same calibration the counting of this pass used, so
            a message kept under the budget is not truncated past it and a
            message truncated to the budget is not kept past it either.
    """
    if max_tokens <= 0:
        return message

    max_chars = int(max_tokens * chars_per_token)
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
    chars_per_token: float = CHARS_PER_TOKEN,
) -> list[dict[str, Any]]:
    """Cap the current Cline tool-result message without dropping it.

    Only the messages :func:`_looks_like_cline_tool_result_message` recognizes are
    candidates, which is the planning/history compatibility set - the four tools
    the gateway treated as Cline bookkeeping before roadmap C1, plus the two
    reminder bodies.  A ``write_to_file`` or ``replace_in_file`` result is not
    truncated here: it carries the file's whole new content, and shortening it
    would be a change to what the model is shown.

    Args:
        messages: The message list to cap the current envelope in.
        max_current_tool_result_tokens: The token budget that envelope has to
            fit in, or ``None`` to leave every message as it arrived.
        chars_per_token: The ratio converting that budget to characters.
    """
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
        chars_per_token=chars_per_token,
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
    chars_per_token: float | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return (capped_messages, dropped_count).

    Keeps the conversation valid while fitting recent history into a
    token budget.  Older messages are dropped first.

    Rules (in priority order):

    1. **Never drop system messages.** All system messages are kept
       regardless of budget. They are not counted against
       ``max_history_tokens``.
    2. **Never drop the protected turn, and never drop part of the group
       around it.** The protected turn is the last ``user`` message when the
       list holds one, and that message is kept in full.  A list with no user
       message - the tail of an agent loop, or an all-assistant transcript -
       has no such message, so the protected *position* falls back to the slot
       after the trailing assistant messages, which can hold an assistant
       message or a ``role: "tool"`` result; when even that falls outside the
       list (every message is a trailing assistant) there is nothing to
       protect and no index is invented for it.  Whatever role the protected
       position holds, it belongs to one atomic group (rule 4) and the whole
       group is kept: keeping a lone tool result while dropping the assistant
       call that produced it would emit an orphan.  Only the protected message
       itself is free of the budget; the other members of its group are worth
       what ``summarize_history_shape`` says they are, and are *reserved*
       against the budget before any other group is considered.
    3. **Keep the most recent groups that fit what the reservation leaves** of
       ``max_history_tokens``, walking backward from the newest and stopping at
       the first group that does not fit.  Older messages are dropped first,
       and a group that cannot be kept whole is not kept at all.
    4. **Preserve tool-call / tool-result pairing.** If a message is an
       assistant tool call and its matching tool result would be dropped
       (or vice versa), drop or keep them **together**.  Never leave a
       tool call without its result or a result without its call.
    5. **Preserve order, and never duplicate a message.** The kept messages
       stay in their original relative order and each input message appears at
       most once, because what is kept is a set of positions in the input.
    6. **When nothing needs dropping** (history already fits), return the
       messages unchanged and ``dropped_count=0``.  The transform is a
       no-op under the budget.
    7. **``dropped_count`` is truthful**: it is always
       ``len(messages) - len(capped_messages)``.

    Args:
        messages: Full message list including system messages.
        max_history_tokens: Token budget for non-system messages other than the
            protected one.  When the protected position falls inside a larger
            atomic group, that group's cap-eligible tokens are charged against
            this budget first and the rest of it is what the walk gets to fill.
        estimate: A callable that estimates token count from text.  Applied to
            every text field that is counted.  If not provided, uses
            ``int(len(text) / chars_per_token)``.
        max_current_tool_result_tokens: Optional cap for the final user
            message when it is a Cline-style tool-result envelope.
        chars_per_token: Calibrated characters-per-token ratio used wherever
            this pass converts between characters and tokens - the default
            estimator and the current-envelope truncation.  ``None`` keeps the
            platform default.  An unusable value falls back to it rather than
            reaching the math; an explicit ``estimate`` still wins for the
            counting it drives.

    Returns:
        A tuple of (capped_messages, dropped_count).
    """
    # A ratio is used here as both a divisor and a multiplier, so an unusable
    # value is not merely inaccurate: zero raises, a negative one inverts the
    # size ordering this exists to measure, and NaN compares false against every
    # budget and so caps nothing at all.  Anything outside the range the provider
    # registry validates ``chars_per_token`` against falls back to the platform
    # estimate instead of reaching the math.
    ratio: float = CHARS_PER_TOKEN
    if (
        not isinstance(chars_per_token, bool)
        and isinstance(chars_per_token, (int, float))
        and math.isfinite(chars_per_token)
        and RATIO_MIN <= chars_per_token <= RATIO_MAX
    ):
        ratio = float(chars_per_token)

    if not messages:
        return messages, 0

    # Count tokens for each message.
    token_counts: list[int] = [_message_token_count(m, ratio, estimate) for m in messages]

    # Separate system messages (never counted, never dropped).
    system_indices = [i for i, m in enumerate(messages) if m.get("role") == "system"]
    non_system_indices = [i for i, m in enumerate(messages) if m.get("role") != "system"]

    if not non_system_indices:
        return messages, 0

    # The position this pass never drops.  A real ``user`` message when the list
    # holds one; otherwise the fallback slot after the trailing assistant
    # messages, which is a position rather than a user message; and otherwise
    # nothing at all.  The validity guard matters: on an all-assistant list the
    # fallback is ``len(messages) - 1 - len(messages)``, i.e. ``-1``, and a
    # ``-1`` among the kept positions reads back as ``messages[-1]`` - the newest
    # message kept twice, out of order, with a dropped count that no longer
    # describes what came out.  An index outside the list protects nothing, so
    # it never enters the kept set.
    protected_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            protected_idx = i
            break
    if protected_idx is None:
        fallback_idx = len(messages) - 1 - _trailing_assistant_count(messages)
        protected_idx = fallback_idx if 0 <= fallback_idx < len(messages) else None

    # FIX 3: Total tokens of non-system messages EXCLUDING the protected one.
    # The protected message is always kept outside the budget.  This is the same
    # figure ``summarize_history_shape`` states as ``cap_eligible_tokens``, which
    # is what lets a budget be read off a recorded shape and land here.
    eligible_total = sum(token_counts[i] for i in non_system_indices if i != protected_idx)

    # If everything fits, return unchanged.
    if eligible_total <= max_history_tokens:
        return (
            _cap_current_tool_result(
                messages, max_current_tool_result_tokens, ratio
            ),
            0,
        )

    # --- Capping logic ---

    # Build atomic groups for tool-call/result pairing.
    groups = _build_cap_groups(messages)

    # The group the protected position belongs to.  It is reserved rather than
    # treated as a candidate, because capping cannot split an atomic group: a
    # protected tool result travels with the assistant call that produced it,
    # and a protected assistant call travels with its results.  For a list that
    # holds a real user message this is exactly the single protected message it
    # has always been, because grouping links assistant calls to tool results
    # and never touches a ``user`` or ``system`` message.
    protected_group: set[int] = set()
    if protected_idx is not None:
        for group in groups:
            if protected_idx in group:
                protected_group = group
                break

    # Build candidate groups for dropping: everything except the protected
    # group, and only groups with at least one member that is not a system
    # message - a group of nothing but system text is kept regardless.
    # Each group is a set of indices.
    candidate_groups: list[set[int]] = []
    for group in groups:
        if group == protected_group:
            continue
        has_capable_member = any(i not in system_indices for i in group)
        if has_capable_member:
            candidate_groups.append(group)

    # If no candidate groups, nothing to cap: what is left is system text and
    # the protected group, all of which is kept whatever the budget says.
    if not candidate_groups:
        return (
            _cap_current_tool_result(
                messages, max_current_tool_result_tokens, ratio
            ),
            0,
        )

    # Sort groups by their maximum index (newest-first ordering).
    candidate_groups.sort(key=lambda g: max(g), reverse=True)

    # Reserve before filling: the protected group is kept whole, but only the
    # protected message inside it is free, so the rest of that group spends
    # budget - and spends it before any other group gets a chance at what is
    # left.  The same eligibility rule prices every candidate group; on
    # candidates it is a no-op (they hold no system and no protected message),
    # which is what keeps a real-user transcript capped precisely as before.
    accumulated = sum(
        token_counts[i]
        for i in protected_group
        if i != protected_idx and i not in system_indices
    )
    kept_groups: list[set[int]] = []

    for group in candidate_groups:
        group_tokens = sum(
            token_counts[i]
            for i in group
            if i != protected_idx and i not in system_indices
        )
        if accumulated + group_tokens <= max_history_tokens:
            kept_groups.append(group)
            accumulated += group_tokens
        else:
            # This and older groups will be dropped.
            break

    # Build kept set: all system indices + the whole protected group + kept
    # group members.  Every one of them is an index that exists in ``messages``,
    # so no message is kept twice and none is pulled out of order.
    kept_set: set[int] = set(system_indices)
    kept_set.update(protected_group)
    for group in kept_groups:
        kept_set.update(group)

    # Build result: all kept messages in original order.
    result = [messages[i] for i in sorted(kept_set)]

    dropped_count = len(messages) - len(result)

    result = _cap_current_tool_result(result, max_current_tool_result_tokens, ratio)
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
