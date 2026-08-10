# Roadmap

This roadmap is based on the current live gateway, not on dormant scaffolding.

Last reviewed: 2026-08-09.

## Done Enough For Now

- OpenAI-compatible gateway
- vLLM provider
- OpenAI-compatible provider (`packages/providers/openai.py`, registered as "openai")
- provider registry and factory
- model registry
- True Multi-Provider (live, two backends):
  - model "qwen36" -> provider "vllm" -> http://100.106.236.88:8000/v1
    (backend_model "qwen36", context_window 180000)
  - model "qwen27" -> provider "openai" -> http://100.106.236.88:8080/v1
    (backend_model "/models/Qwen3.6-27B-NVFP4-MTP-GGUF.gguf", llama.cpp server,
    context_window 131072)
  - Live smoke: `quality_harness.py --probe multiturn_history_cap_budget --json
    --max-tokens 900 --model qwen27` scored 3/3 routed through OpenAIProvider to
    the real llama.cpp backend
- model router
- client `model` to upstream `backend_model` mapping
- normalized request boundary
- OpenAI protocol compatibility tests
- repository index at startup
- planning stage and deterministic intent detection
- Cline list-form content support in planning
- repository-context injection
- delta context injection
- structured session logs
- session analyzer
- history capping
- measured Cline/vLLM A/B flow proving capping can reduce latency
- explicit per-request context intent override
- configurable custom context intent rules
- live quality harness with context-on/context-off comparison

## Immediate Goals

### 1. Dormant-Code Inventory And Activation — first candidates DONE

Use the dormant packages as a backlog, not as assumed runtime behavior. For
each candidate, decide whether it should be wired into the live gateway,
adapted as a script/tool, or left dormant. See
`docs/dormant-code-backlog.md` for the activated slices and what remains
dormant in each package.

First candidates, all activated as narrow, script-reachable slices:

- `packages.evaluation` - `quality_harness_report.py` scores quality-harness runs
- `packages.engineering_memory` - `quality_harness_records.py` persists deterministic run summaries
- `packages.observability` - `quality_history.py` reuses the persisted records for trend summaries

Remaining dormant packages stay on hold per `docs/dormant-code-backlog.md`'s
"Hold For Later" list until there is a concrete product need.

### 2. Quality Harness Expansion

The fixed probe set now proves repository context adds answer-quality signal
(`20/20` with context versus `2/20` without context in the latest qwen36
`--compare-context` run, including the 2 multi-turn probes).

Done in this area:

- deterministic style/compliance signal for unwanted reasoning preambles and
  tool/thinking chatter, carried through quality-harness JSON,
  `evaluate_quality_harness.py`, and `QualityRun`
- two multi-turn Cline-like probes (`multiturn_history_cap_budget`,
  `multiturn_config_systems`) — `QualityProbe.history` carries prior
  user/assistant turns, sent before the scored final prompt
- delta-context smoke probe (`quality_harness.py --delta-context`) sends two
  sequential live requests and checks session-log `symbols_suppressed` on the
  follow-up request; the live `delta_context_live_smoke` run found that the
  session-log middleware flushes after the HTTP response reaches the client,
  so the harness now retries reads (`_read_session_log_records_with_retry`)
  instead of racing the write
- local-agent coding workflow catalog (`scripts/local_agent_coding.py`) emits
  role-specific prompts and verifier commands for a staged
  Cline/Claude-extension/Claude-CLI/Codex branch; `style_preamble_cleanup`
  (quality-harness system prompt now explicitly bans reasoning-preamble
  phrases and tool-chatter tags) and `delta_context_live_smoke` are both
  complete
- compare-run trend tracking, via `scripts/evaluate_quality_harness.py
  --persist` (writes each run to `EngineeringMemory`) and
  `scripts/quality_history.py` (reads back best/worst/average score ratio,
  latest context delta, recent missing facts)
- live-path CI realignment for gateway/pipeline/provider/planning/context/
  repository tests, lint, and type checks
- multi-turn follow-up retrieval now carries recent clean user task text for
  anaphoric prompts and promotes live history-cap/config-system symbols; latest
  qwen36 live comparison scores `20/20` with context versus `2/20` without

Next improvements:

- keep running `--delta-context` live after gateway changes that touch
  repository context, delta injection, or session logging
- next real product item is Repository Context Budgeting And Ranking (below),
  planning-first via the `context_budget_ranking` local-agent-coding task

