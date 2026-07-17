# Capabilities

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
   the `ContextResult` — extracting primary symbol, supporting symbols,
   callers, callees, and related modules.

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

## Future Capabilities

Future capabilities must require **one class and one registration**. No changes
to the framework infrastructure.

| Capability | Description | Intent |
|------------|-------------|--------|
| **Debug** | Diagnose errors and produce fix suggestions | `DEBUG` |
| **Implement Feature** | Generate code for a new feature | `IMPLEMENT` |
| **Refactor** | Suggest refactoring changes | `REFACTOR` |
| **Review** | Review code for quality and correctness | `REVIEW` |
| **Generate Tests** | Generate test cases for existing code | `GENERATE_TESTS` |

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