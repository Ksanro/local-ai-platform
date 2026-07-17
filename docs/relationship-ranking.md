# Relationship-Aware Context Ranking

## Overview

Relationship-aware ranking extends the Context Builder's ranking engine with signals derived from the repository's cross-reference graph. Instead of answering only "find the requested symbol", the system now answers "find the requested symbol and the code most likely needed to understand or modify it."

## Architecture

```
Repository Index
        │
        ▼
Ranking Engine
        │
        ├── Lexical Signals
        ├── Repository Signals
        └── Relationship Signals
                │
                ▼
Ranked Candidates
                │
                ▼
Context Builder
```

No new architectural layer is introduced. The existing `RankingEngine` is extended with relationship-aware scoring.

## Ranking Signals

### Lexical Signals

| Signal | Weight | Description |
|--------|--------|-------------|
| `EXACT_SYMBOL_NAME` | 100 | Any name segment exactly matches a query token (case-insensitive) |
| `EXACT_QUALIFIED_NAME` | 90 | The full qualified name exactly equals a query token |
| `PARTIAL_SYMBOL_NAME` | 50 | A name segment contains a query token as a substring |
| `MODULE_MATCH` | 30 | The module path contains a query token |
| `TOKEN_MATCH` | 10 per token | A query token appears anywhere in the qualified name (accumulates) |
| `PUBLIC_SYMBOL` | 5 | The symbol name does not start with "_" |

### Relationship Signals

| Signal | Weight | Description |
|--------|--------|-------------|
| `SHARED_MODULE` | 15 | Candidate and primary symbol are in the same module |
| `SHARED_CLASS` | 25 | Candidate and primary symbol share the same class scope |
| `DIRECT_CALLER` | 20 | Candidate calls the primary symbol (CALLS relationship, target → source) |
| `DIRECT_CALLEE` | 20 | Primary symbol calls the candidate (CALLS relationship, source → target) |
| `SHARED_PARENT` | 25 | Candidate and primary symbol share a parent via DEFINES relationship |

Relationship signals are **additive** — they stack on top of lexical signals.

### Signal Weights

All weights are defined in `packages/context/scoring.py`:

```python
WEIGHT_EXACT_MATCH = 100
WEIGHT_QUALIFIED_NAME = 90
WEIGHT_FILENAME = 40
WEIGHT_MODULE = 30
WEIGHT_SHARED_CLASS = 25
WEIGHT_DIRECT_CALLER = 20
WEIGHT_DIRECT_CALLEE = 20
WEIGHT_SHARED_PARENT = 25
WEIGHT_SHARED_MODULE = 15
WEIGHT_TOKEN_OVERLAP = 10
WEIGHT_PUBLIC_SYMBOL = 5
```

These are the authoritative defaults. No magic numbers should be used elsewhere.

## Ranking Rules

### Deterministic Ordering

Candidates are sorted by:

1. **Score descending** — higher score comes first
2. **Qualified name ascending** — alphabetical tie-breaker

This ordering is guaranteed to be identical across repeated executions with the same input.

### Scoring Model

The total score for a candidate is:

```
total_score = lexical_score + relationship_score
```

Where:

- `lexical_score` is computed from name-matching rules (mutually exclusive, highest wins)
- `relationship_score` is the sum of all applicable relationship signals (additive)

### Duplicate Prevention

The ranking engine never creates duplicate candidates. Each `ContextCandidate` appears at most once in the output. Relationship expansion only adds candidates that are not already present in the ranked list.

## Context Expansion

After the main ranking pass, the engine may include direct callers and direct callees of the primary symbol as additional context.

### Expansion Rules

1. Only direct (one-hop) relationships are considered — no recursive graph traversal
2. Candidates already in the ranked list are skipped
3. Expansion candidates are scored using relationship signals only
4. Expansion candidates are sorted by score descending, qualified name ascending
5. Candidates are added until the token budget is exhausted

### Budget Constraints

Each candidate is estimated at ~100 tokens. Expansion candidates are added only if:

```
existing_tokens + expansion_candidate_tokens <= max_tokens
```

