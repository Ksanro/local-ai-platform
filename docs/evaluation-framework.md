# Evaluation Framework v1

## Purpose

The Evaluation Framework provides **deterministic evaluation** of engineering workflow executions.

It measures the quality of actual workflow executions — not the quality of AI-generated content.

It does NOT call providers, parse repositories, or perform planning.

It consumes only existing public APIs.

---

## Architecture

```
Engineering Workflow
    ↓
Execution
    ↓
Provider Response
    ↓
EvaluationReport
```

The evaluation framework sits **after** workflow execution. It consumes:

- `WorkflowPlan` — the plan that was executed
- `ExecutionReport` — the execution results
- `CapabilityResult` — optional capability output
- `TaskPlan` — optional task plan
- `ProviderResponse` — optional provider response (tokens, etc.)

And produces:

- `EvaluationReport` — an immutable quality report

---

## Constraints

### Must NOT

- Call providers
- Inspect repositories
- Parse AST
- Build context
- Perform planning
- Rank symbols
- Perform semantic evaluation
- Duplicate diagnostics
- Duplicate architecture analysis
- Duplicate workflows

### Must

- Consume only public APIs
- Produce immutable reports
- Be deterministic
- Be side-effect free

---

## Components

### 1. Models (`models.py`)

Three immutable dataclasses:

| Model | Purpose |
|-------|---------|
| `EvaluationMetric` | A single computed metric (name, value, weight, passed, metadata) |
| `EvaluationScore` | A scored category (category, score, maximum, weight) |
| `EvaluationReport` | Complete evaluation report (metrics, scores, overall_score, summary) |

All models use `frozen=True, slots=True` for immutability.

### 2. Metrics (`metrics.py`)

Deterministic metric computation functions:

| Category | Metrics |
|----------|---------|
| **Context Quality** | `compute_context_compression_ratio`, `compute_context_utilization`, `compute_selected_symbols_count`, `compute_selected_modules_count`, `compute_selected_relationships_count` |
| **Execution Quality** | `compute_execution_duration_ms`, `compute_total_tokens`, `compute_throughput` |
| **Engineering Quality** | `compute_diagnostics_collected`, `compute_architecture_findings_count`, `compute_workflow_completeness` |
| **Determinism** | `compute_execution_consistency`, `compute_identifier_stability` |

All functions are pure, deterministic, and side-effect free.

### 3. Scoring (`scoring.py`)

Weighted score calculation:

| Function | Purpose |
|----------|---------|
| `calculate_category_score()` | Weighted average of metrics in a category |
| `calculate_overall_score()` | Weighted average of all category scores |

Category weights (constants):

| Category | Weight |
|----------|--------|
| Context Quality | 0.25 |
| Execution Quality | 0.20 |
| Engineering Quality | 0.30 |
| Performance | 0.10 |
| Determinism | 0.15 |

**Total: 1.00**

### 4. Registry (`registry.py`)

Registration of custom metrics and categories:

| Function | Purpose |
|----------|---------|
| `register_metric()` | Register a custom metric computation function |
| `register_category()` | Register a custom evaluation category |
| `get_metric()` | Look up a registered metric |
| `get_category()` | Look up a registered category |
| `list_metrics()` | List all registered metric names |
| `list_categories()` | List all registered category names |
| `reset_registry()` | Reset all registries (for testing) |

Duplicate names are silently ignored — the original registration is preserved.

### 5. Evaluator (`evaluator.py`)

The main entry point:

```python
from packages.evaluation.evaluator import WorkflowEvaluator

report = WorkflowEvaluator.evaluate(
    workflow_plan=workflow_plan,
    execution_report=execution_report,
    capability_result=capability_result,
    task_plan=task_plan,
    provider_response=provider_response,
)
```

Responsibilities:

1. Validate input types (public API compliance)
2. Compute deterministic metrics from platform outputs
3. Calculate category scores from metrics
4. Compute overall weighted score
5. Produce immutable `EvaluationReport`

---

## Usage

### Basic Usage

```python
from packages.evaluation import WorkflowEvaluator, EvaluationReport

# Evaluate a workflow execution
report: EvaluationReport = WorkflowEvaluator.evaluate(
    workflow_plan=workflow_plan,
    execution_report=execution_report,
)

# Access results
print(report.overall_score)        # 0.0 to 1.0
print(report.summary)               # Human-readable summary
print(report.metrics)               # Tuple of EvaluationMetric
print(report.scores)                # Tuple of EvaluationScore
```

