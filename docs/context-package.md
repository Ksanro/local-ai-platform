# Context Package v2

## Overview

The **Context Package** is a structured representation of repository context produced by the Context Builder. It groups related information with explicit semantics, enabling LLMs to reason more effectively about the provided context.

```
Context Builder
       │
       ▼
Context Package v2
       │
       ▼
Serializer
       │
       ▼
Provider (serialises)
```

## Motivation

Current context answers:

> Here are some symbols.

Desired context answers:

> Here is the symbol you asked for, why it was selected, what depends on it, what it depends on, and the surrounding implementation.

The goal is to maximize information density without increasing token count.

## Structure

```python
ContextPackage
├── primary_symbol: str                    # Exactly one — highest-ranked symbol
├── supporting_symbols: list[str]          # Ordered by deterministic score, no duplicates
├── related_callers: list[str]             # Symbols connected via CALLS, alphabetical
├── related_callees: list[str]             # Symbols connected via CALLS, alphabetical
├── related_modules: list[str]             # Unique modules, sorted alphabetically
├── relationship_summary: RelationshipSummary  # Metadata counts
├── estimated_tokens: int                  # Token estimate from budget
└── metadata: ContextMetadata              # Ranking version, revision
```

### Section Ordering

Sections appear in this order when serialized:

```
1. System
2. Primary Symbol
3. Supporting Symbols
4. Related Callers
5. Related Callees
6. Related Modules
7. User Messages
```

### Primary Symbol

Exactly one primary symbol. Represents the highest-ranked symbol from the ranking engine. Always appears first in the serialized output.

### Supporting Symbols

Symbols selected through lexical ranking. Ordered by deterministic score. Duplicates are forbidden — the `__post_init__` method deduplicates while preserving insertion order.

### Related Callers

Symbols connected through CALLS relationships (symbols that call the primary symbol). Ordered alphabetically by `qualified_name`. No recursion — maximum depth = 1.

### Related Callees

Symbols connected through CALLS relationships (symbols that the primary symbol calls). Same rules as callers.

### Related Modules

Unique modules represented in the package. Sorted alphabetically.

### Relationship Summary

```python
RelationshipSummary
├── caller_count: int    # Number of symbols in related_callers
├── callee_count: int    # Number of symbols in related_callees
├── module_count: int    # Number of unique modules in related_modules
└── symbol_count: int    # Total unique symbols (primary + supporting + callers + callees)
```

Pure metadata — contains no source code.

### Metadata

```python
ContextMetadata
├── ranking_version: str       # Version identifier for the ranking engine
├── repository_revision: str   # Repository revision (e.g. git commit hash)
├── estimated_tokens: int      # Estimated token count
└── generated_at: str | None   # Must be None for determinism
```

No timestamps. No UUIDs. Metadata must be deterministic.

## Ownership

| Component | Responsibility |
|-----------|---------------|
| **Context Builder** | Assembles structured `ContextPackage` from `ContextResult` |
| **Context Composer** | Extracts primary symbol, supporting symbols, callers, callees |
| **Serializer** | Formats `ContextPackage` into provider-specific messages |
| **Provider** | Translates `ContextPackage` into their request format |

### What the Context Package Must NOT Do

The `ContextPackage` must **not**:

- Access providers
- Serialize itself
- Format prompts
- Estimate new rankings
- Modify `RepositoryIndex`
- Access the filesystem
- Perform ranking
- Traverse repositories

It is a **pure immutable model**.

## Serializer Interaction

The serializer (e.g., `OpenAISerializer`) consumes the `ContextPackage` and produces a `ProviderRequest`. The serializer owns formatting:

```python
serializer = OpenAISerializer()
provider_request = serializer.serialize(context_package, messages)
```

The serializer emits sections in this order:

1. System message (platform system message)
2. Primary Symbol section
3. Supporting Symbols section
4. Related Callers section
5. Related Callees section
6. Related Modules section
7. User messages (copied unchanged)

## Deterministic Guarantees

The Context Package provides **deterministic** output:

1. **Primary symbol**: Always the first candidate from the ranking engine.
2. **Supporting symbols**: Ordered by rank, deduplicated by `qualified_name`.
3. **Related callers**: Sorted alphabetically by `qualified_name`.
4. **Related callees**: Sorted alphabetically by `qualified_name`.
5. **Related modules**: Sorted alphabetically.
6. **No timestamps**: `generated_at` is always `None`.
7. **No UUIDs**: No random identifiers.

Repeated executions with identical input always produce identical output.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Context Builder                            │
│                                                                 │
│  RepositoryIndex ──► RankingEngine ──► ContextBudget           │
│                            │                                     │
│                            ▼                                     │
│                     ContextResult                               │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Context Composer                             │
│                                                                 │
│  ContextResult + Primary Symbol ──► ContextPackage              │
│                                    ├── primary_symbol            │
│                                    ├── supporting_symbols        │
│                                    ├── related_callers           │
│                                    ├── related_callees           │
│                                    ├── related_modules           │
│                                    ├── relationship_summary      │
│                                    ├── estimated_tokens          │
│                                    └── metadata                  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Serializer                                 │
│                                                                 │
│  ContextPackage + User Messages ──► ProviderRequest             │
│                                    ├── System message            │
│                                    ├── Primary Symbol section    │
│                                    ├── Supporting Symbols        │
│                                    ├── Related Callers           │
│                                    ├── Related Callees           │
│                                    ├── Related Modules           │
│                                    └── User messages             │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Provider                                  │
│                                                                 │
│  ProviderRequest ──► API Call ──► Response                      │
└─────────────────────────────────────────────────────────────────┘
```

## Public API

```python
from packages.context.context_package import (
    ContextMetadata,
    ContextPackage,
    RelationshipSummary,
)

package = ContextPackage(
    primary_symbol="auth.AuthenticationMiddleware",
    supporting_symbols=["auth.middleware.JWTAuth", "auth.Tokens"],
    related_callers=["main.create_app", "router.register"],
    related_callees=["auth.Tokens.create_token"],
    related_modules=["auth.py", "main.py", "router.py"],
    relationship_summary=RelationshipSummary(
        caller_count=2,
        callee_count=1,
        module_count=3,
        symbol_count=5,
    ),
    estimated_tokens=230,
    metadata=ContextMetadata(
        ranking_version="1",
        repository_revision="abc123",
        estimated_tokens=230,
    ),
)
```

## Future Evolution

Future versions may extend `ContextPackage` with:

- Git metadata (author, commit, blame)
- Semantic clusters
- Ownership information
- Test relationships
- Memory snippets
- DSPARK reasoning

The public `ContextPackage` API should remain stable.

## Constraints

- No provider-specific fields
- No token counts beyond what the budget engine reports
- No prompt content
- No formatting instructions
- No filesystem access
- No ranking
- No repository traversal