Budget constraints always win — if the budget is full, no expansion candidates are added.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RELATIONSHIP_RANKING_ENABLED` | `true` | Enable/disable relationship scoring |
| `RELATIONSHIP_EXPANSION_ENABLED` | `true` | Enable/disable relationship expansion |
| `RELATIONSHIP_MAX_DEPTH` | `1` | Maximum graph traversal depth (only depth 1 supported) |

### Programmatic Configuration

The `RankingEngine` constructor accepts explicit configuration:

```python
engine = RankingEngine(
    symbol_graph_view=graph_view,      # For relationship lookups
    primary_symbol=primary_candidate,  # Primary symbol for relationship scoring
    relationship_enabled=True,         # Override environment default
    expansion_enabled=True,            # Override environment default
)
```

When `symbol_graph_view` is `None`, relationship scoring is automatically disabled regardless of other settings.

## Example Ranking

### Scenario

Query: `"AuthenticationMiddleware"`

Symbols:

| Qualified Name | Type | Module |
|----------------|------|--------|
| `auth.middleware.AuthenticationMiddleware` | CLASS | `auth/middleware.py` |
| `auth.middleware.authenticate` | FUNCTION | `auth/middleware.py` |
| `auth.middleware.validate_token` | FUNCTION | `auth/middleware.py` |
| `auth.services.auth_user` | FUNCTION | `auth/services.py` |
| `auth.middleware.AppMiddleware` | CLASS | `auth/middleware.py` |

Relationships (CALLS):

```
authenticate → AuthenticationMiddleware
AuthenticationMiddleware → validate_token
AuthenticationMiddleware → auth.services.auth_user
```

### Ranking Result

| Qualified Name | Lexical | Relationship | Total | Reasons |
|----------------|---------|--------------|-------|---------|
| `auth.middleware.AuthenticationMiddleware` | 115 (exact + token + public) | 0 | 115 | EXACT_SYMBOL_NAME, TOKEN_MATCH, PUBLIC_SYMBOL |
| `auth.middleware.validate_token` | 55 (partial + public) | 20 (DIRECT_CALLEE) | 75 | PARTIAL_SYMBOL_NAME, PUBLIC_SYMBOL, DIRECT_CALLEE |
| `auth.middleware.authenticate` | 55 (partial + public) | 20 (DIRECT_CALLER) | 75 | PARTIAL_SYMBOL_NAME, PUBLIC_SYMBOL, DIRECT_CALLER |
| `auth.services.auth_user` | 55 (partial + public) | 20 (DIRECT_CALLEE) | 75 | PARTIAL_SYMBOL_NAME, PUBLIC_SYMBOL, DIRECT_CALLEE |
| `auth.middleware.AppMiddleware` | 55 (partial + public) | 15 (SHARED_MODULE) + 25 (SHARED_CLASS) = 0 (different class) | 70 | PARTIAL_SYMBOL_NAME, PUBLIC_SYMBOL, SHARED_MODULE |

Note: `validate_token` and `authenticate` tie at 75. Tie-break by qualified name ascending puts `validate_token` before `authenticate` (alphabetically).

## Constraints

The relationship-aware ranking:

- **Must not** recurse indefinitely
- **Must not** modify the RepositoryIndex
- **Must not** modify the SymbolGraph
- **Must not** create synthetic symbols
- **Must not** duplicate candidates

Only existing symbols from the repository index may be ranked.

## Performance

### Time Complexity

- **Graph lookups**: O(1) per symbol via the `SymbolGraphView` methods
- **Relationship scoring**: O(1) per candidate (only direct relationships, no traversal)
- **Overall**: O(n) where n is the number of candidates

### Space Complexity

- **Additional memory**: O(1) per candidate for relationship data
- **No caching**: Relationship data is computed on-demand, not cached

### Current Complexity

The ranking engine is O(n) where n is the number of candidates. Each candidate's relationship scoring requires:

- 1 call to `callers()` — iterates all modules' relationships
- 1 call to `callees()` — iterates all modules' relationships
- 1 call to `parents()` — iterates all modules' relationships
- For each parent, 1 call to `children()` — iterates all modules' relationships

In the worst case, this is O(m × r) where m is the number of modules and r is the average number of relationships per module. For typical repositories, this is negligible compared to the initial index construction.

## Out of Scope

The following are explicitly out of scope for this feature:

- Git history signals
- Semantic embeddings
- Tree-sitter analysis
- Runtime profiling
- Multi-hop graph traversal
- DSPARK integration

## Future Evolution

Future ranking signals may include:

- Git history (commit frequency, recent changes)
- Semantic similarity (code embeddings)
- Ownership (authorship, review history)
- Hotspot analysis (change frequency)
- Test coverage
- Runtime profiling

No changes to the RepositoryIndex should be required for these additions.

## Implementation Files

| File | Purpose |
|------|---------|
| `packages/context/scoring.py` | Scoring constants, `RankingReason` enum, `score_candidate()`, `score_relationship()` |
| `packages/context/ranking.py` | Extended `RankingEngine` with relationship scoring and expansion |
| `packages/context/builder.py` | `ContextBuilder.build()` passes `SymbolGraphView` to `RankingEngine` |
| `packages/context/models.py` | `ContextCandidate` data model |
| `tests/context/test_relationship_ranking.py` | Comprehensive test coverage |
| `docs/relationship-ranking.md` | This documentation |