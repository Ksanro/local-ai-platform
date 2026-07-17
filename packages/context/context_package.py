"""Structured Context Package v2.

Defines the structured representation produced by the Context Builder.
This is the internal platform model — not a provider payload.

Architecture
------------

Context Builder
       |
       v
Context Package v2
       |
       v
Serializer
       |
       v
Provider (serialises)

The Context Package is **not**

- an OpenAI request
- an Anthropic request
- a DSPARK request
- a provider payload

Providers are responsible for translating ContextPackage into their
own request format.

Constraints
-----------

- No provider-specific fields.
- No token counts beyond what the budget engine already reports.
- No prompt content.
- No formatting instructions.
- No filesystem access.
- No ranking.
- No repository traversal.

Public API
----------

.. code-block:: python

    package = ContextPackage(
        primary_symbol="auth.AuthenticationMiddleware",
        supporting_symbols=["auth.middleware.JWTAuth"],
        related_callers=["main.create_app"],
        related_callees=["auth.Tokens.create_token"],
        related_modules=["auth.py", "main.py"],
        relationship_summary=RelationshipSummary(
            caller_count=1,
            callee_count=1,
            module_count=2,
            symbol_count=4,
        ),
        estimated_tokens=230,
        metadata=ContextMetadata(
            ranking_version="1",
            repository_revision="abc123",
            estimated_tokens=230,
        ),
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContextMetadata:
    """Metadata attached to a context package.

    Attributes:
        ranking_version: Version identifier for the ranking engine
            that produced this package.
        repository_revision: Repository revision (e.g. git commit hash)
            at the time of context assembly.
        estimated_tokens: Estimated token count for the context.
        generated_at: Timestamp string.  Must remain ``None`` to
            guarantee deterministic output.
    """

    ranking_version: str = "1"
    repository_revision: str = ""
    estimated_tokens: int = 0
    generated_at: str | None = None


@dataclass(frozen=True)
class RelationshipSummary:
    """Counts of relationships in a context package.

    Pure metadata — contains no source code.

    Attributes:
        caller_count: Number of symbols in ``related_callers``.
        callee_count: Number of symbols in ``related_callees``.
        module_count: Number of unique modules in ``related_modules``.
        symbol_count: Total number of symbols (primary + supporting +
            callers + callees, deduplicated).
    """

    caller_count: int = 0
    callee_count: int = 0
    module_count: int = 0
    symbol_count: int = 0


@dataclass(frozen=True)
class ContextPackage:
    """A structured context package produced by the Context Builder.

    This is the internal platform model.  Providers translate this
    into their own request format.

    Attributes:
        primary_symbol: The highest-ranked symbol — always appears first.
        supporting_symbols: Symbols selected through lexical ranking.
            Ordered by deterministic score.  No duplicates.
        related_callers: Symbols connected through CALLS relationships
            (symbols that call the primary symbol).
            Ordered alphabetically by qualified_name.  No recursion.
        related_callees: Symbols connected through CALLS relationships
            (symbols that the primary symbol calls).
            Ordered alphabetically by qualified_name.  No recursion.
        related_modules: Unique modules represented in the package.
            Sorted alphabetically.
        relationship_summary: Metadata counts for the package.
        estimated_tokens: Estimated token count from the budget engine.
        metadata: Ranking and revision metadata.
    """

    primary_symbol: str = ""
    supporting_symbols: list[str] = field(default_factory=list)
    related_callers: list[str] = field(default_factory=list)
    related_callees: list[str] = field(default_factory=list)
    related_modules: list[str] = field(default_factory=list)
    relationship_summary: RelationshipSummary = field(
        default_factory=RelationshipSummary
    )
    estimated_tokens: int = 0
    metadata: ContextMetadata = field(default_factory=ContextMetadata)

    def __post_init__(self) -> None:
        """Ensure deterministic, duplicate-free collections."""
        # Deduplicate supporting_symbols while preserving order.
        seen: set[str] = set()
        deduped: list[str] = []
        for sym in self.supporting_symbols:
            if sym not in seen:
                seen.add(sym)
                deduped.append(sym)
        object.__setattr__(self, "supporting_symbols", deduped)

        # Deduplicate callers/callees.
        if self.related_callers:
            seen = set()
            deduped = []
            for sym in self.related_callers:
                if sym not in seen:
                    seen.add(sym)
                    deduped.append(sym)
            object.__setattr__(self, "related_callers", deduped)

        if self.related_callees:
            seen = set()
            deduped = []
            for sym in self.related_callees:
                if sym not in seen:
                    seen.add(sym)
                    deduped.append(sym)
            object.__setattr__(self, "related_callees", deduped)