### Custom Metrics

```python
from packages.evaluation import register_metric

def compute_code_quality() -> float:
    # Compute from existing platform outputs
    return 0.85

register_metric(
    name="code_quality",
    computation=compute_code_quality,
    weight=0.5,
    description="Code quality score",
)
```

### Custom Categories

```python
from packages.evaluation import register_category

register_category(
    name="Code Quality",
    weight=0.20,
    metric_names=["code_quality", "test_coverage"],
    description="Code quality metrics",
)
```

---

## Evaluation Report Structure

```python
EvaluationReport(
    workflow_name="bug-investigation",
    task_name="investigate-bug",
    provider="vllm",
    model="gpt-4",
    started_at="2024-01-01T00:00:00",
    completed_at="2024-01-01T00:01:00",
    metrics=(
        EvaluationMetric(name="context_compression_ratio", value=0.85, ...),
        EvaluationMetric(name="execution_duration_ms", value=5000, ...),
        ...
    ),
    scores=(
        EvaluationScore(category="Context Quality", score=0.85, ...),
        EvaluationScore(category="Execution Quality", score=0.70, ...),
        ...
    ),
    overall_score=0.78,
    summary="Evaluation: bug-investigation/investigate-bug — PASSED\nOverall Score: 0.780/1.000\n  Context Quality: 0.850 (weight: 0.25)\n  ...",
)
```

---

## Integration with Engineering Workflows

```
Engineering Workflow
    ↓
Execution Engine
    ↓
ExecutionReport + ProviderResponse
    ↓
WorkflowEvaluator.evaluate()
    ↓
EvaluationReport
    ↓
Persistence (optional)
    ↓
Engineering Knowledge Graph (future)
```

### Workflow Integration Steps

1. **Execute workflow** — Execution Engine runs the workflow
2. **Collect outputs** — ExecutionReport, ProviderResponse
3. **Evaluate** — Call `WorkflowEvaluator.evaluate()`
4. **Store report** — Optionally persist the report
5. **Query later** — Use the report for analysis

### Example Integration

```python
from packages.evaluation.evaluator import WorkflowEvaluator

# Execute workflow
execution_report = execution_engine.execute(workflow_plan)

# Evaluate
report = WorkflowEvaluator.evaluate(
    workflow_plan=workflow_plan,
    execution_report=execution_report,
    provider_response=provider_response,
)

# Store report
save_evaluation_report(report)
```

---

## Why Structured Engineering Memory?

### This is NOT vector memory

- No embeddings
- No semantic search
- No LLM-based indexing

### This IS structured engineering memory

- **Immutable** — frozen dataclasses
- **Deterministic** — same inputs produce same outputs
- **Structured** — typed fields, not raw text
- **Queryable** — by type, name, category
- **Persistent** — JSON serialization

### Why structured?

1. **Reliability** — Deterministic queries, no randomness
2. **Auditability** — Every metric has a computed value and metadata
3. **Performance** — O(1) lookup by name, no vector search
4. **Simplicity** — No ML dependencies, no embedding models
5. **Correctness** — Engineering data is structured, not semantic

---

## Testing

### Run tests

```bash
uv run pytest tests/evaluation/ -v --cov=packages.evaluation
```

### Coverage target

> 95%

### Test categories

- **Immutability** — frozen=True, slots=True
- **Determinism** — same inputs produce same outputs
- **Edge cases** — empty, zero, negative, unicode
- **Integration** — full evaluate() flow
- **Registry** — registration, lookup, reset

---

## Files

```
packages/evaluation/
    __init__.py          # Package exports
    models.py            # EvaluationMetric, EvaluationScore, EvaluationReport
    metrics.py           # Deterministic metric computation
    scoring.py           # Score calculation
    registry.py          # Metric and category registration
    evaluator.py         # WorkflowEvaluator

tests/evaluation/
    __init__.py
    test_models.py       # Model tests
    test_metrics.py      # Metric computation tests
    test_scoring.py      # Score calculation tests
    test_evaluator.py    # Evaluator tests
    test_registry.py     # Registry tests

docs/
    evaluation-framework.md  # This file
```

---

## Future Work

- **Persistence** — JSON file storage
- **Query engine** — find_by_type, find_by_category
- **Knowledge Graph integration** — persist reports to the graph
- **Historical analysis** — track score trends over time
- **Threshold configuration** — configurable pass/fail thresholds