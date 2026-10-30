# Roadmap

This roadmap is based on the current live gateway, not on dormant scaffolding.

Last reviewed: 2026-10-24 (the next measured development sequence is recorded
below. Dormant code stays intact and isolated; no deletion, archival move, or
incidental activation is part of the current plan).

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
  - model "qwen38-27b" -> provider "openai" -> http://100.106.236.88:18300/v1
    (vLLM server, backend_model "qwen3.8-flash-next", context_window 262144;
    "openai" is the OpenAI-compatible client used to talk to it, checked against
    /v1/models on 2026-10-12)
  - Previous measured backends: the same alias on SGLang
    (http://100.106.236.88:30000/v1, backend_model "qwen3.8-27b"), model "qwen36"
    via vLLM
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

### Agreed Development Sequence (2026-10-24)

The next work continues the existing pattern: activate or change one small,
reachable slice at a time, measure behavior, run the focused live-path gates,
and update the relevant documentation in the same session. Historical
measurements remain labeled with their original model, backend, commit, probe
set, and configuration; a new baseline supplements them rather than replacing
them.

#### Phase A: Repair And Refresh The Measurement Base

1. **A2 - deterministic A/B launcher configuration - DONE (2026-10-24).**
   `scripts/ab_launcher.py` now builds, validates, and renders the two
   isolated-worktree arms without starting a process or contacting the backend.
   It requires an explicit symmetric measurement configuration, validates the
   provider/harness timeout margin, refuses a non-detached or incomplete tree,
   keeps credentials out of files and output, and renders paste-ready gateway
   and harness blocks. `tests/scripts/test_ab_launcher.py` pins the contract;
   the runbook and `TESTING.md` document the operator workflow.
2. **A1 - current full baseline - DONE (2026-10-24).** One controlled
   `scripts/quality_harness.py --compare-context --json` run over the complete
   11-probe / 30-fact set, from a detached worktree of `0371d64`
   (`C:\Users\ovidi\lap-ab-a1-0371d64`, holding no `.env`) with the configuration
   `scripts/ab_launcher.py` wrote and validated, one feature-off gateway on
   `127.0.0.1:8011` (`APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false`,
   `REQUEST_TIMEOUT=300`, harness `--timeout 345`, the rest of the shared block as the
   launcher renders it), against `qwen3.8-flash-next` on the vLLM backend at
   `http://100.106.236.88:18300/v1` through the alias `qwen38-27b`: `25/30` expected
   facts with repository context against `4/30` without it, style `11/11` ok in both
   arms, 33109 prompt tokens in 129.6 seconds versus 2221 in 532.1 seconds, no errored
   and no timed-out request, and one no-context answer truncated at the 8192-token
   completion ceiling. Commit, backend/checkpoint, configuration, flags and worktree
   state are recorded with the result; artifact
   `logs\quality_compare_qwen38_vllm_20261024.json`, persisted as session
   `quality_harness_compare-20261024T173757728411-2a4297e1`, commands and per-probe
   numbers in `docs/live-gateway-runbook.md`. The older 8-probe `20/20` results stand as
   historical measurements of their own set and were not rewritten.
3. **A3 - calibrated history-cap estimation.** After the ranking decision below,
   make history capping use the resolved model's `chars_per_token`, preserving
   the default behavior for models that do not override it. Re-measure
   `multiturn_history_cap_budget` and one controlled Cline A/B because this
   changes what is forwarded to the provider.

#### Phase B: Settle Change-Aware Ranking

1. **B1 - choose one safety rule offline - DONE (2026-10-25).** Chosen rule: a
   promoted changed-file symbol may not push the best candidate that earned its
   place without the bonus out of the ranked positions the context actually
   renders with source text. `RankingEngine.rank` restores that symbol to the
   last such position - `RankingConfig.PROMOTION_ANCHOR_SLOTS`, currently two:
   the primary body and the shared supporting preview `ContextBuilder` spends -
   and it does so only when the symbol's module matched the query, it held one of
   those positions with the bonus off, and the bonus is what moved it out. The
   candidate is found by scanning every symbol the promotion passed over, not by
   looking only at the first one, because the first can still hold its own slot
   while a later one has lost the only slot it had. A dirty file may still win the
   primary, which is what the signal is for. The first cut of the guard looked only
   at the first symbol the bonus did not touch, and review found the shape that
   left unprotected: a query-matching symbol pushed out of the prefix from behind
   an untouched one that kept its own slot. The scan is what closes it, pinned by
   `test_promotion_guard_scans_past_the_candidate_it_did_not_promote` in
   `tests/context/test_changed_file_ranking.py`.
   Measured offline on this checkout's index at the configured 4096 tokens: the
   eviction case now holds `3/3` facts with `facts_lost` empty (it held `0/3`, all
   three lost, before the rule) while the gain case still reaches `4/4` and
   reports `MOVE`, the negative control and the path-token gate case are unchanged
   row for row, and the smallest flip weight of every one of the 12 fixed sweep
   queries is identical. Rejected: a cap on how much of the selected context
   promotion may occupy - at every cap tried the eviction case stayed at `0/3`,
   and the looser forms also changed the primary of the documented path-token
   case - and plain retention without a content slot, which measured `1/3`: a
   symbol that survives the reorder past the rendered prefix is still in the
   context, still named with its signature and docstring, and without the
   source body its facts are read from - exactly the failure this item warned
   about. `RankingConfig.WEIGHT_CHANGED_FILE` stays `+25` and the feature stays
   off by default; no counter or field changed meaning, and `changed_symbols_*`
   and `changed_context_differs` read the same values they read before. One
   consequence for B3: the eviction pair is no longer expected to separate the
   two arms by what is missing from the enabled context - offline it now measures
   that the guard holds - so the live eviction run becomes a check that the rule
   survives serialization, and `gains_the_changed_file` /
   `explain_changed_files_history_cap` stays the discriminating pair.
2. **B2 - pin the selected invariant - DONE (2026-10-25).** The edges B1 left
   open are pinned in `tests/context/test_changed_file_ranking.py` and
   `tests/pipeline/test_changed_file_promotion_counts.py`. More than one untouched
   query-matching module competing for the same slot: the `MULTI_*` fixtures rank
   two anchors ahead of the dirty file, the second is still selected and must keep
   its position, and the restore protects one symbol rather than one module. The
   guard against the builder's own promotions: `ContextBuilder.build` now calls
   `RankingEngine.restore_promotion_anchor` after its query-specific hoists,
   because a hoist shifts everything behind it down by one and can move the symbol
   the guard restored back outside the prefix that source text is rendered from -
   `test_builder_promotion_that_names_a_file_does_not_undo_the_guard` measures the
   order, `test_builder_keeps_the_restored_symbol_inside_the_source_preview_budget`
   measures the text that reaches the prompt. The counterfactual baseline the stage
   builds without `changed_modules` is untouched by construction: the second
   application is a no-op whenever the ranking pass gave the bonus to nothing,
   which `test_promotion_guard_is_inert_when_the_slot_is_already_restored` pins for
   an already-restored order and for a clean tree. And
   `test_the_guard_decides_which_symbols_the_budget_admits` runs a whole stage
   request twice at a budget that holds two symbols, where the guard is what
   decides what the working tree brought in - one symbol promoted with it, two
   without. B3 ran that live validation on 2026-10-25, and the registered
   `evicts_the_asked_about_file` pair held against a model - `9/9` on both arms, the
   enabled arm's context differing from its own no-bonus baseline on every record.
3. **B3 - validate live - DONE (2026-10-25).** The three pairs ran with three repeats
   per arm against `qwen3.8-flash-next` on the vLLM backend at
   `http://100.106.236.88:18300/v1` through the alias `qwen38-27b`, from one detached
   worktree of `57bd045` (`C:\Users\ovidi\lap-ab-b3-57bd045`, holding no `.env`, its own
   `uv sync --locked` environment at CPython 3.13.14), with the two gateways of each pair
   differing only in `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED` and
   `APP_SESSION_LOG_PATH` as `scripts/ab_launcher.py` proved from its own validation and
   `show --diff`. Every gate passed. Eviction/guard: `9/9` on both arms, the disabled arm
   holding its documented direction and the enabled arm carrying all three
   `packages/repository/index/builder.py` facts on records that read
   `changed_files_signal=ok`, `changed_files_count=1`,
   `changed_symbols_promoted=1`, `changed_primary_promoted=true` and
   `changed_context_differs=true` - so the guard survives the builder's promotions, the
   serializer and a live request, which is what this item existed to find out. Gain:
   `3/12` off against `8/12` on, still the discriminating pair, with the one fact neither
   arm's answers quoted being the truncation marker the model paraphrases although the
   enabled context carries it. Control: `3/3` on every repeat of both arms, with the
   enabled arm's retrieval genuinely different and its score genuinely not. The observable
   context fingerprint was identical across the three repeats inside all six arms (primary
   symbol, selected-symbol count, estimated tokens, prompt tokens and the seven `changed_*`
   counters, to the unit) while answer text varied, which is the split the item asked for; a
   session record carries no ordered supporting-symbol list, so ordered determinism stays an
   offline-probe and unit-test claim rather than a live one. No errored or timed-out request,
   no budget overrun (highest estimated context 4091 of 4096), style clean in all eighteen
   answers, +228 prompt tokens per enabled request on average, and no unexplained or material
   latency regression at this sample size - +1.1 s per enabled request, 9.7 s over the nine, of
   which ~450 ms a request is the counterfactual baseline build that this run left
   untouched and B4 has since made opt-in. `RankingConfig.WEIGHT_CHANGED_FILE` stays
   `+25`, the feature stays off by default,
   and this passing run does not authorize switching it on: it prices and validates the
   rule. Full configuration, per-repeat tables, determinism, promotion counters, token and
   latency comparison and the recorded confounds are in `docs/live-gateway-runbook.md`,
   "Isolated-worktree promotion-guard A/B, 2026-10-25 (roadmap B3)"; artifacts under the
   Git-ignored `logs\b3\20261025\` and `build\b3\20261025\`. One thing the run recorded
   that is not a B3 item, and not A3 either: the offline probe's symbol tallies run higher
   than the live arms' because `_stage_arm` builds a bare `PipelineContext` with no resolved
   model, so the stage falls back to `CHARS_PER_TOKEN=4.0` where the live path uses the
   alias's calibrated `3.5`. That is an offline-probe calibration gap in its own right, the
   same in both arms so it moves no verdict. Item A3 stays as written and stays open - it is
   about history capping using the resolved model's `chars_per_token`, which this
   run neither advances nor measures.
4. **B4 - remove mandatory counterfactual cost - DONE (2026-10-25).** The cheap
   direct counters stay on every request and the second context build is now a
   separate opt-in,
   `APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED`, default off, wired
   through `Settings`, the gateway lifespan and `RepositoryContextStage`. An
   ordinary enabled request that fires the bonus builds and sends its context
   once and records `changed_baseline_status="not_sampled"` with
   `changed_baseline_ms=0` - a state of its own, never `built`, `none`,
   `skipped_no_bonus` or `failed`, so it cannot be read as a measured no-change.
   What needs no counterfactual is still measured there: the signal state, the
   changed-file count and the sent symbols that carry the bonus. What needs one -
   `changed_context_differs`, `changed_primary_promoted`,
   `changed_symbols_promoted` - keeps its name, type and place in the record and
   is inert, the status being the only thing that says so. The setting never
   changes what is sent: `test_the_comparison_setting_never_changes_what_is_sent`
   serializes one change-aware request both ways and compares the provider
   messages, and `test_an_enabled_request_without_the_opt_in_builds_once` counts
   the builds. Turning the comparison on alone turns on neither ranking nor Git
   capture. Opting in reproduces the old behavior exactly, `built`,
   `skipped_no_bonus` and `failed` included, so B3's recorded measurements stand
   as recorded. `scripts/ab_launcher.py` pins the setting to `true` in the shared
   block of every experiment it renders and refuses a changed-file A/B that
   declines it, and the offline probes in `scripts/quality_harness.py` opt in the
   same way, so the promotion fields those workflows read stay measurable;
   `scripts/analyze_sessions.py` tallies `not_sampled` with `failed`, as
   unmeasured rather than inert. No ranking arithmetic and no recorded result
   changed. This is the last cost question ahead of the decision below, which
   stays open and is unchanged by this item: nothing here authorizes switching
   the feature on.
5. **Default and weight decision - DONE (2026-10-30).** The full fixed probe set ran
   16 times: four controlled dirty-file layouts (A one changed file, B two, C two
   chosen so the relevance gate admits nothing, D eight), each against the shipped
   `+25` and each against a scratch tree holding `+5`, each with the flag off and on,
   three repeats of the 11 probes per arm - 528 requests against the live gateway,
   33 records in every run plus one arm replayed for 33 more, zero request errors,
   zero new style findings and an identical index in all sixteen. It measured the
   build at `35e8b91` and changed no production behaviour:
   `RankingConfig.WEIGHT_CHANGED_FILE` stays `+25` and
   change-aware ranking stays off by default. What is deterministic here is the
   context, not the answers. All eight off-arms scored exactly `75/90` expected facts,
   every `+5` arm matched its own off-arm probe for probe, and only two cells in the
   whole matrix move - layout A at `+25`, `75/90` to `80/90`, and layout D at `+25`,
   `75/90` to `72/90` - both of them the same probe,
   `explain_changed_files_history_cap`, whose four expected facts over three repeats
   make twelve slots: `3/12` to `8/12` in the first and `3/12` to `0/12` in the
   second. That first cell had to be replayed to be quoted at all: the
   `--compare-context` run below reused its session-log path and truncated it from 33
   records to 22, so the arm was re-measured on 2026-10-30 into new files, 33 requests
   again and 561 in all. The replay reproduced the context side exactly - the same
   `101,328` prompt tokens against the same `98,634`, the same `109,272` estimated
   context tokens, the same 186 symbols selected, the same `3/33` contexts differing
   and the same 18 built baselines - and moved on the answer side: `83/90` for the arm
   and `11/12` for that probe. So the gain and the loss are a layout-dependent effect
   of `+25` and not noise in retrieval: the bonus lifts that probe when one file is
   dirty and erases it when eight are, the retrieval going from 60 symbols to 24 while
   what is sent grows from 8,421 to 10,995 estimated tokens. How far a lifted probe
   reaches inside its twelve slots is answer-side variance, and is quoted as a range
   (`8/12` to `11/12`) rather than a number. The split is the one B3 recorded on
   2026-10-25 - context fingerprint identical, answer text varying - and the replay
   is a second observation of it, on the same arm six runs deep. The weight
   question resolves the other way, and against `+5`: it changed `0/33` contexts and
   no token count on the layout where `+25` changes the answer, and where it did
   change contexts - 6/33 at layout B, 15/33 at layout D - it changed no outcome
   anywhere. `+5` is recorded as inert on this probe set rather than as a smaller
   candidate, which closes the candidate the weight sweep left open under *Git
   Integration*; a default-on at `+5` would be the feature off wearing an `on` label.
   Where the bonus does fire at `+25` it is cheap and, at layout A, twice measured:
   `+2,694` prompt tokens across the 90 facts (`98,634` to `101,328`, identical in
   both passes), `+864` at B, `-156` at D, and `+0` at C, the gate-negative control,
   which pays the machinery on 21 of its 33 requests and changes no context, no token
   count and no verdict, exactly as designed. Latency is not priceable from this
   matrix and no claim is made from it: cells whose contexts are provably identical
   differ by seconds in both directions, and the replayed arm is the clearest case -
   13,359 ms to 16,198 ms mean on an arm whose context record matches to the token -
   so the cost question stays settled by B4's own measurement. A `--compare-context`
   confirmation on the candidate cell, 22 requests at layout A `+25`, shows the
   promoted context still carrying every fact asked of it - all eleven probes gain
   from having context, 26 facts between them,
   `explain_changed_files_history_cap` reaching `4/4` - so the layout A gain is a
   real context effect on that layout and the layout D loss a real context effect on
   that one. Item 5 is closed with the default and the weight unchanged, and nothing
   here authorizes switching the feature on: an attempt to ship it on needs a layout
   set where the benefit is not one probe moving either way.

#### Phase C: Measure Conversation-Scoped File Activity

1. **C1 - touched-file signal and correlation - DONE (2026-10-30).** Derive recognized file reads
   and modifications from Cline tool-result envelopes already identified at the
   planning boundary. Treat envelope content as untrusted, normalize paths,
   reject paths outside the repository, isolate state by conversation, and fall
   back safely for clients without these envelopes. Keep session output
   count-only and distinguish at least files read, files modified, supplied
   context files later touched, touched files absent from supplied context, and
   changed-signal files later touched. This is a conversation-scoped ranking
   signal and observability slice, not an activation of `packages.capabilities`.
   Landed in `f74d16d` (initial implementation) and `c0d91bd` (hardening). The
   hardening commit made `tracker_miss` sticky across a broken lineage, counted
   rejections per envelope, and kept write/replace results out of the
   planning/history bookkeeping set so C1 stays observational. Live evidence is a
   four-request probe against a restarted gateway on 2026-10-26 plus a survey of
   existing session records (`docs/live-gateway-runbook.md`, *Conversation File
   Activity (roadmap C1)*). Still unmeasured: C1 under native Cline traffic, and
   its incremental latency against a feature-off arm. Both are optional follow-ups,
   not blockers.

#### Phase D: Documentation And Dormant-Code Policy

1. Update `CLAUDE.md`, `docs/STATUS.md`, this roadmap, the live runbook, and
   `docs/dormant-code-backlog.md` as their facts change. Compact the long
   changed-file narrative out of `docs/STATUS.md` into the runbook, leaving a
   current summary and link.
2. **Keep all dormant code for now.** Do not delete packages or tests, move them
   to another branch, broadly refactor them, or activate them incidentally.
   Capabilities, tasks, workflows, controller, execution, verification,
   modification, patches, session, bootstrap, and autonomous packages remain
   outside the live path until a concrete product workflow is chosen.
3. Continue tracking the documented full-suite failure baseline as dormant
   debt. Reducing that count is not a current objective, and tests must not be
   skipped, weakened, or removed to improve it.

#### Explicitly Deferred

- true tokenizer integration
- semantic/vector search
- GitHub API integration
- Git snapshot/diff persistence
- a general autonomous engineering loop
- wholesale activation of the dormant platform stack

A1, A2, all of Phase B, and C1 are complete. The remaining execution order is
**A3**, with documentation updated continuously.

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

The fixed probe set proves repository context adds answer-quality signal. On the
current set, measured 2026-10-24 from a controlled worktree of `0371d64` against
`qwen3.8-flash-next` on vLLM with changed-file ranking off, a `--compare-context` run
scored `25/30` expected facts with repository context against `4/30` without it - `+21`
facts for `+30888` prompt tokens, style clean in both arms. On the earlier 8-probe,
20-fact set the same comparison put the qwen36 run at `20/20` with context versus `2/20`
without, including the 2 multi-turn probes, and the qwen38-27b/SGLang full baseline of
2026-10-10 (the backend that alias pointed at before it moved to vLLM) came in clean at
`20/20` with style `8/8`; those two stay measurements of the set they were taken on.
`PROBES` now has 11 entries and 30 expected facts, the three added ones
being `explain_changed_files_contextbuilder`,
`explain_changed_files_repository_index` and
`explain_changed_files_history_cap` - the scored halves of the change-aware
ranking decision under Git Integration below.

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
already carry a query-match or relationship reason. Since Phase B1 that bonus is
bounded by a promotion guard, which keeps a promoted dirty file from pushing the
best un-promoted symbol of a query-matching module out of the positions the
context renders with source text, and since Phase B2 that guard is given the order
the builder finally assembles, not only the ranking pass, because the builder's own
promotions are reorders too. No new Git command, no new pipeline stage, no
new persisted artifact.
Enable with `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=true`;
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS` (default `0`) is the only
way to let the snapshot refresh after startup, and the refresh never runs in a
request path.

Completed the same slice's observability gap (2026-10-10): the promotion is now
measured counterfactually, not inferred from presence.
`packages.pipeline.stages.repository_context` re-ranks the same request without
the working-tree bonus and reports `changed_files_signal`,
`changed_files_count`, `changed_symbols_selected`, `changed_context_differs`,
`changed_symbols_promoted`, `changed_primary_promoted` and
`changed_baseline_status` on the request log line, in the stage result and
in the session record's `context` block; the counters describe the context that
was actually sent, so a promoted symbol trimmed by the budget or filtered by
delta injection is not counted. Promotion is proven by
`changed_files_signal="ok"`, `changed_files_count >= 1`,
`changed_baseline_status="built"` and `changed_context_differs=true` - which
includes the reorder-only case, `changed_primary_promoted=false` with
`changed_symbols_promoted=0`, because a flat bonus is a reordering signal and
comparing the primary plus the rest as sets read it as "nothing changed".
`changed_symbols_promoted` counts every sent symbol absent from the no-bonus
context, so it can include a symbol outside the changed modules that entered
through relationship expansion after a primary change. `changed_baseline_status`
separates a comparison that ran (`built`) from one that could not be built
(`failed`, which is unmeasurable rather than inert) and from one that was
provably unnecessary (`skipped_no_bonus`).
`changed_symbols_selected` above zero with `changed_context_differs` false is
the opposite result, and it is the one the earlier four-field version could not
express. The comparison build is read-only: it never touches the delta tracker,
is never serialized into the request, and its cost is reported as
`changed_baseline_ms` on the log line only. That cost is real: a second full
context build roughly doubles the stage on a dirty tree - measured on this
repository's real index of 328 modules with 8 changed, about 50 ms becomes about
105 ms - so it is paid only when `RankingEngine.rank()` gave the bonus to at
least one candidate, a count `ContextResult.changed_bonus_count` carries for the
purpose. `changed_modules` reaches nothing else in the builder, which makes the
skip exact. A stage that composes nothing still states the signal state it read,
or `unavailable` when it failed before reading it, so a degraded request cannot
record as a disabled feature.

Roadmap B4 (2026-10-25) changed the trigger of that second build, not this
paragraph's measurements. The build is now gated on
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED` in addition to the
bonus count, and the setting is off by default, so an ordinary enabled request
pays one build and records `changed_baseline_status="not_sampled"` - a fifth
state, kept apart from `skipped_no_bonus`, which is still the proof that the two
arms cannot differ and still costs nothing, and from `failed`, which is still an
attempted comparison that could not be made. Everything described above, and the
B3 figures recorded further below, was measured with that second build in place
and stands as recorded; a run that wants those fields today has to ask for them,
which is what `scripts/ab_launcher.py` now does for every experiment it renders
and what `scripts/quality_harness.py` does for its offline probes.
`scripts/analyze_sessions.py` summarizes the fields from session JSONL in a
changed-file promotion section, splitting proved (primary changed, membership
changed, reorder only) from present but inert and unmeasured, and counting records
that predate the fields separately so they can never enter a rate. It never
accepts a repository path,
query, symbol or path filter, and prints no path, symbol or content - the counts
are the whole contract. A separate A/B of two gateway runs is no longer needed
to answer "did the bonus change anything", so the standalone
`scripts/changed_files_observability.py` it briefly lived in is gone. This closes
the "how do we know a promotion happened" question that made the 2026-10-10 A/B
run hard to read; the benchmark harness has no changed-files switch and was not
extended.

Exploratory live A/B on 2026-10-10 used a temporary dirty marker in
`apps/gateway/core/config.py` against `qwen3.8-flash-next`. The off/on totals
were 15/20 and 19/20, but the difference was caused by unrelated model-side
variance in `explain_live_path`; the probe that retrieved the dirty module
(`multiturn_config_systems`) scored 2/2 in both arms with identical prompt
tokens and primary symbol. The run therefore did not measure a quality benefit.
The feature stays off by default. What that experiment needed - a probe whose
context actually differs between a feature-off and a feature-on arm, plus replication
that can tell the effect apart from sampling noise - is now registered, as
`explain_changed_files_repository_index` run with `--repeat 3` beside its negative
control `explain_changed_files_contextbuilder`, and since 2026-10-12 as
`explain_changed_files_history_cap`, the pair whose changed arm gains context instead of
paying for it; the paragraphs below record what the
offline cases say and what the live half found when it ran on 2026-10-12 and again on
2026-10-13.
Measuring which files an agent actually touched also remains open.

Measured offline on 2026-10-11, and still open as a decision. The question - can
the working-tree bonus outrank a symbol the query matched by name? - needed one
term splitting in two, because `EXACT_SYMBOL_NAME` fires when *any* segment of a
qualified name equals a query token, and the module-path segments count:

- a **name match** can be an accident of where a symbol lives;
- **named in the query** means the prompt contains the symbol's own name, and is
  the case the bonus has no business losing.

What `scripts/quality_harness.py --changed-file-probe` measured over this
repository's real index, running `RepositoryContextStage` on both arms with a dirty
module injected (never read from Git, so the working tree is irrelevant), at the
configured 4096-token budget:

- the query that names `ContextBuilder` holds its primary at `+5` and `+10` and
  loses it from `+15`, when a dirty `packages/context/budget.py` puts `155 + 15`
  against the leader's `170` and sorts first on the tie-break;
- and losing it costs nothing. The bonus puts the budget file's two symbols in front
  of the builder file's three instead of in place of them, so `ContextBuilder`,
  `_enforce_budget` and `packages/context/builder.py` are in the text both arms would
  have sent. A moved primary with an intact context is not an effect an answer can
  show, and that is why this pair is the control rather than the claim;
- a dirty file the prompt never mentions stays out at any weight, reported as
  `changed_baseline_status=skipped_no_bonus`;
- `--changed-file-sweep` gives the same flip point per query without touching Git
  at all: across 12 fixed queries, 6 are already tied with a candidate in another
  file and flip at `+1`, and the rest at 10, 15, 21, 30, 30 and 70. There is no
  single "name floor" to sit under - a tie needs no size to be decided.
- bonus size is not the main lever on what gets sent. With
  `packages/repository/index/models.py` dirty, "how does model resolution pick a
  backend" sends 12 symbols the no-bonus context did not at `+5` and `+10`, and 13
  at `+25`, with the primary unchanged every time: `model` is a path token of that
  module, `MODULE_MATCH` counts as query relevance, and the gate lets the file in.
  Reducing the weight does not touch that.
- one query does lose something, and it loses a whole file. "How does the repository
  index builder construct the index, including its collaborators for files and
  models?" with
  `packages/repository/index/models.py` dirty sends 10 symbols instead of 14: the
  dirty module's symbols take the front of the order, the budget runs out inside
  `packages/repository/index/models.py`, and `packages/repository/index/builder.py`
  leaves the context. `PythonAstExtractor`, `RelationshipRegistry`, and
  `CallExtractor` are available in the off arm and unavailable in the on arm -
  `facts_lost` reports all three, and no symbol of that file survives anywhere in the
  changed context to be counted as still-visible. It happens at `+1` exactly as at
  `+25` (`changed_symbols_promoted=0`, `changed_primary_promoted=1`), and it is a
  representation effect as well as an eviction at the configured budget: at 6144
  tokens both files' symbols fit and `PythonAstExtractor` returns, but the builder is
  supporting context and its constructor-body details `RelationshipRegistry` and
  `CallExtractor` remain unavailable. At 4096 all three details are lost.
- one query gains a mechanism instead, and it is the case the opt-in is offered for.
  "How does the gateway cap conversation history before sending it to the model?" with
  `packages/pipeline/history` dirty sends 7 symbols instead of 20: the four added are the
  cap's own definitions (`cap_history`, `_build_cap_groups`, `_cap_current_tool_result`,
  `_estimate_tokens`), the facts the two texts can support go `1/4` to `4/4`, and
  `facts_lost` is empty. The prompt is prose and names no symbol, so the bonus reaches it
  through the gate alone, and the verdict is `MOVE`: the primary moves *into* the changed
  file, which is what the case is for.

So the evidence says a smaller bonus is defensible and a large one is not needed,
but it does not say `+5` is right either: `WEIGHT_CHANGED_FILE` stays at the `+25`
that shipped, and `+5` was recorded here as a candidate, comparable without a code
change through `--changed-file-probe --changed-file-weight 5`. Phase B item 5 has
since measured that candidate live across four dirty-file layouts and closed it: the
`+5` bonus changed no outcome on any layout and `0/33` contexts on the one layout
where `+25` changes the answer, so the candidate stands measured as inert rather than
open, and `+25` remains the only shipped value.
`tests/context/test_changed_file_ranking.py` pins the arithmetic that both modes
read - a tie flips at `+1`, a competitor flips at the gap or the gap plus one
depending on the tie-break, and the gate holds at any weight - and asserts nothing
about the shipped value.

Answered on both sides now: 2026-10-12 measured what the promotion costs, and
2026-10-13 what it buys. What the first live A/B settled is that it costs this query its
answer;
what it did not settle is whether it buys any query anything, because no run yet
shows a promotion improving an answer. The instrument for that question is now
registered rather than to be
invented, and it is three probes rather than one, because the first version of the
comparison measured a retrieval change that turned out to cost no context. The
offline cases say which pairs can differ, and all three are in the normal scored probe
set: `explain_changed_files_repository_index` asks
`REPOSITORY_INDEX_BUILD_QUERY`, whose dirty `packages/repository/index/models.py`
pushes `packages/repository/index/builder.py` out of the context entirely, so a
changed-arm answer cannot reach its three facts from the prompt;
`explain_changed_files_contextbuilder` asks `CONTEXT_BUILDER_BUDGET_QUERY`, whose
dirty `packages/context/budget.py` reorders the context and loses nothing, so it is
expected to tie and tells a real effect apart from a probe that merely has a dirty
file near it; and `explain_changed_files_history_cap` asks `HISTORY_CAP_QUERY`, whose
dirty `packages/pipeline/history.py` is the file the question is about - prose that
names no symbol, so the bonus reaches it only through the relevance gate, and what
`+25` spends on it is the cap's own implementation: four symbols the disabled arm does
not get, and nothing scored given up (`1/4` to `4/4` facts available, `facts_lost`
empty). Either is selectable with `--probe <id> --repeat 3`, so the replicated
A/B (feature off on one gateway, feature on in another, the pair's own module dirty in
the tree, isolated session logs read back through `scripts/analyze_sessions.py`, both
arms at the configured `APP_REPOSITORY_CONTEXT_MAX_TOKENS=4096`) needed only a
gateway pointed at a reachable backend. It was not run on 2026-10-11, when nothing
answered on either end; it ran on 2026-10-12 against vLLM at
`http://100.106.236.88:18300/v1`, and the discriminating pair separated the way the
offline case said it would: feature off `9/9` across three repeats, feature on `0/9`
across three, the enabled arm sending 8 symbols where the disabled arm sent 11 with
`packages/repository/index/builder.py` gone from its context outright, and its
session records showing `changed_context_differs=true`,
`changed_primary_promoted=true` and `changed_baseline_status=built` while the
disabled arm reports the signal `off`. Per-repeat numbers and the two limits that
belong to this measurement - the flag is global, so the enabled arm took the bonus
across the 18 locally modified indexed modules rather than the experiment's single
marker, and two of its three answers ran to the 8192-token completion ceiling - are
in `docs/live-gateway-runbook.md`. The offline probes stay supporting diagnostics: that
run priced what this retrieval change costs on one query, and did not show
what it buys on any.

It shows what it buys now. On 2026-10-13 the gain pair ran against the same vLLM
backend, with both gateways started inside a detached worktree of `4330e8f` whose single
locally modified file was a two-line marker in `packages/pipeline/history.py` - the
isolation the October-12 run could not have, and the reason its enabled arm reported
`changed_files_count=18` where this one reports `1`. Feature off `3/12` (1/4 on all three
repeats: `cap_history` is the public name, and the disabled arm's call sites still show
the model where to look), feature on `8/12` (3/4, 3/4, 2/4), with
`max_current_tool_result_tokens` named by all three enabled answers and
`_looks_like_cline_tool_result_message` by two, neither named once by a disabled answer,
and no scored fact the disabled arm had going missing. Inside each arm the context was
identical across repeats: 20 symbols and `estimated_tokens` 2807 disabled, 7 symbols and
4087 enabled, the enabled primary inside `packages/pipeline/history`, and
`changed_symbols_promoted=4`, `changed_primary_promoted=true`,
`changed_context_differs=true` and `changed_baseline_status=built` in all three enabled
records against `off`, `false` and zeros in the disabled ones. Two things came with it
that are not gains: 402-507 ms per enabled request for the counterfactual baseline, and
the fourth fact (`truncated by gateway history cap`) reaching the enabled text without
reaching any answer in either arm - a property of scoring a string verbatim rather than
of what the context contained. Three enabled requests
were also lost to a confound worth naming: with no `.env` in the worktree, the gateway's
own provider timeout stayed at its 60-second default while the harness was told to wait
300, and those repeats came back as HTTP 503 at 61 s until `REQUEST_TIMEOUT=300` was set
on both arms; the numbers above are the pass taken after that.

So the weight decision is informed on both sides and unchanged: `WEIGHT_CHANGED_FILE`
stays at the `+25` that shipped, and the feature stays off by default, because the flag
is global - turning it on takes this gain and the eviction cost together - and no rule
yet decides per query which of the two a repository is getting.
`tests/observability/test_quality_harness.py` runs the real
stage over this checkout's index on both arms of every pair and asserts the context
difference, so what the A/B sees is a regression test, not a guess. Measuring
which files an agent actually touched also remains open.


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
