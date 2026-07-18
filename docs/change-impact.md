# Change Impact Analysis

## Overview

The Change Impact Analyzer predicts which repository elements are affected by modifying one or more symbols. It provides deterministic, analysis-only output using existing Repository public APIs — no AI, no providers, no filesystem traversal, no AST parsing.

## Architecture

```
Changed Symbol
  ↓
Dependency Graph (RepositoryIndex relationships)
  ↓
Cross References (IMPORTS, INHERITS, DEFINES, CALLS)
  ↓
Impact Analyzer (BFS traversal, max_depth)
  ↓
Impact Report (ImpactReport with confidence)
```

## Motivation

When you modify a symbol, you need to know:

- "If I change this class, what else is affected?"
- "Which tests should I run?"
- "Which modules are downstream?"
- "What is the blast radius?"

The Change Impact Analyzer answers these questions with **deterministic** analysis — no heuristics, no AI, no randomness.

## Public API

```python
from packages.repository.impact import ChangeImpactAnalyzer, ImpactReport

analyzer = ChangeImpactAnalyzer()

report: ImpactReport = analyzer.analyze(
    symbols=[
        "providers.factory.ProviderFactory"
    ],
    repository_index=index,
)
```

### Configurable Depth

```python
# Default: depth 2 (direct + one level of transitive)
analyzer = ChangeImpactAnalyzer()

# Custom depth
analyzer = ChangeImpactAnalyzer(max_depth=3)

# Unlimited depth
analyzer = ChangeImpactAnalyzer(max_depth=-1)
```

## ImpactReport

The `ImpactReport` is an immutable, frozen dataclass containing:

| Field | Type | Description |
|-------|------|-------------|
| `root_symbols` | `tuple[str, ...]` | Input symbols that were analyzed |
| `impacted_symbols` | `tuple[ImpactNode, ...]` | All impacted symbols sorted by (distance, qualified_name) |
| `impacted_modules` | `tuple[str, ...]` | Unique module paths sorted alphabetically |
| `impacted_tests` | `tuple[str, ...]` | Test module paths linked to impacted symbols |
| `dependency_distance` | `int` | Maximum distance in the impact graph |
| `confidence` | `float` | Deterministic confidence value 0.0–1.0 |
| `generated_at` | `str` | ISO 8601 timestamp |

### ImpactNode

Each impacted symbol is represented as an `ImpactNode`:

| Field | Type | Description |
|-------|------|-------------|
| `qualified_name` | `str` | Fully qualified name of the symbol |
| `module` | `str` | Source file path |
| `distance` | `int` | Hop distance from root (1 = direct, 2 = transitive) |
| `reason` | `str` | Relationship type (CALLER, CALLEE, IMPORT, DEPENDENCY, INHERITANCE, TEST) |

## Analysis Algorithm

### 1. Symbol Resolution

The analyzer validates each input symbol against the `RepositoryIndex`:

```python
found = repository_index.find(name)
```

Unknown symbols produce no impact.

### 2. Relationship Traversal

For each root symbol, the analyzer traverses all relationship types:

| Relationship | Direction | Reason |
|-------------|-----------|--------|
| DEFINES | Outgoing | DEPENDENCY |
| DEFINES | Incoming | DEPENDENCY |
| IMPORTS | Outgoing | IMPORT |
| IMPORTS | Incoming | IMPORT |
| INHERITS | Outgoing | INHERITANCE |
| INHERITS | Incoming | INHERITANCE |
| CALLS | Outgoing | CALLEE |
| CALLS | Incoming | CALLER |

### 3. BFS Traversal

The analyzer performs Breadth-First Search through relationships:

- **Distance 1**: Direct relationships from root symbols
- **Distance 2**: Relationships from distance-1 nodes (transitive)
- **Depth limit**: Configurable via `max_depth` parameter
- **Cycle prevention**: Visited set prevents infinite loops

### 4. Test Discovery

Test modules are discovered using existing Repository relationships:

- CALLS relationships where the target is in a test module
- Heuristic: module path contains `/tests/` or starts with `tests/`

### 5. Confidence Calculation

Confidence is computed deterministically:

```
base_score = 1.0 if max_distance <= 1
base_score = 0.8 if max_distance <= 2
base_score = 0.6 if max_distance > 2

penalty = 1 + (relationship_count - 1) * 0.1
confidence = base_score / penalty
confidence = max(0.0, min(1.0, confidence))  # clamp
```

**Higher confidence means:**
- Closer relationship (lower distance)
- Fewer relationships (more focused impact)

## Example

### Input

```python
from packages.repository.impact import ChangeImpactAnalyzer

analyzer = ChangeImpactAnalyzer()

report = analyzer.analyze(
    symbols=["gateway.Gateway"],
    repository_index=index,
)
```

### Output

```python
print(f"Root symbols: {report.root_symbols}")
# Root symbols: ('gateway.Gateway',)

print(f"Impacted symbols: {len(report.impacted_symbols)}")
# Impacted symbols: 5

for node in report.impacted_symbols:
    print(f"  {node.qualified_name} (distance={node.distance}, reason={node.reason})")
#   gateway.Handler (distance=1, reason=DEPENDENCY)
#   logger.Logger (distance=1, reason=CALLEE)
#   gateway.Handler.process (distance=1, reason=DEPENDENCY)
#   logger.Logger.log (distance=2, reason=CALLEE)
#   tests.test_gateway.test_gateway (distance=1, reason=CALLER)

print(f"Impacted modules: {report.impacted_modules}")
# Impacted modules: ('gateway.py', 'logger.py', 'tests/test_gateway.py')

print(f"Impacted tests: {report.impacted_tests}")
# Impacted tests: ('tests/test_gateway.py',)

print(f"Confidence: {report.confidence:.2f}")
# Confidence: 0.69

print(f"Max distance: {report.dependency_distance}")
# Max distance: 2
```

## Constraints

The analyzer **must not**:

- Parse Python source files
- Inspect AST
- Perform filesystem traversal
- Call providers
- Mutate RepositoryIndex

The analyzer **must**:

- Use only public Repository APIs
- Produce deterministic output
- Sort by (distance, qualified_name)
- Return frozen/immutable dataclasses

## Ordering

Results are always sorted deterministically:

1. **Distance** ascending (direct relationships first)
2. **Qualified name** ascending (alphabetical within same distance)

## Usage Patterns

### Find Affected Tests

```python
if report.impacted_tests:
    print("Run these tests:")
    for test in report.impacted_tests:
        print(f"  - {test}")
```

### Check Blast Radius

```python
if report.dependency_distance > 2:
    print("WARNING: High blast radius detected")
    print(f"Maximum dependency distance: {report.dependency_distance}")
```

### Filter by Confidence

```python
if report.confidence < 0.5:
    print("WARNING: Low confidence impact analysis")
    print("Consider manual review")
```

## Future Evolution

Future versions may incorporate:

- Runtime telemetry
- Git history
- Semantic relationships
- Ownership information
- DSPARK dependency information

without changing the public analyzer API.