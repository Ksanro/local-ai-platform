# Current Status

This file is the current runtime snapshot. It intentionally describes only
what matters for the live gateway path and calls out dormant code explicitly.

Last reviewed: 2026-10-31 (two things, one pass. Roadmap Phase A item 3 is closed: history capping now
estimates message tokens with the resolved model's `chars_per_token` (`qwen38-27b`: `3.5`) instead of the
global `4.0`, after finding that `cap_history` had accepted an `estimate` callable it never called, and it
now budgets against the routed model's `definition.context_window` - a branch verified offline, because
every live arm forced `APP_HISTORY_CAP_TOKENS=3000`. Measured on vLLM `qwen3.8-flash-next`:
`multiturn_history_cap_budget` `3/3` and style-clean on both arms, and one controlled Cline A/B where the
same transcript at the 3000-token cap forwards four of seven messages instead of seven, dropping 0 to 3.
Second, this snapshot was compacted: the RepositoryContextStage changed-file, B1-B4, C1 and pre-A3
measurement narrative moved verbatim to docs/live-gateway-runbook.md, leaving a current summary and links.
Evidence: docs/live-gateway-runbook.md, "Calibrated History-Cap Estimation (roadmap A3)".)

Previous review: 2026-10-30 (roadmap Phase B item 5 closed the change-aware ranking decision: no change - the
feature stays off by default, `RankingConfig.WEIGHT_CHANGED_FILE` stays `+25`, and the `+5` candidate is inert,
changing no outcome across 528 live requests over four dirty-file layouts. The context side is deterministic;
one probe carries the answer: `explain_changed_files_history_cap` goes 3/12 to 8-11/12 on the one-file layout
(arm replayed - same context, same `+2,694` tokens) and 3/12 to 0/12 on the eight-file one. Evidence:
docs/roadmap.md, Phase B item 5.)

