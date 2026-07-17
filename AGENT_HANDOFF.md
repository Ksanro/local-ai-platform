# Debug Capability v1 — Handoff to Testing Agent

## Implementation Summary

### Files Created

1. **`packages/capabilities/debug.py`** — `DebugCapability` class
2. **`packages/capabilities/__init__.py`** — Updated to export `DebugCapability`

### Classes Created

#### `DebugCapability`

Located in `packages/capabilities/debug.py`.

**Properties:**
- `name` → returns `"debug"`
- `intent` → returns `PlannerIntent.DEBUG`

**Pipeline Stages:**
1. `_stage_planning` — Invokes `ContextPlanner` with user query → produces `ContextPlan` with `DEBUG` intent
2. `_stage_repository_search` — Queries `RepositoryIndex.find()` → returns tuple of selected symbol qualified names
3. `_stage_context_building` — Uses `ContextBuilder` with `ContextQuery` derived from `ContextPlan` (depth=2, relationship_expansion=True)
4. `_stage_assemble_package` — Assembles `ContextPackage` from `ContextResult`
5. `_stage_serialization` — Uses `SerializerFactory` to create `ProviderRequest`
6. Returns `CapabilityResult` with all fields populated

**Retrieval Profile (vs Explain):**
- `maximum_depth` = 2 (vs 1 for Explain)
- `relationship_expansion` = True
- `include_callers` = True (from planning rules)
- `include_callees` = True (from planning rules)
- `include_diagnostics` = True (from planning rules)

**Constraints:**
- No AST inspection
- No graph traversal
- No repository parsing
- No ranking
- No provider calls
- No filesystem access
- Stateless (no instance attributes)

### Registration

The capability is registered in `__init__.py`:
```python
from packages.capabilities.debug import DebugCapability
```

And exported via `__all__`:
```python
__all__ = [..., "DebugCapability", ...]
```

### Usage

```python
from packages.capabilities.factory import CapabilityFactory
from packages.capabilities.registry import CapabilityRegistry
from packages.capabilities.debug import DebugCapability

registry = CapabilityRegistry()
registry.register("debug", DebugCapability)

factory = CapabilityFactory(registry)
capability = factory.create("debug")
result = capability.execute(
    query="Why is auth failing?",
    repository_index=index,
)
```

## Test Requirements

Verify:
- Capability registration (`registry.register("debug", DebugCapability)`)
- Factory creation (`factory.create("debug")` returns DebugCapability instance)
- `DEBUG` planner intent used
- Callers requested in context
- Callees requested in context
- Diagnostics requested in context
- Dependency expansion requested in context
- Context respects token budget
- Deterministic execution
- Immutable result
- Explain behavior unchanged

Coverage target: >95%

## Test Results

### pytest
```
46 passed in 0.19s
```

### ruff
```
All checks passed!
```

### mypy
```
Success: no issues found in 1 source file
```

### Analysis
- All 46 debug-specific tests pass
- ruff linter passes with no issues
- mypy type checker passes with no issues
- All test requirements met:
  - Capability registration
  - Factory creation
  - DEBUG planner intent used
  - Callers requested in context
  - Callees requested in context
  - Diagnostics requested in context
  - Dependency expansion requested in context
  - Context respects token budget
  - Deterministic execution
  - Immutable result
  - Explain behavior unchanged

STATUS: PASSED
