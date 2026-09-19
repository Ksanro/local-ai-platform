# Capabilities

> Status: dormant / not wired into the live gateway.
>
> This document describes scaffolded future architecture. It is not runtime
> behavior unless `docs/STATUS.md` says otherwise.

## Capability Framework v1

### Overview

The platform exposes developer capabilities through a **reusable plugin architecture** rather than
standalone classes. Every capability implements a common interface, shares the same lifecycle,
execution model, result model, registration, and discovery mechanism.

```
User Request
    ↓
CapabilityFactory.create("explain")
    ↓
Capability.execute(query, repository_index)
    ↓
CapabilityResult
```

### Architecture

```
User Request
    ↓
Capability (defines intent via profile)
    ↓
RetrievalProfile (configuration only)
    ↓
ContextPlanner (orchestrates retrieval)
    ↓
RepositoryIndex
    ↓
ContextBuilder
    ↓
Serializer
    ↓
CapabilityResult
```

The key architectural principle: **capabilities define *what* they need, not *how* to retrieve it.**
Retrieval strategy is expressed through immutable `RetrievalProfile` objects. The actual retrieval
behavior lives in the Planner, Repository, and ContextBuilder packages.

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Capability Registry                    │
│  (registration, lookup, deterministic ordering)          │
└──────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────┐
│                   Capability Factory                      │
│  (create instances via registry, never hardcodes)        │
└──────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────┐
│                  Capability (ABC)                         │
│  name | intent | execute(query, repository_index)        │
└──────────────────────────────────────────────────────────┘
                          ↓
          ┌─────────────────┼─────────────────┐
          ↓                 ↓                 ↓
   ExplainCapability   DebugCapability  RefactorCapability
   (existing)          (future)         (future)
          ↓                 ↓                 ↓
   ContextPlanner    ContextPlanner    ContextPlanner
   RepositoryIndex   RepositoryIndex   RepositoryIndex
   ContextBuilder    ContextBuilder    ContextBuilder
   Serializer        Serializer        Serializer
          ↓                 ↓                 ↓
   CapabilityResult  CapabilityResult  CapabilityResult
```

### Constraints

Capabilities must **not**:

- access providers directly
- parse repositories
- implement ranking
- implement planning
- implement serialization
- mutate platform state

Capabilities orchestrate existing public APIs only.

## Public API

```python
from packages.capabilities.factory import CapabilityFactory
from packages.capabilities.registry import CapabilityRegistry
from packages.capabilities.explain import ExplainCapability

# Register
registry = CapabilityRegistry()
registry.register("explain", ExplainCapability)

# Create through factory
factory = CapabilityFactory(registry)
capability = factory.create("explain")

# Execute
result = capability.execute(
    query="Explain ProviderFactory",
    repository_index=index,
)
```

## Capability Interface

```python
class Capability(ABC):

    @property
    def name(self) -> str:
        """Unique identifier (e.g. 'explain')."""
        ...

    @property
    def intent(self) -> PlannerIntent:
        """Planner intent enum value."""
        ...

    def execute(
        self,
        query: str,
        repository_index: RepositoryIndex,
    ) -> CapabilityResult:
        """Orchestrate the capability pipeline."""
        ...
```

**Capabilities are stateless.** No instance attributes.

## RetrievalProfile

Retrieval profiles are **immutable configuration objects** that describe *what* repository context
a capability needs. They contain **zero business logic** — purely configuration.

```python
@dataclass(frozen=True, slots=True)
class RetrievalProfile:
    name: str
    include_callers: bool
    include_callees: bool
    include_dependencies: bool
    include_dependents: bool
    include_tests: bool
    include_dead_code: bool
    include_diagnostics: bool
    relationship_depth: int
    max_context_tokens: int
```

Only `relationship_depth`, `max_context_tokens`, and the `include_callers` /
`include_callees` pair have a `ContextQuery` counterpart (they become
`maximum_depth`, `max_tokens`, and `relationship_expansion`). The remaining
`include_*` flags record **declarative retrieval intent**: the current
`ContextQuery` API (`text`, `max_symbols`, `max_modules`, `max_tokens`,
`maximum_depth`, `relationship_expansion`) has no `include_tests`,
`include_dependencies`, `include_dependents`, `include_dead_code`, or
`include_diagnostics` field, so a capability cannot forward them to the context
builder today. Capabilities also do not take `max_symbols` from a plan:
`ContextPlan.maximum_depth` is traversal depth, not a candidate count, so the
established `ContextQuery` ceiling (20 symbols) stays in force.

### Built-in Profiles

| Profile | Name | Callers | Callees | Dependencies | Dependents | Tests | Dead Code | Diagnostics | Depth |
|---------|------|---------|---------|-------------|------------|-------|-----------|-------------|-------|
| `EXPLAIN_PROFILE` | `"explain"` | False | False | False | False | False | False | False | 1 |
| `DEBUG_PROFILE` | `"debug"` | True | True | True | False | True | False | True | 2 |
| `REFACTOR_PROFILE` | `"refactor"` | True | True | True | True | True | True | True | 3 |
| `IMPLEMENT_PROFILE` | `"implement-feature"` | True | True | True | True | True | False | True | 2 |
| `GENERATE_TESTS_PROFILE` | `"generate-tests"` | True | False | True | True | True | False | True | 2 |
| `REVIEW_PROFILE` | `"review"` | True | True | True | True | True | False | True | 2 |

`REVIEW_PROFILE` is the general, symbol-level review profile. `ARCHITECTURE_REVIEW_PROFILE`
stays separate and heavier (depth 3, 8192 tokens, dead code included) for
repository-wide architecture reviews.

### Usage

```python
from packages.capabilities.explain import ExplainCapability

