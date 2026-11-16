"""Structure-only summary of an inbound message list (history-cap observability).

Why this is a module of its own
------------------------------

``packages/pipeline/history.py`` is measured as a *symbol set*.  Its own header
says so: constants live there as constants, not behind a helper function, "so
this file's index symbols - what the changed-file ranking sees when
``packages/pipeline/history`` is the dirty module - stay the set every
measurement of them recorded".  The changed-file A/B case built on the
``explain_changed_files_history_cap`` probe
(``tests/observability/test_quality_harness.py``) then asserts how many symbols
that dirty module promotes, and it is a live-path test.

Adding a function there would therefore move a retrieval measurement that belongs
to no part of this task.  So the summary lives here and calls the real capping
code from outside:

* :func:`packages.pipeline.history._message_token_count` prices every message,
  at the ratio the request's resolved model calibrated;
* :func:`packages.pipeline.history._build_cap_groups` supplies the atomic groups,
  so a "group" in this summary is the same unit capping keeps or drops;
* :func:`packages.pipeline.history._trailing_assistant_count` reproduces the
  protected-turn position ``cap_history`` falls back to when a transcript holds
  no user message.

Nothing here restates grouping or counting.  Nothing here drops, truncates,
reorders, copies or replaces a message, and
:func:`packages.pipeline.history.cap_history` is never consulted: this is the
observation a cap decision needs, not a cap.

Privacy
-------

The result contains counts, booleans, one float, and three kinds of string: the
schema token, the status token, and a role drawn from a fixed list.  It cannot
contain message content, a content preview, reasoning text, a tool name, a tool
argument, a raw tool-call id, a path derived from message text, or a hash of any
of them.  A tool-call id is reduced to set membership inside
:func:`_shape_id_key` and discarded; a ``role`` outside :data:`_SHAPE_ROLES` is
reported as ``other`` rather than echoed back, so the one client-controlled string
in the shape cannot reach a log either.  Positions are relative - a newest-first
group ordinal and a distance from the end - never message indices.

Usage
-----

.. code-block:: python

    from packages.pipeline.history_shape import summarize_history_shape

    summary = summarize_history_shape(messages, chars_per_token=3.5)

"""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable, Sequence

from packages.context.budget import CHARS_PER_TOKEN
from packages.pipeline.history import (
    RATIO_MAX,
    RATIO_MIN,
    _build_cap_groups,
    _message_token_count,
    _trailing_assistant_count,
)

#: Version token a summary carries, so a reader of ``history.shape`` in a session
#: record knows which fields it is contracted to hold.  It is stated in the
#: summary itself rather than inferred from the date of the log.
#:
#: v2 changed what the detail bound counts.  v1 stopped recording groups once the
#: groups it had written carried ``MAX_SHAPE_DETAIL_TOKENS`` tokens, but that total
#: included system text and the protected current turn, neither of which
#: ``cap_history`` ever charges against a budget.  A transcript whose protected
#: turn (or a system message) was itself larger than the floor therefore recorded
#: nothing that a cap simulation needs.  v2 counts cap-eligible tokens only, states
#: the eligible partition explicitly, and reserves the protected turn's detail so
#: the marker cannot drop out of a bounded list.
SHAPE_SCHEMA_VERSION: str = "history-shape-v2"

#: Status token of a summary that was actually built.
SHAPE_MEASURED: str = "measured"

#: Status token a caller records when the summary could not be built, so an
#: absent measurement is never read as a zero.
SHAPE_UNAVAILABLE: str = "unavailable"

#: How many atomic groups a shape summary may detail.  This is a count, not a
#: token budget, and it bounds one session-log line the way the repository's
#: other observational bounds bound theirs - 256 envelopes per request in
#: ``packages/pipeline/cline_activity.py`` and three 256-entry limits in
#: ``packages/pipeline/file_activity.py``.  Truncation is never silent: a summary
#: that stopped early states ``omitted_groups``, ``omitted_tokens`` and
#: ``detail_complete: false``, while every top-level total still describes the
#: whole message list.
MAX_SHAPE_GROUPS: int = 256

#: How far the ordered detail has to reach in **cap-eligible** tokens before it is
#: allowed to stop.  It is the largest budget a history-cap policy measurement is
#: planned against - 128k tokens - and capping keeps a prefix of the newest-first
#: group order (``cap_history`` walks newest-first and breaks at the first group that
#: does not fit), so a prefix carrying this many eligible tokens places the cut for
#: every smaller budget in that sweep too.  A detail that stops here rather than at
#: :data:`MAX_SHAPE_GROUPS` is therefore complete for 16k/32k/64k/96k/128k simulation;
#: a detail that stopped at the count bound is not, and says so.
#:
#: System messages and the protected current turn do not advance this counter: they
#: are never charged against a budget, so counting them would let a transcript's
#: largest always-kept message buy the detail out of the history it exists to record.
#: :func:`_cap_eligible_group_tokens` is the single place that decides what counts.
MAX_SHAPE_DETAIL_TOKENS: int = 131072