Review before that: 2026-10-25 (roadmap item C1 now measures what a conversation's agent
touches, on the live path: `RepositoryContextStage` reads the Cline tool-result
envelopes already in the request, normalizes every target against the repository
root, and records count-only activity in a bounded store of transcript-prefix
states, which the chat endpoint maps through `sanitize_file_activity` and the session
logger writes as
`context.file_activity` - fifteen counters and two state tokens, `unavailable` being
the shape that says nothing was looked at rather than that nothing was touched, and
`partial` the one that says an envelope was seen and a bound refused to read it. Every
number describing what the client reported is a snapshot recomputed from the transcript
of the request being answered rather than a tally carried across turns, because a Cline
client resends its whole conversation every turn and there is nothing to accumulate;
what that replaced was a counter that read a file touched on turn one as fifteen by turn
fifteen and explained the drift with a `replay_suppressed` field, which no longer exists.
What a header attempted is likewise kept apart from what the client's own result line
said happened: `files_modified` counts files whose write was confirmed, and an attempt
that confirmed nothing is reported in `modification_attempts`,
`modifications_not_modified` and `modifications_unknown` instead, by per-file precedence
rather than by whichever envelope arrived first. Aligning its tests with the running code
settled two claims that read the wrong way round - a target that does not exist is still
measurable, containment being resolved with `realpath(strict=False)`, and a file dropped
by the per-state bound is counted as beyond-bound rather than rejected - and
exposed one real bug: a Windows drive-absolute target was treated as relative and joined
onto the root, landing outside it, and is now recognized as absolute first. The C1 path that
does this is observational, and so is all of it: the two places where widening envelope
recognition had quietly changed what the model is shown - the history cap truncating write and
replace results, and planning text selection ignoring them - are reverted to the pre-C1 set,
which is now a derived view of one registry rather than a second literal list
(`docs/live-gateway-runbook.md`, section *Conversation File Activity (roadmap C1)*, and the
corrections recorded under *Verification status*). That section also carries the live evidence:
four requests through a gateway restarted from `f74d16d` on 2026-10-26, which is a scripted
transcript rather than native Cline traffic, and a survey of this repository's own session
records for what a real client sends. C1's incremental latency was measured against a
feature-off arm on 2026-11-03 (roadmap E3): after two fixes it is 1.6 ms per request at the
median calibrated conversation and 5.6 ms at a p99 shape larger than the context window
allows; the first request to name a path still pays its `realpath`. Before that, B4
removed the mandatory per-request counterfactual cost from change-aware ranking: the
no-bonus comparison build now
sits behind `APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED`, off by
default, so an ordinary enabled request that fires the changed-file bonus builds
and sends its context once and records `changed_baseline_status=not_sampled` - a
state of its own, not a measured no-change - while every counter that needs no
counterfactual stays exact, and a diagnostic run that opts in gets precisely the
measurements B3 recorded. B3's numbers below stand as recorded, and the item that
produced them is unchanged. Earlier the same day, B3 validated change-aware
ranking live: three
A/B pairs of two gateways, run from one detached worktree of `57bd045` holding no `.env`
with one comment-only marker dirty per pair, three repeats per arm, against
`qwen3.8-flash-next` on the vLLM backend through the alias `qwen38-27b` - eviction/guard
`9/9` on both arms, which is the promotion guard surviving final serialization; gain
`3/12` off against `8/12` on, still the discriminating pair; negative control `9/9` in both
arms with a real context difference and no score difference; the observable context
fingerprint identical inside every arm across its three repeats while the answers varied (a
session record carries no ordered supporting-symbol list, so ordered determinism stays an
offline-probe and unit-test claim); no error, timeout, budget overrun or style regression in
eighteen requests, and no unexplained or material latency regression at that sample size - 9.7 s
more across the nine enabled requests, ~450 ms of each one being the counterfactual baseline
build, which B4 has since made opt-in. `RankingConfig.WEIGHT_CHANGED_FILE`
stays `+25`, the feature stays off by default, and a passing B3 does not authorize switching
it on. Before that, roadmap item B1 chose and implemented one offline safety
rule for change-aware repository-context ranking: a promoted changed-file symbol may no
longer push the best un-promoted symbol of a module the query matched out of the ranked
positions that reach the prompt with source text, and the symbol it restores is found
by scanning every symbol the promotion passed over rather than the first one.
Measured on this checkout's index at
the configured 4096-token budget, the eviction case holds `3/3` facts where it held
`0/3`, the gain case still reaches `4/4`, the negative control and the path-token gate
case are unchanged row for row, and every one of the 12 sweep flip weights is identical.
`RankingConfig.WEIGHT_CHANGED_FILE` stays `+25` and the feature stays off by default.
Before that, 2026-10-24: roadmap item A1 measured the current controlled quality
baseline: the 2026-10-24 `--compare-context` run at commit `0371d64`, `25/30` expected
facts with repository context against `4/30` without it, style `11/11` ok in both arms,
no errored and no timed-out request, taken from a detached worktree with changed-file
ranking off and recorded below and in `docs/live-gateway-runbook.md`. The `20/20` figures
below belong to the earlier 8-probe, 20-fact set and stay measurements of it; `PROBES`
has 11 entries and 30 expected facts now.)

