# Benchmark Framework v1

## Overview

The Benchmark Framework evaluates the complete retrieval pipeline **without invoking any LLM or network calls**. It provides deterministic, reproducible measurement of retrieval quality across all pipeline stages.

## Architecture

```
BenchmarkRunner
    ↓
BenchmarkEngine (pipeline execution)
    ↓
Planning → Repository → Ranking → Context → Serializer
    ↓
BenchmarkResult / BenchmarkReport
```

### Execution Flow

```
BenchmarkCase (input)
    ↓
[1] Planning — ContextPlanner.build()
    ↓
[2] Repository Search — RepositoryIndex.find()
    ↓
[3] Ranking + Context Building — ContextBuilder.build()
    ↓
[4] Serialization — ProviderSerializer.serialize()
    ↓
BenchmarkResult (output)
```

### Data Flow

```
BenchmarkCase ──────────────────────────────────────────┐
│                                                       │
│  id, name, query, expected_symbols,                   │
│  expected_modules, max_context_tokens,                │
│  planner_intent, tags                                 │
│                                                       │
▼                                                       │
BenchmarkEngine.run()                                   │
│                                                       │
│  Stage 1: Planning                                    │
│    ContextPlanner.build([case.query])                 │
│                                                       │
│  Stage 2: Repository Search                           │
│    for symbol in repository_index.symbols():          │
│        if query in symbol.qualified_name:             │
│            found.append(symbol.qualified_name)        │
│                                                       │
│  Stage 3: Context Building                            │
│    ContextBuilder.build(ContextQuery(                 │
│        text=case.query,                              │
│        max_tokens=case.max_context_tokens,            │
│    ))                                                 │
│                                                       │
│  Stage 4: Serialization                               │
│    ProviderSerializer.serialize(context_package, msg) │
│                                                       │
▼                                                       │
BenchmarkResult ─────────────────────────────────────────┘
│                                                       │
│  benchmark, selected_symbols,                         │
│  selected_modules, estimated_tokens,                  │
│  duration_ms, passed, score, failures                 │
│                                                       │
▼                                                       │
BenchmarkReport (aggregate)                             │
│                                                       │
│  executed, passed, failed,                            │
│  average_score, average_duration_ms,                  │
│  results                                              │
```

## Models

### BenchmarkCase (Input)

Immutable dataclass specifying a single benchmark case.

| Field               | Type          | Description                           |
|---------------------|---------------|---------------------------------------|
| `id`                | `str`         | Unique identifier                     |
| `name`              | `str`         | Human-readable name                   |
| `description`       | `str`         | Detailed description                  |
| `query`             | `str`         | Query text driving the pipeline       |
| `expected_symbols`  | `tuple[str]`  | Expected qualified symbol names       |
| `expected_modules`  | `tuple[str]`  | Expected module paths                 |
| `expected_relationships` | `tuple[str]` | Expected relationship identifiers  |
| `max_context_tokens`| `int`         | Maximum token budget                  |
| `planner_intent`    | `str`         | Expected planner intent               |
| `tags`              | `tuple[str]`  | Categorization tags                   |

### BenchmarkResult (Per-Case Output)

Immutable dataclass with results for a single case.

| Field               | Type          | Description                           |
|---------------------|---------------|---------------------------------------|
| `benchmark`         | `str`         | Benchmark case id                     |
| `selected_symbols`  | `tuple[str]`  | Symbols selected by pipeline          |
| `selected_modules`  | `tuple[str]`  | Modules selected by pipeline          |
| `selected_relationships` | `tuple[str]` | Relationships selected by pipeline |
| `estimated_tokens`  | `int`         | Estimated token count                 |
| `duration_ms`       | `float`       | Total execution time in ms            |
| `passed`            | `bool`        | Whether the benchmark passed          |
| `score`             | `float`       | Overall score (0.0–1.0)              |
| `failures`          | `tuple[str]`  | Failure descriptions                  |

### BenchmarkReport (Aggregate Output)

Immutable dataclass with aggregate statistics across multiple cases.