#: The role tokens a shape summary is allowed to state.  The set is wider than
#: the four roles capping reads, because a summary of what actually arrives has
#: to be able to say that something else arrived.
_SHAPE_ROLES: tuple[str, ...] = (
    "assistant",
    "developer",
    "function",
    "system",
    "tool",
    "user",
)

_SHAPE_OTHER_ROLE: str = "other"


def _shape_role(message: dict[str, Any]) -> str:
    """Return the structural role token of one message.

    Only :data:`_SHAPE_ROLES` can be stated.  A role outside that set - which a
    malformed client can send - is reported as ``other`` rather than echoed, so
    the summary has no field a caller can write text into.

    Args:
        message: A single message dict.

    Returns:
        One of the known role tokens, or ``other``.
    """
    role = message.get("role")
    if isinstance(role, str) and role in _SHAPE_ROLES:
        return role
    return _SHAPE_OTHER_ROLE


def _shape_ratio(chars_per_token: float | None) -> float:
    """Return the characters-per-token ratio a summary may divide by.

    The same range ``cap_history`` guards with, restated here rather than shared
    as a helper, because this pass must not become a reason to touch the capping
    path.  An unusable ratio falls back to the platform estimate, so a summary is
    never the thing that raises on a bad setting.

    Args:
        chars_per_token: The caller's ratio, or ``None``.

    Returns:
        A ratio safe to divide by.
    """
    if (
        not isinstance(chars_per_token, bool)
        and isinstance(chars_per_token, (int, float))
        and math.isfinite(chars_per_token)
        and RATIO_MIN <= chars_per_token <= RATIO_MAX
    ):
        return float(chars_per_token)
    return CHARS_PER_TOKEN


def _protected_history_index(messages: list[dict[str, Any]]) -> int | None:
    """Return the index ``cap_history`` treats as the turn it never drops.

    That is the last ``user`` message when one exists.  When none does, capping
    falls back to the position after the trailing assistant messages, and this
    reproduces that fallback through the production helper so the group marked
    protected here is the group the real cap would mark: the point is a faithful
    simulation, not a nicer story.

    Args:
        messages: The full message list.

    Returns:
        The protected index, or ``None`` when there is nothing to protect.
    """
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            return i
    if not messages:
        return None
    fallback = len(messages) - 1 - _trailing_assistant_count(messages)
    return fallback if 0 <= fallback < len(messages) else None