Previous review: 2026-10-13 (`qwen38-27b` aliases the `qwen3.8-flash-next`
checkpoint on the vLLM backend at `http://100.106.236.88:18300/v1`, which is
reachable; SGLang is no longer in use - the measurements below that name it were
made on it before the endpoint moved. Its 2026-10-10 20/20 quality baseline,
context-on/context-off
comparison, and `chars_per_token=3.5` revalidation are recorded below. The
opt-in change-aware repository-context ranking added on 2026-10-09 remains off by
default. Its live A/B was run on 2026-10-12: one prompt, one
`APP_REPOSITORY_CONTEXT_MAX_TOKENS=4096` budget, three repeats, the two gateways
differing only in `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED` - feature off
`9/9`, feature on `0/9`, because the dirty module evicted
`packages/repository/index/builder.py` from the enabled arm's context. Its other half
was measured on 2026-10-13 on the pair `gains_the_changed_file` /
`explain_changed_files_history_cap`, with both gateways started inside one detached
worktree of the current commit so that `packages/pipeline/history.py` was the only
dirty indexed module either could see: feature off `3/12`, feature on `8/12` at the
same 4096-token budget, because the cap's own symbols arrived and nothing the other
arm had was lost. Its promotion is observable
counterfactually - the stage re-ranks the same request without the working-tree
bonus and reports, in count-only fields, whether that changed the context it sent;
`scripts/analyze_sessions.py` summarizes those fields from session JSONL without
reading prompts, answers, paths or symbols. On 2026-10-11 the size of that bonus
was measured offline and left at `+25`; the 2026-10-12 run priced the cost side of
turning it on and the 2026-10-13 run the benefit side, so the weight stays an open
decision - now with a number on both sides of the same ledger, and the feature still
opt-in because the flag is global and takes both effects together - see below.)

Previous review: 2026-09-19 (Git Change Snapshot v1 added as a script-reachable,
read-only repository utility, and the dormant `packages.capabilities` inventory was
recounted with repository commands the same day. The live gateway path itself was
unchanged since the 2026-09-09 review).

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
  -> vLLM backend (OpenAI-compatible, via the "openai" provider)
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

Selects ranked symbols and modules from the startup repository index and injects the composed context into the
provider-bound messages. `APP_REPOSITORY_CONTEXT_ENABLED=false` turns the stage off; `APP_REPOSITORY_CONTEXT_MAX_TOKENS`
(default `4096`) is the budget ranking, relationship expansion and final trimming enforce - the builder keeps the
primary symbol first, drops lower-ranked support, then trims oversized primary source - and
`APP_REPOSITORY_CONTEXT_INTENT_BUDGETS`, optional and empty by default, overrides it per planner intent, explicit
request metadata still winning. Delta injection (`APP_CONTEXT_DELTA_INJECTION=true`,
`APP_CONTEXT_DELTA_CACHE_SIZE=256`) suppresses symbols already sent; logs record `context.estimated_tokens` and
`context.max_tokens` so context size is measurable apart from provider prompt tokens. Test files are indexed
(`APP_REPOSITORY_EXCLUDE_TESTS=false`) for TEST-mode retrieval of the real validation files, penalized for ordinary
non-test queries, and credited by a test-target signal and descriptive filename tokens for test-seeking queries.

Change-aware ranking is opt-in: `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false`. Enabled, startup takes one
read-only Git snapshot through `packages.repository.git_changes` - no new Git command, nothing persisted - reduced to
at most `MAX_CHANGED_PATHS` (200) index module keys, and ranking adds one flat `RankingConfig.WEIGHT_CHANGED_FILE`
(`+25`) only to candidates already carrying a query-match or relationship reason: clearing `MINIMUM_CANDIDATE_SCORE`
alone is not enough, since public symbols earn name and type bonuses regardless of the query, so the bonus reorders
the same pool instead of enlarging it. The B1/B2 bound keeps a promotion from costing the best un-promoted symbol of
a query-matched module one of the `RankingConfig.PROMOTION_ANCHOR_SLOTS` (2) positions that reach the prompt with
source text; no guard runs when the bonus touched nothing. `APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS`
(default `0`) refreshes it off the request path through `packages.repository.changed_files_refresh`; a clean tree, no
Git metadata or a failed snapshot falls back.

Counterfactual comparison is a separate opt-in, `APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED=false`: it
switches on neither the bonus nor the snapshot and changes nothing sent; without it an ordinary enabled request
records `changed_baseline_status=not_sampled` and its three difference fields stay inert. Seven path-free telemetry
fields - state tokens `changed_files_signal`, `changed_baseline_status`; counts `changed_files_count`,
`changed_symbols_selected`; booleans `changed_context_differs`, `changed_symbols_promoted`,
`changed_primary_promoted` - ride the log line, the stage result and the session record's `context` block, describe
the context as finally sent, and never carry paths, module names, symbol names, file contents or Git output.

