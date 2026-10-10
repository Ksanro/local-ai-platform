# Roadmap

This roadmap is based on the current live gateway, not on dormant scaffolding.

Last reviewed: 2026-10-09 (the read-only Git change snapshot is now wired into
the live gateway as an opt-in, off-by-default change-aware ranking signal; the
dormant `packages.capabilities` inventory note and the live-gateway priorities
from the 2026-09-09 pass are unchanged).

Previous review: 2026-09-19 (records the completed dormant Capability Framework v1
prototype and the first read-only, script-reachable Git Integration slice; the
live-gateway priorities were unchanged since the 2026-09-09 pass).

## Done Enough For Now

- OpenAI-compatible gateway
- vLLM provider
- OpenAI-compatible provider (`packages/providers/openai.py`, registered as "openai")
- provider registry and factory
- model registry
- True Multi-Provider (live):
  - model "qwen38-27b" -> provider "openai" -> http://100.106.236.88:30000/v1
    (SGLang backend_model "qwen3.8-27b", context_window 262144)
  - Previous measured backends: model "qwen36" via vLLM
    (http://100.106.236.88:8000/v1) and model "qwen27" via llama.cpp
    (http://100.106.236.88:8080/v1); keep older measurements labeled with their
    model/backend.
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
- measured Cline A/B flow proving capping can reduce latency
- explicit per-request context intent override
- configurable custom context intent rules
- live quality harness with context-on/context-off comparison
- per-model chars-per-token calibration for repository-context accounting
  (default 4.0; qwen38-27b 3.5, live-validated 2026-09-09: 5/8 -> 0/8 measured
  context-cost overages, no quality/style regression)

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

Completed prototype work, deliberately not activated (2026-09-19):
`packages.capabilities` - the Capability Framework v1 is finished as dormant
context-assembly code. Nine capabilities exist (Explain, Debug, Refactor,
Implement Feature, Generate Tests, Review, Architecture Review, Bug
Investigation, and the non-`Capability`-ABC Pull Request Review), covered by 691
passing focused tests in `tests/capabilities`. None of them is registered by
default, reachable from the gateway path, or performs provider execution, so this
closes the framework's own inventory item only. It does not promote controller,
tasks, workflows, execution, verification, autonomous operation, or gateway
capability routing, and it does not displace the measured latency/retrieval work
in sections 2 and 3.

### 2. Quality Harness Expansion

The fixed probe set proves repository context adds answer-quality signal
(`20/20` with context versus `2/20` without context in the qwen36
`--compare-context` run, including the 2 multi-turn probes). The current
qwen38-27b/SGLang full baseline is clean at `20/20` with style `8/8`.

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
  anaphoric prompts and promotes live history-cap/config-system symbols; the
  qwen36 live comparison scored `20/20` with context versus `2/20` without

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
- 2026-08-22: confirmed context-selection determinism on qwen38-27b/SGLang +
  `EXPLAIN:4096` - 3 EXPLAIN probes x 3 in-process repeats and a post-restart
  re-run reproduced identical prompt_tokens / estimated_tokens / primary
  symbols; remaining run-to-run variance is model-side sampling, so no code
  change is needed (numbers in `docs/STATUS.md`)

Next:

- `multiturn_history_cap_budget` was resolved in commit 6fe9283
  ("Clarify history cap budget probe facts"): two root causes —
  `APP_HISTORY_CAP_TOKENS` was missing from `_apply_history_cap`'s docstring,
  and the probe prompt asked for the Python argument name
  (`max_tokens_override`) instead of the environment variable. Historical live
  check (qwen27, --max-tokens 900): 8/8 replicate runs scored 3/3 with zero
  misses.
- per-model chars-per-token calibration is implemented and live-validated
  (2026-09-09, qwen38-27b at 3.5); a true tokenizer-aware estimate remains
  deferred unless future measurements justify it (see "Tokenizer Registry"
  under "Next After That")

### 4. CI Realignment - DONE

CI now follows the documented live-path baseline instead of treating every
dormant package as production runtime:

- tests: `tests/pipeline`, `tests/gateway`, `tests/providers`,
  `tests/planning`, `tests/context`, `tests/repository`
- lint: `apps/gateway`, live `packages/*` slices, and `scripts`
- type checks: `packages/providers`, `packages/pipeline`, and `apps/gateway`

## Next After That

### Tokenizer Registry - deferred; calibrated ratio in place

Per-model token accounting is implemented as a calibrated characters-per-token
ratio: `ModelDefinition.chars_per_token` (default `4.0`) drives
repository-context budget estimation, validated live on qwen38-27b/SGLang at
`3.5` on 2026-09-09: measured context-cost overages went 5/8 at 4.0 -> 0/8 at
3.5, with no quality/style regression (run files
`logs\quality_compare_qwen38_token_estimate_20260909.json` and
`logs\quality_compare_qwen38_chars_per_token_3_5_20260909.json`). History
capping still uses the platform default estimate.

`ModelDefinition.tokenizer` exists as metadata only; the true tokenizer
registry stays deferred unless future measurements justify it.

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

### Git Integration - slices 1 and 2 DONE (slice 2 is live but opt-in)

`packages.repository.git_changes` (`capture_change_snapshot`,
`parse_porcelain_v2`, `GitChangeStatus`, `GitFileChange`, `GitChangeSnapshot`)
plus `scripts/git_change_snapshot.py` now capture a deterministic snapshot of a
working tree: repository root, branch, HEAD, upstream and ahead/behind when
configured, staged, unstaged, untracked, renamed/copied (old and new path),
deleted, and conflicted paths, and a clean/dirty flag. `run_git_command` enforces
an exact allowlist and will only ever start these two read-only vectors:

```text
git rev-parse --show-toplevel
git --no-optional-locks status --porcelain=v2 -z --branch --untracked-files=all
```

Any other argument vector raises `GitUnsafeCommandError` before a process is
created, so mutating commands - and prefix, suffix or reordered variants of the
allowed ones - cannot reach Git through this module. Because parsing is limited to
NUL-delimited porcelain v2, taking a snapshot never stages, commits, resets,
checks out, cleans, fetches, or pushes, and never rewrites `.git`.

Still deliberately not done: engineering-memory persistence of snapshots, diffs
and patch generation, and the GitHub API.

Completed next slice (2026-10-09, opt-in and off by default): change-aware
repository-context ranking. `packages.repository.changed_files` derives a
bounded set of index module keys from a snapshot (rename and copy sources
included, deletions excluded), `apps/gateway/main.py` captures it once during
startup and keeps it warm through `packages.repository.changed_files_refresh`,
and `RankingEngine` adds one flat `+25` bonus
(`RankingConfig.WEIGHT_CHANGED_FILE`) to symbols in those modules only when they
already carry a query-match or relationship reason. No new Git command, no new
pipeline stage, no new persisted artifact.
Enable with `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=true`;
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS` (default `0`) is the only
way to let the snapshot refresh after startup, and the refresh never runs in a
request path.

Exploratory live A/B on 2026-10-10 used a temporary dirty marker in
`apps/gateway/core/config.py` against `qwen3.8-flash-next`. The off/on totals
were 15/20 and 19/20, but the difference was caused by unrelated model-side
variance in `explain_live_path`; the probe that retrieved the dirty module
(`multiturn_config_systems`) scored 2/2 in both arms with identical prompt
tokens and primary symbol. The run therefore did not measure a quality benefit.
The feature stays off by default; a future experiment needs a probe whose
expected retrieval order is sensitive to the changed-module bonus, plus
replication to separate that effect from sampling noise. Measuring which files
an agent actually touched also remains open.

## Deferred

- DSPARK adapter
- DFlash adapter
- autonomous engineering loop
- controller/execution/verification/evaluation runtime
- agent orchestration
- gateway capability routing (the dormant `packages.capabilities` prototype is
  complete; wiring a capability into the live path stays deferred until the
  activation prerequisites in `docs/dormant-code-backlog.md` are met)
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