| Field               | Type          | Description                           |
|---------------------|---------------|---------------------------------------|
| `executed`          | `int`         | Number of benchmarks executed         |
| `passed`            | `int`         | Number of benchmarks that passed      |
| `failed`            | `int`         | Number of benchmarks that failed      |
| `average_score`     | `float`       | Average score across all benchmarks   |
| `average_duration_ms` | `float`   | Average duration across all benchmarks|
| `results`           | `tuple[BenchmarkResult]` | Sorted results by benchmark id |

## Scoring

### Metrics

| Metric | Range | Description |
|--------|-------|-------------|
| Symbol Precision | 0.0–1.0 | Fraction of expected symbols retrieved |
| Module Precision | 0.0–1.0 | Fraction of expected modules retrieved |
| Relationship Precision | 0.0–1.0 | Fraction of expected relationships retrieved |
| Budget Compliance | 0.0–1.0 | Whether estimated tokens fit within budget |

### Weights (Constants)

The overall score is a weighted average:

```
40% symbol precision
20% module precision
20% relationship precision
20% budget compliance
```

These weights are **constants** — not configurable per-case — to ensure deterministic, comparable scores across runs.

### F1 Scoring

All precision metrics use F1-like scoring (harmonic mean of precision and recall):

```
F1 = 2 × precision × recall / (precision + recall)
```

Where:
- **Precision** = |retrieved ∩ expected| / |retrieved|
- **Recall** = |retrieved ∩ expected| / |expected|

### Budget Compliance

Budget compliance is a **hard constraint** — not a gradient:

```
1.0 if estimated_tokens <= max_context_tokens
0.0 otherwise
```

## Public API

```python
from packages.benchmark import BenchmarkRunner, BenchmarkCase

# Single case
runner = BenchmarkRunner()
result = runner.run(case, repository_index)

# Multiple cases
report = runner.run_multiple(cases, repository_index)
```

## Constraints

The benchmark framework **must NOT**:

- Invoke providers
- Perform HTTP requests
- Call LLMs
- Modify RepositoryIndex
- Mutate ContextPackage
- Access the filesystem
- Parse source code
- Inspect AST

All operations are pure evaluation only.

## Golden Snapshots

Golden snapshots are stored in `benchmarks/*/expected.json`. They capture expected retrieval output for specific intent types:

- `benchmarks/explain/expected.json` — EXPLAIN intent
- `benchmarks/debug/expected.json` — DEBUG intent
- `benchmarks/implement/expected.json` — IMPLEMENT intent

Future commits compare actual results against these golden values to detect retrieval regressions.

## Adding New Benchmarks

To add a new benchmark case:

1. Create a `BenchmarkCase` with appropriate fields.
2. Add it to the `cases` list in your test file.
3. Run `pytest` to verify.
4. Update golden snapshots if needed.

Example:

```python
from packages.benchmark import BenchmarkCase

case = BenchmarkCase(
    id="my_new_benchmark",
    name="My New Benchmark",
    description="Tests X retrieval quality",
    query="Query text",
    expected_symbols=("symbol1", "symbol2"),
    expected_modules=("mod1.py", "mod2.py"),
    max_context_tokens=4096,
    planner_intent="EXPLAIN",
    tags=("explain", "new"),
)
```

## Future Evolution

Future versions may add:

- Provider latency measurement
- Actual token counting
- DSPARK benchmarks
- Memory benchmarks
- Semantic retrieval benchmarks
- Routing benchmarks

These additions must not change the public `BenchmarkRunner` API.

## Testing

Run the test suite:

```bash
pytest tests/benchmark/ -v
```

Coverage target: >95%

## File Structure

```
packages/benchmark/
    __init__.py      — Package exports
    models.py        — Immutable dataclasses
    metrics.py       — Scoring functions
    engine.py        — Pipeline execution
    runner.py        — Public API

tests/benchmark/
    __init__.py
    test_engine.py   — Engine tests
    test_metrics.py  — Metrics tests
    test_runner.py   — Runner tests

benchmarks/
    explain/expected.json
    debug/expected.json
    implement/expected.json

docs/
    benchmark-framework.md