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

Context Quality v2
------------------

The package now carries source-aware data alongside the original
identifier-based fields.  This enables serializers to emit actual
source code (signatures, docstrings, source bodies) instead of
symbol names alone.

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
        primary_symbol_context=SymbolContext(
            qualified_name="auth.AuthenticationMiddleware",
            signature="class AuthenticationMiddleware(Middleware):",
            source="...complete source...",
        ),
        supporting_symbol_contexts=[...],
        module_descriptions=[...],
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

    ranking_version: str = "2"
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
class SymbolContext:
    """Source-aware representation of a single symbol.

    Used for both primary and supporting symbols in Context Quality v2.

    Attributes:
        qualified_name: Fully qualified symbol name.
        signature: Function/class signature line.
        docstring: Docstring content (may be empty).
        decorators: List of decorator names (without ``@``).
        source: Complete source body for primary, truncated for supporting.
        source_preview: Short excerpt for supporting symbols.
        location: Tuple of (module_path, start_line, end_line) or None.
    """

    qualified_name: str
    signature: str = ""
    docstring: str = ""
    decorators: list[str] = field(default_factory=list)
    source: str = ""
    source_preview: str = ""
    location: tuple[str, int, int | None] | None = None


@dataclass(frozen=True)
class ModuleDescription:
    """Purpose and relationship summary for a related module.

    Attributes:
        module_path: Source file path relative to repository root.
        purpose: Brief description of the module's purpose.
        relationship_summary: Summary of how this module relates to the
            primary symbol.
        symbol_count: Number of symbols from this module in the package.
    """

    module_path: str
    purpose: str = ""
    relationship_summary: str = ""
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
        primary_symbol_context: Source-aware context for the primary symbol.
        supporting_symbol_contexts: Source-aware contexts for supporting symbols.
        module_descriptions: Purpose summaries for related modules.
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
    # Context Quality v2: source-aware fields
    primary_symbol_context: SymbolContext | None = None
    supporting_symbol_contexts: list[SymbolContext] = field(default_factory=list)
    module_descriptions: list[ModuleDescription] = field(default_factory=list)

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
