# Dormant Code Backlog

This backlog tracks code that exists in the repository but is not wired into
the live gateway path.

Last reviewed: 2026-10-09 (`packages.repository.git_changes` gained a live but
opt-in consumer - change-aware repository-context ranking - recorded under
"Cleanup Notes"; the `packages.capabilities` inventory recount from 2026-09-19
stands, and the remaining rows still date from the 2026-08-01 pass).

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

Approximate footprint. The `packages.capabilities` row was recounted with
repository commands on 2026-09-19; every other row is a 2026-08-01 estimate, not
measured inventory:

| Package area | Package files | Test files | Approx. lines | Current role |
|---|---:|---:|---:|---|
| `packages.capabilities` | 15 | 13 | 4.5k (package only, approx.) | Capability Framework v1 prototype, complete but dormant: 8 `Capability` subclasses plus the non-ABC `PullRequestReviewCapability`. |
| `packages.tasks` | 14 | 8 | 2.6k | Task model and task-specific wrappers. |
| `packages.workflows` | 13 | 9 | 2.2k | Workflow definitions and engine scaffolding. |
| `packages.controller` | 9 | 10 | 3.8k | Engineering controller / decision layer. |
| `packages.execution` | 8 | 6 | 1.4k | Execution planning/runtime layer. |
| `packages.verification` | 6 | 6 | 1.7k | Self-verification scaffolding. |
| `packages.evaluation` | 6 (+1 new) | 6 (+2 new) | 1.6k | `quality_harness_report.py` slice activated; `evaluator.py`/`registry.py` still dormant. |
| `packages.session` | 6 | 6 | 1.1k | Engineering session lifecycle/registry. |
| `packages.engineering_memory` | 4 (+1 new) | 4 (+1 new) | 1.1k | `quality_harness_records.py` slice activated for quality-harness/comparison persistence. |
| `packages.observability` | 7 (+1 new) | 9 (+1 new) | 2.1k | `quality_history.py` slice activated; telemetry/event/tracing stack remains dormant. |
| `packages.modification` | 6 | 6 | 1.5k | Code modification engine. |
| `packages.patches` | 5 | 5 | 1.5k | Patch model/generation scaffolding. |
| `packages.bootstrap` | 6 | 6 | 2.6k | Dependency container/platform bootstrap. |
| `packages.autonomous` | 8 | 7 | 2.6k | Autonomous loop policies/state. |
| `packages.architecture` | 3 | 2 | 0.8k | Architecture analyzer. |
| `packages.benchmark` | 5 | 4 | 1.1k | Older benchmark framework. |
| `packages.advisors` | 6 | 6 | 1.4k | Advisor prototypes. |

The `packages.capabilities` line counts are package code only: 4,504 lines across
15 Python files. Its tests add 14,765 lines across 15 files - 13 `test_*.py`
modules plus the shared `assembly_probes.py` helper and `__init__.py` - and
691 focused tests pass (`.\uv.exe run python -m pytest tests\capabilities -q`).
Other rows were not re-measured in this pass.

## Capability Framework v1 - completed prototype (still dormant)

The framework itself is finished as prototype work: nine capabilities, one shared
ABC pipeline, profiles, registry, factory, and a frozen result model, all covered
by focused tests. None of it is reachable from `apps/gateway/main.py`, a gateway
endpoint, or a live script, so it stays in this backlog rather than in
`docs/STATUS.md`'s "What Is Implemented And Reachable" list.

| Capability | `name` | Capability intent | Profile | Retrieval / plan shape |
|---|---|---|---|---|
| `ExplainCapability` | `explain` | `PlannerIntent.EXPLAIN` | `EXPLAIN_PROFILE` | planner-derived plan |
| `DebugCapability` | `debug` | `PlannerIntent.DEBUG` | `DEBUG_PROFILE` | planner-derived plan |
| `RefactorCapability` | `refactor` | `PlannerIntent.REFACTOR` | `REFACTOR_PROFILE` | planner-derived plan |
| `ImplementFeatureCapability` | `implement-feature` | `PlannerIntent.IMPLEMENT` | `IMPLEMENT_PROFILE` | planner called with `intent_override="IMPLEMENT"` |
| `GenerateTestsCapability` | `generate-tests` | `PlannerIntent.GENERATE_TESTS` | `GENERATE_TESTS_PROFILE` | planner called with `intent_override="TEST"` (the planner has no `GENERATE_TESTS` token) |
| `ReviewCapability` | `review` | `PlannerIntent.REVIEW` | `REVIEW_PROFILE` | planner called with `intent_override="SEARCH"` (the planner has no `REVIEW` token); context-assembly only |
| `ArchitectureReviewCapability` | `architecture-review` | `PlannerIntent.REVIEW` | `ARCHITECTURE_REVIEW_PROFILE` | whole-repository analyzer; builds its plan without `ContextPlanner` |
| `BugInvestigationCapability` | `bug-investigation` | `PlannerIntent.DEBUG` | `DEBUG_PROFILE` (reuses the debug profile) | planner-derived plan |
| `PullRequestReviewCapability` | `pull-request-review` | - | - | **different, non-ABC orchestration shape**: not a `Capability` subclass; it builds a dormant `TaskRequest` instead of a `CapabilityResult` |

What is true for every one of them:

- No capability is registered by default. `CapabilityRegistry` starts empty, and
  the only `register(...)` calls in the package live in docstring examples.
