# Architecture Review v1

## Overview

The **Architecture Review** capability analyzes a repository and produces a structured architectural assessment using only repository intelligence.

It does **NOT** invoke an LLM.

It prepares an **Architecture Review Package** that can later be consumed by any provider.

## Architecture

```
User Query
    ↓
ArchitectureAnalyzer
    ↓
RepositoryIndex
    ↓
Dependency Graph
    ↓
Diagnostics
    ↓
Impact Analysis
    ↓
ArchitectureReview
    ↓
CapabilityResult
```

## Pipeline

1. **User Query** — the developer asks "Review the architecture of this project."
2. **ArchitectureAnalyzer** — orchestrates public Repository APIs.
3. **RepositoryIndex** — provides modules, symbols, relationships.
4. **Dependency Graph** — provides dependency structure.
5. **Diagnostics** — provides dead code, cycles, orphans.
6. **Impact Analysis** — provides change impact summary.
7. **ArchitectureReview** — composed result.
8. **CapabilityResult** — final output.

## Models

### ArchitectureReview

| Field | Type | Description |
|-------|------|-------------|
| `modules` | `tuple[ModuleSummary, ...]` | All modules in the repository |
| `dependency_summary` | `dict[str, int]` | Relationship counts by type |
| `dependency_cycles` | `tuple[str, ...]` | Detected dependency cycles |
| `layering_violations` | `tuple[str, ...]` | Layering constraint violations |
| `orphan_modules` | `tuple[str, ...]` | Modules with zero relationships |
| `high_coupling_modules` | `tuple[ModuleSummary, ...]` | Modules with above-average connections |
| `largest_components` | `tuple[ModuleSummary, ...]` | Modules with most symbols |
| `diagnostics` | `dict[str, int]` | Diagnostic statistics |
| `impact_summary` | `dict[str, object]` | Change impact summary |
| `repository_statistics` | `dict[str, int]` | Repository-level statistics |

### ModuleSummary

| Field | Type | Description |
|-------|------|-------------|
| `module` | `str` | Module path |
| `symbol_count` | `int` | Number of symbols in the module |
| `dependency_count` | `int` | Outgoing relationship count |
| `dependent_count` | `int` | Incoming relationship count |
| `instability_score` | `float` | `dependency / (dependency + dependent)` |

## Analyzer Responsibilities

The `ArchitectureAnalyzer` orchestrates:

- **RepositoryIndex** — modules, symbols, relationships, statistics
- **WorkspaceDependencyGraph** — dependency graph summary
- **DiagnosticsEngine** — dead code, cycles, orphans
- **ChangeImpactAnalyzer** — impact summary for top modules

It **never**:

- Parses Python
- Inspects AST
- Traverses filesystem
- Invokes providers
- Computes relationships manually

## Constraints

- **No AI** — no provider invocation
- **No filesystem** — only Repository public APIs
- **No AST** — no Python parsing
- **No duplication** — never reimplements existing logic
- **Deterministic** — repeated execution produces identical output

## Determinism

Output ordering:

1. Module name (alphabetical)
2. Qualified name (alphabetical)

Repeated execution must produce identical output.

## Public API

```python
from packages.capabilities.architecture_review import ArchitectureReviewCapability

capability = ArchitectureReviewCapability()
result = capability.execute(
    query="Review the architecture",
    repository_index=index,
)
```

Returns a `CapabilityResult` containing:

- `context_plan` — the architecture review plan
- `context_package` — assembled context
- `provider_request` — serialized request
- `selected_symbols` — module names
- `selected_modules` — selected modules

## Future Evolution

Future versions may add:

- Architectural smells
- ADR validation
- DDD boundary detection
- Microservice suggestions
- Layering recommendations
- AI-generated reports

without changing the `ArchitectureAnalyzer` public API.