cap = ExplainCapability()
profile = cap.profile  # Returns EXPLAIN_PROFILE

# Access configuration
profile.include_callers   # False
profile.relationship_depth # 1
```

### Architecture

```
Capability
    ↓
RetrievalProfile (configuration only)
    ↓
ContextPlanner (orchestrates retrieval using profile config)
    ↓
RepositoryIndex
    ↓
ContextBuilder
```

Profiles represent **retrieval intent**. All retrieval behavior continues to live in existing
platform components (Planner, Repository, ContextBuilder).

## PlannerIntent Enum

```python
class PlannerIntent(str, Enum):
    EXPLAIN = "EXPLAIN"
    DEBUG = "DEBUG"
    REVIEW = "REVIEW"
    REFACTOR = "REFACTOR"
    IMPLEMENT = "IMPLEMENT"
    GENERATE_TESTS = "GENERATE_TESTS"
```

## Capability Registry

Manages registration, lookup, and discovery of capabilities.

```python
from packages.capabilities.registry import CapabilityRegistry

registry = CapabilityRegistry()
registry.register("explain", ExplainCapability)  # Register
registry.get("explain")                           # Lookup → class or None
registry.has("explain")                           # Check → bool
registry.all()                                    # All names → sorted list
registry.unregister("explain")                    # Remove
```

**Deterministic ordering:** `all()` returns names sorted alphabetically.

**Duplicate rejection:** Registering the same name twice raises `ValueError`.

## Capability Factory

Creates capability instances through the registry.

```python
from packages.capabilities.factory import CapabilityFactory

factory = CapabilityFactory(registry)
capability = factory.create("explain")  # Returns ExplainCapability instance
```

**Never hardcodes classes.** All lookup goes through the registry. Unregistered names
raise `ValueError` with available capabilities in the error message.

## Explain Capability

The **Explain** capability answers natural language questions about code.

### Execution Flow

```
User Query ("Explain ProviderFactory")
    ↓
ContextPlanner
    ↓
RepositoryIndex.find()
    ↓
ContextBuilder
    ↓
ContextPackage assembly
    ↓
Serializer
    ↓
CapabilityResult
```

### Pipeline Stages

1. **Planning** — The `ContextPlanner` detects intent from the user query and
   produces an immutable `ContextPlan`.

2. **Repository Search** — The `RepositoryIndex` is queried for symbols
   matching the query. Returns a tuple of qualified symbol names.

3. **Context Building** — The `ContextBuilder` assembles ranked symbol
   candidates from the repository index using the `ContextQuery` derived
   from the `ContextPlan`.

4. **Package Assembly** — The capability constructs a `ContextPackage` from
   the `ContextResult` — extracting the primary symbol, the supporting
   symbols in rank order, and the sorted candidate modules. Ranked candidates
   are not `CALLS` edges, so no directly executable capability fills
   `related_callers` or `related_callees`: both stay empty and the relationship
   summary counts stay `0` with them
   (see [Relationship Fields](#relationship-fields)).

5. **Serialization** — The `SerializerFactory` creates a provider-specific
   serializer which transforms the `ContextPackage` into a `ProviderRequest`.

6. **Result** — All results are aggregated into an immutable `CapabilityResult`.

### Implementation

```python
from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.models import CapabilityResult

class ExplainCapability(Capability):

    @property
    def name(self) -> str:
        return "explain"

    @property
    def intent(self) -> PlannerIntent:
        return PlannerIntent.EXPLAIN

    def execute(self, query: str, repository_index: RepositoryIndex) -> CapabilityResult:
        # Stage 1: Planning
        # Stage 2: Repository search
        # Stage 3: Context building
        # Stage 4: Package assembly
        # Stage 5: Serialization
        # Aggregate into CapabilityResult
        ...
```

### Output

The `CapabilityResult` is an immutable dataclass with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `query` | `str` | Original user query |
| `intent` | `str` | Detected intent (e.g. "EXPLAIN") |
| `context_plan` | `ContextPlan` | Planning result |
| `context_package` | `ContextPackage` | Assembled context |
| `provider_request` | `ProviderRequest` | Serialized provider request |
| `selected_symbols` | `tuple[str, ...]` | Selected symbol qualified names |
| `selected_modules` | `tuple[str, ...]` | Selected module file paths |
| `estimated_tokens` | `int` | Estimated token count |
| `execution_time_ms` | `float` | Execution time in milliseconds |

## Debug Capability

The **Debug** capability diagnoses errors and produces fix suggestions. Its profile asks for a wider retrieval scope: deeper traversal, relationship expansion, diagnostics and dependencies. That request does not change what the assembled package publishes, see [Relationship Fields](#relationship-fields).

## Refactor Capability

The **Refactor** capability understands code change impact. It retrieves everything necessary for safe refactoring by expanding relationships to their full depth.

### Execution Flow

```
User Query ("Refactor ProviderFactory")
    ↓
