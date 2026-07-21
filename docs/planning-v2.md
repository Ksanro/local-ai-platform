# Planning v2 — Engineering Intent Resolution

## Overview

Planning v2 upgrades the Planning stage so repository retrieval understands engineering intent much better before ranking begins. This is NOT a new framework — it improves planning quality only.

## Architecture

### Pipeline Flow

```
User Messages
    ↓
Intent Detection (intent.py) — EXPLAIN, DEBUG, IMPLEMENT, SEARCH, TEST, REFACTOR, DEFAULT
    ↓
Engineering Intent Resolution (intent_rules.py) — resolves retrieval profile + hints
    ↓
Rule Matching (rules.py) — selects PlanningRule for structural config
    ↓
ContextPlan (with retrieval hints)
    ↓
RankingEngine (consumes hints for scoring)
```

### Key Components

| Component | Responsibility |
|-----------|----------------|
| `Intent.detect()` | High-level intent detection (EXPLAIN, DEBUG, IMPLEMENT, etc.) |
| `IntentRuleEngine` | Resolves engineering intent (retrieval profile + hints) |
| `RuleEngine` | Matches PlanningRule for structural config |
| `ContextPlanner` | Wires everything together |
| `ContextPlan` | Immutable output with retrieval hints |
| `RankingEngine` | Consumes retrieval hints for candidate scoring |

## Intent Resolution

### Engineering Retrieval Profiles

| Profile | Description | Example Query |
|---------|-------------|---------------|
| `IMPLEMENTATION` | Locate concrete implementation | "where is ProviderFactory" |
| `INTERFACE` | Locate interface/abstract definition | "find the API interface" |
| `REGISTRY` | Find registration point / registry | "where is the service registry" |
| `ENTRY_POINT` | Find application entry point | "what is the entry point" |
| `EXECUTION_FLOW` | Trace execution flow | "how does the pipeline work" |
| `CONFIGURATION` | Find configuration logic | "where is Redis configured" |
| `TEST` | Find tests | "find the unit tests" |
| `DEPENDENCY_INJECTION` | Find DI container/wiring | "how is the DI container wired" |
| `API_BOUNDARY` | Find API endpoint definitions | "find the API endpoints" |
| `SERIALIZER` | Find serializer/deserializer logic | "how is data serialized" |
| `WORKFLOW` | Find workflow definition | "find the deployment workflow" |
| `TASK` | Find task definition | "find the background task" |
| `CAPABILITY` | Find capability registration | "find the capability" |
| `PROVIDER` | Find provider hierarchy | "find the database provider" |
| `VALIDATION` | Find validation logic | "find the validation logic" |
| `FACTORY` | Find factory pattern | "find the factory pattern" |
| `EXTENSION` | Find extension point | "find the extension point" |
| `ARCHITECTURE` | Find architecture docs + modules | "why is the architecture designed this way" |
| `SIMILAR` | Find similar implementation | "find similar implementation" |
| `DEFAULT` | Fallback — no engineering goal | "hello world" |

### Retrieval Hints

ContextPlan now includes these immutable retrieval hint fields:

| Field | Type | Description |
|-------|------|-------------|
| `retrieval_profile` | `str` | Engineering goal label |
| `preferred_symbol_types` | `tuple[str, ...]` | Symbol types to prioritize |
| `preferred_module_patterns` | `tuple[str, ...]` | Module path patterns to prioritize |
| `relationship_preferences` | `tuple[str, ...]` | Relationship types to prioritize |
| `excluded_patterns` | `tuple[str, ...]` | Patterns to exclude from results |
| `priority_packages` | `tuple[str, ...]` | Packages to rank highest |
| `secondary_packages` | `tuple[str, ...]` | Packages to rank as secondary |

### Rule Engine

Rules are deterministic. Each rule has:

- `trigger_patterns`: Substring patterns checked against user query (case-insensitive)
- `retrieval_profile`: Engineering goal label
- `preferred_symbol_types`: Symbol types to prioritize
- `preferred_module_patterns`: Module path patterns to prioritize
- `relationship_preferences`: Relationship types to prioritize
- `excluded_patterns`: Patterns to exclude
- `priority`: Rule priority (lower = evaluated first)

#### Example Rules