The decision stands: changed-file ranking stays off by default, `+25` is the shipped weight, the `+5` candidate
measured inert on four dirty-file layouts, and no evidence authorizes default-on. Roadmap C1 observation on this same
path is unconditional - not a ranking input, not a feature flag: `context.file_activity` carries seventeen path-free
keys, fifteen counters plus `state` (`none`: nothing the transcript held that the gateway recognizes as a supported
activity envelope; `unavailable`: the measurement could not run; `partial`: a bound excluded events, so the totals
are floors) and `correlation`, whose `tracker_miss` means incomplete supplied-context lineage, sticks for the rest of
the conversation, and makes its zero not a measurement. Limits: latency unmeasured against a feature-off arm,
unrecognized spellings not counted, and a file a model changes through a shell command not attributed.

Since 2026-11-02 C1 also reads Cline 4.x native tool calls (`read_files`, `editor`, `search_codebase`, `run_commands`
as assistant `tool_calls` plus `role: "tool"` results), not only the older text envelopes. A native-Cline probe found
that the gateway had been dropping a client's `tools` field and that the serializer rejected `role: "tool"`
messages, so a native tool-calling client could not use tools through the gateway at all; both are fixed (`8695063`).
Roadmap E2 then validated C1 on a real Cline 4.1.26 task through an isolated gateway (2026-11-02): 12 requests, 12
records, and a final snapshot matching Cline's own task record call for call.

`scripts/analyze_sessions.py` now summarizes those records offline in a count-only FILE ACTIVITY section that reads
only the seventeen keys and never sums a counter across records, because every one of them is a snapshot of the
transcript its request carried. Do not read a `context.file_activity` `state=none` as "feature off": it means the
gateway looked at a transcript and found no recognized activity envelope, which is a measured zero, while
`changed_files_signal=off` is the token that means the changed-file ranking feature was off and nothing was looked at.

Evidence: `docs/roadmap.md` Phase B items 1-5; in `docs/live-gateway-runbook.md`, *Intent Context Budgets*,
*Intent budget measurements*, *Token-estimate investigation, 2026-08-10*, *Context-selection determinism,
2026-08-22*, *Change-Aware Ranking (Optional)*, *The Phase B1 promotion guard*, *Replicated changed-file A/B,
2026-10-12*, *Isolated-worktree benefit A/B, 2026-10-13*, *Isolated-worktree promotion-guard A/B, 2026-10-25
(roadmap B3)*, *Conversation File Activity (roadmap C1)*.

### History Capping

When `APP_HISTORY_CAP_ENABLED=true`, `PipelineEngine` caps non-system
conversation history to `APP_HISTORY_CAP_TOKENS`, or derives a budget from
the resolved model when the explicit value is `0`. Since roadmap A3 it estimates
what that text is worth with the resolved model's `chars_per_token` rather than
the global `4.0` - the same calibration repository context has used since
2026-09-09 - so `qwen38-27b`'s `3.5` decides which messages fit the budget and
how `history.tokens_after` is measured, while a model that overrides nothing is
capped exactly as before. The derived budget reads that model's real window,
`ResolvedModel.definition.context_window`, less the generation, repository-context
and safety reserves; `8192` stands only when neither the definition nor the resolved
object names a usable window, where before it stood for every request because the
read looked for `context_window` on the resolved object, which that type does not
have.

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
| qwen38-27b | openai | http://100.106.236.88:18300/v1 | qwen3.8-flash-next | 262144 | vLLM server (`owned_by: vllm`, `max_model_len: 400000` on `/v1/models`, checked 2026-10-12); gateway alias retained for client compatibility |

The endpoint answers a direct `GET /v1/models` from this machine, so a connection
failure on a live probe is the local gateway on `:8001` not running, not the
backend being down. The configured `context_window` (262144) stays below the
server's advertised `max_model_len` (400000); nothing was changed for this
review, and the router does not read the server value.

