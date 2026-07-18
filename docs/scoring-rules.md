# Scoring Rules

## Overview

Scoring rules define the additive scoring model used by the Ranking Engine
to rank symbol candidates against a user query. Each rule contributes at
most once (except `TOKEN_MATCH` which accumulates per matching token).

```
User Query
    |
    v
normalise_query_text() → list[str]  (query tokens)
    |
    v
score_candidate(candidate, query_tokens) → (score, reasons)
    |
    v
score_relationship(candidate, primary, graph_view) → (score, reasons)
    |
    v
Total Score = lexical_score + relationship_score
```

## RankingReason Enum

```python
class RankingReason(Enum):
    EXACT_SYMBOL_NAME = auto()    # Name segment exactly matches a query token
    PARTIAL_SYMBOL_NAME = auto()  # Name segment contains a query token
    MODULE_MATCH = auto()         # Module path contains a query token
    TOKEN_MATCH = auto()          # Query token appears in qualified name
    PUBLIC_SYMBOL = auto()        # Symbol name does not start with "_"
    DIRECT_CALLER = auto()        # Candidate calls the primary symbol
    DIRECT_CALLEE = auto()        # Primary symbol calls the candidate
    SHARED_PARENT = auto()        # Candidate and primary share a parent
    SHARED_MODULE = auto()        # Candidate and primary are in the same module
    SHARED_CLASS = auto()         # Candidate and primary share the same class scope
```

These values are attached to candidates for debugging only — they are not
surfaced to end users.

## Scoring Weights

| Constant | Value | Description |
|----------|-------|-------------|
| `WEIGHT_EXACT_MATCH` | 100 | Any name segment exactly matches a query token |
| `WEIGHT_QUALIFIED_NAME` | 90 | The full qualified name exactly equals a query token |
| `WEIGHT_MODULE` | 30 | The module path contains a query token |
| `WEIGHT_SHARED_CLASS` | 25 | Candidate and primary share the same class scope |
| `WEIGHT_DIRECT_CALLER` | 20 | Candidate calls the primary symbol |
| `WEIGHT_DIRECT_CALLEE` | 20 | Primary symbol calls the candidate |
| `WEIGHT_SHARED_PARENT` | 25 | Candidate and primary share a parent via DEFINES |
| `WEIGHT_SHARED_MODULE` | 15 | Candidate and primary are in the same module |
| `WEIGHT_TOKEN_OVERLAP` | 10 | A query token appears anywhere in the qualified name |
| `WEIGHT_PUBLIC_SYMBOL` | 5 | The symbol name does not start with "_" |

These are the **authoritative defaults** — no magic numbers should be used
elsewhere.

## Lexical Scoring

The `score_candidate()` function scores a single candidate against normalised
query tokens. Name-matching rules are **mutually exclusive** — only the
highest-scoring rule fires.

### Scoring Table

| Rule | Score | Condition |
|------|------:|-----------|
| `EXACT_SYMBOL_NAME` | +100 | Any name segment exactly matches a query token (case-insensitive) |
| `EXACT_QUALIFIED_NAME` | +90 | The full qualified name exactly equals a query token |
| `PARTIAL_SYMBOL_NAME` | +50 | A name segment contains a query token as a substring |
| `MODULE_MATCH` | +30 | The module path contains a query token |
| `TOKEN_MATCH` | +10 per token | A query token appears anywhere in the qualified name (accumulates) |
| `PUBLIC_SYMBOL` | +5 | The symbol name does not start with "_" |

### Name-Matching Priority

The rules are evaluated in order: exact symbol name → exact qualified name
→ partial name → module match. Only the first matching rule fires.

### Additive Rules

`TOKEN_MATCH` and `PUBLIC_SYMBOL` are **additive** — they stack on top of
the best name-matching rule.

### Implementation

```python
from packages.context.scoring import score_candidate, RankingReason

score, reasons = score_candidate(candidate, query_tokens)
# score: int — total lexical score
# reasons: list[RankingReason] — which rules fired
```

## Relationship Scoring

The `score_relationship()` function scores a candidate based on relationship
signals to the primary symbol. Relationship signals are **additive** —
multiple signals can fire for the same candidate.

### Relationship Signals

| Signal | Weight | Condition |
|--------|--------|-----------|
| `SHARED_MODULE` | +15 | Candidate and primary are in the same module |
| `SHARED_CLASS` | +25 | Candidate and primary share the same class scope |
| `DIRECT_CALLER` | +20 | Candidate calls the primary symbol |
| `DIRECT_CALLEE` | +20 | Primary symbol calls the candidate |
| `SHARED_PARENT` | +25 | Candidate and primary share a parent via DEFINES |

### Implementation

```python
from packages.context.scoring import score_relationship

score, reasons = score_relationship(
    candidate=candidate,
    primary_symbol=primary,
    symbol_graph_view=graph_view,
    relationship_enabled=True,
)
```

Relationship scoring is only applied when:

1. `relationship_enabled` is `True`
2. `primary_symbol` is provided
3. `symbol_graph_view` is provided

If any of these conditions are not met, the function returns `(0, [])`.

## Query Normalisation

```python
from packages.context.scoring import normalise_query_text

tokens = normalise_query_text("Explain ProviderFactory")
# → ["explain", "providerfactory"]
```

Steps:

1. Lowercase the text.
2. Split on whitespace.
3. Remove empty tokens.
4. Remove duplicate tokens while preserving order.

No stemming, lemmatisation, stop-word removal, or fuzzy matching is
performed.

## Total Score

```
total_score = lexical_score + relationship_score
```

Where:

- `lexical_score` is computed from name-matching rules (mutually exclusive, highest wins)
- `relationship_score` is the sum of all applicable relationship signals (additive)

## Constraints

- No filesystem access.
- No source code parsing.
- No AST, LLM, embedding, or DSPARK usage.
- Pure function: same input always produces same output.

## File Structure

```
packages/context/
    scoring.py    — RankingReason, score_candidate(), score_relationship(),
                  — normalise_query_text(), scoring constants
```
