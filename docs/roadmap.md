# Roadmap

This roadmap is based on the current live gateway, not on dormant scaffolding.

Last reviewed: 2026-11-07 (Phase F closed as a measured negative result: the F3 candidate,
`primary_symbol_max_tokens` 2048 to 1536, converted no fact, broke four Phase B tests and was
rejected and reverted before F5; the shipped runtime is unchanged. See Phase F item 6.)

Previous review: 2026-11-06 (through commit `ebb98f9`. Phase F step F1 was measured, not
written: A1's command shape re-ran from a detached worktree of `ebb98f9`, launched by
`scripts/ab_launcher.py`'s `off` arm on an isolated port with its own session log, with the
live-path gate green first (2519 passed, 206.11 s) and the backend identity confirmed before
any scored request. The context arm scored `25/30` again - 32716 prompt tokens in 188.0 s,
style `11/11` ok, nothing errored, nothing timed out, longest request 29.4 s - and the
no-context half scored `2/30` where A1 scored `4/30`, on requests identical one by one in
prompt tokens (2221 in both runs). Under the unchanged context-arm total the composition
moved: `_choice_content` was delivered by A1's identical context and missed today, and
`packages/context/builder.py`, one of the two facts still open, converted on a request
identical to A1's in every recorded field. `select_last_task_text` and the three history-cap
facts are still missed. No fact is classified from a live arm: F2 owns the classes and F1's
evidence table is its input. Two statements in Phase F were corrected on the way - 1324 and
1471 are ratios of total provider prompt tokens and not of repository context (the
context-only figure is 1412 estimated tokens per scored fact, from the session field
`context.estimated_tokens`), and F1 no longer requires a live run to reproduce `25/30` and
`4/30` before its evidence may be used. Phases A to E stay complete: the measurement base was
repaired and re-run (A1-A2), the history cap became a calibrated number in the code that
spends it (A3), change-aware ranking was settled offline and live and closed with its
default and its weight unchanged (B1-B5), and conversation file activity is measured on the
live path, summarized offline, validated against native Cline traffic, and benchmarked
against a feature-off arm (C1, E1-E3). Dormant code stays intact and isolated; no deletion,
archival move, or incidental activation is part of the current plan, and change-aware ranking
stays off by default.)

Previous review: 2026-11-03 (documentation-only, through commit `ebb98f9`: Phases A to E of
the sequence below were confirmed complete and Phase F, Repository Context Quality Per
Token, was opened as the next measured milestone. It starts from the controlled 11-probe
baseline - `25/30` expected facts with repository context against `4/30` without it, an arm
delta of `+30888` prompt tokens across the `+21` facts the flag converted - and asks what the
five facts context did not deliver cost, in that order. No runtime fact changed: the live
path remains `ModelResolutionStage` -> `PlanningStage` -> `RepositoryContextStage` ->
`ProviderStage` with two configuration switches and no runtime `EngineeringMemory` read, and
C1 stays inert until a client sends `tools`. Everything measured through `ebb98f9` stays as
it was written; the statements that carry it were reworded where they had gone stale, and the
rest of this file is the record. Dormant code stays intact and isolated; no deletion,
archival move, or incidental activation is part of the current plan, and change-aware ranking
stays off by default.)

Review before that: 2026-10-24 (recorded the measured development sequence that Phases
A-E above now closes, and kept dormant code intact and isolated).

