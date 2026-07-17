# Workspace Dependency Graph

## Architecture

```
RepositoryIndex
        │
        │  symbols() + relationships()
        ▼
RelationshipGraph
        │
        ▼
DependencyGraphBuilder
        │
        ▼
WorkspaceDependencyGraph
        │
        ├── Diagnostics

        ├── Context Builder

        ├── Future DSPARK

        ├── Future Git Intelligence

        ├── Future Memory

        └── Future Planning
```

The Workspace Dependency Graph is the canonical representation of repository
dependencies.  It is derived exclusively from the `RepositoryIndex` — no
source files are reparsed, no filesystem access, no AST inspection.

### Data Flow

```
RepositoryIndex
    ├── modules: dict[str, Module]
    ├── symbols: list[Symbol]
    └── relationships: list[Relationship]
              │
              ▼
    DependencyGraphBuilder.build()
              │
              ▼
    WorkspaceDependencyGraph
              │
              ├── nodes: frozenset[GraphNode]
              ├── edges: frozenset[GraphEdge]
              ├── _outgoing: dict[str, list[GraphNode]]
              └── _incoming: dict[str, list[GraphNode]]
```

---

## Graph Model

### Nodes

Nodes represent symbols from the `RepositoryIndex`.  Each node has:

```python
@dataclass(frozen=True, slots=True)
class GraphNode:
    node_type: NodeType          # MODULE, CLASS, FUNCTION, METHOD
    qualified_name: str          # Unique identifier
    symbol_type: SymbolType | None  # Original SymbolType
```

**Node types** map directly from `SymbolType`:

| SymbolType | NodeType |
|------------|----------|
| MODULE | MODULE |
| CLASS | CLASS |
| FUNCTION | FUNCTION |
| METHOD | METHOD |

No new node categories are invented — the graph reuses existing semantic
definitions.

### Edges

Edges represent relationships between nodes.  Each edge has:

```python
@dataclass(frozen=True, slots=True)
class GraphEdge:
    source: str              # Qualified name of source node
    target: str              # Qualified name of target node
    edge_type: GraphEdgeType # Type of relationship
```

**Edge types** map from `RelationshipType`:

| RelationshipType | GraphEdgeType | Meaning |
|-----------------|---------------|---------|
| DEFINES | CONTAINS | Parent → child containment |
| IMPORTS | IMPORTS | Module/symbol import reference |
| INHERITS | INHERITS | Class inheritance |
| CALLS | CALLS | Function/method call |

No new relationship semantics are invented — the graph reuses existing
semantic definitions.

---

## Traversal

### Direct Queries

```python
# Direct dependencies (outgoing edges)
dependencies(node) -> Sequence[GraphNode]

# Direct dependents (incoming edges)
dependents(node) -> Sequence[GraphNode]
```

### Transitive Queries

```python
# All transitive dependencies (BFS)
transitive_dependencies(node, depth=1) -> Sequence[GraphNode]

# All transitive dependents (BFS on incoming edges)
transitive_dependents(node, depth=1) -> Sequence[GraphNode]
```

**Parameters:**

- `depth`: Maximum traversal depth.  Defaults to 1 (direct only).
  Use `depth=-1` for unlimited depth.

### Containment Queries

```python
# Direct children via CONTAINS edges
contains(node) -> Sequence[GraphNode]

# Direct parents via CONTAINS edges
contained_by(node) -> Sequence[GraphNode]
```

Only `CONTAINS` edges (derived from `DEFINES` relationships) are
traversed — these represent parent → child containment.

### Traversal Guarantees

1. **Cycle prevention**: BFS with visited set — no node appears twice
2. **No duplicates**: Results deduplicated by `qualified_name`
3. **Deterministic ordering**: All results sorted by `(node_type, qualified_name)`
4. **No mutation**: Graph is frozen; traversal returns new lists
5. **No synthetic nodes**: Only nodes derived from actual `RepositoryIndex` symbols

---

## Ownership

### Package: `packages/repository/dependencies`

| File | Responsibility |
|------|---------------|
| `__init__.py` | Public API exports |
| `models.py` | `NodeType`, `GraphEdgeType`, `GraphNode`, `GraphEdge`, `map_relationship_type` |
| `graph.py` | `WorkspaceDependencyGraph` — immutable graph with traversal APIs |
| `builder.py` | `DependencyGraphBuilder` — constructs graph from `RepositoryIndex` |

### Tests: `tests/repository/dependencies`

| File | Responsibility |
|------|---------------|
| `conftest.py` | Shared test fixtures |
| `test_graph.py` | All graph tests |

---

## Deterministic Guarantees

### Construction

Repeated construction of a `WorkspaceDependencyGraph` from the same
`RepositoryIndex` produces **equivalent** graphs:

- Same nodes (same `qualified_name` values)
- Same edges (same `(source, target, edge_type)` triples)
- Same adjacency lists (same keys, same values in same order)

### Traversal

All traversal methods return results sorted by `(node_type, qualified_name)`.

This means:

```python
graph1 = DependencyGraphBuilder().build(index)
graph2 = DependencyGraphBuilder().build(index)

# Equivalent
assert graph1.nodes() == graph2.nodes()
assert graph1.edges() == graph2.edges()
assert graph1.dependencies(node) == graph2.dependencies(node)
assert graph1.transitive_dependencies(node) == graph2.transitive_dependencies(node)
```

### Hash Stability

Graphs built from the same index have the same hash:

```python
assert hash(graph1) == hash(graph2)
```

---

## Complexity

### Construction

- **Time**: O(V + E) where V is the number of symbols and E is the number of relationships
- **Space**: O(V + E) for nodes, edges, and adjacency lists

### Traversal

- **Time**: O(V + E) for BFS traversal (each node and edge visited at most once)
- **Space**: O(V) for visited set and result list

---

## Constraints

### Construction

- Nodes are derived exclusively from `RepositoryIndex.symbols()`
- Edges are derived exclusively from `RepositoryIndex.relationships()`
- No source files are reparsed
- No filesystem access
- No AST inspection
- No RepositoryIndex mutation

### Traversal

- Cycle prevention is enforced via visited set
- No node appears twice in traversal results
- No synthetic nodes are created
- The graph is never mutated

---

## Public API

```python
from packages.repository.dependencies import (
    DependencyGraphBuilder,
    GraphEdge,
    GraphNode,
    NodeType,
    WorkspaceDependencyGraph,
)

# Build
graph = DependencyGraphBuilder().build(repository_index)

# Access
graph.nodes()           # Sequence[GraphNode]
graph.edges()           # Sequence[GraphEdge]
graph.node_count()      # int
graph.edge_count()      # int

# Direct queries
graph.dependencies(node)       # Sequence[GraphNode]
graph.dependents(node)         # Sequence[GraphNode]

# Transitive queries
graph.transitive_dependencies(node, depth=1)   # Sequence[GraphNode]
graph.transitive_dependents(node, depth=1)     # Sequence[GraphNode]

# Containment queries
graph.contains(node)           # Sequence[GraphNode]
graph.contained_by(node)       # Sequence[GraphNode]

# Node lookup
graph.find_node(qualified_name)  # GraphNode | None
```

---

## Future Evolution

Future graph nodes may include:

- Git commits
- Test files
- Configuration files
- Documentation
- Build targets
- External libraries

The public `WorkspaceDependencyGraph` API should remain stable.