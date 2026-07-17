# Repository Diagnostics Engine

## Architecture

```
RepositoryIndex
    |
    v
DiagnosticsEngine
    |
    +-- DeadCodeAnalyzer
    +-- LargeModuleAnalyzer
    +-- OrphanAnalyzer
    +-- ModuleStatisticsAnalyzer
    +-- GraphStatisticsAnalyzer
    |
    v
RepositoryDiagnostics
```

The Repository Diagnostics Engine analyzes the existing Repository Index
to produce static analysis results. It never reparses source files,
never modifies the RepositoryIndex, and never performs side effects.

## Overview

Repository Intelligence answers:

> What exists?

Developer Intelligence answers:

> How is it connected?

Diagnostics answers:

> What deserves attention?

Diagnostics become another signal consumed by Context Builder and future
ranking algorithms.

## Architecture

```
RepositoryIndex
    |
    v
DiagnosticsEngine
    |
    +-- DeadCodeAnalyzer
    +-- LargeModuleAnalyzer
    +-- OrphanAnalyzer
    +-- ModuleStatisticsAnalyzer
    +-- GraphStatisticsAnalyzer
    |
    v
RepositoryDiagnostics
```

Diagnostics are read-only. They never modify RepositoryIndex.

## Usage

Build a diagnostics result:

```python
from packages.repository.diagnostics.engine import DiagnosticsEngine
from packages.repository.diagnostics.analyzers import (
    DeadCodeAnalyzer,
    LargeModuleAnalyzer,
    OrphanAnalyzer,
    ModuleStatisticsAnalyzer,
    GraphStatisticsAnalyzer,
)

engine = DiagnosticsEngine()
engine.register(DeadCodeAnalyzer())
engine.register(LargeModuleAnalyzer())
engine.register(OrphanAnalyzer())
engine.register(ModuleStatisticsAnalyzer())
engine.register(GraphStatisticsAnalyzer())

diagnostics = engine.analyze(repository_index)

# Access results
print(diagnostics.dead_symbols)       # tuple[DeadSymbol, ...]
print(diagnostics.orphan_modules)     # tuple[OrphanModule, ...]
print(diagnostics.large_modules)      # tuple[LargeModule, ...]
print(diagnostics.module_statistics)  # ModuleStatistics
print(diagnostics.graph_statistics)   # GraphStatistics
```

## RepositoryDiagnostics

Immutable models with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `dead_symbols` | `tuple[DeadSymbol, ...]` | Functions/methods with no callers |
| `large_modules` | `tuple[LargeModule, ...]` | Modules exceeding symbol threshold |
| `orphan_modules` | `tuple[OrphanModule, ...]` | Modules never imported or disconnected |
| `module_statistics` | `ModuleStatistics` | Aggregate module-level statistics |
| `graph_statistics` | `GraphStatistics` | Aggregate graph-level statistics |
| `warnings` | `tuple[str, ...]` | Non-critical diagnostic messages |

Collections must be deterministic. Repeated execution on the same
RepositoryIndex always produces identical results.

### DeadSymbol

| Field | Type | Description |
|-------|------|-------------|
| `qualified_name` | `str` | Fully qualified symbol name |
| `symbol_type` | `SymbolType` | Type of the symbol |
| `module` | `str` | Module path |
| `lineno` | `int` | Line number |

### LargeModule

| Field | Type | Description |
|-------|------|-------------|
| `path` | `str` | Module path |
| `symbol_count` | `int` | Number of symbols in the module |

### OrphanModule

| Field | Type | Description |
|-------|------|-------------|
| `path` | `str` | Module path |
| `symbol_count` | `int` | Number of symbols in the module |

### ModuleStatistics

| Field | Type | Description |
|-------|------|-------------|
| `module_count` | `int` | Total number of modules |
| `average_symbols` | `float` | Average symbols per module |
| `largest_module` | `str` | Path of the largest module |
| `largest_module_symbol_count` | `int` | Symbol count of largest module |
| `largest_call_graph` | `str` | Path of module with most relationships |
| `largest_call_graph_size` | `int` | Relationship count of largest module |
| `average_relationships` | `float` | Average relationships per module |
| `relationship_density` | `float` | Relationship density (0.0–1.0) |