ContextPlanner (REFACTOR intent)
    ↓
RepositoryIndex.find()
    ↓
ContextBuilder (depth=3, relationship_expansion=True)
    ↓
ContextPackage assembly (primary + supporting symbols, related modules); caller and callee fields stay empty
    ↓
Serializer
    ↓
CapabilityResult
```

### Pipeline Stages

1. **Planning** — The `ContextPlanner` detects `REFACTOR` intent and produces a `ContextPlan` with maximum depth and relationship expansion.

2. **Repository Search** — The `RepositoryIndex` is queried for symbols matching the query.

3. **Context Building** — The `ContextBuilder` assembles context with **depth=3** and **relationship expansion enabled**. Only the depth, the token budget and `relationship_expansion` reach `ContextQuery`; the caller, callee, diagnostics, dead-code and test flags stay declarative profile intent.

4. **Package Assembly** — The `ContextPackage` records the primary symbol, the supporting symbols in rank order, and the sorted candidate modules. `related_callers` and `related_callees` stay empty: ranked candidates carry a score and a module path, never a `CALLS` edge, see [Relationship Fields](#relationship-fields).

5. **Serialization** — The `SerializerFactory` creates a provider-specific serializer.

6. **Result** — All results are aggregated into an immutable `CapabilityResult`.

### Retrieval Profile

| Option | Refactor Value | Debug Value | Explain Value |
|--------|---------------|-------------|---------------|
| `maximum_depth` | 3 | 2 | 1 |
| `relationship_expansion` | True | True | False |
| `include_callers` | True | True | False |
| `include_callees` | True | True | False |
| `include_dependencies` | True | True | False |
| `include_diagnostics` | True | True | False |
| `include_dead_code` | True | False | False |
| `include_tests` | True | False | False |

### Implementation

```python
from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.models import CapabilityResult

class RefactorCapability(Capability):

    @property
    def name(self) -> str:
        return "refactor"

    @property
    def intent(self) -> PlannerIntent:
        return PlannerIntent.REFACTOR

    def execute(self, query: str, repository_index: RepositoryIndex) -> CapabilityResult:
        # Stage 1: Planning (REFACTOR intent)
        # Stage 2: Repository search
        # Stage 3: Context building (depth=3, relationship_expansion)
        # Stage 4: Package assembly (symbols + modules; no CALLS edge here)
        # Stage 5: Serialization
        # Aggregate into CapabilityResult
        ...
```

### Retrieval Strategy vs Debug

Refactor differs from Debug in **depth** and in the **scope its profile asks for**: Debug works at depth 2, Refactor at depth 3 and additionally marks dead code and tests as wanted scope. Neither claim changes what the assembled package publishes, which stays symbols and modules.

| Capability | Context Strategy |
|------------|------------------|
| Explain | minimal — symbol + immediate context |
| Debug | diagnostic — profile asks for callers, callees, diagnostics, dependencies |
| Refactor | impact — profile asks for callers, callees, diagnostics, dependencies, dead code, tests |

The important architectural rule: **Capabilities define retrieval strategy, not retrieval algorithms.** The Repository, Planning, Ranking and Context packages remain the only owners of their respective logic.

### Comparison Table

| Capability | Retrieval Strategy | Depth | Relationship Expansion | Includes |
|------------|-------------------|-------|------------------------|----------|
| Explain | Minimal | 1 | False | Symbol + immediate context |
| Debug | Diagnostic | 2 | True | Profile intent: callers, callees, diagnostics, dependencies |
| Refactor | Impact | 3 | True | Profile intent: callers, callees, diagnostics, dependencies, dead code, tests |

### Execution Flow

```
User Query ("Why is auth failing?")
    ↓
ContextPlanner (DEBUG intent)
    ↓
RepositoryIndex.find()
    ↓
ContextBuilder (depth=2, relationship_expansion=True)
    ↓
ContextPackage assembly (primary + supporting symbols, related modules); caller and callee fields stay empty
    ↓
Serializer
    ↓