Review before that: 2026-09-19 (records the completed dormant Capability Framework v1
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
- per-model chars-per-token calibration for context accounting
  (`ModelDefinition.chars_per_token`, default `4.0`; qwen38-27b `3.5`), live-
  validated 2026-09-09 for repository-context budgeting: 5/8 -> 0/8 measured
  context-cost overages, no quality/style regression; roadmap A3 extended the
  same resolved ratio to history capping, measured 2026-10-31
- conversation-scoped file activity on the live path (roadmap C1, landed
  `f74d16d`/`c0d91bd`, complete 2026-10-30): recognized Cline write/edit/search tool
  results normalized to repository-relative paths, counted per conversation and
  recorded count-only in every session record behind `FileActivityTracker`; analyzed
  offline by the session analyzer's FILE ACTIVITY section (E1), validated against
  native Cline 4.x tool calls (E2), and benchmarked against a feature-off arm (E3)

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
3. **A3 - calibrated history-cap estimation - DONE (2026-10-31).** History
   capping now estimates message tokens with the resolved model's
   `chars_per_token` - read off `ResolvedModel.definition`, the shape
   `ModelResolutionStage` stores - instead of the global `CHARS_PER_TOKEN` of
   `4.0`, and a model that overrides nothing caps byte-for-byte as it did, since
   `ModelDefinition.chars_per_token` still defaults to `4.0`. Getting there
   needed a fix first: `cap_history` has accepted an `estimate` callable since
   it was written, and the engine handed it one on every request, but nothing
   ever called it - counting went through the module-level `_estimate_tokens`
   and the constant, so a calibrated estimator passed through that argument
   would have changed no bytes on the wire. The callable now reaches every text
   field that is counted (`content`, `name`, `reasoning_content`, and each tool
   call's name and arguments), and the same ratio converts the current-envelope
   budget back into characters, so the truncation marker lands at the
   calibration the keeping decision used. Budgets are untouched:
   `APP_HISTORY_CAP_TOKENS` still wins, and the derived budget still subtracts
   the generation, repository and safety reserves. A3 also corrected where that
   derived budget reads the window: it takes
   `ResolvedModel.definition.context_window` now - the production shape, where no
   top-level `context_window` attribute exists - instead of the
   `getattr(resolved_model, "context_window", 8192)` that answered `8192` for
   every model, which is why a request with `max_tokens` at or above that
   default capped nothing. The live arms forced `APP_HISTORY_CAP_TOKENS=3000` and
   so never entered that branch; the correction is verified offline, and a test
   shows that no window value changes what the explicit branch forwards. Measured against
   `qwen3.8-flash-next` on vLLM through `qwen38-27b` (`chars_per_token=3.5`),
   two detached worktrees of `c161999` - candidate scratch commit `f0a77df4` -
   launcher-rendered configuration, `APP_HISTORY_CAP_TOKENS=3000`, 18 requests
   in 6 min 48 s. The named probe `multiturn_history_cap_budget` holds at `3/3`
   with style clean on both arms and the cap dropping nothing on either, so the
   probe does not discriminate the calibration; the controlled Cline A/B does -
   one transcript and one budget forwarded whole at `4.0` (dropped 0,
   `history_tokens_after` 6,971) and reduced to four of seven messages at `3.5`
   (dropped 3, 6,550), identically on all three repeats, 738 fewer prompt
   tokens, no candidate-only error, timeout or budget violation, all four facts
   answered with style clean on every scored turn. The seed turn is the parity
   control: identical forwarded bytes recorded as `2,846` against `3,253`,
   which is `4.0` against `3.5` over the same characters. No latency claim; the
   candidate answered longer and three paired samples price nothing. Offline:
   live-path gate 2,345 passed and full suite on the documented 43-failure
   baseline with the same composition at measurement, and both re-run clean on
   the corrected derived-budget tree afterwards - 2,357 and 4,959 passed against
   the same 43 - with `tests/pipeline/test_history.py` grown from three
   tautological and formula-copy tests to 79 behavioral ones, four of which fail
   against the window read that correction replaced.
   Configuration, commands, tables and artifact paths:
   `docs/live-gateway-runbook.md`, *Calibrated History-Cap Estimation (roadmap
   A3)*.

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
   same in both arms so it moves no verdict. Item A3 was as written and was still
   open at that point - it is about history capping using the resolved model's
   `chars_per_token`, which this run neither advanced nor measured; it closed
   separately on 2026-10-31.
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
   again - 528 matrix requests, 22 confirmation requests, and 33 replay requests:
   583 live gateway requests in total. The replay reproduced the context side exactly - the same
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
   Activity (roadmap C1)*). Both follow-ups are since done: native Cline
   traffic in E2 and the incremental latency in E3 (Phase E).

#### Phase D: Documentation And Dormant-Code Policy

1. **Documentation as facts change - an ongoing policy, not a closable task.**
   Update `CLAUDE.md`, `docs/STATUS.md`, this roadmap, the live runbook, and
   `docs/dormant-code-backlog.md` whenever a fact in them moves. Its one bounded
   piece - compacting the long changed-file narrative out of `docs/STATUS.md` into
   `docs/live-gateway-runbook.md`, leaving a current summary and links - is
   **DONE (2026-10-31, at `466ab59`)**; the policy of keeping those documents
   true as the path changes stays open on purpose and never closes.
2. **Keep all dormant code for now - standing policy, unchanged.** Do not delete
   packages or tests, move them to another branch, broadly refactor them, or
   activate them incidentally. Capabilities, tasks, workflows, controller,
   execution, verification, modification, patches, session, bootstrap, and
   autonomous packages remain outside the live path until a concrete product
   workflow is chosen.
3. **Continue tracking the documented full-suite failure baseline as dormant debt -
   standing policy, unchanged.** Reducing that count is not a current objective,
   and tests must not be skipped, weakened, or removed to improve it.

#### Phase E: Analyze What The Live Path Already Records

1. **E1 - Conversation File Activity session analysis - DONE (2026-10-31).** C1
   writes seventeen count-only keys into every session record and nothing read
   them: `scripts/analyze_sessions.py` tallied the changed-file promotion fields
   and had no counterpart for `context.file_activity`. The analyzer now prints a
   FILE ACTIVITY section, and it is analysis only - no runtime code changed, no
   new field was added, and no backend request is needed to produce it.

   The section is snapshot-safe by construction. C1's counters are recomputed
   from the complete transcript each request carries, and a Cline client resends
   its whole conversation every turn, so a read done on turn one is stated again
   by every later record. Adding the column would count that read once per later
   turn - the exact double-counting C1's snapshot model replaced - so the
   analyzer reports, per counter, how many records can answer, how many answered
   above zero, and the median and maximum a *single* record reached, and never
   reports a cross-record total of files read, touched, attempted or otherwise.

   Records stay distinguishable rather than collapsing into zeros: one that
   states no `file_activity` predates C1, one missing a key is incomplete, one
   whose object or values are unreadable is malformed, and all three are counted
   apart from `state=none`, which is a measured zero. `state=unavailable` and an
   unrecognized state token are excluded from the activity statistics;
   `correlation=tracker_miss` and `correlation=unavailable` are excluded from
   `context_files_touched` and `touched_without_context`, whose zeros there
   describe a lineage gap and not a conversation that never saw context;
   `state=partial` is kept with its values labelled floors. The section reads
   only the seventeen documented keys, ignores unknown nested keys, and prints no
   path, module, symbol, result body or envelope text.

   Evidence: `tests/scripts/test_analyze_sessions_activity.py` (36 tests), and offline
   runs of the analyzer over four retained logs - the 2026-10-26 C1 probe
   (`logs/c1_live_validation_20261025.jsonl`, 4 records), both roadmap A3 arms
   (`build/a3/20261030/sessions_base.jsonl` and `sessions_cand.jsonl`, 9 records each,
   carrying real `state=none`, `state=measured`, `correlation=measured`,
   `no_prior_context` and `tracker_miss` cases), and a pre-C1 log
   (`logs/implement_budget_A_4096_20260801.jsonl`, 591 of 592 records counted as
   predating C1 and excluded). Each of the four is the complete command against the
   whole log, not the new section on its own: "offline validation" here means the run
   exits 0 and reaches `END OF REPORT`, which all four now do. Getting that on the
   fourth log required repairing a pre-existing `ERROR REQUESTS` crash on a null
   `error` field - it crashes HEAD's own copy of the script at that statement, and it
   is not something this item introduced. All of it is analysis of evidence C1 had
   already recorded; no new measurement was taken.
2. **E2 - Validate file activity with native Cline traffic - DONE (2026-11-02).**
   The first probe (`e2native-20261101-2121Z`, at `6adb30a`) executed no tool at
   all: the gateway dropped the client's `tools` field, so the model wrote tool
   calls as text, and the serializer rejected `role: "tool"` messages. Both were
   fixed in `8695063`. A wire capture of Cline 4.1.26 then showed it uses OpenAI
   native tool calls, which C1 did not read; `193c049` (type fix `b6d4a58`) taught
   C1 that format. The rerun (`e2native-20261102-0939Z`, at `b6d4a58`) drove a real
   Cline 4.1.26 task through an isolated gateway: 12 requests, 12 records, all with
   usage, repository context assembled on every one. The final record states one
   confirmed read, one failed read, one confirmed modification, one search and no
   rejected path, and matches Cline's own task record call for call; every later
   record restates the same snapshot rather than adding to it. Correlation was
   `measured` from the second request on. This validates counting only - no latency
   or ranking-quality claim. Evidence stays outside the repository
   (`C:\Users\ovidi\lap-e2-evidence\`); details in the runbook, *Native tool calls
   (Cline 4.x)*.
3. **E3 - C1's incremental latency against a feature-off arm - DONE (2026-11-03).**
   `scripts/bench_c1_latency.py` (`43d55f7`) times `RepositoryContextStage` with a
   `FileActivityTracker` against the identical stage built with `file_activity=None`,
   in one process, on the same transcripts; every timed call builds fresh objects,
   warm cells replay their conversation's earlier requests outside the timer, and a
   correctness pass checks every payload field. Realistic cells take their shape from
   `scripts/calibrate_c1_shapes.py`, which reads the 39 local Cline sessions and
   prints counts only. Thresholds were set before measuring: under 2 ms negligible,
   5 ms or more actionable, on the conservative interval of 8 per-block deltas.
   The first measurement was actionable: 23.3 ms at R-p99-warm, 6.1 ms at
   R-p50-warm. A pilot sweep and a profile found two causes - every native tool
   result in the transcript was JSON-decoded and then discarded by the 256-envelope
   bound, and every distinct path was re-resolved with `realpath` (about 150 us
   each on Windows) on every request. `fa1fa22` fills the bound newest first and
   counts what falls outside it without decoding; the follow-up keeps `realpath`
   answers across requests in a bounded map on `RepositoryPathNormalizer`
   (`MAX_RESOLVED_PATHS`, 4096), which reverses the earlier per-request-only design
   on purpose. After both: R-p50-warm 1.6 ms (negligible), R-p90-warm 4.3 ms,
   R-p99-warm 5.6 ms. The p99 cell is one whole stored session sent as one request
   (4.9 M characters, about 1.2 M tokens), larger than any request the 262 k context
   window allows, so it is an upper bound rather than traffic. Cold cells are
   unchanged (R-p99-cold 18.3 ms): the first sighting of a path still pays
   `realpath`, and the map is shared by every conversation on the gateway. Accepted
   cost: a symlink or junction re-pointed while the gateway runs keeps its old
   answer until evicted or restarted. Benchmark output stays under `build/`.

#### Phase F: Repository Context Quality Per Token

The milestone now in line, opened 2026-11-03 at commit `ebb98f9`, where step F1 was measured and
step F2 classified on 2026-11-06 - the first live, the second offline and deterministic. F3 was
authorized by what F2 found, was built and measured offline on 2026-11-06, and did not convert
the fact it predicted; F4 measured what it does change and found four established Phase B tests
broken by it. **Phase F closed 2026-11-07 as a measured negative result (item 6):** the candidate
was rejected and reverted, F5 was not run, and no Phase F runtime change was accepted - the
shipped `primary_symbol_max_tokens` is still 2048. Phases A to E are closed, so
this was the item that followed them. It keeps the pattern the 2026-10-24 sequence set - reproduce,
change one variable, test, measure live, accept or revert -
and stays planning-first through the existing `context_budget_ranking` task in
`scripts/local_agent_coding.py`, whose scope this phase extends.

**The number it starts from.** The controlled A1 baseline (2026-10-24, `0371d64`,
`scripts/quality_harness.py --compare-context --json` over the whole 11-probe /
30-fact set against `qwen3.8-flash-next` on vLLM through the `qwen38-27b` alias,
`chars_per_token=3.5`, `repository_context_max_tokens=4096`, intent budgets
`SEARCH/TEST/DEBUG=2048` and `REFACTOR/IMPLEMENT/EXPLAIN=4096`, history cap on at
3000 tokens, changed-file ranking off in both halves of the pair, `REQUEST_TIMEOUT=300`
against a 345 s harness timeout): `25/30` expected facts with repository context
against `4/30` without it, style `11/11` ok in both arms, no errored and no timed-out
request, 33109 prompt tokens in 129.6 s against 2221 in 532.1 s. Both of those are total
prompt tokens the provider reported for the whole request, so the two ratios drawn from
them are per-request figures and not repository-context figures: `+30888` prompt tokens
bought `+21` facts, about 1471 prompt tokens per fact the flag converted, and the context
arm spent 1324 per fact it scored. The context-only figure is a different quantity from a
different source - the session record field `context.estimated_tokens`, summed over the
same run's 11 context-arm records, totals 35309 there, which is 1412 estimated context
tokens per scored fact and 1681 per converted fact. That field is the stage's own
character-based estimate at the calibrated `chars_per_token`, and for these eleven
requests it runs 4421 tokens above the measured prompt-token delta and 2200 above the
context arm's entire reported prompt, so the two bases are quoted side by side and never
interchanged. The five facts the context arm did not deliver are
this phase's subject: `select_last_task_text` (`refactor_repository_context`, 1/2,
3220 prompt tokens), `packages/context/builder.py`
(`explain_changed_files_contextbuilder`, 2/3, 3466), and three of the four on
`explain_changed_files_history_cap` (1/4, 3025) - `max_current_tool_result_tokens`,
`_looks_like_cline_tool_result_message` and
`[... truncated by gateway history cap ...]`, with only `cap_history` arriving. The
configuration, commands and per-probe numbers are in
`docs/live-gateway-runbook.md`, "Current controlled baseline, 2026-10-24 (roadmap A1)";
artifact `logs\quality_compare_qwen38_vllm_20261024.json`.

**What is already explained, and so is not this phase's target.** Three of the five
sit in the one probe whose working-tree bonus is their documented reason: the runbook
records `1/4` there as what an arm without the bonus scores, and roadmap B5 closed
that question on 2026-10-30 with `RankingConfig.WEIGHT_CHANGED_FILE` at `+25` and
change-aware ranking off by default. Recovering those three facts by turning that
feature on is a decided matter and is not on the table here. What is genuinely open is
the other two facts, and the cost question that covers all five.

**The question this phase answers.** F1 has been measured, and it says which facts moved
rather than why. It reproduced `25/30` at `ebb98f9`, and the movement inside that unchanged
total sat on probes whose recorded context is identical between the two days - same symbols
selected, same estimated tokens, same primary - so on those probes the answer side is
implicated by observation, not by inference. What still no measurement says is whether the
facts that remain missed are retrieval, ranking and composition, or answer-side. The three
lead to different work: the text never reached the prompt, it reached the prompt thin or out
of position, or it reached the prompt complete and the answer did not use it. The ratio is
only worth quoting once they are separated.

**The metric to report.** Keep A1's reporting shape - facts per arm, prompt tokens per
arm, style, errors, timeouts, wall seconds - and add the marginal number in both bases,
each named for what it divides. On reported prompt tokens the baseline is 1324 per fact
the context arm scored and 1471 per fact the flag converted; on the stage's own
`context.estimated_tokens` it is 1412 and 1681 for the same counts. A candidate that
converts a fact while adding context improves quality per token only if its marginal
cost is below the figure it is quoted against, so the base used, the conversion count and
the token delta are reported together or not at all. F1 measured those four numbers on
2026-11-06: 32716 prompt tokens and 34902 estimated context tokens for `25/30`, against a
no-context half of 2221 tokens and `2/30` - `+30495` prompt tokens for `+23` converted
facts, which is 1309 prompt tokens per scored fact, 1326 per converted fact, 1396 estimated
context tokens per scored fact and 1517 per converted fact. The context arm reached A1's
score for 393 fewer prompt tokens than A1 spent, and that came from composition rather than
from a cheaper mechanism: one probe sent a symbol fewer, another sent the same symbol at 391
estimated tokens more.

1. **F1 - reproduce the live behaviour and record what moved.** Re-run A1's command shape
   at the current commit, from a detached worktree, with the harness and the gateway
   pointed at that tree's own session log so the run's records hold nothing else. A1 is
   the historical reference, not a gate: answer-side sampling variance at this sample
   size is already documented in this file (roadmap B5 re-ran a probe for that reason
   alone), so a run that does not land on `25/30` and `4/30` is not a change in
   conditions that voids it - it is the current number, and what has to be recorded is
   which probes moved, in which direction, and whether anything other than the answer
   explains it: a style violation, an error, a timeout, or a `context.status` that is not
   `assembled`. No fact may be called context-side or answer-side from this step alone.
   Per fact - the five historical misses first - record whether the current answer scored
   it, and what the run left behind says about it, which measured here is everything a live
   arm can give: the session record's `intent`, `context.status`, `context.primary_symbol`,
   `context.symbols_selected`, `context.max_tokens` and `history.dropped_count`, plus the
   stage's own `context.estimated_tokens`. Neither the harness document nor the session log
   stores the serialized prompt - `apps/gateway/session_log.py` records message counts and
   previews, not the request text - so this step reports the shape of what was sent and never
   its text, which is precisely the gap F2 exists to close. Record the probe's delta against
   A1 beside it, and what stays unresolved.

   Measured 2026-11-06 at `ebb98f9`, from `C:\Users\ovidi\lap-f1-ebb98f9` on port 8011. The
   commands, configuration, artifact paths and per-probe deltas are in
   `docs/live-gateway-runbook.md`, "Phase F1 reproduction of the A1 baseline, 2026-11-06
   (roadmap F1)". The context arm scored `25/30` as A1 did, for 32716 prompt tokens in
   188.0 s, style `11/11` ok, zero errored and zero timed-out requests, longest 29.4 s. The
   no-context half scored `2/30` where A1 scored `4/30`, on eleven requests whose prompt
   tokens are identical one by one (2221 in both runs), so whatever moved there moved in the
   answer. Under the matching context-arm total three facts moved: `_choice_content` was
   delivered by A1's identical context - same single symbol, same 2046 estimated tokens, same
   primary - and missed here, `packages/context/builder.py` converted on a request identical
   to A1's in every recorded field (3466 prompt tokens, 3988 estimated context tokens, 3
   symbols, primary `packages/context/builder.ContextBuilder._enforce_budget`, both days),
   and `implement_health_flag` and `multiturn_history_cap_budget` held their scores while
   sending one symbol fewer each. Still missed and unmoved: `select_last_task_text` (1 symbol
   at 4049 estimated tokens of a 4096 budget, against A1's same single symbol at 3658) and all
   three `explain_changed_files_history_cap` mechanism facts (20 symbols at 2861 estimated
   tokens, 1235 of budget unspent, recorded primary `apps/gateway/api/models.list_models`).
   `history.dropped_count` is 0 in all 22 records of both runs, so nothing the cap does can
   account for the truncation-marker fact on either day: its only route into a prompt is as
   text inside a selected symbol's source.

   What F2 has to settle from deterministic evidence, and a live arm cannot: whether
   `packages/pipeline/user_messages` is a candidate for the REFACTOR query at all, and whether
   one 4049-token symbol leaves room for a second; whether the two `packages/pipeline/history`
   helpers are unreachable from that query's ranking or reached and cut by the count of 20;
   and whether A1's builder-file miss was ever reachable from the context side, which the
   identical-request record already answers for the answer. One condition note for F5: answer
   times rose on both halves with prompt counts unchanged, and the repository-context stage
   summed 32.2 s against A1's 12.8 s over the same eleven requests, so A1's 11.8 s per request
   is a historical reference and a material-latency floor has to be quoted against a same-day
   control arm.

2. **F2 - read the deterministic evidence, offline, and classify from it.** This is where
   the five classes get assigned, one per fact, with the evidence line named for each:
   (a) not retrieved - the symbol never entered the builder's candidate set; (b) retrieved
   and trimmed - it entered the ranking and the `max_symbols` limit or `_enforce_budget`
   removed it; (c) selected and thin - it reached the package as `signature` or
   `source_preview` rather than as `source`; (d) delivered and unused - the serialized
   prompt carried the fact's text and the answer did not use it; (e) scored wording - the
   answer states it and the verbatim match misses it. (a) to (c) are context-side and are
   settled here; (d) and (e) are settled against F1's recorded answers, which makes F1's
   evidence table the input to this step rather than a parallel result. No gateway, no
   backend, no new capability: extend the seam the changed-file probe already uses.
   `_stage_arm()` runs
   the real `RepositoryContextStage` over this checkout's index, and
   `context_facts_available()` serializes that package through the real
   `OpenAISerializer` and applies the same `score_answer` matching the live probe uses, so
   the answer is which fact text objectively reaches the prompt. Run it on the three
   probes that hold the five facts with `changed_modules` empty - the arm the baseline
   measures - and record per probe: the primary symbol, the selected symbols in order,
   which of them carry `source` rather than `source_preview`, estimated tokens against the
   budget in force, and whether each missed fact's text appears in the serialized prompt
   at all. That settles classes (a) to (c); only a live arm settles (d) and (e). Two
   limits to state rather than hide: `_stage_arm` builds a bare `PipelineContext` with no
   resolved model, so it estimates at `CHARS_PER_TOKEN` 4.0 where the live path uses the
   alias's calibrated 3.5 (recorded under roadmap B3), and `RepositoryIndex` is AST-based,
   so a symbol its expansion never produces is absent in a way no ranking change reaches
   (recorded under *Deferred*). One asymmetry is worth naming before any of that, because
   it is checkable offline and is not yet a conclusion:
   `_promote_repository_context_stage_symbols` lists
   `packages/pipeline/user_messages.select_last_task_text` among its targets but only
   reorders candidates ranking already found, with no `_ensure_named_candidates` call
   (`packages/context/builder.py:398-414`), while the history-cap and config-system
   promotions append their targets from the index when ranking missed them
   (`packages/context/builder.py:433-447` and `:449-463`, appending at `:492-519`).

   Classified 2026-11-06, offline, at `ebb98f9`, from `C:\Users\ovidi\lap-f1-ebb98f9`: no
   gateway, no backend, no live harness and no runtime change. What ran is the real thing - that
   tree's index (515 modules, 9022 symbols, 19720 relationships), the real `PlanningStage`
   intent, `RepositoryContextStage`, `ContextBuilder`, `RankingEngine`, `ContextBudget`,
   `ContextComposer`, `OpenAISerializer`, and the harness's own `_stage_arm()`,
   `context_facts_available()` and `score_answer` matcher - over the three probes with
   `changed_modules` empty, in two shapes. Shape A is `_stage_arm()` as it stands: a bare
   `PipelineContext`, no resolved model, so `_resolve_chars_per_token` falls back to 4.0 and no
   plan is present. Shape B puts the same stage behind `ModelResolutionStage` and
   `PlanningStage` with the alias's real `ResolvedModel` (`chars_per_token=3.5`,
   `context_window=262144`) and the same intent budgets and 4096 maximum. Shape B reproduces
   F1's context-arm records exactly - 4049, 3988 and 2861 estimated tokens, 1, 3 and 20 symbols
   selected, the same three primaries and the same `REFACTOR`/`EXPLAIN`/`EXPLAIN` intents, which
   is what licenses the classes below, and classification follows that production shape.
   The 4.0 shape reaches the *same class for all five facts* at 3799, 3810 and 2567
   estimated tokens, and the shapes differ only in how much text survives a budget
   expressed in characters: the same 512-token supporting preview is 2070 characters at
   4.0 and 1814 at 3.5.

   | fact | probe | class | the evidence line, from the production-shaped replay |
   |---|---|---|---|
   | `select_last_task_text` | `refactor_repository_context` | (b) retrieved and trimmed | ranked (4127 candidates cleared the score floor), hoisted to candidate position 2 by `_promote_repository_context_stage_symbols`, survived `max_symbols=20`, then removed by `_enforce_budget`, which walked that 20-candidate package down to its single primary (20 in, 1 out, 4049 estimated of 4096). Text appears 0 times in the serialized prompt and in `context_facts_available()` |
   | `packages/context/builder.py` | `explain_changed_files_contextbuilder` | (d) delivered and unused | 33 of the file's symbols entered the candidate list and 3 were selected (primary `ContextBuilder._enforce_budget`, 7168 source chars + 6817 docstring + 19 signature, then a preview and a signature-only symbol), 20 in and 3 out at 3988 estimated; the context message carries the module key 8 times and `context_facts_available()` lists the fact. A1's answer missed it, F1's scored it, on a request the replay matches field for field - so the miss was never context-side |
   | `max_current_tool_result_tokens` | `explain_changed_files_history_cap` | (c) selected and thin | 250 owners, 116 of them in the ranked list, 114 cut at `max_symbols=20`, 2 selected (`packages/pipeline/history._build_cap_groups.find` delivered as a 1814-character `source_preview`, `.union` as signature only). `get_symbol_source` returns the 18056-character module text for both, and the literal sits at offset 5842 of it, so the delivered form stops 3628 characters short. 0 prompt occurrences |
   | `_looks_like_cline_tool_result_message` | `explain_changed_files_history_cap` | (b) retrieved and trimmed | its own definition symbol entered the candidate list and was one of the 25 owners cut at `max_symbols=20`; 0 prompt occurrences. It is not in any promotion target list, and the history-cap promotion did not fire on this prompt at all |
   | `[... truncated by gateway history cap ...]` | `explain_changed_files_history_cap` | (c) selected and thin | no symbol is named for it, so the ladder runs on the symbols that carry it: 111 ranked owners, 109 cut at 20, the same 2 selected in preview and signature form with the literal at module-text offset 5842, 0 prompt occurrences. Requirement satisfied: it is only "delivered" if a selected representation contains it, and none does |

   The asymmetry flagged above is settled, and it is not what cost the two facts. On the
   REFACTOR query `_query_targets_repository_context_stage` returns true, the promotion
   passes its three targets to `_promote_named_symbols` with `appended=[]` and no
   `_ensure_named_candidates` call - reorder only, exactly as documented - and
   `targets_missing_from_candidates` is empty, so all three targets were already in the
   ranked list and the append it does not have was never needed.

   On the history-cap query the opposite happened: `_query_targets_history_cap` returns
   false for "How does the gateway cap conversation history before sending it to the model?" -
   none of its seven clauses match - so `_promote_history_cap_symbols` never ran, and
   `ensure_named_candidates calls` is empty in all six replays of all three probes. The
   history-cap facts are lost to the count of 20 and to preview depth, not to a promotion
   that could have appended them; widening that gate to name one probe's helpers would be
   making a fact appear, which F3 rules out. No fact landed in class (a) and none in (e):
   every answer that missed a fact said nothing resembling it, so the open set is
   context-side by observation.

   Four of the five facts are open and context-side - two (b), two (c) - so **F3 is
   authorized**. The one bounded variable it should weigh, proposed and not implemented: the
   primary symbol's share of the unchanged budget, `ContextBuilder`'s
   `primary_symbol_max_tokens` from 2048 to 1536 tokens. What it predicts, from the replay's
   arithmetic rather than a hope:
   `select_last_task_text` converts, because that fact's symbol is the one that reached the
   package and was popped, and the pop is a fit problem - the primary is 7168 source characters
   plus a 6817-character docstring, 4049 estimated tokens against a 4096 ceiling, so 512 tokens
   of primary source freed is exactly the 512-token supporting preview that carries the helper.
   Its token cost is about zero, because the ceiling is not touched: the same 4096 buys a
   shorter primary and one more supporting symbol. It predicts no conversion for the two
   history-cap facts, which are cut before any budget is spent, and none for the builder file,
   which is already delivered. The alternatives that would reach those two - `max_symbols` above
   20, or a deeper supporting pool - are separate variables that buy facts with tokens, which is
   the ratio this phase exists to improve; they are recorded as the open choice, not taken here.

   Everything above comes from `build\f2\f2_classification.py`, a disposable Git-ignored
   analysis script (no runtime source or test was edited), and its artifacts
   `build\f2\f2_run1.json`, `build\f2\f2_run1.txt`, `build\f2\f2_run2.json` and
   `build\f2\f2_run2.txt`: two runs, byte identical, JSON sha256
   `B150BE7A25BF49468ECC15E0204A60AA3D2225293061CB098B0AC8BD4B361DE1` and report sha256
   `D81B26E401564AB82147E87D6A06D25C897661C89E4466494E91E8758D0F726D`. The commands, the
   candidate-order dumps and the offline output are in `docs/live-gateway-runbook.md`,
   "Phase F2 offline classification of the five A1 fact misses, 2026-11-06 (roadmap F2)". The
   focused suites the seam touches - `tests\context\test_builder.py`,
   `tests\context\test_ranking.py`, `tests\pipeline\test_repository_context_stage.py` and
   `tests\observability\test_quality_harness.py` - pass 248/248 unchanged.

3. **F3 - propose one change, only if F1 and F2 say the misses are context-side.** One
   variable on the live path, inside `packages/context` or the repository-context stage.
   It must not turn change-aware ranking on, re-tune its `+25` bonus, raise
   `APP_REPOSITORY_CONTEXT_MAX_TOKENS` as its mechanism (that buys facts with tokens,
   which is the ratio this phase exists to improve), add a Git call, a stage, a persisted
   artifact or a package, or touch `apps/` or the serializer to make a fact appear. If
   F1 and F2 land every open miss in class (d) or (e), this phase records "no change" the
   way B5 recorded its negative result, items 4 to 6 do not run, and the milestone is
   closed. A proposal has to name, before it is built, the fact or facts it expects to
   convert and the token cost it expects to pay.

   **Built and measured 2026-11-06.** The variable was implemented and nothing else was:
   `ContextBuilder`'s default `primary_symbol_max_tokens`, `2048` to `1536`, at
   `packages/context/builder.py:99`. The total budget, `max_symbols`, the 512-token
   supporting pool, the ranking weights, the promotion rules, the serializer, the gateway
   apps and every configuration default are untouched, and the ceiling is still 4096.
   Predicted: `select_last_task_text` (b) to (d) at about zero net prompt tokens, no other
   conversion. Observed offline, over the unchanged `ebb98f9` corpus in both shapes: **the
   conversion did not happen.** The fact stays (b), its literal's count in the serialized
   prompt stays 0, and on that probe the change only shrinks what is sent - 4049 estimated
   context tokens to 3537, 15,319 context characters to 13,351, the delivered package still
   the primary alone. F2's arithmetic was read wrong. `_enforce_budget` pops from the tail, so
   it can deliver only a *prefix* of the promoted order, and the order the promotions build is
   `RepositoryContextStage`, then `RepositoryContextStage._extract_query`, then
   `select_last_task_text` - and the method sits in the primary's own file, so it is charged
   that file's 6,817-character module docstring a second time. The prefix costs, measured over
   the same index at both allowances (`build\f3\f3_prefix_costs.txt`):

   | delivered prefix | at 2048 | at 1536 | fits 4096? |
   |---|---:|---:|---|
   | `[stage]` | 4,049 | 3,537 | yes - what both arms send |
   | `[stage, _extract_query]` | 6,561 | 6,049 | no, in both arms |
   | `[stage, _extract_query, select_last_task_text]` | 6,968 | 6,456 | no, in both arms |

   So the helper is never the symbol the walk drops; it goes on the way past a predecessor that
   no prefix can afford, and the walk settles back to the primary alone. The lever cannot reach
   it at any value: with `primary_symbol_max_tokens` set to 1 token - a package carrying nothing
   of the primary's body but its module docstring - the three-symbol prefix is still 4,921
   tokens against the 4,096 ceiling, and the sweep in `build\f3\f3_gradient.txt` returns one
   delivered symbol at 2048, 1792, 1536, 1280, 1024, 768 and 512 alike. What the change does
   move is breadth on the other probes: 16 of the 22 probe/shape rows differ, across eight of
   the eleven probes - `explain_changed_files_history_cap`, `implement_health_flag` and
   `test_list_content` are delivered identically in both arms. Five probes gain a supporting
   symbol (`explain_live_path`, `multiturn_history_cap_budget`, `multiturn_config_systems`,
   `explain_changed_files_contextbuilder`, `explain_changed_files_repository_index`), eight
   deliver a smaller package somewhere, the `cap_history` occurrence count in the
   production-shaped multiturn history-cap context moves 14 to 18 with the wider package, and
   across all eleven probes no expected fact is gained and none is lost.
   `packages/context/builder.py` keeps (d), the three history-cap facts keep their F2 classes,
   and every arm of every probe stays within 4096 with the configured ceiling unchanged. The
   commands, the two-arm table and the hashes are in `docs/live-gateway-runbook.md`, "Phase
   F3/F4 offline measurement of the primary-allowance candidate, 2026-11-06 (roadmap F3, F4)".

4. **F4 - pin it with focused tests, in the live-path suites that already own the
   behaviour.** `tests/context/test_builder.py` and `tests/context/test_ranking.py` for
   selection and ordering, `tests/pipeline/test_repository_context_stage.py` for what the
   stage sends, and `tests/observability/test_quality_harness.py`, whose offline arms run
   the real stage. Per `TESTING.md`, a test that passes with and without the change
   certifies nothing: record the arm that passes and the arm that fails, and run the
   documented gates - `.venv\Scripts\python.exe -m pytest tests/context tests/pipeline
   -q` and the live-path gate from `CLAUDE.md`,
   `& 'C:\Program Files\Git\bin\bash.exe' scripts/precommit_test_gate.sh`.

   **Pinned 2026-11-06, with four Phase B counters left standing in the way; the F4 tests were
   removed with the reversion on 2026-11-07 (item 6), so none of the tests described in this
   paragraph is in the tree.** Four tests were
   added, two of them before the source was touched, and the two that carry the claim failed
   against the unchanged 2048 behaviour and pass at 1536.
   `tests/context/test_builder.py::TestDefaultPrimaryAllowanceAgainstTotalBudget` is the
   behavioral one - no constant in it: at the default, over a 4096-token budget, the promoted
   supporting symbol reaches the package, the primary stays first, and the budget result stays
   within 4096. At 2048 it did not, and the failure named the absence rather than a number:
   `selected=['packages/pipeline/stages/repository_context.RepositoryContextStage'],
   estimated_tokens=3920 of 4096`. Its companion asserts the direction of the trade - one
   allowance step above whatever the default is, taken from the signature, and the symbol is
   crowded out again - so the first assertion cannot pass by accident.
   `tests/pipeline/test_repository_context_stage.py::TestPrimaryAllowanceAtTheStageBoundary`
   carries the same pair through the real stage, builder, budget engine, composer and OpenAI
   serializer: with the helper next in the order, the trimmed primary hands it the pool and the
   serialized provider request contains `select_last_task_text` - at 2048 it did not, with
   `supporting_symbols=[]` at the same 3920 tokens - and with a same-file symbol in front of it
   the request contains it at neither allowance, which is the live tree's shape and the reason
   F3's prediction failed. That second test is a tripwire, not a certification: it passes
   before and after, and it is the reason the conversion claim is recorded as unproven in the
   suite that owns what the stage sends.
   The documented context/pipeline gate `.venv\Scripts\python.exe -m pytest tests\context
   tests\pipeline -q` passes at 817, scoped ruff and scoped mypy are clean, and the full suite
   reads 47 failed against the documented 43 baseline. The four new failures are all in
   `tests/observability/test_quality_harness.py`: three `test_changed_file_ab_*` counters and
   the weight-5 negative control. They pin measurements Phase B took at the shipped allowance -
   `symbols_promoted` of 0 and 4, a strict-subset relation between two arms' symbol sets, and a
   negative control whose two contexts must be equal - and a second primary-allowance variable
   moves all four, on the clean `ebb98f9` corpus as well as on this checkout's. None of them
   reports a lost fact. Per `CLAUDE.md` they were not re-baselined, weakened, skipped or
   edited; the live-path gate `scripts/precommit_test_gate.sh` therefore blocks on them (4
   failed, 2519 passed, exit 1), and the candidate cannot be carried to a commit in this state.
   This item originally also named a coverage gate script; it was never in the repository and
   no coverage package is installed, so it was not run, and item 4 now names the live-path gate
   instead.

   **State: superseded by item 6 (rejected and reverted 2026-11-07).** At the time of
   measurement 1536 was in the working tree, unaccepted and uncommitted. What F5 was scoped to
   confirm - that a freed primary allowance converts a fact - did not happen offline, so a live
   arm would have measured a smaller prompt and a wider package on other probes, not a
   conversion. Re-baselining the four Phase B counters was neither authorized nor justified by a
   candidate that gains no fact.

5. **F5 - isolated live A/B, context on in both arms.** Current code against the
   candidate, built from two detached worktrees of the same base so the trees differ in
   exactly one variable, launched by `scripts/ab_launcher.py` and measured by
   `scripts/quality_harness.py --base-url ... --model qwen38-27b --max-tokens 8192
   --timeout 345 --repeat 3` against each arm's own log, then
   `scripts/evaluate_quality_harness.py`. Same model, same budget, same probe set,
   `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false` in both arms, no shared session
   log or `EngineeringMemory`. The current-code arm is the control: a cell that
   disagrees with the A1 baseline is re-run or explained before the candidate is judged,
   because run-to-run variance on the answer side is documented at this sample size. Name
   the threshold that counts as a material latency change before measuring, the way E3
   named its 2 ms and 5 ms lines in advance; the proposed floor, to confirm before the
   run, is the candidate arm's mean per-request provider wait within 5% of the control
   arm's, against the A1 context arm's 11.8 s per request (129.6 s over 11) as the
   reference, and no request approaching the 300 s provider or 345 s client ceiling, the
   193.8 s longest request of the baseline run being the shape to watch.

   **Not run.** Both of its prerequisites failed: the offline conversion F3 predicted did not
   happen, and the live-path gate did not pass with the candidate in the tree. No worktree,
   gateway or backend was started for it.

6. **F6 - accept or revert, and record it here.** Accept only with the context arm's
   scored-fact count not lower, the predicted conversions actually converted, no new
   style violation, zero errored and zero timed-out requests, and no latency movement
   past the F5 threshold. Anything else is reverted. The record is the deliverable either
   way: numbers, commit, configuration and the classification from F2 go into
   `docs/live-gateway-runbook.md`, and this roadmap, `docs/STATUS.md` and `CLAUDE.md` say
   what is now true.

   **Closed 2026-11-07: rejected and reverted - Phase F is a measured negative result.** The
   candidate (`primary_symbol_max_tokens` 2048 to 1536, item 3) failed every acceptance
   condition it could be judged on before F5: it did not convert `select_last_task_text`, it
   gained no expected fact across the 11 probes while changing context composition on 8 of
   them (16 of 22 probe/shape rows), and it broke four established Phase B tests in
   `tests/observability/test_quality_harness.py` (`test_changed_file_ab_*`), so the live-path
   gate failed and the full suite rose from the documented 43 failures to 47. The line in
   `packages/context/builder.py` was reverted to 2048 and the four F4 tests were removed from
   `tests/context/test_builder.py` and `tests/pipeline/test_repository_context_stage.py`,
   restoring both files to their pre-F3 state; none was kept, because each encoded either the
   rejected value or the current flawed delivery as expected behaviour. The shipped runtime is
   unchanged and `CLAUDE.md` needs no update. Reversion verification is in
   `docs/live-gateway-runbook.md`, "Phase F3/F4 offline measurement of the primary-allowance
   candidate", subsection *Rejection and reversion (roadmap F6)*.

   What the phase found, recorded for a future milestone and not proposed here: (1) the budget
   walk in `_enforce_budget` can deliver only a prefix of the promoted order, so a promoted
   symbol behind an unaffordable predecessor is unreachable by any allowance; (2) a symbol in
   the primary's own file is charged that file's module docstring a second time. Promotion
   order, docstring accounting, `max_symbols` and preview depth are each a possible future
   investigation that would need its own milestone, its own F2-style classification of the
   reachable set before any prediction, and its own authorization.

**Not part of this phase.** Turning change-aware ranking on or re-tuning its weight
(closed, roadmap B5); activating anything listed in
`docs/dormant-code-backlog.md` - capabilities, tasks, workflows, controller, execution,
verification, modification, patches, session, bootstrap and autonomous stay dark; a true
tokenizer in place of the calibrated `chars_per_token`; semantic or vector retrieval over
the AST index; GitHub API integration; Git snapshot and diff persistence; and any general
autonomous engineering loop. Those stay recorded where they already are - *Explicitly
Deferred* and *Deferred* below - and no item above opens them by accident.

#### Explicitly Deferred

- true tokenizer integration
- semantic/vector search
- GitHub API integration
- Git snapshot/diff persistence
- a general autonomous engineering loop
- wholesale activation of the dormant platform stack

Phases A to E are complete, which closes the sequence agreed on 2026-10-24: A1's
re-run and A2's launcher artifact settled the measurement base, all of Phase B is
settled with the changed-file default and weight unchanged, C1 and A3 are on the live
path, and Phase E's three items are done with it. Phase D items 2 and 3 are standing
policies rather than work left to do, and Phase D item 1's bounded compaction is done
while its policy of keeping these documents true as the path changes never closes.
Phase F above closed 2026-11-07 as a measured negative result with no runtime change.
Dormant packages, true tokenizers, vector search,
GitHub integration, Git snapshot persistence and autonomous execution stay deferred,
as recorded there and below.

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

What came after that judgement:

- keep running `--delta-context` live after gateway changes that touch
  repository context, delta injection, or session logging
- the product item that followed was Repository Context Budgeting And Ranking
  (below), planning-first via the `context_budget_ranking` local-agent-coding
  task. Its Phases A to E are complete, and Phase F, Repository Context Quality
  Per Token (above), measured from 2026-11-06 at `ebb98f9`, closed 2026-11-07 as
  a measured negative result with no runtime change

### 3. Repository Context Budgeting And Ranking — measured, decision closed

History capping works, but repository context often dominates total prompt
tokens. `SEARCH`, `TEST`, `DEBUG`, and now `EXPLAIN` have measured
`APP_REPOSITORY_CONTEXT_INTENT_BUDGETS` overrides (see "Intent budget measurements" under
"Intent Context Budgets" in `docs/live-gateway-runbook.md`).
`REFACTOR` was measured and reverted to the shared 4096 default after live
replication showed a real regression, not noise, at both 2048 and 3072 - see
`docs/live-gateway-runbook.md`, "Intent budget measurements", for the measured
numbers. Ran planning-first via the
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
  change is needed (numbers in `docs/live-gateway-runbook.md`, "Context-selection
  determinism, 2026-08-22")

Where those threads went:

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
`logs\quality_compare_qwen38_chars_per_token_3_5_20260909.json`). Roadmap A3 put
history capping on the same resolved ratio, so an override now reaches the cap as
well as the context budget; a model that overrides nothing is still estimated at
`4.0` in both.

`ModelDefinition.tokenizer` exists as metadata only; the true tokenizer
registry stays deferred unless future measurements justify it.

Investigated 2026-08-10: an apparent 2.17x-3.43x EXPLAIN-intent divergence
turned out to be a stale-budget comparison artifact (the source data predated
an EXPLAIN budget retune by two days) rather than a real tokenizer-accuracy
problem - see "Token-estimate investigation, 2026-08-10" in
`docs/live-gateway-runbook.md` for the full account. No fix implemented; the gate above remains unmet.

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
Measuring which files an agent actually touched was still open at that point;
roadmap C1 has since measured it on the live path and roadmap E1 summarizes its
records.

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
which files an agent actually touched was still open when that run was recorded;
roadmap C1 has since measured it on the live path and roadmap E1 summarizes its
records.


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