### GraphStatistics

| Field | Type | Description |
|-------|------|-------------|
| `connected_components` | `int` | Number of weakly connected components |
| `maximum_call_depth` | `int` | Maximum call chain depth |
| `average_out_degree` | `float` | Average outgoing edges per node |
| `average_in_degree` | `float` | Average incoming edges per node |

## Analyzers

### DeadCodeAnalyzer

Detects functions and methods with no callers.

**Ignores:**

- Entry points (module-level functions named `main`)
- Abstract methods (`@abstractmethod` decorator)
- CLASS and MODULE symbols (only FUNCTION and METHOD are analyzed)

**Algorithm:** O(V + E) where V is the number of symbols and E is the
number of CALLS relationships. A BFS from all callers marks every
reachable symbol.

### LargeModuleAnalyzer

Detects modules with symbol count exceeding the configured threshold.

**Default threshold:** 10 symbols.

**Algorithm:** O(S) where S is the total number of symbols.
Single pass over all modules.

### OrphanAnalyzer

Detects modules that are never imported and disconnected from the
repository graph.

**Ignores:**

- Repository root modules (`__init__.py` files)
- Modules directly in the repository root (no directory component)

**Algorithm:** O(E + S) where E is the number of IMPORTS relationships
and S is the total number of symbols. Pre-built set for O(1) lookups.

### ModuleStatisticsAnalyzer

Calculates module-level aggregate statistics.

**Computes:**

- `module_count` — Total number of modules
- `average_symbols` — Average symbols per module
- `largest_module` — Module with most symbols
- `largest_call_graph` — Module with most relationships
- `average_relationships` — Average relationships per module
- `relationship_density` — Actual relationships / possible pairs

**Algorithm:** O(M + S + R) where M is modules, S is symbols, R is
relationships. Single pass over each collection.

### GraphStatisticsAnalyzer

Computes graph-level aggregate statistics.

**Computes:**

- `connected_components` — Number of weakly connected components
  in the CALLS graph (includes isolated nodes)
- `maximum_call_depth` — Maximum call chain depth via CALLS edges
- `average_out_degree` — Average outgoing edges per node
- `average_in_degree` — Average incoming edges per node

**Algorithm:**

- Connected components: O(V + E) using BFS on the CALLS graph
- Maximum call depth: O(V + E) using DFS with memoization
- Average degrees: O(E) single pass

## Extension Mechanism

New analyzers are added by subclassing `DiagnosticsAnalyzer` and
registering with the engine:

```python
from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.models import RepositoryDiagnostics
from packages.repository.index.models import RepositoryIndex

class MyCustomAnalyzer(DiagnosticsAnalyzer):
    @property
    def name(self) -> str:
        return "my_custom"

    def analyze(self, repository_index: RepositoryIndex) -> RepositoryDiagnostics:
        # ... analysis logic ...
        return RepositoryDiagnostics()

engine = DiagnosticsEngine()
engine.register(MyCustomAnalyzer())
```

The base class defines:

```python
class DiagnosticsAnalyzer(ABC):
    @property
    def name(self) -> str:
        """Return the analyzer name."""
        ...

    def analyze(self, repository_index: RepositoryIndex) -> RepositoryDiagnostics:
        """Run analysis and return results."""
        ...
```

## Deterministic Guarantees

All collections in `RepositoryDiagnostics` are sorted deterministically:

- `dead_symbols` — sorted by `(qualified_name, module, lineno)`
- `orphan_modules` — sorted by `path`
- `large_modules` — sorted by `path`
- `warnings` — sorted alphabetically

Repeated execution on the same `RepositoryIndex` always produces
identical results.

## Constraints

Diagnostics must **not**:

- Modify RepositoryIndex
- Modify SymbolGraph
- Call providers
- Access filesystem
- Parse AST
- Perform inference

Consume RepositoryIndex only.

## Performance

- Never rescan source files
- Reuse RepositoryIndex
- Each analyzer runs independently
- Documented algorithmic complexity

## Future Evolution

Future analyzers may include:

- Git hotspots
- Test coverage
- Complexity metrics
- Security analysis
- Performance analysis
- Ownership analysis

No changes to RepositoryIndex should be required.