SGLang routing was configured and live-smoked on 2026-08-20. The gateway
exposed `qwen38-27b` and
`scripts/quality_harness.py --delta-context --json --model qwen38-27b
--max-tokens 8192 --session-log-path logs\implement_budget_A_4096_20260801.jsonl`
returned `ok: true`. Primer context selected
`packages/pipeline/history.cap_history` with 1843 estimated context tokens;
follow-up context selected `packages/pipeline/history._build_cap_groups` with
1844 estimated context tokens and `symbols_suppressed=1`. Both answers scored
all expected facts with no style violations.

The current controlled quality baseline is the 2026-10-24 `--compare-context` run
(roadmap item A1): commit `0371d64`, code and repository index from the detached
worktree `C:\Users\ovidi\lap-ab-a1-0371d64`, one gateway on `127.0.0.1:8011` started
from the environment `scripts/ab_launcher.py` wrote
(`APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false`, `REQUEST_TIMEOUT=300`, harness
`--timeout 345`, `APP_REPOSITORY_CONTEXT_MAX_TOKENS=4096` with
`SEARCH/TEST/DEBUG=2048,REFACTOR/IMPLEMENT/EXPLAIN=4096`, `APP_HISTORY_CAP_ENABLED=true`
and `APP_HISTORY_CAP_TOKENS=3000`, `chars_per_token=3.5`), against the vLLM backend
`http://100.106.236.88:18300/v1`, whose `/v1/models` serves one checkpoint,
`qwen3.8-flash-next` (`owned_by: vllm`, `max_model_len: 400000`), through the alias
`qwen38-27b`. Over the complete 11-probe / 30-fact set it scored `25/30` with repository
context versus `4/30` without it, style `11/11` ok in both arms, 33109 prompt tokens in
129.6 seconds against 2221 in 532.1 seconds - `+21` facts for `+30888` prompt tokens on
one per-request flag. Nothing errored and nothing timed out. The context arm is missing
five facts (`select_last_task_text`, `packages/context/builder.py`, and
`max_current_tool_result_tokens`, `_looks_like_cline_tool_result_message` and
`[... truncated by gateway history cap ...]` on `explain_changed_files_history_cap`),
and one no-context request spent all 8192 completion tokens on hidden reasoning and
returned an empty answer in 193.8 seconds, which is a measured model behaviour at the
documented ceiling rather than a failed request. Artifact:
`logs\quality_compare_qwen38_vllm_20261024.json`; persisted as engineering-memory session
`quality_harness_compare-20261024T173757728411-2a4297e1`. The exact commands, the checks
run before it, and the per-probe table are in `docs/live-gateway-runbook.md`, "Current
controlled baseline, 2026-10-24 (roadmap A1)".

The previous single-run baseline was completed on 2026-10-10, when this alias still
resolved to the SGLang deployment (`scripts/quality_harness.py --json --model
qwen38-27b --max-tokens 8192 --reasoning-model qwen38-27b`): clean TOTAL 20/20 expected
facts, style 8/8 ok, 25093 prompt tokens, 99.2 seconds, saved at
`logs\quality_baseline_qwen3_8_flash_next_20261010.json` and persisted as
engineering-memory session `quality_harness-20261009T214258101237-9d6f90f9`.
That was the 8-probe, 20-fact set, and so was the same-backend context comparison
that scored 20/20 with context versus 3/20 without it; context-on completed in 93.1
seconds versus 454.1 seconds without context because the no-context arm spent far more
completion tokens guessing. The gateway alias `qwen38-27b` has routed to
`qwen3.8-flash-next` via vLLM, serving the same checkpoint, since that move.

The previous `qwen3.8-27b` baseline remains historical: on 2026-08-22 it
scored 20/20 with style 8/8, 28013 prompt tokens, and 144.6 seconds, persisted
as session `quality_harness-20260821T214629502370-6d519523`.

