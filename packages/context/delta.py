"""Delta context injection for multi-turn sessions.

Identifies which symbols have already been sent in a conversation so that
``RepositoryContextStage`` can skip redundant re-injections.

Conversation key
----------------

A conversation turn is identified by hashing **only the user messages
already seen** (the prefix, excluding the new user turn).  This means
assistant replies never change the key, so turn N stores under the same
key that turn N+1 looks up.

This is intentionally simple and pure – no I/O, no providers, no
repository access.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.context.models import ContextCandidate

_SENTINEL_KEY = "__new__"


def _hash_user_turns(users: list[dict[str, str]]) -> str:
    """Hash a list of user messages by position and content.

    The index is folded into the hash so that two identical consecutive
    questions produce different keys — otherwise repeating a question would
    collide with its own earlier turn in the cache.

    Args:
        users: User-role messages, in order.

    Returns:
        A hex SHA-256 digest, or the ``__new__`` sentinel for an empty list.
    """
    if not users:
        return _SENTINEL_KEY

    h = hashlib.sha256()
    for i, m in enumerate(users):
        h.update(f"{i}\x00".encode())
        h.update(m.get("content", "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def conversation_key(messages: list[dict[str, str]]) -> str:
    """Stable lookup key for a conversation, keyed on user messages only.

    Hashes the sequence of **user** turns excluding the current (last)
    one, so the value stored on turn N is found by the lookup on turn N+1.
    Assistant replies do not affect the key — they are invisible to the
    cache.  Returns the sentinel ``__new__`` when there are no prior user
    turns (first turn of a session).

    Args:
        messages: The full message list from the request.

    Returns:
        A lowercase hex SHA-256 digest, or ``__new__`` when no prior
        user turns exist.
    """
    users = [m for m in messages if m.get("role") == "user"]
    return _hash_user_turns(users[:-1])


def store_key(messages: list[dict[str, str]]) -> str:
    """Key under which to store this turn's full symbol set.

    Hashes **all** user messages including the current one.  The result
    equals what the next turn's :func:`conversation_key` computes (its
    prefix will include this turn's user message), so turn N's store is
    found by turn N+1's lookup.

    Args:
        messages: The full message list from the request.

    Returns:
        A lowercase hex SHA-256 digest, or ``__new__`` when no user turns.
    """
    users = [m for m in messages if m.get("role") == "user"]
    return _hash_user_turns(users)


class SentSymbolTracker:
    """LRU cache mapping conversation keys -> sets of injected qualified names.

    Uses an ``OrderedDict`` internally so it works on Python 3.13
    (where ``functools.LRUCache`` is not available).

    Attributes:
        maxsize: Maximum number of entries before evicting the least-recently-used.
    """

    __slots__ = ("_cache", "_maxsize")

    def __init__(self, maxsize: int = 256) -> None:
        """Initialise the tracker.

        Args:
            maxsize: Maximum number of conversation entries to keep.
        """
        self._maxsize = maxsize
        self._cache: OrderedDict[str, set[str]] = OrderedDict()

    def get(self, conversation_key: str) -> set[str]:
        """Return the set of already-injected symbols for *key*.

        Moves the key to the end (most-recently-used) position so that
        frequently accessed keys are retained.

        Args:
            conversation_key: The key returned by :func:`compute_conversation_key`.

        Returns:
            A set of qualified symbol names, or an empty set on cache miss.
        """
        if conversation_key in self._cache:
            self._cache.move_to_end(conversation_key)
            return self._cache[conversation_key]
        return set()

    def store(self, conversation_key: str, symbols: set[str]) -> None:
        """Store a set of already-injected symbols under *key*.

        Evicts the oldest entry if ``maxsize`` is exceeded.

        Args:
            conversation_key: The key returned by
                :func:`conversation_key` (user-message prefix key).
            symbols: The set of *all* injected symbols (union of old + new).
        """
        if self._maxsize <= 0:
            return

        if conversation_key in self._cache:
            self._cache[conversation_key] = symbols
            self._cache.move_to_end(conversation_key)
            return

        if len(self._cache) >= self._maxsize:
            self._cache.popitem(last=False)

        self._cache[conversation_key] = symbols

    def clear(self) -> None:
        """Remove all entries from the cache."""
        self._cache.clear()


def filter_candidates(
    candidates: list["ContextCandidate"],
    already_sent: set[str],
) -> list["ContextCandidate"]:
    """Return candidates minus already-sent supporting symbols.

    The primary symbol (first in the list) is always preserved even if it
    appears in ``already_sent``.

    Args:
        candidates: Ranked candidate list from the builder (may be empty).
        already_sent: Set of qualified names already injected in this
            conversation.

    Returns:
        A filtered candidate list with no duplicates and the primary intact.
    """
    if not candidates:
        return candidates

    if not already_sent:
        return candidates

    # Always keep the primary (first candidate).
    primary = candidates[0]
    filtered: list["ContextCandidate"] = [primary]
    seen: set[str] = {primary.qualified_name}

    for c in candidates[1:]:
        if c.qualified_name in already_sent:
            continue
        if c.qualified_name in seen:
            continue
        seen.add(c.qualified_name)
        filtered.append(c)

    return filtered


def collect_all_symbols(
    candidates: list["ContextCandidate"],
) -> set[str]:
    """Return the set of all qualified names in *candidates*.

    Args:
        candidates: Ranked candidate list.

    Returns:
        Set of qualified names including the primary.
    """
    return {c.qualified_name for c in candidates}