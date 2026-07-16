"""Query utilities for the Context Builder.

Provides helpers for normalising and validating query text before it
reaches the builder.  This module is intentionally thin — the builder
consumes raw ``ContextQuery`` objects directly.
"""

from __future__ import annotations

from packages.context.models import ContextQuery


def normalise_query(query: ContextQuery) -> ContextQuery:
    """Return a normalised copy of the given query.

    Normalisation steps:
    - Strip and collapse whitespace in ``text``.
    - Clamp ``max_symbols`` and ``max_modules`` to positive integers.

    Args:
        query: The query to normalise.

    Returns:
        A new ``ContextQuery`` with normalised values.
    """
    text = query.text.strip()
    # Collapse runs of whitespace into a single space.
    parts = text.split()
    text = " ".join(parts)

    max_symbols = max(1, query.max_symbols) if query.max_symbols > 0 else 0
    max_modules = max(1, query.max_modules) if query.max_modules > 0 else 0

    return ContextQuery(
        text=text,
        max_symbols=max_symbols,
        max_modules=max_modules,
        max_tokens=query.max_tokens,
    )