CapabilityResult
```

### Pipeline Stages

1. **Planning** — The `ContextPlanner` detects `DEBUG` intent and produces a `ContextPlan` with diagnostic rules.

2. **Repository Search** — The `RepositoryIndex` is queried for symbols matching the query.

3. **Context Building** — The `ContextBuilder` assembles context with **depth=2** and **relationship expansion enabled**. Only the depth, the token budget and `relationship_expansion` reach `ContextQuery`; the caller, callee and diagnostics flags stay declarative profile intent.

4. **Package Assembly** — The `ContextPackage` records the primary symbol, the supporting symbols in rank order, and the sorted candidate modules. `related_callers` and `related_callees` stay empty: ranked candidates carry a score and a module path, never a `CALLS` edge, see [Relationship Fields](#relationship-fields).

5. **Serialization** — The `SerializerFactory` creates a provider-specific serializer.

6. **Result** — All results are aggregated into an immutable `CapabilityResult`.

### Retrieval Profile

| Option | Debug Value | Explain Value |
|--------|-------------|---------------|
| `maximum_depth` | 2 | 1 |
| `relationship_expansion` | True | False |
| `include_callers` | True | False |
| `include_callees` | True | False |
| `include_diagnostics` | True | False |
| `include_dependencies` | True | False |

### Implementation

```python
from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.models import CapabilityResult

class DebugCapability(Capability):

    @property
    def name(self) -> str:
        return "debug"

    @property
    def intent(self) -> PlannerIntent:
        return PlannerIntent.DEBUG

    def execute(self, query: str, repository_index: RepositoryIndex) -> CapabilityResult:
        # Stage 1: Planning (DEBUG intent)
        # Stage 2: Repository search
        # Stage 3: Context building (depth=2, relationship_expansion)
        # Stage 4: Package assembly (symbols + modules; no CALLS edge here)
        # Stage 5: Serialization
        # Aggregate into CapabilityResult
        ...
```

### Retrieval Strategy vs Explain

Debug defines **retrieval strategy**, not retrieval algorithms. All expansion logic comes from existing public APIs.

| Capability | Context Strategy |
|------------|------------------|
| Explain | minimal — symbol + immediate context |
| Debug | expanded — profile asks for callers, callees, diagnostics, dependencies |

The important architectural rule: **Capabilities define retrieval strategy, not retrieval algorithms.** The Repository, Planning, Ranking and Context packages remain the only owners of their respective logic.

## Implement Feature Capability

The **Implement Feature** capability collects the engineering context required to implement a new
feature. It is **dormant**: exported from `packages.capabilities` for direct use and covered by
tests, but not registered in the live gateway or pipeline.

### Execution Flow

```
User Query ("Implement the new retrieval profile in the gateway pipeline")
    ↓
ContextPlanner (intent_override="IMPLEMENT")
    ↓
RepositoryIndex.find()
    ↓
ContextBuilder (maximum_depth=2, relationship_expansion=True)
    ↓
ContextPackage assembly (primary + supporting symbols, related modules); caller and callee fields stay empty
    ↓
Serializer
    ↓
CapabilityResult
```

### Pipeline Stages

1. **Planning** — `ContextPlanner.build()` is called with `intent_override="IMPLEMENT"`,
   so debug-like or ambiguous wording still produces an `IMPLEMENT` plan. The profile
   supplies the retrieval depth and the token budget; the plan supplies the intent (always
   `IMPLEMENT`) and its own rule depth (`1` for `IMPLEMENT`, which is traversal depth and
   never a candidate count).
2. **Repository Search** — The `RepositoryIndex` is queried for symbols matching the query.
   Results are consumed in repository order with no ranking or reordering.
3. **Context Building** — The `ContextBuilder` assembles context with the profile's
   `relationship_depth` and relationship expansion enabled. The candidate ceiling is
   not derived from the plan: `ContextQuery` keeps its own default (`max_symbols` = 20)
   because `ContextPlan.maximum_depth` measures traversal depth, not symbol count. The
   profile's dead-code and diagnostics flags are declarative and have no `ContextQuery`
   counterpart in this version.
4. **Package Assembly** — The `ContextPackage` records the primary
   symbol, the supporting symbols in rank order (deduplicated by qualified
   name), and the sorted candidate modules. `related_callers` and
   `related_callees` stay empty: a candidate that ranks next to, or inside the
   same module as, the primary has not been shown to call it. Tests,
   dependencies, dependents, and diagnostics are not retrieved; those profile
   flags stay declarative.
5. **Serialization** — The `ContextPackage` is serialized through `SerializerFactory`.
6. **Result** — All results are aggregated into an immutable `CapabilityResult`.

### Retrieval Profile

| Option | Implement Value | Refactor Value | Debug Value | Explain Value |
|--------|-----------------|----------------|-------------|---------------|
| `relationship_depth` | 2 | 3 | 2 | 1 |
| `relationship_expansion` | True | True | True | False |
| `include_callers` | True | True | True | False |
| `include_callees` | True | True | True | False |
| `include_dependencies` | True | True | True | False |
| `include_dependents` | True | True | False | False |
| `include_diagnostics` | True | True | True | False |
| `include_dead_code` | False | True | False | False |
| `include_tests` | True | True | True | False |

`relationship_depth` becomes `ContextQuery.maximum_depth` and
`max_context_tokens` becomes `ContextQuery.max_tokens`; the caller/callee pair
decides `ContextQuery.relationship_expansion`. `include_dependencies`,
`include_dependents`, `include_diagnostics`, `include_dead_code`, and
`include_tests` are declarative profile intent only — the current
`ContextQuery` API has no such fields, so `ImplementFeatureCapability` does not
pass them. The candidate ceiling also stays at the `ContextQuery` default
(20 symbols); it is never taken from `ContextPlan.maximum_depth`, which is `1`
for the `IMPLEMENT` rule.

### Implementation

```python
from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.models import CapabilityResult