- Nothing outside the package imports it at runtime. The only cross-package
  references are `if TYPE_CHECKING:` imports of `CapabilityResult` in
  `packages/evaluation/evaluator.py` and `packages/tasks/models.py`, both dormant
  packages that are themselves not on the gateway path.
- No provider execution occurs. The eight context-assembly capabilities build a
  frozen `CapabilityResult` whose `provider_request` is an unsent
  `ProviderRequest`; nothing sends it, and creating it does not make a capability
  live. `PullRequestReviewCapability.execute()` is narrower still - it returns a
  `dict` carrying a dormant `TaskRequest` and review metadata.
- Importing `packages.serializers` (or any submodule of it, which is how a
  capability reaches `SerializerFactory`) imports the built-in serializer modules
  so they self-register. That is infrastructure availability of the serialization
  layer, not capability activation.
- Relationship honesty: the first ranked candidate becomes `primary_symbol`, the
  remaining candidates become `supporting_symbols`, and `related_modules` is the
  sorted, deduplicated set of candidate modules - the contract pinned by the
  shared `tests/capabilities/assembly_probes.py::assert_relationship_honesty`
  probe. `related_callers` and `related_callees` are never populated from ranked
  candidates: they stay empty, and `RelationshipSummary.caller_count` /
  `callee_count` are `0` with them, because no verified `CALLS` edges reach a
  capability. Ranked candidates carry a score and a module path, never an edge.
- Profile flags: only `relationship_depth`, `max_context_tokens` and the
  `include_callers` / `include_callees` pair (collapsed into
  `relationship_expansion`) have a `ContextQuery` effect.
  `include_dependencies`, `include_dependents`, `include_tests`,
  `include_dead_code` and `include_diagnostics` are declarative intent only.
  `ContextQuery.max_symbols` stays at the platform default (20); a capability
  does not derive a candidate count from `ContextPlan.maximum_depth`, which is
  traversal depth.

## Activation Rules

A capability (or any other dormant area) may move out of dormant status only with
all of the following - not because the code already exists:

- a concrete product need for the behavior
- an explicit reachable entry point in `apps/gateway/main.py`, a gateway
  endpoint, or a documented script
- observable behavior in session logs, quality-harness output, or API responses
- focused tests covering that live path, not only the dormant unit
- documentation updated in `docs/STATUS.md` (and this backlog entry closed)
- measurement wherever latency or context quality can change

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

### 2. Engineering Memory — DONE (first slice)

First useful slice activated:

- `packages/engineering_memory/quality_harness_records.py` —
  `build_quality_harness_record` and `build_quality_harness_comparison_record`,
  turning a `QualityHarnessReport`/`ComparisonReport` (from the evaluation
  slice above) directly into an `EngineeringSessionRecord`. Stores model,
  gateway commit, config snapshot, and notes in `metadata`; the full
  score/missing-facts/token/latency/delta data in `evaluation_report`.
  `controller_decision` is always `"COMPLETE"` — there is no controller
  driving these records, so retry/fail semantics don't apply.
- `scripts/evaluate_quality_harness.py --persist [--model][--gateway-commit]
  [--notes][--storage-path]` — stores the record via `EngineeringMemory`
  (existing `packages/engineering_memory/memory.py` and `persistence.py`,
  unchanged) once evaluation has run.
- Semantic memory, querying by module, and any `packages.session`/
  `packages.controller` wiring were **not** added — only direct record
  construction and storage, per the "avoid semantic memory until the
  deterministic history is useful" guidance below.
- Covered by `tests/engineering_memory/test_quality_harness_records.py` and
  the `TestPersist` cases in `tests/scripts/test_evaluate_quality_harness.py`;
  documented in `docs/STATUS.md`.

Avoid semantic memory until the deterministic history is useful.

### 3. Observability — DONE (first slice)

First useful slice activated:

- `packages/observability/quality_history.py` — read-only summaries of
  persisted quality-harness `EngineeringMemory` records. Reports run counts,
  latest run per workflow, best/worst/average score ratio, average prompt
  tokens, latest context score delta, and recent missing facts by probe id.
- `scripts/quality_history.py` — optional CLI for table or JSON output.
- Does not add a dashboard, external dependency, gateway runtime hook, or
  replacement for existing session JSONL logs.

Keep the broader telemetry/event/tracing stack dormant until the stored
quality summaries prove useful.

## Hold For Later

Keep these dormant until there is a concrete product need:

- `packages.capabilities` — the framework prototype is complete and covered by
  focused tests, but it stays here: no reachable entry point, no registration, no
  live-path behavior to measure yet
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

- `packages.repository.git_changes` is now consumed by the live gateway through
  `packages.repository.changed_files`, but only when
  `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=true` (default off). It stays a
  read-only, two-command Git surface - now under a wall-clock budget per
  command - and no diff, patch, or GitHub capability was activated by that
  wiring.

- `packages/pipeline/stages/__init__.py` imports dormant stages for package
  convenience, but `apps/gateway/main.py` registers only
  `ModelResolutionStage`, `PlanningStage`, `RepositoryContextStage`, and
  `ProviderStage`.
- Dormant docs in `docs/index.md` should remain labeled as future/dormant.
- Full-repo test/lint still includes dormant packages with known debt; use
  focused live-path gates until CI is realigned.
