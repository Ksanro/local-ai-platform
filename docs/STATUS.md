# Current Status

This file is the current runtime snapshot. It intentionally describes only
what matters for the live gateway path and calls out dormant code explicitly.

Last reviewed: 2026-10-25 (roadmap item C1 now measures what a conversation's agent
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
records for what a real client sends. C1's incremental latency has not been measured with a
feature-off arm. Before that, B4
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

Uses the startup repository index to select ranked symbols and modules, then
injects repository context into the provider-bound messages. Delta injection
suppresses symbols already sent in the conversation.

Change-aware ranking is opt-in and off by default. With
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=true`, startup takes one
read-only Git change snapshot through `packages.repository.git_changes`
(no new Git commands, nothing persisted) and reduces it to a bounded set of
index module keys - at most 200, rename and copy sources counted alongside
their targets, deletions never. Ranking then adds one flat `+25` bonus
(`RankingConfig.WEIGHT_CHANGED_FILE`) to candidates from those modules, and
only to candidates that already carry a query-match or relationship reason.
Clearing `MINIMUM_CANDIDATE_SCORE` is not enough on its own, because every
public symbol earns the public-name and symbol-type bonuses whether or not the
query mentioned it. Edited files therefore break relevance ties in their favour
without pulling unrelated symbols in; the token budget still decides how many
symbols fit, so the signal reorders the same candidate pool instead of enlarging
it.

The reorder has a bound since 2026-10-25 (roadmap Phase B1). A promoted symbol may
not push the best candidate that earned its place without the bonus out of the
ranked positions that reach the prompt with source text - the primary body and the
one shared supporting preview `ContextBuilder` spends - because a symbol past
those positions keeps its signature and docstring but loses the source body or
preview its implementation facts are read from. `RankingEngine.rank` restores such
a symbol to the last of those positions
(`RankingConfig.PROMOTION_ANCHOR_SLOTS`) when its module matched the query, it
held one of them on a clean tree, and the bonus is what moved it out - the scan
runs over every candidate the promotion passed over, not only the first, because
the first may still hold a slot while a later one has lost its only one. The dirty
file may still win the primary, which is what the signal is for. Nothing else
about the bonus changed: same gate, same `+25`, same reasons, same counters, and
no guard pass at all when the bonus touched nothing - a disabled feature and a
clean tree rank exactly as they did before.

The counterfactual that makes promotion measurable is opt-in since 2026-10-25
(roadmap B4). `RepositoryContextStage` builds the no-bonus context only when
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED=true`, which the gateway
passes through at startup and which is off by default: an ordinary enabled request
now composes, serializes and sends its change-aware context once, where it used to
compose it twice - B3 priced that second build at roughly 450 ms of a live
request's wall time. What a request can state without a counterfactual is
unchanged and still exact: `changed_files_signal`, `changed_files_count`,
`changed_symbols_selected` and the rest of the direct counts. What needs one -
`changed_context_differs`, `changed_primary_promoted`, `changed_symbols_promoted` -
keeps its field, name and type and is inert, and
`changed_baseline_status="not_sampled"` is what says so, so such a record cannot be
read as a comparison that found no difference. The setting changes nothing about
what is sent, and on its own it switches on neither the ranking bonus nor the Git
snapshot: with the feature off the status stays `none`. `scripts/ab_launcher.py`
declares it `true` in the shared block of every experiment it renders and refuses a
changed-file A/B that declines it, and the offline probes in
`scripts/quality_harness.py` build with it on, so a controlled comparison still
measures what B3 measured.

How large that bonus should be is measured, and still open. Two terms have to be
kept apart, because `EXACT_SYMBOL_NAME` fires when *any* segment of a qualified
name equals a query token - the module-path segments included. A **name match**
can therefore come from a file path alone; being **named in the query** means the
prompt contains the symbol's own name. Measured over this repository's real index
(508 modules, 8571 symbols on this checkout, dirty modules injected rather than
read from Git, so the working tree is irrelevant) by `scripts/quality_harness.py
--changed-file-probe`, which runs `RepositoryContextStage` on both arms at the
configured 4096-token budget and reads its own counters back:

- a query that names `ContextBuilder` holds its primary at `+5` and `+10` and
  loses it from `+15` to `ContextBudget` in a dirty `packages/context/budget.py`,
  which sits 15 points behind and sorts first on the tie-break - so the ceiling
  for that case is the gap itself, not the gap plus one;
- what that swap costs is nothing, and that is worth recording because it is the
  claim this feature first tried to make live. The bonus puts the dirty file's two
  symbols in front of the builder file's three rather than in place of them, so
  `ContextBuilder`, `_enforce_budget` and `packages/context/builder.py` are all in
  the text of both arms and a changed-arm answer can be exactly as correct as the
  baseline one. A moved primary is not a measured effect;
- a dirty file the query never mentions changes nothing at any weight, and says so
  with `changed_baseline_status=skipped_no_bonus`;
- `--changed-file-sweep` reports, for 12 fixed queries, the smallest bonus that
  would hand the primary to a symbol in another file. Six of the twelve are
  decided by a tie and flip at `+1`; the other six flip at 10, 15, 21, 30, 30 and
  70. The size of the bonus therefore buys nothing in the tie case, which is the
  case the feature exists for, and only decides how far behind a name-matched
  competitor the working tree can reach.
- the size is also not what changes most contexts. With
  `packages/repository/index/models.py` dirty, the query "how does model
  resolution pick a backend" sends 12 symbols the no-bonus context did not at both
  `+5` and `+10` (13 at `+25`) while the primary stays put: the token `model` is a
  segment of that module path and `MODULE_MATCH` counts as query relevance, so the
  gate admits the whole file. Shrinking the bonus does not undo that.
- one query did lose something, and what it lost was a file - the case the bound
  above exists for. "How does the
  repository index builder construct the index, including its collaborators for
  files and models?" with `packages/repository/index/models.py` dirty sent 10 symbols
  instead of 14: the dirty module's symbols took the front of the order, the
  budget ran out inside `packages/repository/index/models.py`, and
  `packages/repository/index/builder.py` left the context outright.
  `PythonAstExtractor`, `RelationshipRegistry`, and `CallExtractor` were available
  in the arm with the bonus off and unavailable in the arm with it on -
  `facts_lost` said all three, none could be copied from the question, and no symbol
  of that file survived to be
  counted as still-visible. It happened at `+1` exactly as at `+25`
  (`changed_symbols_promoted=0`, `changed_primary_promoted=1`), so the lever was
  the gate and the rendered prefix rather than the number. Measured again on
  2026-10-25 with the guard in place, the same run still sends 10 symbols, still
  moves the primary into the dirty file, and loses nothing: the builder file's own
  best symbol is restored to the supporting slot and the three facts stay available
  on both arms. Keeping *a* symbol of that file was not enough on its own - the
  form of this rule that only kept one in the list measured `1/3` - and at 6144
  tokens, where both files' symbols fit either way, the two arms now agree on all
  three facts as well.
- one query gains instead, and it is the case the opt-in is offered for. "How does the
  gateway cap conversation history before sending it to the model?" with
  `packages/pipeline/history` dirty sends 7 symbols instead of 20, four of them new
  (`cap_history`, `_build_cap_groups`, `_cap_current_tool_result`, `_estimate_tokens`),
  and the facts its text can support go `1/4` to `4/4` with `facts_lost` empty: the
  disabled arm sees the cap's call sites and can say history is capped, and cannot say
  how. Registered as `gains_the_changed_file`, it reports `MOVE` - the primary moves
  into the changed file, which is what the case is for - and its scored half,
  `explain_changed_files_history_cap`, is the pair the 2026-10-13 live run used.

`+5` came out of this pass as a candidate, not as shipped behavior. The value in
`RankingConfig.WEIGHT_CHANGED_FILE` is unchanged at `+25`; the live replicated
comparison ran on 2026-10-12 against the vLLM backend and separated the arms the way
the offline case predicts - `9/9` expected facts with the flag off over three
repeats, `0/9` with it on, one identical prompt and one
`APP_REPOSITORY_CONTEXT_MAX_TOKENS=4096`, the enabled arm sending 8 symbols where
the disabled arm sent 11 and losing `packages/repository/index/builder.py`
altogether (`prompt_tokens` 3589 against 3342). Two limits on that number are part
of it: the flag is global, so the enabled arm applied the bonus across the 18
locally modified indexed modules of this tree rather than the experiment's single
marker, and two of its three answers ran to the 8192-token completion ceiling
instead of ending short. The other half of the decision was measured on 2026-10-13 on
`explain_changed_files_history_cap`, with both gateways started inside one detached
worktree of this commit so that the marker in `packages/pipeline/history.py` was the
only dirty indexed module either arm could see: feature off `3/12` (1/4 on every
repeat), feature on `8/12` (3/4, 3/4, 2/4), with `max_current_tool_result_tokens` named
in 3/3 of the enabled answers and `_looks_like_cline_tool_result_message` in 2/3, and
neither named in any disabled answer. Within each arm the context was identical across
repeats - 20 symbols and `estimated_tokens` 2807 disabled against 7 symbols and 4087
enabled - and every request sent to either gateway, in every pass, carried the same
77-character prompt text with the same SHA-256 prefix and no answer near the completion
ceiling. The enabled records read `changed_files_count=1`, `changed_context_differs=true`,
`changed_primary_promoted=true`, `changed_symbols_promoted=4`,
`changed_baseline_status=built` while the disabled records read `off`, `false` and
zeros. Two details belong to that measurement: three of the nine enabled requests sent
before that pass were lost to the gateway's own 60-second provider timeout, which
the isolated launcher had not raised to the harness `--timeout 300`, and the enabled arm
pays 402-507 ms per request for the counterfactual baseline that produces those
counters. The fourth fact, the `truncated by gateway history cap` marker, was quoted by
neither arm, which is the answer side saying it wants a string verbatim - `4/4` offline
is about the text sent, not about what a model repeats.

All three pairs were measured again live on 2026-10-25, with the guard in the build
(roadmap B3), from one detached worktree of `57bd045` that held no `.env` and whose only
difference from a clean checkout was the pair's own comment-only marker - so
`changed_files_count` read 1 on every enabled record, rather than the 18 locally modified
indexed modules that confounded the 2026-10-12 pass. Every gate passed: eviction `9/9` off
against `9/9` on, gain `3/12` off against `8/12` on, negative control `9/9` in both arms, the
observable context fingerprint identical across the three repeats inside all six arms while the
answers were not, and no error, timeout, budget overrun or style problem in any of the eighteen
requests. The fingerprint is what a session record can witness - `primary_symbol`,
`symbols_selected`, `estimated_tokens`, `prompt_tokens` and the seven `changed_*` fields - and
not the ordered supporting-symbol list, so the exact live order is not claimed here; ordered
determinism belongs to the offline probe and to the ranking tests
(`tests/context/test_ranking_v2.py::TestDeterministicOrdering::test_repeated_runs_produce_same_order`).
Latency came out 9.7 s higher across the nine enabled requests than across the nine disabled
ones, about 4.2 s of it the counterfactual build and the rest provider spread that ran the
other way in the control pair, which is no unexplained or material regression in a sample this
size rather than no difference. The eviction pair is the one that decides B3: the enabled arm's
context still differs from its
own no-bonus baseline on every record (`changed_context_differs=true`,
`changed_primary_promoted=true`, `changed_symbols_promoted=1`, the primary moved into the
dirty file, 9 symbols where the disabled arm sent 11) and it now loses none of the three
`packages/repository/index/builder.py` facts, so the guard survives `ContextBuilder`'s own
promotions, the serializer and a live request. Its price is measured too: 409-542 ms of
every enabled request goes into the counterfactual build that produces those counters, which
is B4's target rather than a B3 change, and a passing B3 does not authorize the default -
the `+25` weight and the off-by-default flag are untouched. One caveat the run exposed
without touching: the offline probe's symbol tallies run higher than the live arms' because
`_stage_arm` builds a bare `PipelineContext` with no resolved model and so budgets at the
platform's 4.0 chars per token instead of the alias's calibrated 3.5 - the same in both arms,
so it moves no verdict. It is an offline-probe calibration gap of its own, and not the gap
item A3 is about: A3 concerns history capping using the resolved model's `chars_per_token`,
and this run neither advances it nor closes it. Per-repeat tables, launcher
configuration, promotion counters and the recorded confounds are in
`docs/live-gateway-runbook.md`,
"Isolated-worktree promotion-guard A/B, 2026-10-25 (roadmap B3)".

That comparison now has its instrument, and the two halves of it ask one question
each. The eviction case is registered in the ordinary scored probe set as
`explain_changed_files_repository_index`, and its three facts -
`PythonAstExtractor`, `RelationshipRegistry`, and `CallExtractor` - are the three
implementation collaborators the offline arm reports losing: none appears in the
prompt to be copied from it, and none survives in the
context the dirty file replaces the builder with. `CONTEXT_BUILDER_BUDGET_QUERY`,
`REPOSITORY_INDEX_BUILD_QUERY` and `HISTORY_CAP_QUERY` are the prompts both halves of a
pair send, and
`CHANGED_FILE_AB_PAIRS` names the pairs, so an offline case and its live probe
cannot drift into measuring two retrievals - the flaw in the first version of this
comparison, which appended its own wording to the scored probe and then attributed
a retrieval difference to the bonus.
`explain_changed_files_contextbuilder` stays registered as the negative control of
the same design: identical prompt on both sides, an arm-to-arm reorder that costs
no context, and 3/3 expected on both sides. `explain_changed_files_history_cap` is that
design on the gain side: `HISTORY_CAP_QUERY`, whose dirty `packages/pipeline/history`
adds the cap's implementation to the context and takes nothing scored out of it, so the
pair measures an addition rather than a trade.
`tests/observability/test_quality_harness.py` runs the real
`RepositoryContextStage` over this checkout's index for both arms of every pair and
asserts the difference in what the two contexts can support, so the claim is a
regression test and not a handcrafted pair of answers. The `--changed-file-probe`
cases stay supporting diagnostics for retrieval, and their verdict rule keeps them
honest: a case holds only when both arms sent its expected primary, which the gain case
forced the rule to grow around - it reports `MOVE` when the primary arrives inside the
changed file, and that counts as the case working. An arm that
was already wrong before the bonus was switched on reports `BAD_BASELINE` rather
than passing. Registered here, the probes join the fixed set, which is now 11 probes
and 30 expected facts - the `20/20` baselines in these docs are the earlier
denominator. The live runs happened on 2026-10-12 and 2026-10-13 and are recorded in
`docs/live-gateway-runbook.md`; the weight remains comparable without editing code
through
`--changed-file-probe --changed-file-weight 5`.
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS` (default `0`) optionally
refreshes the snapshot once per window through
`packages.repository.changed_files_refresh`, a background task started during
lifespan startup that calls the signal on a worker thread, so refreshing never
runs inside a request; with the default
`0`, "currently being edited" means "dirty when the gateway started", exactly
like the index itself. A clean tree, a directory without Git metadata, and a
failed snapshot all fall back to today's behaviour.
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED` (default `false`,
roadmap B4) is a third, separate opt-in: it lets the stage build the no-bonus
context that `changed_context_differs`, `changed_primary_promoted` and
`changed_symbols_promoted` are measured from, it changes nothing about the
context that is sent, and on its own it switches on neither the ranking bonus nor
the Git snapshot - startup states it as
`changed_files_comparison enabled=true|false` either way. Paths are matched after
`realpath`, so a repository configured through a symlink, junction, `subst`
drive or 8.3 short name still works, and the count of paths that resolve
outside the indexed root is reported. Logs and stage data carry counts only -
never paths, module names or file contents. Seven count-only fields make the
promotion itself observable, on the per-request log line, in the stage result,
and in the session record's `context` block:

- `changed_files_signal` - whether the working-tree source was usable: `off`
  (none configured), `ok` (it answered, including with a clean tree), or
  `unavailable` (it raised, or the stage failed before it could be read). A
  request whose stage assembled nothing still states the state that was read,
  so a degraded request never records as a disabled feature;
- `changed_files_count` - how many locally modified files the signal mapped onto
  indexed modules (`0` with `ok` means a clean tree);
- `changed_symbols_selected` - how many of the symbols that were actually sent
  carry the change-aware reason;
- `changed_context_differs` - whether the context that was sent differs from the
  same request composed without the bonus. This is the measurement: the whole
  composed package is compared, so order counts, and a flat bonus - which is a
  reordering signal - can no longer be mistaken for "nothing happened";
- `changed_symbols_promoted` - how many of the sent symbols are absent from the
  same request re-ranked without the bonus, including symbols outside the
  changed modules that entered through relationship expansion once the primary
  changed;
- `changed_primary_promoted` - whether the bonus changed the primary symbol;
- `changed_baseline_status` - whether that comparison ran: `none` (nothing to
  compare), `built` (compared), `skipped_no_bonus` (no candidate received the
  bonus, so the two contexts are identical by construction), `not_sampled` (the
  bonus fired and the comparison was deliberately not asked for, which is what an
  ordinary enabled request records since roadmap B4), or `failed` (the comparison
  was asked for and could not be built - an unmeasurable request, not an inert
  one). Only `built` and `skipped_no_bonus` make the three `*_promoted` /
  `*_differs` fields readings; on `not_sampled` and `failed` they are placeholders
  and the status is what says so.

The counters describe the final context - after budget trimming and delta
suppression - so a promoted candidate that did not survive the budget is not
counted, while `changed_files_count` still reports the files that were seen.
That split is what makes the claim falsifiable:
`changed_files_signal="ok"`, `changed_files_count >= 1`,
`changed_baseline_status="built"` and `changed_context_differs=true` proves the
bonus changed what was sent; a record with `changed_primary_promoted=false` and
`changed_symbols_promoted=0` inside that proof is the reorder-only case.
`changed_symbols_selected` above zero with `changed_context_differs=false` and a
status of `built` or `skipped_no_bonus` proves it was present and changed
nothing. `not_sampled` and `failed` prove nothing at all: on the first the
comparison was declined, on the second it was tried and could not be made, and
neither is the finding that the bonus changed nothing.
`changed_files_count` above zero
with `changed_symbols_selected` zero means the tree was dirty and nothing
qualified, which is a selection-gate result rather than a broken signal.
Building the comparison context costs a second full context build: measured on
this repository's real index (328 modules, 8 changed) about 50 ms becomes about
105 ms per request on a dirty tree, and B3 measured roughly 450 ms of a live
enabled request. Since roadmap B4 it is paid only when
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED=true` - off by default,
so an ordinary request does not pay it at all - and then only when the ranking
pass gave the bonus to at least one candidate: `changed_modules` reaches nothing
else in the builder, which makes that second skip exact. The cost of a build that
was made is reported as `changed_baseline_ms` on the log line only and never
recorded; a request that skipped the comparison reports `0`.
`scripts/analyze_sessions.py` aggregates the fields from session JSONL without
reading any content, tallies `proved` (with a primary-changed,
membership-changed and reorder-only breakdown) apart from `present but inert` and
`unmeasured` - which is where a `not_sampled` record lands - keeps the unmeasured
records out of the counterfactual counts and their rate, which divide by the
records whose comparison was made or proved unnecessary, and separates records
that predate them from every rate - see the
runbook.

Roadmap C1 adds a second, unrelated measurement to the same record:
`context.file_activity`, seventeen keys of nothing but integers and two state tokens.
`RepositoryContextStage` reads the Cline tool-result envelopes already present in the
request's messages (`packages/pipeline/cline_activity.py`), normalizes every target
against the repository root and refuses the ones that do not live inside it
(`paths_rejected` counts refused envelopes and never paths), and reports which files
this conversation's agent read and wrote and how many of them it had already been
shown as context (`packages/pipeline/file_activity.py`, an LRU-bounded store of
transcript-prefix states sized with `APP_CONTEXT_DELTA_CACHE_SIZE` - states, not
conversations: one conversation adds an entry per request that answered one of its
earlier prefixes, so a long one spends many). Those numbers are a **snapshot recomputed
from the transcript of the request being answered**, not a tally: the same transcript and
the same supplied-context state produce the same dict, which is the right model precisely
because a Cline client re-sends its whole conversation every turn, so there is nothing to
accumulate and nothing left to suppress on a replay. Attempts are kept apart from
outcomes - `read_attempts`/`reads_failed`/`reads_unknown` and
`modification_attempts`/`modifications_not_modified`/`modifications_unknown` partition
unique files, a file's outcome being decided by precedence (confirmed, then
failed/not-modified, then unknown) rather than by whichever envelope arrived first - and
the one genuinely temporal quantity, `context_files_touched`, is credited **before** this
request's supplied files are recorded, so a file an earlier turn touched is never
re-attributed to context that arrived later. `state` says whether the transcript was read
at all (`measured`, `none`, `partial`, `unavailable`) and `correlation` says whether the
gateway was in a position to know what had been supplied (`measured`, `no_prior_context`,
`tracker_miss`, `unavailable`), a miss being reported as a zero that is not a measurement
and being **sticky**: the request that finds its remembered prefix missing marks that
lineage discontinuous, so every later request in the conversation keeps reporting the miss
instead of resuming `measured` over a partition it cannot reconstruct. `unavailable` is the
inert shape and a zero is never a substitute for it. No file path crosses the stage boundary
or reaches the record, and resolution of the paths in it is memoized only for the duration of
one request.

The mechanics - the accepted grammar and its bounds, the outcome precedence, the
correlation ordering rules, every constant, and what each of the seventeen keys means -
are in `docs/live-gateway-runbook.md`, section *Conversation File Activity (roadmap C1)*.
That section also carries the evidence: **C1 received its first restarted-gateway live
validation on 2026-10-26** - vLLM `qwen3.8-flash-next` behind the gateway alias
`qwen38-27b`, four requests, one session record each. The shape moved from
`state=none`/`correlation=no_prior_context` on a request carrying no envelope to
`state=measured`/`correlation=measured` with `context_files_touched=1` on the request that
reported reading a file request one had already been given, and an unchanged replay returned
the identical dictionary. **Those four requests were scripted by the probe, not produced by a
Cline client** - they validate the gateway's read of a transcript, not the grammar against the
client. What the client does send is settled from this repository's own session records instead
(same section): 515 records carry an anchored Cline envelope, among them 315 `read_file`, 108
`search_files`, 49 `list_files`, 29 `execute_command`, 5 `replace_in_file` and 2 `write_to_file`.
Every writer result begins `The content was successfully saved to ...` and classifies as a
confirmed modification - seven for seven - reads split 284 confirmed against 31 failed on the
anchored failure prefix, and every envelope arrived under `role="user"`. 72 of those 284 are
Cline's `[DUPLICATE READ] You have already read ...` notice, which says the content was not sent
again and which the anchored rule does not treat as a failure; that is recorded, not fixed,
because changing it changes what `files_read` means. Six
`[ask_followup_question for ...]` headers are real Cline traffic the gateway does not recognize,
which is correct for a grammar it has not verified. No native Cline task was run through a
restarted gateway for this pass, and nothing was added to the grammar on the strength of the
records alone. What the run and the survey do not show is any quality, ranking or performance
effect: C1 decides nothing about what is sent, and no feature-off arm ran beside it, so its
latency cost is unmeasured and it remains unvalidated as an input to context quality.

The one place C1 reached past observation has been pulled back. Its first version widened
`CLINE_TOOL_RESULT_PREFIXES` - what the history cap truncates and what planning text selection
ignores - by deriving it from the file-activity tool set, which made write and replace results
into truncation targets and dropped them from query text. `packages/pipeline/user_messages.py`
now holds one envelope registry and derives two views from it: recognition, which includes
`write_to_file` and `replace_in_file`, and the planning/history compatibility set, which is
byte-for-byte the pre-C1 tuple. A writer's result is counted and reaches the model whole.

Three things that look like failures are not. A target that does not exist on disk is
still measurable - containment resolves both sides with `realpath(strict=False)`, so the
file a write is about to create measures like one already there, and only a root the
filesystem refuses to name at all marks the measurement unavailable. A file dropped
because a stored state already holds `MAX_UNIQUE_FILES_PER_STATE` distinct files
is counted in `events_beyond_bound` and not in `paths_rejected`: the path was fine, the
bound was not. And a Windows drive-absolute target (`C:\Users\dev\repo\x.py`) was the one
spelling that used to be read as relative and joined onto the root, landing outside it;
it is now recognized as absolute before any joining is attempted.

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
At that point `CHARS_PER_TOKEN = 4.0` was unchanged; no tokenizer-accuracy
problem was measured. The real, smaller question that remained open was the
run-to-run
variance already noted above (`explain_live_path` ranged 1119-1975 tokens
across 3 replicates at the same 2048 budget on 2026-08-09) - a
context-selection determinism question, not a token-estimation-accuracy one.
That question was closed on 2026-08-22 (see the determinism note below).

The context-selection determinism question was closed on 2026-08-22 on the
stack in use then (qwen38-27b via SGLang, `EXPLAIN:4096`):

- Phase 1 (in-process): 3 EXPLAIN probes x 3 repeats produced byte-identical
  context fields on every repeat - `explain_live_path` prompt_tokens=4132,
  estimated_tokens=4036, primary `apps/gateway/main.lifespan`;
  `multiturn_history_cap_budget` 3997 / 3892, primary
  `packages/pipeline/engine._apply_history_cap`; `multiturn_config_systems`
  4443 / 3861, primary `packages/providers/vllm._get_vllm_config`.
- Phase 2 (across restart): after a full gateway stop/restart on an
  unchanged repo and `.env`, re-runs of `explain_live_path` and
  `multiturn_config_systems` matched Phase 1 exactly.

Conclusion for that pass: on the repo and `.env` as they stood on 2026-08-22,
qwen38/SGLang + `EXPLAIN:4096`
context selection is deterministic within a gateway process and across
gateway restarts. Remaining run-to-run variance is model-side sampling
(answer wording, `completion_tokens`, wall-clock seconds). No code fix was
warranted.

On 2026-09-09 repository-context token accounting moved from the global
`CHARS_PER_TOKEN = 4.0` to per-model calibration: `ModelDefinition.chars_per_token`
(default `4.0`) is resolved from the request's resolved model and drives the
repository-context budget estimate. `qwen38-27b` is calibrated to `3.5`.
Live validation on qwen38-27b/SGLang (`--compare-context` with context): the
`4.0` baseline had 5 of 8 probes with measured context cost over their intent
budget; with `3.5` it is 0 of 8, with no fact misses and no style regressions.
Baseline run: `logs\quality_compare_qwen38_token_estimate_20260909.json`;
calibrated run: `logs\quality_compare_qwen38_chars_per_token_3_5_20260909.json`.
The inherited `3.5` ratio was revalidated on 2026-10-10 after the gateway alias
was moved to `qwen3.8-flash-next`: all 8 measured context costs stayed below
their estimates (measured/estimated ratio `0.82x-0.96x`) with 0 budget
overages. The same context-on/context-off run scored `20/20` versus `3/20`.
History capping is not affected and still uses the platform default
`CHARS_PER_TOKEN = 4.0` estimate. True tokenizer integration remains out of
scope (deferred).

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
  size is an open decision, see the 2026-10-11 note above; off
  by default, `apps/gateway/main.py` ->
  `RepositoryContextStage` -> `ContextBuilder` -> `RankingEngine`)
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
  regression - see `docs/roadmap.md` section 3 and the "RepositoryContextStage"
  section above for the measured numbers.
- The model often includes reasoning/preamble despite terse system prompts; the
  quality harness now records deterministic style violations separately from
  required-fact score.
- Repository-context token estimates now use a per-model calibrated
  characters-per-token ratio (`ModelDefinition.chars_per_token`, default
  `4.0`; qwen38-27b `3.5`), live-validated 2026-09-09: measured context-cost
  overages went 5/8 at 4.0 -> 0/8 at 3.5 with no quality or style regression.
  History capping still uses the platform default estimate. True tokenizer
  integration is out of scope/deferred.