class ImplementFeatureCapability(Capability):

    @property
    def name(self) -> str:
        return "implement-feature"

    @property
    def intent(self) -> PlannerIntent:
        return PlannerIntent.IMPLEMENT

    def execute(self, query: str, repository_index: RepositoryIndex) -> CapabilityResult:
        # Stage 1: Planning (intent_override="IMPLEMENT")
        # Stage 2: Repository search
        # Stage 3: Context building (maximum_depth=2, relationship_expansion=True)
        # Stage 4: Package assembly (primary + supporting symbols,
        #          caller and callee fields empty: no verified CALLS edge)
        # Stage 5: Serialization
        # Aggregate into CapabilityResult
        ...
```

### Dormancy

- `packages/capabilities/__init__.py` exports `ImplementFeatureCapability` and
  `IMPLEMENT_PROFILE`.
- `apps/gateway` and `packages/pipeline` contain no references to either symbol.
- Registration is explicit and left to callers, e.g.
  `registry.register("implement-feature", ImplementFeatureCapability)`.
- Name overlap is benign: `packages/pipeline/stages/workflow_stage.py` registers a live
  default **workflow** named `"implement-feature"` in the workflow registry. That is a
  different abstraction and a different registry from `Capability` / `CapabilityRegistry`,
  and the pipeline never imports `packages.capabilities`.

## Generate Tests Capability

`GenerateTestsCapability` (`packages/capabilities/generate_tests.py`) assembles the
repository context a later test-generation step would consume: the ranked symbols
that match the query and the modules they live in. It is **context
assembly only**: it produces a `ProviderRequest` and stops. It never authors test
code, never writes files, never runs a provider, and never executes a test suite.

### Execution Flow

```
query (str) + RepositoryIndex
    ↓
Stage 1: Planning        ContextPlanner.build(intent_override="TEST")
    ↓
Stage 2: Search          repository_index.find(query)
    ↓
Stage 3: Context         ContextBuilder.build(ContextQuery(...))
    ↓
Stage 4: Assembly        ContextPackage (caller/callee fields stay empty)
    ↓
Stage 5: Serialization   SerializerFactory.create(ProviderType.openai).serialize(...)
    ↓
CapabilityResult (intent="GENERATE_TESTS")
```

### Pipeline Stages

| Stage | Method | Reused API |
|-------|--------|-----------|
| Planning | `_stage_planning` | `ContextPlanner.build` |
| Repository search | `_stage_repository_search` | `RepositoryIndex.find` |
| Context building | `_stage_context_building` | `ContextBuilder.build` |
| Package assembly | `_stage_assemble_package` | `ContextPackage` |
| Serialization | `_stage_serialization` | `SerializerFactory` |

The capability orchestrates those existing public APIs and adds no retrieval,
ranking, planning, parsing, or relationship-analysis logic of its own.

### Relationship Fields

`ContextResult` hands over ranked candidates, and a candidate carries a score
and a module path -- never a `CALLS` edge. `related_callers` and
`related_callees` are therefore empty in the package every directly executable
capability assembles, and `RelationshipSummary.caller_count` / `callee_count`
stay `0` with them. Candidate order and same-module membership are not reported
as call relationships: a package that claimed them would serialize a call graph
nothing in the platform verified.

What assembly does keep is the ranked membership builder output supports: the
first candidate becomes `primary_symbol`, the remaining candidates become
`supporting_symbols` in rank order (deduplicated by qualified name), and every
candidate module is listed in `related_modules`, sorted.

Verified `CALLS` edges do exist one layer down, in the repository symbol graph
the ranking engine already consumes for scoring, but `ContextResult` does not
surface them and reaching for them from the capability would mean relationship
analysis and graph traversal here, which the constraints forbid. Carrying real
relationships into capability output is a platform change.

### Serializer Availability

Stage 5 calls `SerializerFactory.create(ProviderType.openai)`. The registry
behind that factory is populated by import side effects: a serializer module
registers itself when it is first imported. The serialization layer owns that
import for the built-ins, so importing `packages.serializers` -- or any
submodule of it, which is how a capability reaches `SerializerFactory` --
registers them. No capability carries a bootstrap import of its own, and this is
the only import a caller needs:

```python
from packages.capabilities.generate_tests import GenerateTestsCapability
```

The contract is unchanged in every other direction: registration still goes
through `registry.register()`, a duplicate registration still raises
`ValueError`, `unregister()` still removes an entry for good, and
`SerializerFactory.create()` still raises `UnknownSerializerError` for a provider
type with no registered serializer. No serializer class is instantiated directly
and no provider is contacted. `tests/capabilities/assembly_probes.py` pins this
in a separate interpreter for `ReviewCapability`, `GenerateTestsCapability`,
`ImplementFeatureCapability`, and `ExplainCapability`.

### Intent Vocabulary Boundary

The planner and the capability use **different vocabularies**, and both are kept
intentionally:

| Surface | Value | Why |
|---------|-------|-----|
| `ContextPlanner.build(intent_override=...)` | `"TEST"` | `packages.planning.intent.Intent` has no `GENERATE_TESTS` member, and an override that is not a known `Intent` value is ignored silently — the plan would fall back to whatever the keyword rules matched. |
| `ContextPlan.intent` | `"TEST"` | The plan records the planner vocabulary. |
| `CapabilityResult.intent` | `"GENERATE_TESTS"` | `PlannerIntent.GENERATE_TESTS` is the capability-facing vocabulary and stays stable for callers. |

The capability's `intent` property returns `PlannerIntent.GENERATE_TESTS`; only
the value handed to the planner is translated. `PLANNER_INTENT_FOR_TESTS` is the
single place that pins the planner-side spelling.

### Retrieval Profile

`GENERATE_TESTS_PROFILE` (`packages/capabilities/profiles.py`) is coverage
oriented: it asks for callers and declines callees. Both flags are declarative
retrieval intent -- what the profile wants a relationship-aware retrieval to
prefer -- and neither of them fills `ContextPackage.related_callers` or
`related_callees`. See [Relationship Fields](#relationship-fields).

| Setting | Value |
|---------|-------|
| `name` | `"generate-tests"` |
| `include_callers` | `True` |
| `include_callees` | `False` |
| `relationship_depth` | `2` |
| `max_context_tokens` | `4096` |

Only `relationship_depth`, `max_context_tokens`, and the caller/callee pair reach
`ContextQuery` (as `maximum_depth`, `max_tokens`, and `relationship_expansion`).
The one behavioural effect of the caller/callee pair is that `relationship_expansion`
switch, which lets the ranking engine weigh verified `CALLS` edges while scoring
candidates; the edges themselves never arrive in `ContextResult`. The other
`include_*` flags stay declarative, and `ContextQuery.max_symbols` keeps
the established `ContextBuilder` ceiling (20) rather than being derived from
`ContextPlan.maximum_depth`, which measures traversal depth, not candidate count.

### Implementation

```python
from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.models import CapabilityResult

