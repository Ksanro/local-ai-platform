# Capabilities

## Concept

A **capability** is a user-facing abstraction that composes existing platform
components into coherent workflows. Each capability represents a developer task
that the platform can solve.

Capabilities are **orchestration only** — they do not duplicate logic. They
invoke the public APIs of existing platform components and aggregate the
results into an immutable output.

### Architecture

```
User Request
    ↓
Capability (orchestration)
    ↓
Planner → Repository → Context → Serializer
    ↓
CapabilityResult
```

### Constraints

Capabilities must not

- perform ranking
- inspect AST
- access filesystem directly
- call providers
- execute HTTP
- mutate platform state

Only orchestration.

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
   the `ContextResult` — extracting primary symbol, supporting symbols,
   callers, callees, and related modules.

5. **Serialization** — The `SerializerFactory` creates a provider-specific
   serializer which transforms the `ContextPackage` into a `ProviderRequest`.

6. **Result** — All results are aggregated into an immutable `CapabilityResult`.

### Public API

```python
from packages.capabilities.explain import ExplainCapability

engine = ExplainCapability()
result = engine.execute(
    query="Explain ProviderFactory",
    repository_index=index,
)
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

### Example

```python
from packages.capabilities.explain import ExplainCapability
from packages.repository.index import RepositoryIndexBuilder

# Build the index
index = RepositoryIndexBuilder().build("./my-project")

# Execute the capability
engine = ExplainCapability()
result = engine.execute(
    query="Explain ProviderFactory",
    repository_index=index,
)

# Access results
print(result.intent)              # "EXPLAIN"
print(result.selected_symbols)    # ("packages.providers.factory.ProviderFactory", ...)
print(result.provider_request)    # ProviderRequest ready for provider consumption
```

## Future Capabilities

The following capabilities are planned and must follow the same orchestration
model:

| Capability | Description |
|------------|-------------|
| **Debug** | Diagnose errors and produce fix suggestions |
| **Implement Feature** | Generate code for a new feature |
| **Refactor** | Suggest refactoring changes |
| **Review** | Review code for quality and correctness |
| **Generate Tests** | Generate test cases for existing code |

Each capability will:

- Reuse existing public APIs only
- Produce an immutable result
- Stop after ProviderRequest creation (no provider execution)
- Be fully testable with mocked components