### 3. Repository Context Budgeting And Ranking — REFACTOR/EXPLAIN measured

History capping works, but repository context often dominates total prompt
tokens. `SEARCH`, `TEST`, `DEBUG`, and now `EXPLAIN` have measured
`APP_REPOSITORY_CONTEXT_INTENT_BUDGETS` overrides (see `docs/STATUS.md`).
`REFACTOR` was measured and reverted to the shared 4096 default after live
replication showed a real regression, not noise, at both 2048 and 3072 - see
`docs/STATUS.md` for the measured numbers. Ran planning-first via the
`context_budget_ranking` task in `scripts/local_agent_coding.py` (Cline
planned, Claude extension implemented, this pass measured live and iterated):

Done in this pass:

- measured `REFACTOR`/`EXPLAIN` budget quality with live `quality_harness.py
  --json` runs (`--compare-context` toggles context on/off, not budget level -
  a budget A/B needs two separate `--json` runs at different
  `APP_REPOSITORY_CONTEXT_INTENT_BUDGETS` values, diffed by probe `id`)
- found real, replicated (n=3) regressions distinguishable from measurement
  noise by running the same unchanged-budget control probe alongside each
  test - a probe with an untouched budget still swung by 2 hits run to run,
  which is the noise floor these results were checked against

Next:

- `multiturn_history_cap_budget` was resolved in commit 6fe9283
  ("Clarify history cap budget probe facts"): two root causes —
  `APP_HISTORY_CAP_TOKENS` was missing from `_apply_history_cap`'s docstring,
  and the probe prompt asked for the Python argument name
  (`max_tokens_override`) instead of the environment variable. Verified live:
  8/8 replicate runs (3 + 5, qwen27, --max-tokens 900) scored 3/3 with zero
  misses.
- add tokenizer-aware estimates when the current character estimate becomes a
  practical blocker

### 4. CI Realignment - DONE

CI now follows the documented live-path baseline instead of treating every
dormant package as production runtime:

- tests: `tests/pipeline`, `tests/gateway`, `tests/providers`,
  `tests/planning`, `tests/context`, `tests/repository`
- lint: `apps/gateway`, live `packages/*` slices, and `scripts`
- type checks: `packages/providers`, `packages/pipeline`, and `apps/gateway`

## Next After That

### Tokenizer Registry

`ModelDefinition.tokenizer` exists as metadata only. Token estimates still use
`CHARS_PER_TOKEN = 4.0`. Add tokenizer-aware accounting when budget precision
becomes a practical problem.

Investigated 2026-08-10: an apparent 2.17x-3.43x EXPLAIN-intent divergence
turned out to be a stale-budget comparison artifact (the source data predated
an EXPLAIN budget retune by two days) rather than a real tokenizer-accuracy
problem - see `docs/STATUS.md`'s RepositoryContextStage section for the full
account. No fix implemented; the gate above remains unmet.

### Engineering Memory

`packages.engineering_memory` has two active slices:
- **Quality-harness records:** `quality_harness_records.py` persists evaluation
  runs; `quality_history.py` + `scripts/quality_history.py` summarize them.
- **Session-log records:** `session_log_records.py` ingests `logs/sessions.jsonl`
  into EngineeringMemory; `session_log_history.py` + `scripts/session_log_history.py`
  produce deterministic success/failure summaries (timing, intent distribution,
  error breakdown, history-cap rate).

Both slices share the same `memory_v1.json` storage file, distinguished by
`workflow_name` ("quality_harness" vs "gateway_session").

Remaining dormant: controller/execution/verification wiring, semantic memory,
packages.session/packages.controller integration.

### Git Integration

Useful later for change-aware context, memory, and measuring which files were
actually touched. Not urgent for the current latency/retrieval loop.

## Deferred

- DSPARK adapter
- DFlash adapter
- autonomous engineering loop
- controller/execution/verification/evaluation runtime
- agent orchestration
- semantic/vector search

These may become valuable, but they should not pull focus from the proven live
gateway path without a concrete measurement or product need.

## Definition Of Live

A feature should be documented as live only when all are true:

- reachable from `apps/gateway/main.py` or a gateway endpoint
- visible in session logs or response behavior
- covered by focused tests
- validated by live measurement when it affects latency or agent behavior

Otherwise it is dormant, planned, or experimental.