class GenerateTestsCapability(Capability):

    @property
    def name(self) -> str:
        return "generate-tests"

    @property
    def intent(self) -> PlannerIntent:
        return PlannerIntent.GENERATE_TESTS

    def execute(self, query: str, repository_index: RepositoryIndex) -> CapabilityResult:
        # Stage 1: Planning (intent_override="TEST")
        # Stage 2: Repository search
        # Stage 3: Context building (maximum_depth=2, relationship_expansion=True)
        # Stage 4: Package assembly (primary + supporting symbols, modules;
        #          caller/callee fields stay empty: no verified CALLS edge)
        # Stage 5: Serialization through SerializerFactory (the built-in
        #          serializers are registered by packages.serializers itself)
        # Aggregate into CapabilityResult
        ...
```

### Dormancy

- `packages/capabilities/__init__.py` exports `GenerateTestsCapability` and
  `GENERATE_TESTS_PROFILE`.
- The capability is **not** registered anywhere by default. `packages.capabilities`
  exposes only the `CapabilityRegistry` class; there is no default-registration
  helper, and the gateway has no capability wiring to extend.
- `apps/gateway`, `packages/pipeline`, `packages/workflows`, and
  `packages/controller` contain no references to `"generate-tests"`.
- Registration is explicit and left to callers, e.g.
  `registry.register("generate-tests", GenerateTestsCapability)`.
- Verification lives in `tests/capabilities/test_generate_tests.py`, which pins
  the exports, the five-stage order, the vocabulary translation, the
  profile-to-`ContextQuery` wiring, package assembly, determinism, and the
  no-side-effect and no-wiring boundaries.

## Review Capability

`ReviewCapability` (`packages/capabilities/review.py`) assembles the repository
context a later review step would read: the ranked symbols that match the query
and the modules they live in. It is **context assembly only** — it produces a
`ProviderRequest` and stops. It does **not** produce an LLM-authored review: no
findings, no line comments, no severity list, no file writes, no provider call.
A capability that turns this package into review text lives downstream of it.

| Capability | Module | Name | Output |
|------------|--------|------|--------|
| `ReviewCapability` | `packages/capabilities/review.py` | `"review"` | `CapabilityResult` carrying review *context*; planned through `ContextPlanner` |
| `ArchitectureReviewCapability` | `packages/capabilities/architecture_review.py` | `"architecture-review"` | `CapabilityResult` for repository-wide architecture: stage 1 runs `ArchitectureAnalyzer` over the module graph with `ARCHITECTURE_REVIEW_PROFILE` (depth 3, 8192 tokens, dead code included) and its `ContextPlan` is synthesized from the profile, so `ContextPlan.intent` reads `"REVIEW"` and no planner call happens |
| `PullRequestReviewCapability` | `packages/capabilities/pull_request_review.py` | `"pull-request-review"` | a plain `dict` of aggregated review metadata built from a `PullRequestReviewRequest` turned into a `TaskRequest`; it does not subclass `packages.capabilities.base.Capability` and assembles no `ContextPackage` |

`ReviewCapability` and `ArchitectureReviewCapability` deliberately share the same
capability intent (`PlannerIntent.REVIEW`); they differ in scope, profile and
result shape. The orchestrator class only shares the word.

### Execution Flow

```
query (str) + RepositoryIndex
    ↓
