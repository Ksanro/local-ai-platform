# Current Status

This file is the current runtime snapshot. It intentionally describes only
what matters for the live gateway path and calls out dormant code explicitly.

Last reviewed: 2026-08-22.

## Product Shape

Local AI Platform is an OpenAI-compatible gateway for coding agents. It sits
between agents and a self-hosted OpenAI-compatible backend, injects ranked
repository context, optionally caps forwarded chat history, and records
session logs for measurement.

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
  -> vLLM / OpenAI-compatible backend (SGLang)
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

For anaphoric multi-turn follow-ups such as "for that capping logic" or
"given that split", retrieval includes the previous clean user task text so
ranking sees the disambiguating prior turn instead of only the short follow-up.

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
intent, for example `SEARCH:2048,TEST:2048,DEBUG:2048,EXPLAIN:4096`. Explicit
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

REFACTOR and EXPLAIN were measured on 2026-08-09 with
`scripts/quality_harness.py --json --max-tokens 900` (the harness has no
`--budget` flag; a budget A/B means two full `--json` runs at different
`APP_REPOSITORY_CONTEXT_INTENT_BUDGETS` values, diffed by probe `id`).
**REFACTOR** was tried at `2048` and `3072`, both reverted: 3 replicate runs at
`3072` consistently missed the same required fact
(`select_last_task_text`, replaced with a hallucinated but wrong
`select_context_query_text`) that the `4096` default answers correctly every
time - a real, repeatable regression, distinguished from noise by an
unrelated control probe (budget untouched) that swung by 2 hits across the
same runs. REFACTOR stays at the `4096` default. **EXPLAIN** moved to `2048`
(from `8192`): 3 replicate runs averaged 3.67/9 combined hits across the three
EXPLAIN probes versus a single-run baseline of 2/9 at `8192` - noisy (0 to 6
across replicates) but net positive, driven by `explain_live_path` going from
always-broken to passing in 2 of 3 runs; one other EXPLAIN probe
(`multiturn_config_systems`) got consistently worse. `explain_live_path`
prompt tokens dropped from `5136` to `1119-1975` across runs.

