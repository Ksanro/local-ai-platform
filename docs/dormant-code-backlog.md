# Dormant Code Backlog

This backlog tracks code that exists in the repository but is not wired into
the live gateway path.

Last reviewed: 2026-08-01.

## Live Boundary

The live gateway path is:

```text
FastAPI /v1/chat/completions
  -> ModelResolutionStage
  -> PlanningStage
  -> RepositoryContextStage
  -> PipelineEngine history cap
  -> ProviderStage
  -> vLLM
```

Anything not reachable from that path, a gateway endpoint, or a live script is
treated as dormant until deliberately activated.

## Inventory

Approximate footprint:

| Package area | Package files | Test files | Approx. lines | Current role |
|---|---:|---:|---:|---|
| `packages.capabilities` | 12 | 11 | 3.1k | Capability orchestration prototypes. |
| `packages.tasks` | 14 | 8 | 2.6k | Task model and task-specific wrappers. |
| `packages.workflows` | 13 | 9 | 2.2k | Workflow definitions and engine scaffolding. |
| `packages.controller` | 9 | 10 | 3.8k | Engineering controller / decision layer. |
| `packages.execution` | 8 | 6 | 1.4k | Execution planning/runtime layer. |
| `packages.verification` | 6 | 6 | 1.7k | Self-verification scaffolding. |
| `packages.evaluation` | 6 (+1 new) | 6 (+2 new) | 1.6k | `quality_harness_report.py` slice activated; `evaluator.py`/`registry.py` still dormant. |
| `packages.session` | 6 | 6 | 1.1k | Engineering session lifecycle/registry. |
| `packages.engineering_memory` | 4 | 4 | 1.1k | Persistent engineering-session summaries. |
| `packages.observability` | 7 | 9 | 2.1k | Telemetry/event/tracing models. |
| `packages.modification` | 6 | 6 | 1.5k | Code modification engine. |
| `packages.patches` | 5 | 5 | 1.5k | Patch model/generation scaffolding. |
| `packages.bootstrap` | 6 | 6 | 2.6k | Dependency container/platform bootstrap. |
| `packages.autonomous` | 8 | 7 | 2.6k | Autonomous loop policies/state. |
| `packages.architecture` | 3 | 2 | 0.8k | Architecture analyzer. |
| `packages.benchmark` | 5 | 4 | 1.1k | Older benchmark framework. |
| `packages.advisors` | 6 | 6 | 1.4k | Advisor prototypes. |

## Activation Rules

Before moving dormant code into the live product, require all of:

- reachable from `apps/gateway/main.py`, a gateway endpoint, or a documented script
- visible in session logs, quality-harness output, or API response behavior
- covered by focused tests for the live path
- documented in `docs/STATUS.md`
- validated by measurement if it affects latency, prompt tokens, or answer quality

## Recommended Order

### 1. Evaluation — DONE (first slice)

First useful slice activated:

- `packages/evaluation/quality_harness_report.py` — `evaluate_results` and
  `evaluate_comparison`, consuming the plain JSON shape emitted by
  `scripts/quality_harness.py --json` (not `QualityResult` objects, so this
  module has no import dependency on `scripts/`). Reports score, missing
  facts (`misses`), prompt-token cost, latency, and — for
  `--compare-context --json` — per-probe context delta matched by id.
- `scripts/evaluate_quality_harness.py` — CLI that reads harness `--json`
  output from a file or stdin and prints/emits the evaluation.
- Reachable via a documented script (`TESTING.md`), covered by
  `tests/evaluation/test_quality_harness_report.py` and
  `tests/scripts/test_evaluate_quality_harness.py`, and documented in
  `docs/STATUS.md`.
- `evaluator.py` (`WorkflowEvaluator`) and `registry.py` were **not** reused —
  they're bound to the dormant `WorkflowPlan`/`ExecutionReport`/
  `CapabilityResult` shapes and remain dormant.

### 2. Engineering Memory

Useful after evaluation produces stable summaries.

First useful slice:

- Persist quality-harness/session-analysis runs as deterministic records.
- Store model, gateway commit, config snapshot, score, token cost, and notes.
- Avoid semantic memory until the deterministic history is useful.

### 3. Observability

Potentially useful, but only selectively.

First useful slice:

- Reuse event/metric models if they improve session analysis.
- Do not replace JSONL session logs yet; they are simple and already live.

## Hold For Later

Keep these dormant until there is a concrete product need:

- `packages.capabilities`
- `packages.tasks`
- `packages.workflows`
- `packages.controller`
- `packages.execution`
- `packages.verification`
- `packages.modification`
- `packages.patches`
- `packages.bootstrap`
- `packages.autonomous`

These form a larger autonomous engineering stack. Activating them wholesale
would change the product shape from "gateway with context" to "engineering
agent runtime", which should be a deliberate milestone.

## Cleanup Notes

- `packages/pipeline/stages/__init__.py` imports dormant stages for package
  convenience, but `apps/gateway/main.py` registers only
  `ModelResolutionStage`, `PlanningStage`, `RepositoryContextStage`, and
  `ProviderStage`.
- Dormant docs in `docs/index.md` should remain labeled as future/dormant.
- Full-repo test/lint still includes dormant packages with known debt; use
  focused live-path gates until CI is realigned.