Stage 1: Planning        ContextPlanner.build(intent_override="SEARCH")
    ↓
Stage 2: Search          repository_index.find(query)
    ↓
Stage 3: Context         ContextBuilder.build(ContextQuery(...))
    ↓
Stage 4: Assembly        ContextPackage (caller/callee fields stay empty)
    ↓
Stage 5: Serialization   SerializerFactory.create(ProviderType.openai).serialize(...)
    ↓
CapabilityResult (intent="REVIEW")
```

### Pipeline Stages

| Stage | Method | Reused API |
|-------|--------|-----------|
| Planning | `_stage_planning` | `ContextPlanner.build` |
| Repository search | `_stage_repository_search` | `RepositoryIndex.find` |
| Context building | `_stage_context_building` | `ContextBuilder.build` |
| Package assembly | `_stage_assemble_package` | `ContextPackage` |
| Serialization | `_stage_serialization` | `SerializerFactory` |

The capability orchestrates those existing public APIs and adds no retrieval,
ranking, planning, parsing, or relationship-analysis logic of its own.

### Intent Vocabulary Boundary

The planner has no `REVIEW` intent, so the capability translates through the
module constant `PLANNER_INTENT_FOR_REVIEW = "SEARCH"`:

| Surface | Value | Why |
|---------|-------|-----|
| `ReviewCapability.intent` | `PlannerIntent.REVIEW` (`"REVIEW"`) | Capability-facing vocabulary (`packages.capabilities.base`). |
| `ContextPlanner.build(intent_override=...)` | `"SEARCH"` | `packages.planning.intent.Intent` has no `REVIEW` member, and an override that is not a known `Intent` value is ignored silently — the plan would fall back to whatever the keyword rules matched. |
| `ContextPlan.intent` | `"SEARCH"` | The plan records the planner vocabulary. |
| `CapabilityResult.intent` | `"REVIEW"` | The framework contract reports the capability intent, so this field comes from `self.intent.value`, not from the plan. |

`SEARCH` is the chosen token because review is read-only inspection of everything
a change reaches, and `SEARCH` is the only planner intent that asks for reach
without asking for an outcome. The rejected alternatives each narrow or mutate the
task: `DEBUG` presumes a defect, `REFACTOR` presumes a restructure, `IMPLEMENT`
presumes new code being written (review never writes), `TEST` presumes coverage
work, `EXPLAIN` presumes the goal is understanding rather than judgement, and
`DEFAULT` is the no-match fallback.

Query wording cannot move the pipeline. `"review"` is not a planner keyword at
all (that wording detects as `DEFAULT`), and debug-, implementation-, test-,
refactor- or explanation-shaped wording is overridden the same way.

A `SEARCH` plan also arrives with `relationship_expansion=False` and
`maximum_depth=0` — a plain lookup. Those plan values do not cap retrieval:
stage 3 takes budget, traversal depth and expansion from `REVIEW_PROFILE`, the
same profile-over-plan precedence the other directly executable capabilities
document. `ContextQuery.max_symbols` stays at the established default (20)
instead of being derived from `ContextPlan.maximum_depth`, which measures
traversal depth, not candidate count.

### Retrieval Profile

`REVIEW_PROFILE` (`packages/capabilities/profiles.py`) is the general,
symbol-level counterpart of `ARCHITECTURE_REVIEW_PROFILE`:

| Setting | Value |
|---------|-------|
| `name` | `"review"` |
| `include_callers` | `True` |
| `include_callees` | `True` |
| `include_dependencies` | `True` |
| `include_dependents` | `True` |
| `include_tests` | `True` |
| `include_dead_code` | `False` |
| `include_diagnostics` | `True` |
| `relationship_depth` | `2` |
| `max_context_tokens` | `4096` |

Only `relationship_depth`, `max_context_tokens` and the caller/callee pair reach
`ContextQuery` (as `maximum_depth`, `max_tokens` and `relationship_expansion`).
The other `include_*` flags are **declarative retrieval intent**: the
`ContextQuery` API has no field for them, so a capability cannot forward them
today. Dead code stays off because a change under review is live code by
definition.

### Relationship Fields

The framework-wide rule applies unchanged — see [Relationship Fields](#relationship-fields).
`ContextResult` supplies ranked candidates, never verified `CALLS` edges, so
`related_callers` and `related_callees` are empty and
`RelationshipSummary.caller_count` / `callee_count` are `0` alongside them. The
first candidate becomes `primary_symbol`, the remaining candidates become
`supporting_symbols` in rank order (deduplicated by qualified name), and
`related_modules` is the sorted, deduplicated set of candidate modules. Neither
rank position nor a shared module file is ever reported as a call relationship.

### Serializer Availability

Stage 5 goes through `SerializerFactory.create(ProviderType.openai)`; the built-in
serializers are registered by the serialization layer itself, so this single
import is the whole contract:

```python
from packages.capabilities.review import ReviewCapability
```

`tests/capabilities/assembly_probes.py` pins that in a separate interpreter for
`ReviewCapability` as well as for `GenerateTestsCapability`,
`ImplementFeatureCapability`, and `ExplainCapability`.

### Implementation

```python
from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.models import CapabilityResult