An exploratory changed-file-ranking A/B was also run on 2026-10-10 against
`qwen3.8-flash-next`, using a temporary dirty marker in
`apps/gateway/core/config.py` and otherwise identical gateway processes. The
off arm scored 15/20 and the on arm 19/20, but the difference came from
`explain_live_path` model variance (the off arm exhausted all 8192 completion
tokens), not the changed module. `multiturn_config_systems`, the probe that
actually retrieved the dirty module, scored 2/2 in both arms with the same
4172 prompt tokens and the same primary symbol. This is not evidence that the
promotion improves quality; the feature remains off by default. Summary:
`logs\quality_changed_files_ab_qwen3_8_flash_next_20261010_summary.json`.

Previous measured backends included `qwen36` on vLLM at
`http://100.106.236.88:8000/v1` and `qwen27` on llama.cpp at
`http://100.106.236.88:8080/v1`; keep older measurements labeled with their
actual model/backend.

Historical smoke: `quality_harness.py --probe multiturn_history_cap_budget
--json --max-tokens 900 --model qwen27` scored 3/3 routed through
OpenAIProvider to the llama.cpp backend.

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
- read-only `GET /debug/runtime-context` introspection endpoint: live and
  read-only, it returns settings-driven context flags, `routing_mode`,
  `models[]` (whitelisted, no `api_key`), `repository_context_intent_budget_map`,
  a persisted `quality_baseline`, and a persisted `gateway_session_summary`
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
- opt-in change-aware repository-context ranking (symbols the query already
  matched get one bounded `+25` bonus when their file is locally modified; the
  weight was retained at `+25` and the decision closed on 2026-10-30 by
  roadmap Phase B item 5; off by default, `apps/gateway/main.py` ->
  `RepositoryContextStage` -> `ContextBuilder` -> `RankingEngine`)
- history capping
- session JSONL logging
- session log analyzer, including a count-only FILE ACTIVITY section that
  summarizes roadmap C1's `context.file_activity` records as per-record
  transcript snapshots without summing any counter across records
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
- qwen36 live `scripts/quality_harness.py --compare-context` run (previous
  backend) scored `20/20` with repository context versus `2/20` without
  context across the full 8-probe set, including the multi-turn probes
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
- `packages.repository.git_changes` (`capture_change_snapshot`,
  `parse_porcelain_v2`, `GitChangeStatus`, `GitFileChange`, `GitChangeSnapshot`,
  `GitUnsafeCommandError`) via `scripts/git_change_snapshot.py` — Git Change
  Snapshot v1: a script-reachable, strictly read-only Git integration that
  reports repository-root, branch, HEAD, upstream, ahead/behind, staged,
  unstaged, untracked, renamed/copied (old and new path), deleted, and
  conflicted paths plus a clean/dirty flag. Its subprocess boundary enforces an
  exact two-vector allowlist
  (`git rev-parse --show-toplevel` and `git status --porcelain=v2 -z --branch`
  with `--no-optional-locks` and `--untracked-files=all`) and raises
  `GitUnsafeCommandError` for anything else — including prefix, suffix and
  reordered variants — before a process starts. It parses NUL-delimited porcelain
  v2 only, never stages, commits, resets, checks out, cleans, fetches, or pushes,
  and orders every collection deterministically. It stays out of the request
  path itself - no endpoint and no memory persistence - but
  `packages.repository.changed_files` now feeds its snapshot into
  repository-context ranking when
  `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=true` (off by default).

## What Exists But Is Dormant

These packages are not part of the live gateway path unless explicitly wired
later:

- `packages.capabilities` — the Capability Framework v1 prototype is complete and
  covered by focused tests, but it is not reachable from the live gateway: no
  `apps/gateway` or live `packages/pipeline` module imports it, no capability is
  registered by default, and no provider execution happens through it. It
  contains nine capabilities (Explain, Debug, Refactor, Implement Feature,
  Generate Tests, Review, Architecture Review, Bug Investigation, and
  Pull Request Review — the last one being a different, non-`Capability`-ABC
  orchestration shape that only builds a `TaskRequest`). The roster, the exact
  dormant boundaries and the activation prerequisites live in
  `docs/dormant-code-backlog.md`; the design itself is in `docs/capabilities.md`
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

