# Context Planning Engine

## Overview

The Context Planning Engine introduces deterministic planning to the retrieval pipeline. Before context construction begins, the platform now reasons about *how* to retrieve context instead of treating every request identically.

## Motivation

### Current behaviour

```
User Request
    ↓
Ranking
    ↓
Budget
    ↓
Prompt
```

Every request follows the same retrieval strategy regardless of intent.

### Desired behaviour

```
User Request
    ↓
Intent Detection
    ↓
Retrieval Plan
    ↓
Ranking
    ↓
Budget
    ↓
Prompt
```

The platform now selects the appropriate retrieval strategy before context construction begins.

## Architecture

```
Pipeline
    ↓
PlanningStage
    ↓
RepositoryContextStage (consumes ContextPlan)
    ↓
SerializerStage
    ↓
Provider
```

The planner becomes another Pipeline stage. It does not replace Context Builder.

### Data Flow

```
User Request
    ↓
PlanningStage
    ↓
ContextPlan → stored in PipelineContext.metadata["context_plan"]
    ↓
RepositoryContextStage
    ↓
    Reads: plan.ranking_profile, plan.maximum_depth,
           plan.relationship_expansion, plan.include_callers,
           plan.include_callees, plan.include_diagnostics
    ↓
ContextBuilder (configured by ContextPlan)
    ↓
SerializerStage
```

## Components

### ContextPlan

Immutable model produced by the ContextPlanner. This is the **single source of truth** for retrieval configuration.

```python
@dataclass(frozen=True)
class ContextPlan:
    intent: str
    primary_symbols: tuple[str, ...]  # Always () for this version
    relationship_expansion: bool
    ranking_profile: str
    maximum_depth: int
    include_callers: bool
    include_callees: bool
    include_modules: bool
    include_diagnostics: bool
    estimated_complexity: str
```

**Constraints:**

- `primary_symbols` is always `()` for this version (planning is not retrieval).
- No mutable state (`frozen=True`).
- Consumed by RepositoryContextStage, RankingEngine, BudgetEstimator, and Serializer.

### Intent Detection

Deterministic keyword-based intent detection. No AI, LLM, embeddings, or inference is performed.

**Supported intents:**

| Intent | Description | Keywords |
|--------|-------------|----------|
| `EXPLAIN` | User wants to understand code | explain, how does, how do, what is, what does, describe, architecture |
| `IMPLEMENT` | User wants to add functionality | implement, add, create, build, write, develop, feature |
| `REFACTOR` | User wants to restructure code | refactor, restructure, reorganize, rename, cleanup, simplify |
| `DEBUG` | User wants to find/fix bugs | debug, fix, bug, error, crash, fail, failing, exception |
| `TEST` | User wants to write/run tests | test, unit test, coverage, verify, spec, mock |
| `SEARCH` | User wants to find information | find, search, locate, where is, list, show me |
| `DEFAULT` | Fallback for unrecognized | (no keywords) |

Detection is:

- Case-insensitive
- Based on user messages only
- First-match wins (checked in priority order)
- O(number of keywords)

### Planning Rules

Each intent maps to a deterministic `PlanningRule`:

| Intent | Relationship Expansion | Max Depth | Callers | Callees | Modules | Diagnostics | Ranking Profile |
|--------|----------------------|-----------|---------|---------|---------|-------------|-----------------|
| EXPLAIN | ✅ | 1 | ✅ | ✅ | ✅ | ❌ | EXPLAIN |
| IMPLEMENT | ✅ | 1 | ❌ | ✅ | ✅ | ❌ | IMPLEMENT |
| REFACTOR | ✅ | 1 | ✅ | ✅ | ✅ | ❌ | REFACTOR |
| DEBUG | ✅ | 2 | ✅ | ✅ | ✅ | ✅ | DEBUG |
| TEST | ✅ | 1 | ✅ | ❌ | ✅ | ✅ | TEST |
| SEARCH | ❌ | 0 | ❌ | ❌ | ❌ | ❌ | SEARCH |
| DEFAULT | ❌ | 0 | ❌ | ❌ | ✅ | ❌ | DEFAULT |

### Rule Engine

The `RuleEngine` evaluates rules in order. First matching rule wins.

```python
engine = RuleEngine()
rule = engine.match("EXPLAIN")
plan = engine.build_plan("EXPLAIN")
```

Rules are extensible. Future rules may be registered without modifying `ContextPlanner`.

### ContextPlanner

```python
planner = ContextPlanner()
plan = planner.build(
    user_messages=["Explain how ProviderFactory works"],
    repository_index=index,  # Not used - accepted for API compatibility
)
# Returns: ContextPlan
```

The planner:

- Detects intent from user messages
- Matches against planning rules
- Returns an immutable `ContextPlan`

The planner does **NOT**:

- Access providers
- Execute repository analysis
- Parse source files
- Modify RepositoryIndex
- Modify ContextBuilder
- Search RepositoryIndex
- Resolve symbol names
- Perform fuzzy matching

### PlanningStage

Pipeline stage that integrates the ContextPlanner:

```python
stage = PlanningStage()
# Inserted before RepositoryContextStage in the pipeline
```

Hooks:

- `before()`: Checks if planning is enabled (`planning_enabled` metadata flag)
- `execute()`: Runs the planner, stores `ContextPlan` in metadata
- `after()`: Logs planning results

## Single Source of Truth

> `ContextPlan` is the single source of truth for retrieval configuration.

Components such as `RepositoryContextStage`, `RankingEngine`, `BudgetEstimator`, and `Serializer` must consume the `ContextPlan` rather than introducing independent decision logic. This prevents configuration drift as the platform grows.

## Constraints

### Planner must NOT:

- Access providers
- Execute repository analysis
- Parse source files
- Modify RepositoryIndex
- Modify ContextBuilder

### Planner must ONLY:

- Produce a `ContextPlan`

### Performance:

- Planning is O(number of rules)
- Repository traversal is forbidden

## Integration

### Pipeline Configuration

The `PlanningStage` is inserted before `RepositoryContextStage`:

```python
engine = PipelineEngine()
engine.register(PlanningStage())           # NEW: planning
engine.register(RepositoryContextStage())  # consumes ContextPlan
engine.register(ProviderStage(provider))
```

### RepositoryContextStage Consumption

The `RepositoryContextStage` reads the `ContextPlan` from metadata:

```python
plan = context.get_metadata("context_plan")
if plan is not None:
    # Use plan.ranking_profile for symbol scoring
    # Use plan.maximum_depth for relationship traversal
    # Use plan.relationship_expansion for expansion
    # Use plan.include_callers/include_callees for expansion
    # Use plan.include_diagnostics for diagnostics
```

## Future Evolution

Future planners may use:

- DSPARK
- Memory
- Git history
- Semantic retrieval
- Multi-agent planning

The `ContextPlanner` API remains stable.

## File Structure

```
packages/planning/
    __init__.py      # Package exports
    plan.py          # ContextPlan model
    intent.py        # Intent enum + detection
    rules.py         # PlanningRule + RuleEngine
    planner.py       # ContextPlanner

packages/pipeline/stages/
    planning_stage.py # PlanningStage

tests/planning/
    __init__.py
    test_intent.py
    test_rules.py
    test_planner.py
    test_planning_stage.py

docs/
    context-planning.md