```python
# Implementation queries
EngineeringIntentRule(
    trigger_patterns=("where is", "implement", "implementation", "locate"),
    retrieval_profile="IMPLEMENTATION",
    preferred_symbol_types=("CLASS", "FUNCTION"),
    priority=10,
)

# Interface queries
EngineeringIntentRule(
    trigger_patterns=("interface", "abstract", "protocol", "base class"),
    retrieval_profile="INTERFACE",
    preferred_symbol_types=("CLASS",),
    preferred_module_patterns=("*_interface*", "*_abstract*"),
    priority=10,
)

# Debug/fix queries
EngineeringIntentRule(
    trigger_patterns=("fix", "debug", "error", "bug", "diagnose"),
    retrieval_profile="IMPLEMENTATION",
    preferred_symbol_types=("CLASS", "FUNCTION"),
    relationship_preferences=("CALLS", "DEFINES"),
    excluded_patterns=("*test*", "*generated*"),
    priority=20,
)
```

## Interaction with Ranking

### How RankingEngine Consumes Hints

The RankingEngine receives the ContextPlan with retrieval hints. These hints influence candidate scoring:

1. **preferred_symbol_types**: Candidates with matching symbol types receive a bonus.
2. **preferred_module_patterns**: Candidates in matching modules receive a bonus.
3. **relationship_preferences**: Candidates with matching relationship types receive a bonus.
4. **excluded_patterns**: Candidates matching excluded patterns receive a penalty.
5. **priority_packages**: Candidates in priority packages receive a bonus.
6. **secondary_packages**: Candidates in secondary packages receive a smaller bonus.

### Separation of Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Planning** | Produce deterministic retrieval hints |
| **Ranking** | Score candidates using hints + other factors |

Planning never performs ranking. Ranking always consumes hints.

## Public APIs Consumed

The engineering intent resolver consumes ONLY public Repository APIs:

| API | Usage |
|-----|-------|
| `RankingEngine.rank(query_text, candidates)` | Consumes ContextPlan retrieval hints |

**Key constraint**: The planner does NOT access repository data. It produces hints that RankingEngine will use.

## Future Semantic Planning Extension Points

These are marked with `# TODO: FUTURE` comments in the code. **Do not implement.**

### 1. Semantic Similarity Score

```python
# TODO: FUTURE — Semantic planner integration
# When embedding-based search is available, compute semantic similarity
# between user query and symbol descriptions/candidate names.
# This supplements (not replaces) deterministic scoring.
```

### 2. Call Chain Depth Analysis

```python
# TODO: FUTURE — Multi-hop caller/callee analysis
# When the SymbolGraph supports transitive relationships, analyze
# call chain depth to determine if user wants deep trace (execution flow)
# or shallow lookup (implementation).
```

### 3. Cross-Package Dependency Analysis

```python
# TODO: FUTURE — Import graph analysis
# When package dependency metadata is available, analyze import
# relationships to prioritize candidates from packages that are
# direct dependencies vs transitive dependencies.
```

### 4. Usage Frequency Signal

```python
# TODO: FUTURE — Co-occurrence analysis
# Track which symbols are frequently retrieved together for the same
# query patterns. Use this to boost co-occurring symbols.
```

### 5. Recency Signal

```python
# TODO: FUTURE — Recently modified symbols preference
# When Git metadata is available, prefer recently modified symbols
# for debugging/fix queries.
```

### 6. Test Coverage Signal

```python
# TODO: FUTURE — Symbols with tests get bonus
# When test coverage metadata is available, symbols with tests
# may indicate well-documented, stable code that's more useful.
```

### Integration Path for Semantic Planner

```
User Messages
    ↓
Intent Detection (intent.py) — unchanged
    ↓
Engineering Intent Resolution (intent_rules.py) — DETERMINISTIC
    ↓
Semantic Planner (future) — supplements with embedding scores
    ↓
PlanningRule + Retrieval Hints — merged
    ↓
ContextPlan — consumed by RankingEngine
    ↓
RankingEngine — applies deterministic + semantic scores
```

The semantic planner would be an **optional middle layer** between Engineering Intent Resolution and PlanningRule matching. It would never replace deterministic behavior.

## Planning v1 vs Planning v2 Comparison