Approximate dormant-package footprint. The `packages.capabilities` row was
recounted with repository commands on 2026-09-19; the other rows still reflect
the 2026-08-01 pass and are estimates, not measured inventory:

| Area | Package files | Test files | Approx. lines | Backlog posture |
|---|---:|---:|---:|---|
| `packages.evaluation` | 6 | 6 | 1.6k | `quality_harness_report.py` slice activated; `evaluator.py`/`registry.py` still dormant. |
| `packages.engineering_memory` | 5 | 5 | 2.8k | `quality_harness_records.py` and `session_log_records.py` slices activated; controller wiring still dormant. |
| `packages.observability` | 8 | 10 | 6.0k | `quality_history.py` and `session_log_history.py` slices activated; telemetry/tracing stack still dormant. |
| `packages.capabilities` | 15 | 13 | 4.5k (package only) | Capability Framework v1 prototype complete: 8 `Capability` subclasses plus the non-ABC `PullRequestReviewCapability`; overlaps current planning/context path, not reachable from the live gateway. |
| `packages.tasks` / `workflows` | 27 | 17 | 4.8k | Keep dormant until an execution loop is product-proven. |
| Controller/execution/verification stack | 29 | 28 | 7.0k | Large future stack; not on the gateway hot path. |
| Modification/patches/session/bootstrap/autonomous/advisors/architecture/benchmark | 49 | 46 | 12.5k | Inventory before wiring; use only with a concrete measured need. |

The `packages.capabilities` figures are the measured ones: 15 Python files and
4,504 lines of package code, 13 `test_*.py` modules plus a shared
`assembly_probes.py` helper and `tests/capabilities/__init__.py` (15 files,
14,765 lines of test code), and 691 focused tests passing
(`.\uv.exe run python -m pytest tests\capabilities -q`). "Approx. lines" counts
package code only for every row.

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
dormant packages with known failures and pre-existing lint debt. The local
pre-commit hook enforces the live-path gate (`scripts/precommit_test_gate.sh`);
the known full-suite failure baseline (43 on Python 3.13) is an opt-in `--full`
check - see `TESTING.md` "Pre-commit hook".

Recommended live-path checks:

```powershell
.\uv.exe run python -m pytest tests\pipeline tests\gateway tests\providers tests\planning tests\context tests\repository -q
.\uv.exe run python -m ruff check apps\gateway packages\pipeline packages\providers packages\planning packages\context packages\repository scripts
.\uv.exe run python -m mypy packages\providers packages\pipeline apps\gateway
.\uv.exe run python scripts\git_change_snapshot.py --json .
.\uv.exe run python scripts\quality_harness.py
.\uv.exe run python scripts\quality_harness.py --compare-context
.\uv.exe run python scripts\quality_harness.py --delta-context --session-log-path logs\sessions.jsonl
.\uv.exe run python scripts\quality_harness.py --json | .\uv.exe run python scripts\evaluate_quality_harness.py -
```

The mypy gate passes with the dormant `packages/pipeline/stages/workflow_stage.py`
module excluded via a pyproject override; CI's mypy step uses the same live-path
scope.

The count-only changed-file promotion counters ride the same gate:
`tests/pipeline/test_changed_file_promotion_counts.py`,
`tests/gateway/test_changed_file_session_metadata.py`,
`tests/scripts/test_analyze_sessions_promotion.py`, plus the existing
`tests/pipeline/test_repository_context_changed_files.py`,
`tests/pipeline/test_repository_context_stage.py` and
`tests/context/test_changed_file_ranking.py` - 182 tests with roadmap B4 and its
review fix in the tree, 139 when the count was first recorded. Measured on
2026-10-10 (Python 3.13.14) with this work in the tree,
`bash scripts/precommit_test_gate.sh --full` ran the whole suite at the documented
dormant baseline: `43 failed, 4645 passed, 3 skipped`, gate output
`full suite OK (43 failures, baseline 43)` - the 43 being the 26 in
`tests/autonomous`, 12 in `tests/observability`, 4 in
`tests/integration/test_engineering_flow` and 1 in `tests/modification` that
CLAUDE.md records as expected, none of them in the live path. The live-path gate
alone, `bash scripts/precommit_test_gate.sh`, ran `2043 passed` with 0 failures.
On this machine the gate is invoked through Git's bundled bash
(`& 'C:\Program Files\Git\bin\bash.exe' scripts/precommit_test_gate.sh`), because
a bare `bash` resolves to the WSL stub, which has no distribution installed.