def _shape_id_key(value: Any) -> str:
    """Return a membership key for a tool-call id, never the id itself.

    The key exists only to ask whether some id appears on both sides of a
    pairing.  It is never placed in a summary.  An absent, empty or exotic id
    maps to the empty string, which matches nothing and therefore reads as
    orphan - the same thing ``_build_cap_groups`` declines to link on.

    Args:
        value: The raw ``id`` or ``tool_call_id`` field.

    Returns:
        A string key for in-memory membership only.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return ""


def _cap_eligible_group_tokens(
    group: Iterable[int],
    tokens: Sequence[int],
    is_system: Sequence[bool],
    protected: int | None,
) -> int:
    """What ``cap_history`` would charge one group against its budget.

    This is the eligibility rule stated once: a message is charged when it is not a
    system message and is not the protected current turn.  Capping keeps both of
    those regardless of budget, so they are worth nothing to the question a summary
    exists to answer - and the second is exactly the message an agent client sends
    biggest, which is why leaving it in a coverage count was a bug rather than a
    rounding error.

    Args:
        group: The message indices of one atomic group.
        tokens: Per-message estimates, in the order of the message list.
        is_system: Whether each message is a system message.
        protected: The index capping protects, or ``None``.

    Returns:
        The group's cap-eligible tokens.
    """
    return sum(tokens[i] for i in group if not is_system[i] and i != protected)


def summarize_history_shape(
    messages: list[dict[str, Any]],
    chars_per_token: float | None = None,
    estimate: Callable[[str], int] | None = None,
    max_groups: int = MAX_SHAPE_GROUPS,
    max_detail_tokens: int = MAX_SHAPE_DETAIL_TOKENS,
) -> dict[str, Any]:
    """Summarize the structure of a message list without reading its text.

    This is the observation half of the history-cap question: it states what an
    inbound conversation is *made of* - how many atomic groups
    :func:`packages.pipeline.history._build_cap_groups` carves it into, what each
    is worth under the estimator
    :func:`packages.pipeline.history._message_token_count` applies, in the
    newest-first order capping walks - so a cap policy can be simulated
    afterwards, offline, from a session log.  It changes nothing: no message is
    dropped, truncated, reordered or copied, and ``cap_history`` is not called.

    Both the numbers and the groups are the production ones.  A group's token
    figure is ``_message_token_count`` summed over its members at the caller's
    ratio - so content, ``name``, ``reasoning_content`` and tool-call names and
    arguments are all *worth* what capping says they are worth, while none of
    them is *quoted* - and the groups are exactly what ``_build_cap_groups``
    returns, so what a summary says a budget would keep is what the cap keeps.

    Args:
        messages: The full message list, system messages included.
        chars_per_token: The calibrated ratio to estimate with - the same one the
            real history-cap path resolves from the resolved model.  ``None``, or
            an unusable value, keeps the platform default.
        estimate: A caller's text-to-token estimator, passed straight to
            ``_message_token_count``.  It wins over ``chars_per_token`` exactly
            as it does in ``cap_history``.
        max_groups: How many newest groups to detail.  Defaults to
            :data:`MAX_SHAPE_GROUPS`.
        max_detail_tokens: How far the detail must reach in cap-eligible tokens
            before it is allowed to stop - system and protected-turn tokens advance
            it by nothing.  Defaults to :data:`MAX_SHAPE_DETAIL_TOKENS`.

    Returns:
        The ``history-shape-v2`` summary of ``messages``: counts, booleans, the
        resolved ratio, three kinds of fixed token (the schema, the status and role
        names), one nested group of the same shape as an entry of ``groups``, and a
        bounded newest-first ``groups`` list.  No text a caller wrote is in it - not
        content, a preview, reasoning, a tool name, an argument, a tool-call id, a
        path derived from any of them, or a hash of any of them - and no raw message
        index: a position is stated as a newest-first group ordinal or as a distance
        from the end.

        To read a budget out of it: walk ``groups`` by ascending ``ordinal``,
        unconditionally keeping any group marked ``has_system`` or ``has_last_user``
        and charging nothing for it, and stop at the first other group whose
        ``cap_eligible_tokens`` no longer fits.  That is ``cap_history``'s rule
        restated as a prefix of this order, because capping breaks at the first group
        it cannot fit.

        Two partitions are stated, both exact over the whole list:
        ``recorded_tokens + omitted_tokens`` is the estimate of every message, system
        text included, and ``recorded_cap_eligible_tokens +
        omitted_cap_eligible_tokens == cap_eligible_tokens`` is the part of it a
        budget is actually measured against.  Only the second advances the
        :data:`MAX_SHAPE_DETAIL_TOKENS` coverage bound: a group the cap never charges
        must not be able to buy the detail out of the history it exists to record.

        ``last_user_group`` is that reservation made explicit - the detail of the
        group holding the turn capping never drops, present whether or not the
        bounded walk reached its ordinal, and ``null`` only when the list holds
        nothing to protect.  It repeats the matching entry when the prefix already
        recorded that group, and it is not a member of ``groups``, so ``groups`` stays
        one contiguous newest-first prefix and ``omitted_groups`` keeps counting
        groups absent from that list.
    """
    ratio = _shape_ratio(chars_per_token)

    roles: list[str] = []
    is_system: list[bool] = []
    is_user: list[bool] = []
    is_tool_result: list[bool] = []
    has_tool_calls: list[bool] = []
    call_ids: list[list[str]] = []
    result_ids: list[str] = []
    tokens: list[int] = []

    for message in messages:
        raw_role = message.get("role")
        known_role = raw_role if isinstance(raw_role, str) else ""
        roles.append(_shape_role(message))
        is_system.append(known_role == "system")
        is_user.append(known_role == "user")
        is_tool_result.append(known_role == "tool")

        ids: list[str] = []
        call_count = 0
        result_key = ""
        if known_role == "assistant":
            raw_calls = message.get("tool_calls")
            if isinstance(raw_calls, list):
                calls = [tc for tc in raw_calls if isinstance(tc, dict)]
                call_count = len(calls)
                ids = [_shape_id_key(tc.get("id")) for tc in calls]
        elif known_role == "tool":
            result_key = _shape_id_key(message.get("tool_call_id"))

        has_tool_calls.append(known_role == "assistant" and call_count > 0)
        call_ids.append(ids)
        result_ids.append(result_key)
        tokens.append(_message_token_count(message, ratio, estimate))

    n = len(messages)
    paired_results = {key for key in result_ids if key}
    paired_calls = {key for ids in call_ids for key in ids if key}
    orphan_calls = [sum(1 for key in ids if key not in paired_results) for ids in call_ids]
    orphan_results = [
        1 if is_tool_result[i] and result_ids[i] not in paired_calls else 0 for i in range(n)
    ]

    protected = _protected_history_index(messages)
    last_user_index: int | None = None
    for i in range(n - 1, -1, -1):
        if is_user[i]:
            last_user_index = i
            break

    # The cap's own atomic units, walked in the cap's own order: newest first, by
    # each group's most recent member.  Two groups cannot share a maximum index,
    # so the order is total and one list summarizes identically twice running.
    ordered = sorted(_build_cap_groups(messages), key=lambda group: max(group), reverse=True)

    detail: list[dict[str, Any]] = []
    recorded_tokens = 0
    recorded_messages = 0
    recorded_eligible = 0
    complete_tool_groups = 0
    last_user_group: dict[str, Any] | None = None
    group_limit = max(0, int(max_groups))
    detail_limit = max(0, int(max_detail_tokens))

    for ordinal, group in enumerate(ordered):
        group_tokens = sum(tokens[i] for i in group)
        # What a budget would be charged for this group - the same rule the
        # cap_eligible_tokens total is built from, and the only figure allowed to
        # advance the coverage bound.  System text and the protected turn are
        # always kept and never spend anything, so counting them here would let a
        # transcript's largest always-kept message buy the detail out of the
        # history the detail exists to record.
        group_eligible = _cap_eligible_group_tokens(group, tokens, is_system, protected)
        group_orphan_calls = sum(orphan_calls[i] for i in group)
        group_orphan_results = sum(orphan_results[i] for i in group)
        group_has_calls = any(has_tool_calls[i] for i in group)
        # Nothing in the group dangles.  A group carrying no tool traffic
        # satisfies this trivially, and has_tool_calls/has_tool_results say
        # whether there was any to speak of.
        group_pairing = not group_orphan_calls and not group_orphan_results
        if group_has_calls and group_pairing:
            complete_tool_groups += 1
        role_counts: dict[str, int] = {}
        for i in group:
            role_counts[roles[i]] = role_counts.get(roles[i], 0) + 1
        group_protected = protected in group
        entry: dict[str, Any] = {
            "ordinal": ordinal,
            "message_count": len(group),
            "tokens": group_tokens,
            "cap_eligible_tokens": group_eligible,
            "roles": dict(sorted(role_counts.items())),
            "has_system": any(is_system[i] for i in group),
            "has_last_user": group_protected,
            "has_tool_calls": group_has_calls,
            "has_tool_results": any(is_tool_result[i] for i in group),
            "pairing_complete": group_pairing,
            "orphan_tool_calls": group_orphan_calls,
            "orphan_tool_results": group_orphan_results,
        }
        if group_protected:
            # The protected turn's group is reserved rather than bound: its detail
            # reaches the record whether or not the walk ever reached this ordinal,
            # so a bounded list cannot silently lose the one group capping is
            # guaranteed to keep.  Every group has its own copy of this shape, and
            # ``groups`` stays a contiguous newest-first prefix.
            last_user_group = entry
        if len(detail) >= group_limit or recorded_eligible >= detail_limit:
            # The bound keeps the newest groups and leaves the oldest out, in the
            # same direction a budget runs out.  The totals still count them all.
            continue
        detail.append(entry)
        recorded_tokens += group_tokens
        recorded_messages += len(group)
        recorded_eligible += group_eligible

    # Summed over the groups rather than over the indices: the two are equal
    # because the groups partition the list, and stating the total the same way the
    # per-group figures are computed is what makes the recorded/omitted partition
    # hold by construction instead of by agreement between two expressions.
    cap_eligible_total = sum(
        _cap_eligible_group_tokens(group, tokens, is_system, protected)
        for group in ordered
    )

    system_count = sum(1 for flag in is_system if flag)
    return {
        "schema": SHAPE_SCHEMA_VERSION,
        "status": SHAPE_MEASURED,
        "chars_per_token": ratio,
        "message_count": n,
        "system_message_count": system_count,
        "non_system_message_count": n - system_count,
        "history_tokens": sum(tokens[i] for i in range(n) if not is_system[i]),
        "cap_eligible_tokens": cap_eligible_total,
        "group_count": len(ordered),
        "recorded_groups": len(detail),
        "omitted_groups": len(ordered) - len(detail),
        "recorded_tokens": recorded_tokens,
        "omitted_tokens": sum(tokens) - recorded_tokens,
        "recorded_cap_eligible_tokens": recorded_eligible,
        "omitted_cap_eligible_tokens": cap_eligible_total - recorded_eligible,
        "omitted_messages": n - recorded_messages,
        "detail_complete": len(detail) == len(ordered),
        "last_message_role": roles[-1] if roles else "",
        "last_user_distance": None if last_user_index is None else n - 1 - last_user_index,
        "last_user_group": last_user_group,
        "assistant_with_tool_calls": sum(1 for flag in has_tool_calls if flag),
        "tool_result_count": sum(1 for flag in is_tool_result if flag),
        "complete_tool_groups": complete_tool_groups,
        "orphan_tool_calls": sum(orphan_calls),
        "orphan_tool_results": sum(orphan_results),
        "groups": detail,
    }