`multiturn_history_cap_budget` now consistently scores 3/3. The near-zero
regression was fixed by commit 6fe9283 ("Clarify history cap budget probe
facts"), which added `APP_HISTORY_CAP_TOKENS` to `_apply_history_cap`'s
docstring and reworded the probe prompt to ask for the environment variable
instead of the Python argument name. Verified live: 8/8 replicate runs (qwen27,
--max-tokens 900) with zero misses.

`multiturn_config_systems` had a repeatable 16/17 miss at the `2048` EXPLAIN
budget: the context trim dropped `apps/gateway/core/config.Settings`, so
`apps/gateway/core/config.py` never reached the answer. It was resolved on
2026-08-22 with two fixes - retrieval/promotion support for history-cap/config
symbols, and the EXPLAIN repository-context intent budget raised from `2048` to
`4096`. The probe now scores 2/2 consistently; the gateway log records
`modules_selected=9` and `estimated_tokens=3861` for the scored EXPLAIN turn.

A Tokenizer Registry investigation (2026-08-10) was opened after
`logs/quality_compare_qwen36_20260807*.json` (three saved `--compare-context`
runs, filesystem-dated 2026-08-07 16:27-16:44) appeared to show EXPLAIN real
token cost running 2.17x-3.43x the *current* 2048 nominal budget. That
comparison was methodologically wrong: those files predate the EXPLAIN
8192-to-2048 retune documented above (committed 2026-08-09 08:28, `0dcf2bf`),
so EXPLAIN was still budgeted at 8192 when they were captured. The same real
costs (4452-7030 tokens) divide to 0.54x-0.86x against 8192 - in line with
every other intent's normal behavior, not a divergence. Two plan drafts
(`logs/agent_handoffs/explain_token_estimate_correction_plan.md`, `_v2.md`)
proposed `CHARS_PER_TOKEN` fixes based on the uncorrected comparison; both
were rejected on review before implementation - v1's causal claim was
contradicted by its own data (`implement_health_flag` promotes the same
`apps/gateway/core/config.Settings` symbol without showing elevated
divergence), and v2 additionally cited two `packages/context/builder.py`
promotion functions that do not exist in the file. A fresh live
`--compare-context` re-measurement on 2026-08-10 against the current 2048
budget found EXPLAIN in the normal band (0.83x-1.00x, reproduced twice).
`CHARS_PER_TOKEN = 4.0` is unchanged; no tokenizer-accuracy problem is
currently measured. The real, smaller, still-open question is the run-to-run
variance already noted above (`explain_live_path` ranged 1119-1975 tokens
across 3 replicates at the same 2048 budget on 2026-08-09) - a
context-selection determinism question, not a token-estimation-accuracy one.

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

The current local `.env` routes one live backend through `APP_MODELS_CONFIG`
(no empty-string fallback mode):

| client model | provider | base_url | backend_model | context_window | notes |
|---|---|---|---|---|---|
| qwen38-27b | openai | http://100.106.236.88:30000/v1 | qwen3.8-27b | 262144 | SGLang server (owned_by: "sglang") |

SGLang routing was configured and live-smoked on 2026-08-20. The gateway
exposed `qwen38-27b` and
`scripts/quality_harness.py --delta-context --json --model qwen38-27b
--max-tokens 8192 --session-log-path logs\implement_budget_A_4096_20260801.jsonl`
returned `ok: true`. Primer context selected
`packages/pipeline/history.cap_history` with 1843 estimated context tokens;
follow-up context selected `packages/pipeline/history._build_cap_groups` with
1844 estimated context tokens and `symbols_suppressed=1`. Both answers scored
all expected facts with no style violations.

qwen38-27b via SGLang is the current validated backend. Its full quality
baseline was completed on 2026-08-22
(`scripts/quality_harness.py --json --model qwen38-27b --max-tokens 8192
--reasoning-model qwen38-27b`): clean TOTAL 20/20 expected facts, style 8/8
ok, 28013 prompt tokens, 144.6 seconds, saved at
`logs\quality_baseline_qwen38_27b_after_fixes.json` and persisted as
engineering-memory session `quality_harness-20260821T214629502370-6d519523`.

Previous measured backends included `qwen36` on vLLM at
`http://100.106.236.88:8000/v1` and `qwen27` on llama.cpp at
`http://100.106.236.88:8080/v1`; keep older measurements labeled with their
actual model/backend.

Live smoke: `quality_harness.py --probe multiturn_history_cap_budget --json
--max-tokens 900 --model qwen27` scored 3/3 routed through OpenAIProvider to
the real llama.cpp backend.

**qwen36 max-tokens consideration:** qwen36 is a reasoning model that spends
significant tokens on hidden reasoning before the visible answer. Measured
against the same `multiturn_history_cap_budget` probe: 0/3 at `--max-tokens 900`
(empty completion), 3/3 at `--max-tokens 2048` (completion_tokens=1010). This
is not a routing or provider bug -- 900 tokens simply isn't enough headroom for
this model. The harness default is `--max-tokens 400` (see
`scripts/quality_harness.py` DEFAULT_MAX_TOKENS), so future qwen36 measurement
runs should use `--max-tokens 2048` or higher.

## What Is Implemented And Reachable

- FastAPI gateway endpoints: `/health`, `/version`, `/v1/models`,
  `/v1/chat/completions`
- vLLM provider
- vLLM/OpenAI-compatible provider response cleanup for leading empty
  `<think></think>` blocks emitted by some llama.cpp/Qwen chat templates
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
- session analyzer context-cost by-intent table for comparing REFACTOR versus
  EXPLAIN budget use from live session logs
- CI focused on the documented live gateway path instead of dormant packages
- live gateway quality harness
- live Cline/vLLM A/B measurement protocol
- quality-harness style/compliance signal for unwanted reasoning preambles and
  tool/thinking chatter (`style_violations`, `style_ok`)
- local-agent coding workflow catalog (`scripts/local_agent_coding.py`) for a
  staged Cline/qwen27B planning, Claude-extension/qwen35B implementation,
  Claude CLI review/tests, and Codex coordination branch; `style_preamble_cleanup`,
  `delta_context_live_smoke`, and `context_budget_ranking` (`REFACTOR`/`EXPLAIN`
  budget tuning, measured 2026-08-09) are all complete
- multi-turn Cline-like quality-harness probes (`QualityProbe.history`) -
  `multiturn_history_cap_budget`, `multiturn_config_systems`; prior
  user/assistant turns are sent before the scored final prompt
- latest qwen36 live `scripts/quality_harness.py --compare-context` run scores
  `20/20` with repository context versus `2/20` without context across the
  full 8-probe set, including the multi-turn probes
- delta-context quality-harness smoke probe (`scripts/quality_harness.py
  --delta-context`) that sends two sequential live requests and verifies the
  follow-up session record reports suppressed repeated symbols; the live run
  found the session-log middleware flushes after the HTTP response reaches
  the client, so the harness retries reads
  (`_read_session_log_records_with_retry`) instead of racing the write
- `docs/live-gateway-runbook.md` documents how to start the gateway, check it,
  and run the delta-context smoke from a fresh PowerShell or Bash/Git Bash
  terminal, including `.env`/session-log-path alignment
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
- `packages.engineering_memory.session_log_records`
  (`build_session_log_record`, `build_session_log_summary`) via
  `scripts/ingest_session_log.py` — ingests structured gateway session logs
  (`logs/sessions.jsonl`) into `EngineeringMemory` as `gateway_session` records;
  one full-file rewrite per new record stored (fine for periodic runs, not
  designed for high-frequency ingestion).
- `packages.observability.session_log_history` (`summarize_session_log_history`,
  `load_session_log_history`) via `scripts/session_log_history.py` — read-only
  summary of persisted session-log `EngineeringMemory` records: success rate,
  median latency, intent distribution, error breakdown, history-cap rate.

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
- `packages.observability` — except `quality_history.py` and
  `session_log_history.py`, both activated (quality-harness history and session-log
  history summaries respectively); the telemetry/event/tracing stack remains dormant
- `packages.architecture`
- `packages.benchmark`
- `packages.engineering_memory` — except `quality_harness_records.py` and
   `session_log_records.py`, both activated (quality-harness evaluations and
   live gateway session ingestion respectively); the controller/execution/
   verification wiring and semantic memory surface remains dormant

They may contain tests and useful designs, but they should not be treated as
runtime behavior.

Approximate dormant-package footprint as of 2026-08-01:

| Area | Package files | Test files | Approx. lines | Backlog posture |
|---|---:|---:|---:|---|
| `packages.evaluation` | 6 | 6 | 1.6k | `quality_harness_report.py` slice activated; `evaluator.py`/`registry.py` still dormant. |
| `packages.engineering_memory` | 5 | 5 | 2.8k | `quality_harness_records.py` and `session_log_records.py` slices activated; controller wiring still dormant. |
| `packages.observability` | 8 | 10 | 6.0k | `quality_history.py` and `session_log_history.py` slices activated; telemetry/tracing stack still dormant. |
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
.\uv.exe run python -m pytest tests\pipeline tests\gateway tests\providers tests\planning tests\context tests\repository -q
.\uv.exe run python -m ruff check apps\gateway packages\pipeline packages\providers packages\planning packages\context packages\repository scripts
.\uv.exe run python -m mypy packages\providers packages\pipeline apps\gateway
.\uv.exe run python scripts\quality_harness.py
.\uv.exe run python scripts\quality_harness.py --compare-context
.\uv.exe run python scripts\quality_harness.py --delta-context --session-log-path logs\sessions.jsonl
.\uv.exe run python scripts\quality_harness.py --json | .\uv.exe run python scripts\evaluate_quality_harness.py -
```

## Current Open Issues

- Repository context can dominate prompt size; history capping alone is not the
  full latency lever. Configurable repository-context budget enforcement and
  targeted retrieval promotions now exist; recent quality-harness runs show
  `20/20` with context versus `2/20` without context on the fixed probe set.
  `SEARCH`/`TEST`/`DEBUG`/`EXPLAIN` have measured budget overrides; `REFACTOR`
  was measured and reverted to the shared default after a replicated
  regression - see `docs/roadmap.md` section 3 and the "RepositoryContextStage"
  section above for the measured numbers.
- The model often includes reasoning/preamble despite terse system prompts; the
  quality harness now records deterministic style violations separately from
  required-fact score.
- Token estimates still use `CHARS_PER_TOKEN = 4.0`, not model-specific
  tokenizers. True multi-provider is now live (vLLM + OpenAI-compatible to
  llama.cpp); tokenizer-aware accounting remains the next precision improvement.
