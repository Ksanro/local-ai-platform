# Current Status

This file is the current runtime snapshot. It intentionally describes only
what matters for the live gateway path and calls out dormant code explicitly.

Last reviewed: 2026-08-01.

## Product Shape

Local AI Platform is an OpenAI-compatible gateway for coding agents. It sits
between agents and a self-hosted vLLM backend, injects ranked repository
context, optionally caps forwarded chat history, and records session logs for
measurement.

## Live Request Path

The live path is registered in `apps/gateway/main.py` during application
lifespan startup:

```text
FastAPI /v1/chat/completions
  -> ModelResolutionStage
  -> PlanningStage
  -> RepositoryContextStage
  -> PipelineEngine history cap
  -> ProviderStage
  -> vLLM
```

### ModelResolutionStage

Resolves the client-facing `model` to a `ResolvedModel` using either
`APP_MODELS_CONFIG` or fallback single-provider mode. The resolved definition
contains provider, backend model, context window, max output tokens, and
capability metadata.

### PlanningStage

Extracts user text, including OpenAI list-form content used by Cline, detects
intent deterministically, and stores a `ContextPlan` for repository-context
selection. Cline tool-result envelopes sent as user-role text are ignored for
intent selection so search/read/command output does not override the original
task. Ambiguous inspection words such as `investigate`, `inspect`, and `check`
route conservatively to `SEARCH` unless stronger signals such as `failing`,
`error`, or `bug` indicate `DEBUG`.

Clients can force repository-context planning with `context_intent` in the
request body or `X-Context-Intent` in headers. Local deployments can also add
deterministic custom intent phrases with `APP_CONTEXT_INTENT_RULES`, a JSON
object such as `{"IMPLEMENT":["adauga"],"SEARCH":["cauta"]}`. Precedence is:
explicit request override, custom rules, then built-in defaults.

### RepositoryContextStage

Uses the startup repository index to select ranked symbols and modules, then
injects repository context into the provider-bound messages. Delta injection
suppresses symbols already sent in the conversation.

Test files are included in the repository index by default
(`APP_REPOSITORY_EXCLUDE_TESTS=false`) so TEST-mode prompts can retrieve the
actual validation files. Ranking still penalizes test files for ordinary
non-test queries, but explicit test-seeking queries receive a test-target
signal and additional credit for descriptive module filename tokens.

`APP_REPOSITORY_CONTEXT_MAX_TOKENS` controls the token budget passed to
repository-context ranking, relationship expansion, and final assembled
context trimming. The builder preserves the primary symbol first, drops
lower-ranked supporting symbols, and trims oversized primary source when
needed. Session logs record both `context.estimated_tokens` and
`context.max_tokens` so context size can be measured separately from full
provider prompt tokens.

`APP_REPOSITORY_CONTEXT_INTENT_BUDGETS` can override the default by planner
intent, for example `SEARCH:2048,TEST:2048,DEBUG:2048,EXPLAIN:8192`. Explicit
request metadata still wins over intent defaults. The current live tuning
baseline uses `SEARCH:2048`; in a same-prompt Cline A/B it reduced median
repository context from about `4013` to `2047` estimated tokens and median
prompt tokens from about `17,106` to `16,146`. The TEST baseline uses `2048`;
after enabling test indexing and clean Cline task extraction, a same-prompt
Cline validation preserved answer quality while reducing direct repository
context from about `2182` to `2020` estimated tokens and prompt tokens from
about `15,397` to `15,158` on the assembled turn. The DEBUG baseline uses
`2048`; after increasing the non-test-query penalty for test files, a
same-prompt Cline validation preserved answer quality while reducing direct
repository context from about `4095` to `2047` estimated tokens and median
prompt tokens from about `17,580` to `15,880`. Latency remained noisy in the
small samples.

### History Capping

When `APP_HISTORY_CAP_ENABLED=true`, `PipelineEngine` caps non-system
conversation history to `APP_HISTORY_CAP_TOKENS`, or derives a budget from
the resolved model when the explicit value is `0`.

Measured result with Cline/vLLM:

- cap code runs and is visible in session logs
- `3000` token cap dropped history in 3 of 5 measured requests
- mean prompt tokens dropped by about 4.8k
- mean provider wait improved by about 1.85s
- repository context remains a major contributor to total prompt size
- current oversized Cline tool-result envelopes are capped before provider
  forwarding; a live `answer_preview` search-result turn dropped from about
  `104,956` prompt tokens to a max of `20,321` prompt tokens while preserving
  the final task answer quality

### ProviderStage

Builds the provider payload from `NormalizedRequest`, swaps `model` to
`backend_model`, preserves protocol fields, and calls the resolved provider.

## What Is Implemented And Reachable

- FastAPI gateway endpoints: `/health`, `/version`, `/v1/models`,
  `/v1/chat/completions`
- vLLM provider
- provider registry and factory
- model registry and model router
- normalized request boundary
- protocol compatibility tests
- repository index builder
- planning and intent detection
- repository-context injection
- delta context injection
- history capping
- session JSONL logging
- session log analyzer
- live gateway quality harness
- live Cline/vLLM A/B measurement protocol
- quality-harness style/compliance signal for unwanted reasoning preambles and
  tool/thinking chatter (`style_violations`, `style_ok`)
- multi-turn Cline-like quality-harness probes (`QualityProbe.history`) —
  `multiturn_history_cap_budget`, `multiturn_config_systems`; prior
  user/assistant turns are sent before the scored final prompt
