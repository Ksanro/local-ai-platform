# Refactoring Advisor

> "Where should I improve this codebase?"

The Refactoring Advisor answers this question with **deterministic** recommendations backed by repository facts.

## Overview

The Refactoring Advisor consumes existing repository analysis data and produces structured refactoring opportunities. It introduces **no new repository analysis algorithms**. It never:

- Parses Python
- Inspects AST
- Traverses filesystem
- Invokes providers
- Mutates repository state
- Recomputes dependency graphs

It only orchestrates existing public services.

## Architecture

```
RepositoryIndex
        |
        v
DiagnosticsEngine (dead code, orphans, cycles, large modules)
        |
        v
ArchitectureAnalyzer (coupling, layering, impact)
        |
        v
RefactoringAdvisor (orchestrates all -> RefactoringReport)
        |
        v
RefactoringReport
```

## Public API

```python
from packages.advisors.refactoring.advisor import RefactoringAdvisor
from packages.advisors.refactoring.config import DEFAULT_CONFIG

advisor = RefactoringAdvisor()
report = advisor.analyze(repository_index=index)

for opp in report.opportunities:
    print(f"{opp.severity}: {opp.title}")
    print(f"  Confidence: {opp.confidence}")
    print(f"  Evidence: {len(opp.evidence)} items")
    for ev in opp.evidence:
        print(f"    - [{ev.type.value}] {ev.message}")
```

## Models

### RefactoringReport

```python
@dataclass(frozen=True)
class RefactoringReport:
    """Complete refactoring report.

    Attributes:
        summary: Summary statistics.
        statistics: Repository statistics.
        opportunities: All refactoring opportunities.
    """
    summary: RefactoringSummary
    statistics: RepositoryStatistics
    opportunities: tuple[RefactoringOpportunity, ...]
```

### RefactoringOpportunity

```python
@dataclass(frozen=True)
class RefactoringOpportunity:
    """A single refactoring opportunity.

    Attributes:
        id: Stable, deterministic identifier.
        category: The refactoring category.
        severity: The severity level.
        title: Human-readable title.
        description: Detailed description.
        affected_symbols: Symbols affected by this change.
        affected_modules: Modules affected by this change.
        confidence: Confidence value (0.0-1.0).
        evidence: Supporting evidence items.
    """
    id: str
    category: RefactoringCategory
    severity: Severity
    title: str
    description: str
    affected_symbols: tuple[str, ...]
    affected_modules: tuple[str, ...]
    confidence: float
    evidence: tuple[RefactoringEvidence, ...]
```

### RefactoringCategory

| Category | Description |
|---|---|
| `HIGH_COUPLING` | Module has above-average total connections |
| `LARGE_MODULE` | Module exceeds configurable symbol threshold |
| `DEAD_CODE` | Unreachable symbols detected by diagnostics |
| `ORPHAN_MODULE` | Module with zero relationships |
| `CIRCULAR_DEPENDENCY` | Dependency cycle detected |
| `EXCESSIVE_DEPENDENCIES` | Module has excessive outgoing relationships |

### Severity

| Level | Meaning |
|---|---|
| `HIGH` | Immediate attention required |
| `MEDIUM` | Should be addressed |
| `LOW` | Consider addressing |
| `INFO` | Informational only |

### RefactoringEvidence

```python
@dataclass(frozen=True)
class RefactoringEvidence:
    """Supporting evidence for a recommendation.

    Attributes:
        type: The type of evidence.
        source: Where the evidence came from.
        message: Human-readable description.
        reference: Reference to the specific item.
    """
    type: EvidenceType
    source: str
    message: str
    reference: str
```

## Confidence Formula

The confidence value is computed deterministically:

```
confidence = base_score * evidence_factor * completeness_factor
```

### Base Scores by Category

| Category | Base Score |
|---|---|
| CIRCULAR_DEPENDENCY | 0.95 |
| DEAD_CODE | 0.90 |
| ORPHAN_MODULE | 0.85 |
| HIGH_COUPLING | 0.80 |
| EXCESSIVE_DEPENDENCIES | 0.75 |
| LARGE_MODULE | 0.70 |

### Evidence Factor

| Evidence Count | Factor | Meaning |
|---|---|---|
| >= 3 | 1.0 | Strong evidence |
| 2 | 0.9 | Moderate evidence |
| 1 | 0.8 | Minimal evidence |
| 0 | 0.5 | No evidence (should not occur) |

### Completeness Factor

| Value | Meaning |
|---|---|
| 1.0 | All evidence present (complete analysis) |
| 0.9 | Partial evidence (incomplete analysis) |

### Final Confidence

```
clamp(base_score * evidence_factor * completeness_factor, 0.0, 1.0)
```