### Dependency Reproducibility

The live-path gates install from the committed `uv.lock`. CI pins uv 0.11.28 - the uv that
generated that lock - and runs `uv sync --locked`, so a `pyproject.toml` that has drifted
from the lock fails the job instead of silently re-resolving. Until 2026-10-24 three things
kept a clean worktree from reproducing this checkout's environment: `pyproject.toml`
declared `httpx2`, a different distribution that provides no `httpx` module, while
`packages/providers/openai.py` and `packages/providers/vllm.py` import `httpx`; `uv.lock`
was gitignored, so a fresh worktree had nothing pinned to install and `uv run` re-resolved
against the live index; and the dev group omitted `pytest-asyncio`, which the async
provider tests need, so it passed only because this checkout's `.venv` happened to carry an
installed copy. All three are fixed.
`tests/gateway/test_dependency_reproducibility.py` guards them without touching the network:
`httpx` declared and `httpx2` not, the lock resolving `httpx` with no `httpx2`/`httpcore2`,
`uv.lock` absent from the ignore rules, and `packages.providers.openai`,
`packages.providers.vllm` and `apps.gateway.main` importing from the working tree. The
interpreter itself is still unpinned - there is no `.python-version` file, so a fresh
environment uses whatever Python uv discovers, against `requires-python = ">=3.12"`.

## Current Open Issues

- Repository context can dominate prompt size; history capping alone is not the
  full latency lever. Configurable repository-context budget enforcement and
  targeted retrieval promotions now exist. The current measured baseline is the
  2026-10-24 controlled `--compare-context` run on the vLLM `qwen3.8-flash-next`
  backend at commit `0371d64`: `25/30` expected facts with context versus `4/30`
  without it, style `11/11` in both arms, 33109 prompt tokens against 2221, on the
  full 11-probe set. Historical measurements on the earlier 8-probe set - the
  2026-10-10 qwen38-27b/SGLang full baseline (the backend that alias pointed at
  before the move to vLLM) clean at `20/20` with style `8/8`, and the qwen36
  `--compare-context` run at `20/20` with context versus `2/20` without - remain
  valid for what they measured and are not comparable to it as written.
  `SEARCH`/`TEST`/`DEBUG`/`EXPLAIN` have measured budget overrides; `REFACTOR`
  was measured and reverted to the shared default after a replicated
  regression - see `docs/roadmap.md` section 3 and the runbook's "Intent Context Budgets"
  section for the measured numbers.
- The model often includes reasoning/preamble despite terse system prompts; the
  quality harness now records deterministic style violations separately from
  required-fact score.
- Repository-context token estimates now use a per-model calibrated
  characters-per-token ratio (`ModelDefinition.chars_per_token`, default
  `4.0`; qwen38-27b `3.5`), live-validated 2026-09-09: measured context-cost
  overages went 5/8 at 4.0 -> 0/8 at 3.5 with no quality or style regression.
  History capping joined it on 2026-10-31 (roadmap A3), measured on the vLLM
  `qwen3.8-flash-next` deployment: one scripted Cline transcript under
  `APP_HISTORY_CAP_TOKENS=3000` is forwarded whole at `4.0` and cut from seven
  messages to four at `3.5`, identically across three repeats, with no quality
  or style regression and no new error - `docs/live-gateway-runbook.md`. True
  tokenizer integration is out of scope/deferred.