| Aspect | Planning v1 | Planning v2 |
|--------|-------------|-------------|
| **Intent Detection** | High-level: EXPLAIN, DEBUG, IMPLEMENT, SEARCH, TEST, REFACTOR, DEFAULT | Extended: Adds engineering sub-intents (IMPLEMENTATION, INTERFACE, REGISTRY, etc.) |
| **Rule Matching** | Single intent → single PlanningRule | Multi-layer: intent → engineering intent rules → PlanningRule |
| **Retrieval Hints** | None (only `ranking_profile`) | Full hint set: `preferred_symbol_types`, `preferred_module_patterns`, `relationship_preferences`, `excluded_patterns`, `priority_packages`, `secondary_packages` |
| **Determinism** | Fully deterministic | Fully deterministic (no LLM, no embeddings) |
| **Ranking Integration** | RankingEngine receives only query text + ContextPlan | RankingEngine receives ContextPlan with retrieval hints that influence scoring |
| **Extensibility** | Adding new behavior requires modifying BUILTIN_RULES | New profiles added via EngineeringIntentRule without modifying planner |
| **Configuration** | Fixed rules | Configurable: rule priorities, module preferences, package preferences, excluded patterns, default retrieval profile |
| **Query Understanding** | Keyword-based intent detection | Keyword-based intent + engineering intent resolution |

## Files Modified / Created

### Modified Files

| File | Changes |
|------|---------|
| `packages/planning/plan.py` | Added retrieval hint fields to ContextPlan |
| `packages/planning/rules.py` | Added retrieval_profile to PlanningRule, updated build_plan |
| `packages/planning/planner.py` | Wired IntentRuleEngine into planning pipeline |
| `packages/planning/__init__.py` | Exported new types |
| `packages/context/ranking.py` | Added ContextPlan import |
| `packages/context/builder.py` | Added comment about retrieval hints |

### New Files

| File | Purpose |
|------|---------|
| `packages/planning/intent_rules.py` | EngineeringIntentRule model + BUILTIN_INTENT_RULES + IntentRuleEngine |
| `tests/planning/test_intent_rules.py` | Tests for engineering intent rules |
| `docs/planning-v2.md` | This documentation |

## Test Coverage Summary

### Test Matrix

| Query Type | Example Query | Expected Profile |
|------------|---------------|------------------|
| Implementation | "where is ProviderFactory" | IMPLEMENTATION |
| Implementation | "implement authentication" | IMPLEMENTATION |
| Explanation | "how does the pipeline work" | EXECUTION_FLOW |
| Explanation | "explain ProviderFactory" | ARCHITECTURE |
| Debug | "fix the authentication bug" | IMPLEMENTATION |
| Workflow | "find the deployment workflow" | WORKFLOW |
| Provider | "find the database provider" | PROVIDER |
| Registry | "where is the service registry" | REGISTRY |
| Serializer | "how is data serialized" | SERIALIZER |
| Architecture | "why is the architecture designed this way" | ARCHITECTURE |
| Interface | "find the API interface" | INTERFACE |
| Configuration | "where is Redis configured" | CONFIGURATION |
| Entry Point | "what is the application entry point" | ENTRY_POINT |
| Empty | "" | DEFAULT |

### Test Categories

| Category | Count | Coverage |
|----------|-------|----------|
| EngineeringIntentRule model | 2 | Defaults, immutability |
| BUILTIN_INTENT_RULES | 3 | Default rule, implementation rules, all profiles |
| IntentRuleEngine | 30+ | All profiles, case-insensitive, resolve, custom rules, priority |
| RuleEngine | 7 | Match, build_plan, retrieval_profile |
| ContextPlanner Integration | 11 | All query types, empty query, multiple messages |
| Deterministic Planning | 3 | Same input, determinism, no side effects |
| Conflicting Rules | 2 | First match wins, debug vs implementation |
| All Retrieval Profiles | 20 | All 20 profiles with correct hints |

**Total tests: 80+**

## Constraints

- No providers.
- No LLM.
- No embeddings.
- No duplicated repository logic.
- Consume only public APIs.
- Maintain deterministic behavior.

## Success Criteria

- Engineering questions should consistently retrieve the correct area of the repository before ranking occurs.
- Planning should provide deterministic retrieval hints that significantly improve repository search quality.