Rounded to 2 decimal places.

### Example

```python
# DEAD_CODE with 3 evidence items, complete analysis
confidence = compute_confidence(
    category=RefactoringCategory.DEAD_CODE,
    evidence_count=3,
    completeness=1.0,
)
# Returns: 0.90

# LARGE_MODULE with 1 evidence item, partial analysis
confidence = compute_confidence(
    category=RefactoringCategory.LARGE_MODULE,
    evidence_count=1,
    completeness=0.9,
)
# Returns: 0.50
```

## Recommendation Rules

### HIGH_COUPLING

**Rule:** A module is flagged when its total connections (outgoing + incoming) exceed `average * coupling_multiplier`.

**Evidence:**
- Dependency count from architecture review
- Average connections across all modules

**Default threshold:** `average * 1.5`

### LARGE_MODULE

**Rule:** A module is flagged when its symbol count exceeds `large_module_threshold`.

**Evidence:**
- Symbol count from repository index

**Default threshold:** 100 symbols

### DEAD_CODE

**Rule:** Symbols identified as dead by the diagnostics engine.

**Evidence:**
- Dead symbol list from diagnostics
- Each dead symbol is individually referenced

### ORPHAN_MODULE

**Rule:** Modules with zero relationships identified by diagnostics.

**Evidence:**
- Orphan module list from diagnostics
- Symbol count in the orphan module

### CIRCULAR_DEPENDENCY

**Rule:** Dependency cycles identified by diagnostics.

**Evidence:**
- Cycle path from diagnostics
- Cycle length

### EXCESSIVE_DEPENDENCIES

**Rule:** Symbols with outgoing relationships exceeding `dependency_threshold`.

**Evidence:**
- Outgoing relationship count from repository index

**Default threshold:** 20 relationships

## Configuration

```python
from packages.advisors.refactoring.config import RefactoringConfig

config = RefactoringConfig(
    large_module_threshold=100,  # symbols threshold
    coupling_multiplier=1.5,     # multiplier for average
    dependency_threshold=20,     # max outgoing relationships
)

advisor = RefactoringAdvisor(config)
```

## Constraints

The advisor **must not**:

1. Parse Python
2. Inspect AST
3. Traverse filesystem
4. Invoke providers
5. Mutate repository state
6. Recompute dependency graphs

Only orchestrates public services.

## Processing Pipeline

1. **Gather diagnostics** — Call `DiagnosticsEngine.analyze()`
2. **Compute coupling metrics** — From repository relationships
3. **Generate recommendations** — Using config thresholds
4. **Compute confidence** — Deterministic formula
5. **Deduplicate** — By `(category, affected_modules)`
6. **Sort** — By severity desc, confidence desc, id asc

## Deduplication

Duplicates are identified by `(category, affected_modules)` tuple. When duplicates are found, the one with higher confidence is kept.

## Determinism

The advisor is fully deterministic:

- All collections are sorted
- IDs are computed from deterministic values
- Confidence is computed from deterministic formula
- No randomness anywhere

Repeated execution produces identical output.

## Usage Example

```python
from packages.advisors.refactoring.advisor import RefactoringAdvisor
from packages.advisors.refactoring.models import Severity

# Create advisor with default config
advisor = RefactoringAdvisor()

# Analyze repository
report = advisor.analyze(repository_index=index)

# Print summary
print(f"Total opportunities: {report.summary.total_opportunities}")
print(f"  HIGH: {report.summary.high}")
print(f"  MEDIUM: {report.summary.medium}")
print(f"  LOW: {report.summary.low}")
print(f"  INFO: {report.summary.info}")

# Print high-severity opportunities
for opp in report.opportunities:
    if opp.severity == Severity.HIGH:
        print(f"\n{opp.title}")
        print(f"  Description: {opp.description}")
        print(f"  Confidence: {opp.confidence}")
        print(f"  Evidence:")
        for ev in opp.evidence:
            print(f"    - [{ev.type.value}] {ev.message}")
```

## Future Evolution

Future versions may incorporate:

- Git history
- Runtime telemetry
- Code ownership
- Test coverage
- Performance profiling
- AI-generated remediation

without changing the public `RefactoringAdvisor` API.

## Files

```
packages/advisors/refactoring/
    __init__.py          # Package exports
    models.py            # Immutable dataclasses
    config.py            # Configuration
    confidence.py        # Confidence formula
    advisor.py           # Main advisor

tests/advisors/refactoring/
    __init__.py
    test_models.py       # Model tests
    test_config.py       # Config tests
    test_confidence.py   # Confidence tests
    test_advisor.py      # Advisor tests

docs/
    advisors-refactoring.md  # This file