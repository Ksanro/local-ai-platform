# Relationship Extraction

## Overview

The Relationship Extraction package enriches the `RepositoryIndex` with
developer intelligence — how symbols interact at runtime. It provides a
language-independent, pluggable extractor architecture that discovers
relationships from repository metadata.

```
Repository
    |
    v
Repository Index
    |
    v
Relationship Extractors
    |
    |-- CallExtractor
    |-- ImportExtractor (future)
    |-- ReferenceExtractor (future)
    |-- TypeUsageExtractor (future)
    |-- DataFlowExtractor (future)
    v
Relationship Graph
    |
    v
Context Builder
```

No new architectural layer is introduced. Extractors operate on the
existing `RepositoryIndex` and produce `Relationship` objects that are
merged into the index.

## Architecture

```
RelationshipExtractor (ABC)
    |
    +-- CallExtractor (calls)
    +-- ImportExtractor (imports) — future
    +-- ReferenceExtractor (references) — future
    +-- TypeUsageExtractor (type usage) — future
    +-- DataFlowExtractor (data flow) — future
```

Each extractor produces a single relationship type. The `RelationshipRegistry`
invokes all registered extractors in registration order and merges the
results with deduplication.

## Constraints

Extractors must **not**:

- Modify the `RepositoryIndex`
- Perform ranking
- Build prompts
- Estimate tokens
- Access providers
- Perform inference
- Call LLMs

Only repository metadata is analysed.

## Public API

```python
from packages.repository.relationships import (
    RelationshipExtractor,    # Abstract base class
    RelationshipRegistry,     # Registry of extractors
)
```

### RelationshipExtractor (ABC)

```python
class RelationshipExtractor(ABC):

    @property
    def relationship_type(self) -> RelationshipType:
        """The type of relationships this extractor produces."""
        ...

    def extract(self, repository_index: RepositoryIndex) -> list[Relationship]:
        """Extract relationships from a repository index.

        Returns a sorted, deduplicated list of Relationship objects.
        """
        ...
```

**Deterministic guarantee:** Repeated extraction on the same repository
produces identical relationships, sorted by `(source, target)`.

### RelationshipRegistry

```python
from packages.repository.relationships.registry import RelationshipRegistry

registry = RelationshipRegistry()
registry.register(CallExtractor())          # Register an extractor
registry.extract(repository_index)           # Run all extractors
registry.get_extractors_for_type(RelationshipType.CALLS)  # Filter by type
registry.extractors                          # All registered extractors
```

**Behaviours:**

- Extractors are invoked in registration order
- Results are merged and deduplicated by `(source, target, type)` triple
- Final list is sorted by `(source, target, type)` for deterministic output
- Duplicate registrations (same instance) are ignored

## CallExtractor

The `CallExtractor` detects function and method call relationships between
known symbols in the `RepositoryIndex`.

### Supported Call Patterns

- Function → Function
- Method → Method
- Function → Method
- Method → Function

### Not Supported (Ignored)

- Dynamic dispatch
- Monkey patching
- Reflection
- `eval()` / `exec()`
- Runtime imports
- Metaprogramming

### Algorithm

1. For each module in the index, parse the source code AST.
2. Walk all `Call` nodes in the AST.
3. Resolve each call target to a known symbol in the index.
4. Emit a `CALLS` relationship when both caller and callee are known.

**Supported resolution strategies:**

- **Simple call:** `helper()` — resolves by name in the current module or
  cross-module short-name lookup.
- **Attribute call:** `self.method()` — resolves `self` to the current class
  scope, then looks up the method.
- **Chained attribute:** `self.service.method()` — resolves the attribute
  chain to a known class, then looks up the method.

### Implementation

```python
from packages.repository.relationships.call_extractor import CallExtractor
from packages.repository.relationships.registry import RelationshipRegistry

registry = RelationshipRegistry()
registry.register(CallExtractor())

# The builder invokes the registry during index construction.
index = build_index(path, registry=registry)
```

### Output

```python
# Each relationship:
Relationship(
    source="auth.login",           # Caller qualified name
    target="auth.validate_token",  # Callee qualified name
    type=RelationshipType.CALLS,
)
```

## Adding a New Extractor

1. Create a new class inheriting from `RelationshipExtractor`.
2. Implement the `relationship_type` property.
3. Implement the `extract()` method.
4. Register with the `RelationshipRegistry`.

```python
from packages.repository.relationships.base import RelationshipExtractor
from packages.repository.symbols.models import RelationshipType

class ImportExtractor(RelationshipExtractor):

    @property
    def relationship_type(self) -> RelationshipType:
        return RelationshipType.IMPORTS

    def extract(self, repository_index: RepositoryIndex) -> list[Relationship]:
        # ... import analysis logic ...
        return []
```

## File Structure

```
packages/repository/relationships/
    __init__.py          — Package exports
    base.py              — RelationshipExtractor ABC
    registry.py          — RelationshipRegistry
    call_extractor.py    — CallExtractor (calls)

tests/repository/relationships/
    __init__.py
    test_base.py
    test_registry.py
    test_call_extractor.py
```

## Future Evolution

Future extractors may include:

- **ImportExtractor** — import relationships between modules
- **ReferenceExtractor** — cross-reference relationships (read/write)
- **TypeUsageExtractor** — type annotation relationships
- **DataFlowExtractor** — data flow relationships (variables, parameters)

No changes to the `RepositoryIndex` should be required for these additions.