class ReviewCapability(Capability):

    @property
    def name(self) -> str:
        return "review"

    @property
    def intent(self) -> PlannerIntent:
        return PlannerIntent.REVIEW

    def execute(self, query: str, repository_index: RepositoryIndex) -> CapabilityResult:
        # Stage 1: Planning (intent_override=PLANNER_INTENT_FOR_REVIEW, i.e. "SEARCH")
        # Stage 2: Repository search
        # Stage 3: Context building (maximum_depth=2, relationship_expansion=True)
        # Stage 4: Package assembly (primary + supporting symbols, modules;
        #          caller/callee fields stay empty: no verified CALLS edge)
        # Stage 5: Serialization through SerializerFactory (the built-in
        #          serializers are registered by packages.serializers itself)
        # Aggregate into CapabilityResult(intent="REVIEW", ...)
        ...
```

### Dormancy

- `packages/capabilities/__init__.py` exports `ReviewCapability` and
  `REVIEW_PROFILE`.
- The capability is **not** registered anywhere by default, and `apps/gateway`,
  `packages/pipeline`, `packages/workflows`, and `packages/controller` contain no
  reference to `ReviewCapability`, `packages.capabilities.review`, or
  `REVIEW_PROFILE`.
- Registration is explicit and left to callers, e.g.
  `registry.register("review", ReviewCapability)`.
- Verification lives in `tests/capabilities/test_review.py`, which pins the
  exports, the five-stage order, the `REVIEW` -> `SEARCH` translation (including
  that no wording moves it), the profile-to-`ContextQuery` wiring, honest package
  assembly, determinism, the fresh-interpreter serializer path, and the
  no-side-effect and no-wiring boundaries.

## Future Capabilities



Future capabilities must require **one class and one registration**. No changes
to the framework infrastructure.

| Capability | Description | Intent |
|------------|-------------|--------|
| **Debug** | Diagnose errors and produce fix suggestions | `DEBUG` |
| **Implement Feature** | Implemented (dormant) — see [Implement Feature Capability](#implement-feature-capability) | `IMPLEMENT` |
| **Refactor** | Suggest refactoring changes | `REFACTOR` |
| **Review** | Implemented (dormant) — see [Review Capability](#review-capability) | `REVIEW` |
| **Generate Tests** | Implemented (dormant) — see [Generate Tests Capability](#generate-tests-capability) | `GENERATE_TESTS` |

### Adding a New Capability

```python
from packages.capabilities.base import Capability, PlannerIntent

class DebugCapability(Capability):

    @property
    def name(self) -> str:
        return "debug"

    @property
    def intent(self) -> PlannerIntent:
        return PlannerIntent.DEBUG

    def execute(self, query: str, repository_index: RepositoryIndex) -> CapabilityResult:
        # Orchestrate existing public APIs
        ...

# Register
registry = CapabilityRegistry()
registry.register("debug", DebugCapability)

# Use
capability = factory.create("debug")
result = capability.execute(query="Debug auth module", repository_index=index)
```

## Repository Index

The `RepositoryIndex` provides symbol lookup across the codebase:

```python
index = RepositoryIndex(...)
matches = index.find("ProviderFactory")  # Returns list of SymbolMatch
```

## Context Builder

The `ContextBuilder` assembles ranked symbol candidates:

```python
from packages.context.builder import ContextBuilder
from packages.context.models import ContextQuery

query = ContextQuery(text="Explain ProviderFactory", max_symbols=20)
builder = ContextBuilder(index=index)
result = builder.build(query=query)
```

## Serializer

The `SerializerFactory` creates provider-specific serializers:

```python
from packages.serializers.factory import SerializerFactory
from packages.serializers.types import ProviderType

serializer = SerializerFactory.create(ProviderType.openai)
provider_request = serializer.serialize(context_package=package, messages=messages)
```

Registration is owned by the serialization layer. Each built-in serializer
module calls `registry.register()` the first time it is imported, and
`packages.serializers` imports those modules, so any code that reaches
`SerializerFactory` -- including a capability through its documented import
path -- already finds the built-ins registered. Callers and tests never import a
serializer module for that side effect.

Custom serializers keep using the registry directly:

```python
from packages.serializers.registry import register
from packages.serializers.types import ProviderType

register(ProviderType.ollama, MyOllamaSerializer)
```

Registry semantics are unchanged by the built-in import: a duplicate
registration still raises `ValueError`, `unregister()` still removes an entry
for good, and `SerializerFactory.create()` still raises
`UnknownSerializerError` for a provider type that has no serializer.