- `packages.evaluation.quality_harness_report` (`evaluate_results`,
  `evaluate_comparison`) via `scripts/evaluate_quality_harness.py` — scores
  quality-harness `--json` output (score, missing facts, prompt tokens,
  latency, context delta)
- `packages.engineering_memory.quality_harness_records`
  (`build_quality_harness_record`, `build_quality_harness_comparison_record`)
  via `scripts/evaluate_quality_harness.py --persist` — stores quality-harness
  evaluations as deterministic `EngineeringSessionRecord`s (model, gateway
  commit, config snapshot, score, token cost, notes) through the existing
  `EngineeringMemory`/`MemoryStorage` layer
- `packages.evaluation.quality_run` (`QualityRun`, `build_quality_run`,
  `build_quality_run_from_comparison`) via
  `scripts/evaluate_quality_harness.py --quality-run [--quality-run-path]` —
  a flat, storage-agnostic run summary (run_id, model, mode, totals, per-probe
  rows with context-delta fields when in `--compare-context` mode). Optional;
  does not replace `EngineeringMemory` and has no persistence of its own.
- `packages.observability.quality_history` (`summarize_quality_history`,
  `load_quality_history`) via `scripts/quality_history.py` — read-only summary
  of persisted quality-harness `EngineeringMemory` records: run counts,
  workflow aggregates, latest context score delta, prompt-token averages, and
  recent missing facts.

## What Exists But Is Dormant

These packages are not part of the live gateway path unless explicitly wired
later:

- `packages.capabilities`
- `packages.tasks`
- `packages.workflows`
- `packages.advisors`
- `packages.autonomous`
- `packages.verification`
- `packages.patches`
- `packages.modification`
- `packages.session`
- `packages.bootstrap`
- `packages.controller`
- `packages.evaluation` — except `quality_harness_report.py`, activated for
  the quality harness; `evaluator.py`/`registry.py`/`WorkflowEvaluator` remain
  dormant, still bound to the unactivated workflow stack
- `packages.execution`
- `packages.observability` — except `quality_history.py`, activated as a
  read-only quality-harness history summary; the telemetry/event/tracing stack
  remains dormant
- `packages.architecture`
- `packages.benchmark`
- `packages.engineering_memory` — except `quality_harness_records.py`,
  activated to persist quality-harness evaluations; the rest of the package's
  session-lifecycle-oriented surface remains dormant

They may contain tests and useful designs, but they should not be treated as
runtime behavior.

Approximate dormant-package footprint as of 2026-08-01:

| Area | Package files | Test files | Approx. lines | Backlog posture |
|---|---:|---:|---:|---|
| `packages.evaluation` | 6 | 6 | 1.6k | `quality_harness_report.py` slice activated; `evaluator.py`/`registry.py` still dormant. |
| `packages.engineering_memory` | 4 | 4 | 1.1k | `quality_harness_records.py` slice activated; the rest still dormant. |
| `packages.observability` | 7 | 9 | 2.1k | `quality_history.py` slice activated; telemetry/tracing stack still dormant. |
| `packages.capabilities` | 12 | 11 | 3.1k | Useful design source, but overlaps current planning/context path. |
| `packages.tasks` / `workflows` | 27 | 17 | 4.8k | Keep dormant until an execution loop is product-proven. |
| Controller/execution/verification stack | 29 | 28 | 7.0k | Large future stack; not on the gateway hot path. |
| Modification/patches/session/bootstrap/autonomous/advisors/architecture/benchmark | 49 | 46 | 12.5k | Inventory before wiring; use only with a concrete measured need. |

## Configuration Notes

There are two configuration systems:

| System | Prefix | Examples |
|---|---|---|
| Gateway settings | `APP_` | `APP_DEFAULT_MODEL`, `APP_MODELS_CONFIG`, `APP_HISTORY_CAP_ENABLED` |
| vLLM provider raw env | none | `VLLM_BASE_URL`, `VLLM_API_KEY`, `REQUEST_TIMEOUT`, `DEFAULT_MODEL` |

`DEFAULT_MODEL` and `APP_DEFAULT_MODEL` are different. `.env` is loaded with
`override=True`, so changing shell environment variables will not override
values already present in `.env`.

## Testing Reality

Use focused gates for live-path changes. Full-repo tests and lint still include
dormant packages with known failures and pre-existing lint debt.

Recommended live-path checks:

```powershell
.\uv run python -m pytest tests\pipeline tests\gateway tests\providers tests\planning tests\context tests\repository -q
.\uv run python -m ruff check apps\gateway packages\pipeline packages\providers packages\planning packages\context packages\repository scripts
.\uv run python -m mypy packages\providers packages\pipeline apps\gateway
.\uv run python scripts\quality_harness.py
.\uv run python scripts\quality_harness.py --compare-context
.\uv run python scripts\quality_harness.py --json | .\uv run python scripts\evaluate_quality_harness.py -
```

## Current Open Issues

- CI still runs broad repo checks and should be realigned to the documented
  baseline or cleaned up.
- Repository context can dominate prompt size; history capping alone is not the
  full latency lever. Configurable repository-context budget enforcement and
  targeted retrieval promotions now exist; recent quality-harness runs show
  `14-15/15` with context versus `2/15` without context on the fixed probe set.
- Token estimates still use `CHARS_PER_TOKEN = 4.0`, not model-specific
  tokenizers.
- The model often includes reasoning/preamble despite terse system prompts; the
  quality harness now records deterministic style violations separately from
  required-fact score.
- Only vLLM is implemented as a concrete provider; true multi-provider
  operation is not product-proven.
