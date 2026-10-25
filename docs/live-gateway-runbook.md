# Live Gateway Runbook

Use this when an agent or operator needs to run live gateway probes from a
fresh terminal.

Run `uv` as `.\uv.exe` from the repo root. `uv` is not assumed to be on `PATH`.

Use PowerShell for these commands. If an agent is in Bash/Git Bash/WSL, do not
translate the commands unless explicitly asked. Run the PowerShell command blocks
through `powershell.exe -NoProfile -Command "..."`.

Important: `apps/gateway/main.py` loads `.env` with `override=True`. Values in
`.env` can override shell environment variables passed when starting the
gateway. Before live probes, check `.env` for `APP_SESSION_LOG_PATH` and either
use that same path in `--session-log-path` or update `.env` for the run.

Current local backend: vLLM serves `qwen3.8-flash-next` at
`http://100.106.236.88:18300/v1`, exposed through the gateway as
`qwen38-27b` with provider `openai`. That provider is intentional: `openai` is
the plain OpenAI-compatible client (`packages/providers/openai.py`), and a vLLM
server speaks that protocol - it is not a stale reference to a different
engine. `GET /v1/models` on the endpoint answers with `owned_by: vllm` and
`max_model_len: 400000`, last verified directly on 2026-10-12, so the backend is
reachable and a live run only needs the local gateway on `:8001` started. The
Codex sandbox may fail direct TCP checks to this port with `Bad access`; retry
endpoint checks with approved unsandboxed `curl.exe` before treating the backend
as unavailable.

## Start Gateway

From the repo root, in a terminal that will stay open:

```powershell
$env:UV_CACHE_DIR='C:\Users\ovidi\local-ai-platform\.uv-cache'
$env:APP_SESSION_LOG_ENABLED='true'
$env:APP_SESSION_LOG_PATH='logs\sessions.jsonl'
$env:APP_CONTEXT_DELTA_INJECTION='true'
New-Item -ItemType Directory -Force logs | Out-Null
New-Item -ItemType File -Force logs\sessions.jsonl | Out-Null
.\uv.exe run python -m uvicorn apps.gateway.main:create_app --factory --port 8001
```

Leave this terminal running.

If the agent shell is Bash/Git Bash, start the same gateway with:

```bash
powershell.exe -NoProfile -Command "Set-Location 'C:\Users\ovidi\local-ai-platform'; `$env:UV_CACHE_DIR='C:\Users\ovidi\local-ai-platform\.uv-cache'; `$env:APP_SESSION_LOG_ENABLED='true'; `$env:APP_SESSION_LOG_PATH='logs\sessions.jsonl'; `$env:APP_CONTEXT_DELTA_INJECTION='true'; New-Item -ItemType Directory -Force logs | Out-Null; New-Item -ItemType File -Force logs\sessions.jsonl | Out-Null; .\uv.exe run python -m uvicorn apps.gateway.main:create_app --factory --port 8001"
```

## Check Gateway

In a second terminal:

```powershell
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/v1/models
```

If the agent shell is Bash/Git Bash:

```bash
powershell.exe -NoProfile -Command "curl http://127.0.0.1:8001/health; curl http://127.0.0.1:8001/v1/models"
```

If `/health` fails, the gateway is not running. If `/v1/models` fails, the
gateway may be running but the provider/model path is not ready.

## Runtime Context Introspection

When the gateway is running, inspect the live runtime configuration without
reading `.env` or the docs. This is a read-only, non-liveness debug endpoint
that never mutates settings, state, or storage:

```powershell
curl http://127.0.0.1:8001/debug/runtime-context
```

For an agent shell in Bash/Git Bash:

```bash
powershell.exe -NoProfile -Command "curl http://127.0.0.1:8001/debug/runtime-context"
```

Inspect:

- `default_model` / `default_provider` - the settings-driven routing defaults
- `routing_mode` - `models_config`, `fallback`, or `none`
- `models[].base_url` and `models[].backend_model` - where each alias routes
- `models[].chars_per_token` - the calibrated chars-per-token ratio used for
  repository-context budgeting (platform default 4.0; in fallback mode the
  platform default is reported)
- `repository_context_intent_budget_map` - per-intent context budgets
- `quality_baseline.available` and `quality_baseline.latest_score` - persisted
  quality-harness history (empty until a run is stored)
- `gateway_session_summary.available`, `gateway_session_summary.success_rate`,
  and `gateway_session_summary.recent_errors` - persisted gateway session-log
  summary (empty until records are ingested)

Provider secrets such as `api_key` are never serialized.

## Integration Test Note

`tests/integration/test_gateway_to_vllm.py` skips itself unless
`DEFAULT_MODEL` appears in the gateway's `/v1/models` list. To run it live,
make `DEFAULT_MODEL` visible to pytest with a served alias such as
`qwen38-27b`. For full-suite runs that import gateway settings, keep `.env`
aligned too because `load_dotenv(override=True)` can override shell values.

## Delta Context Smoke

Use the same session log path that the gateway was started with. If `.env`
contains `APP_SESSION_LOG_PATH=...`, pass that exact path to
`--session-log-path`.

```powershell
Remove-Item logs\sessions.jsonl -ErrorAction SilentlyContinue
New-Item -ItemType File -Force logs\sessions.jsonl | Out-Null
.\uv.exe run python scripts\quality_harness.py --delta-context --session-log-path logs\sessions.jsonl
```

For the current local `.env`, if it still contains
`APP_SESSION_LOG_PATH=logs/implement_budget_A_4096_20260801.jsonl`, use:

```powershell
.\uv.exe run python scripts\quality_harness.py --delta-context --session-log-path logs\implement_budget_A_4096_20260801.jsonl
```

If the agent shell is Bash/Git Bash:

```bash
powershell.exe -NoProfile -Command "Set-Location 'C:\Users\ovidi\local-ai-platform'; Remove-Item logs\sessions.jsonl -ErrorAction SilentlyContinue; New-Item -ItemType File -Force logs\sessions.jsonl | Out-Null; .\uv.exe run python scripts\quality_harness.py --delta-context --session-log-path logs\sessions.jsonl"
```

If `.env` points at `logs/implement_budget_A_4096_20260801.jsonl`, use that
same path in Bash/Git Bash too:

```bash
powershell.exe -NoProfile -Command "Set-Location 'C:\Users\ovidi\local-ai-platform'; .\uv.exe run python scripts\quality_harness.py --delta-context --session-log-path logs\implement_budget_A_4096_20260801.jsonl"
```

Pass means:

- `ok: True`
- first request scores all expected facts
- follow-up request scores all expected facts
- follow-up context has `symbols_suppressed > 0`

Blocked means:

- gateway unavailable
- backend unavailable or crashed (any OpenAI-compatible server behind the gateway)
- backend timeout/API 500/context-size error
- `session_log_records_not_found` after the harness completes

A missing log file before the first chat request is not a failure. The gateway
creates and writes the file on completed `/v1/chat/completions` requests.

## Focused Probe (--probe)

`--probe <id>` runs only the named probe instead of the full fixed set.
Multiple `--probe` flags are allowed; duplicate ids are deduplicated; unknown
ids return exit code 2 with a list of known ids.

```powershell
.\uv.exe run python scripts\quality_harness.py --probe multiturn_history_cap_budget --json --max-tokens 900 --model local-model
```

`--probe` is allowed with `--compare-context` (filters both sides) but
disallowed with `--delta-context`.

## Repeated Probe (--repeat)

`--repeat N` runs the selected probes N times and reports per-run results
plus an aggregate summary. Default is `--repeat 1` (single run, unchanged
behavior). `--repeat N > 1` is disallowed with `--delta-context` and
`--compare-context`.

When `--json` is used with `--repeat 1`, output remains a flat list (backward
compatible). When `--repeat N > 1` with `--json`, output is a repeat envelope:
`{"repeat": N, "runs": [...], "aggregate": {...}}`.

Interpreting repeats: with an unchanged repo and `.env`, context fields and
`prompt_tokens` are expected to be identical across repeats (verified
2026-08-22 on qwen38-27b/SGLang with `EXPLAIN:4096`); differences in answer
wording, `completion_tokens`, hits, or seconds between repeats are model-side
sampling variance, not context-selection drift.

```powershell
.\uv.exe run python scripts\quality_harness.py --probe multiturn_history_cap_budget --repeat 3 --json --max-tokens 900 --model local-model
```

For reasoning-heavy models, configure warnings with
`APP_QUALITY_REASONING_MODELS=model-a,model-b` or pass
`--reasoning-model <model>`. Use `--max-tokens 2048` or higher when the model
spends significant budget on hidden reasoning tokens.

## Intent Context Budgets

The current `.env` uses
`APP_REPOSITORY_CONTEXT_INTENT_BUDGETS=SEARCH:2048,TEST:2048,DEBUG:2048,REFACTOR:4096,IMPLEMENT:4096,EXPLAIN:4096`.
EXPLAIN is `4096`: the `2048` budget dropped
`apps/gateway/core/config.Settings` from EXPLAIN context assembly and caused a
repeatable `multiturn_config_systems` miss. Restart the gateway after changing
`.env` so new budgets apply.

## Change-Aware Ranking (Optional)

Change-aware ranking lets locally modified files pull their symbols forward in
repository-context ranking. It is off by default and reuses the read-only
snapshot behind `scripts/git_change_snapshot.py` - no new Git command runs, and
each snapshot is bounded by a 30 second command timeout. Only symbols that
already carry a query-match or relationship reason can win the bonus; a public
symbol the query never touched keeps its position no matter how dirty its file
is. The bonus may not, however, be the reason a module the question pointed at
stops contributing anything to the prompt - see "The Phase B1 promotion guard"
below. The bonus itself is `RankingConfig.WEIGHT_CHANGED_FILE` (`+25` on the default
profile). Its size is an open decision, not a settled one: between two candidates
of equal relevance any nonzero value decides the order, so the size buys nothing
there, and against a candidate that only reached the query by a name segment the
size is exactly how far behind it may sit and still take the primary. Note the
term: `EXACT_SYMBOL_NAME` counts a **name match**, which includes the module-path
segments, so a prompt can name-match a symbol without naming it; **named in the
query** is the stricter condition and is the one worth protecting.

Both modes below are offline and deterministic, index this repository once, and
inject the dirty module rather than asking Git - a clean checkout measures the same
thing. They print symbol names and module keys, which is fine for a developer tool
that sends no request and writes no session record; nothing they print comes from
or goes into the promotion-observability fields.

```powershell
.\uv.exe run python scripts\quality_harness.py --changed-file-probe
.\uv.exe run python scripts\quality_harness.py --changed-file-probe --changed-file-weight 5
.\uv.exe run python scripts\quality_harness.py --changed-file-sweep
```

`--changed-file-probe` runs each registered case through `RepositoryContextStage`
twice - once with the signal off, once with one module injected as dirty - and
reports the primary from both arms, the stage's own `changed_context_differs`,
`changed_primary_promoted`, `changed_symbols_promoted` and
`changed_baseline_status`, and, for the cases that carry facts, which of those
facts the text of each arm could support. A case holds only when **both** arms sent
its expected primary: the claim is that a symbol survives the bonus, and an arm that
never sent it proves nothing. A fourth verdict exists for the case that wants the
primary to move: `HOLD` (both arms kept it), `SWAP` (the dirty arm lost it), `MOVE`
(the dirty arm moved it into the changed file, which is the point of that case), and
`BAD_BASELINE` (the off arm did not send the
symbol the case names, which means the case is stated wrong, not that the bonus did
anything). Exit code is 0 when every case held - which at the shipped `+25` it does
not: two cases report `SWAP` and the command exits 1, and that is the measurement,
not a broken tool. `--changed-file-weight` is a diagnostic override for the run only;
it is restored afterwards and never a substitute for changing the constant.
`--changed-file-sweep` does no building at all: one ranking pass per fixed query
yields the smallest bonus that would hand that query's primary to a symbol in
another file, which is the same arithmetic a "dirty every module in turn" sweep
would search for. Measured on 2026-10-11 over this repository's index: 6 of 12
queries flip at `+1` because a candidate in another file already ties with the
leader, and the others at 10, 15, 21, 30, 30 and 70.

A `SWAP` verdict on the primary is not by itself an effect worth running a live A/B
for, because a flat bonus reorders: a case can change its first symbol and still
send the same files. The `facts` line is what separates the two, and the three scored
cases sit on both sides of it.

- `named_in_query` (query `CONTEXT_BUILDER_BUDGET_QUERY`, dirty
  `packages/context/budget`): the primary moves to `ContextBudget` from `+15` up and
  nothing is lost - `ContextBuilder`, `_enforce_budget` and
  `packages/context/builder.py` are in the text of both arms. It is the **negative
  control**, and both arms of its live pair are expected to score 3/3.
- `evicts_the_asked_about_file` (query `REPOSITORY_INDEX_BUILD_QUERY`, dirty
  `packages/repository/index/models`): 14 symbols become 10 and the primary moves
  into the dirty file. Before the guard described below it also lost the file:
  `packages/repository/index/builder.py` left the context outright and its three
  implementation facts - `PythonAstExtractor`, `RelationshipRegistry`, and
  `CallExtractor` - were available off and unavailable on, at `+1` exactly as at
  `+25`, which is what made this the **discriminating** case. With the guard in
  place the builder file's best symbol is restored to the supporting content slot
  and `facts_lost` reads empty: the row is now the check that the guard holds, and
  the offline pair no longer separates the arms by what is missing from them. The
  case is still stated at 4096 - the stage default,
  `APP_REPOSITORY_CONTEXT_MAX_TOKENS` and the EXPLAIN intent budget this probe
  asks under, all of which agree.
- `gains_the_changed_file` (query `HISTORY_CAP_QUERY`, dirty
  `packages/pipeline/history`): the other side of that ledger. The prompt is prose, it
  names no symbol, and the file it is about is the file the dirty marker puts in the
  working tree - so this is the case the opt-in is offered for. 20 symbols become 7 and
  the four newly sent are the cap's own definitions (`cap_history`,
  `_build_cap_groups`, `_cap_current_tool_result`, `_estimate_tokens`), which is where
  three of the four facts live: the per-message budget, the envelope detector, and the
  truncation marker. `facts_lost` is empty, `changed_primary_promoted` is true because
  the primary moves *into* the changed file, and the verdict is the `MOVE` case above -
  the pair whose two arms differ by a gain and not by a loss. The guard leaves this row
  exactly as it was measured, which is the half of the target that says the bound must
  not be bought with the benefit.

### The Phase B1 promotion guard

Change-aware ranking reorders within a fixed budget, and a reorder can cost more
than position. `ContextBuilder` renders the first selected symbol with its full
source body and spends the shared supporting preview on the next; past those two
positions a symbol keeps its signature and docstring but loses the source body or
preview, which is the text implementation facts are read from. So a dirty file with
many symbols can leave a query-matching module *in* the selected set and still take
its source text out of the prompt, which is what the eviction row above measured.
The rule chosen on 2026-10-25 closes that, in `RankingEngine.rank`:

> A promoted changed-file symbol may not push the best candidate that earned its
> place without the bonus out of the ranked positions that reach the prompt with
> source text.

Concretely, and only when the bonus actually promoted something: the engine scans
the ranked list from the first position outside that prefix and takes the strongest
candidate carrying no `CHANGED_FILE` reason - the scan, rather than a look at the
first candidate the bonus did not touch, matters because that first candidate can
still hold its own slot while a later one has lost the only slot it had. A
candidate is restored only when its module matched the query (`MODULE_MATCH` or
`MODULE_TOKEN_MATCH`, the existing path-relevance reasons, so no second query
parser), when it sat inside the first
`RankingConfig.PROMOTION_ANCHOR_SLOTS` positions with the bonus off, and when the
bonus is what moved it out; it is moved to the last of those positions. Everything
else keeps the order the bonus produced. The dirty file still wins the primary -
that is what the signal is for - and a symbol the promotion never touched, or never
displaced, is left exactly where the query put it.

| row | before the guard | after the guard |
|---|---|---|
| `named_in_query` | SWAP, `3/3 -> 3/3`, 3 -> 5 symbols | identical row |
| `path_token_gate` | HOLD, primary held, 11 -> 19 symbols | identical row |
| `evicts_the_asked_about_file` | SWAP, `3/3 -> 0/3`, all three facts lost | SWAP, `3/3 -> 3/3`, `facts_lost` empty, 14 -> 10 symbols |
| `gains_the_changed_file` | MOVE, `1/4 -> 4/4` | identical row |
| `dirty_file_the_query_ignores` | HOLD, `skipped_no_bonus`, arms identical | identical row |
| a ranking whose first unpromoted symbol keeps its slot | unprotected: `other, dirty, dirty, asked-about, quiet` leaves the module the query named outside the rendered prefix | `other, asked-about, dirty, dirty, quiet`: the untouched symbol keeps the primary, the dirty file keeps its forward move, the named module is restored |
| `--changed-file-sweep`, 12 queries | flips 15, 30, 40, 1, 10, 1, 21, 30, 1, 1, 1, 1 | identical, smallest flip 1, six ties |

Counters are unchanged in both directions: the eviction arm still reads
`changed_context_differs=true`, `changed_primary_promoted=true` and
`changed_symbols_promoted=0`, because the guard moves a symbol, it does not add
one. Two candidates were compared against this rule with the same probe and sweep.
A **cap on the share of the selected context promotion may occupy** failed on
substance: at caps of 1, 2 and 4 promoted symbols the eviction case stayed at
`0/3` - the cap only limits how many dirty symbols get in front, and one is enough
to push the asked-about file past the rendered prefix - and the looser form that
took *any* untouched module-matching symbol rather than the best un-promoted one
changed the primary of the documented `path_token_gate` row, which is a behaviour
change in a case this task did not ask to touch. Plain **retention** - keeping the
module's last symbol in the list, which is the narrowest reading of the rule - was
implemented and measured too: it holds the gain case at `4/4` and brings the
eviction case only to `1/3`, because the retained symbol sits outside the rendered
prefix and reaches the prompt with its signature and docstring and without its
source body, which is where these facts are written. That is why the guard protects
a slot and not a membership.

The guard is inert whenever the promotion is: with
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false`, on a clean tree, and on a
dirty file the query never matched, no candidate carries `CHANGED_FILE`, the pass
is skipped and the ranking is bit-for-bit the one the disabled feature produces.
It is also not visible to `--changed-file-sweep`, which ranks with no bonus at all.
Whether it holds on a live pair of gateways is B3, not B1: the eviction pair is now
expected to *tie* on the three facts in both arms, so that run reads as a check
that the guard survives serialization rather than as the discriminating A/B, and
`explain_changed_files_history_cap` carries that role alone. B3 ran it on 2026-10-25 and
the rule held end to end: `9/9` on both arms of the eviction pair with
`changed_context_differs=true` and the primary moved into the dirty file on every enabled
record, `8/12` against `3/12` on the gain pair, and `9/9` both arms of the control - see
"Isolated-worktree promotion-guard A/B, 2026-10-25 (roadmap B3)".

These modes are retrieval diagnostics, not the answer-quality claim. Each case above
has its scored half in the normal probe set -
`explain_changed_files_contextbuilder`,
`explain_changed_files_repository_index` and
`explain_changed_files_history_cap` - and `CHANGED_FILE_AB_PAIRS` names the
pairs, so the offline table and the live run cannot drift into describing different
queries: both halves of a pair read the same prompt constant and the same facts
tuple, and `tests/observability/test_quality_harness.py` asserts equality rather
than containment.

Start the gateway with the flag set (`.env` is loaded with `override=True`, so
put it in `.env` or make sure `.env` does not already define it):

```powershell
$env:APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED='true'
.\uv.exe run python -m uvicorn apps.gateway.main:create_app --factory --port 8001
```

Check that startup captured something - the line reports counts only, never
paths or contents:

```powershell
# in the gateway terminal
changed_files_signal enabled=true paths=5 captures=1 failures=0 outside_root=0 last_error=none
```

`paths=0` means a clean tree (expected on a freshly committed checkout); take the
same number from `scripts\git_change_snapshot.py --json .` to cross-check.
`last_error` names an exception type only, and a non-zero `failures` value means
ranking fell back to its normal behaviour. A non-zero `outside_root` with
`paths=0` means Git's working tree and `APP_REPOSITORY_PATH` do not resolve to
the same directory - only the count is reported, never the paths.

Per-request lines carry the same bound, and name the promotion in counts only:

```text
repository_context request_id=... context_status=ok ... estimated_tokens=1840 changed_files_signal=ok changed_files_count=5 changed_symbols_selected=2 changed_primary_promoted=True changed_symbols_promoted=1 changed_context_differs=True changed_baseline_status=built changed_baseline_ms=0.4 duration_ms=...
```

The same seven fields also land in the session record's `context` block, so a
session log alone is enough to measure the signal (`changed_baseline_ms` is a
cost, so it stays on the log line and is never recorded):

| field | meaning |
| --- | --- |
| `changed_files_signal` | whether the working-tree source was usable: `off` (none configured), `ok` (it answered, a clean tree included), `unavailable` (it raised, or the stage failed before it could be read) |
| `changed_files_count` | locally modified files the signal mapped onto indexed modules (`0` together with `ok` means a clean tree) |
| `changed_symbols_selected` | symbols in the context that was actually sent that carry the working-tree bonus |
| `changed_context_differs` | whether the sent context differs from the same request composed without the bonus - order included, which is what a flat bonus usually moves |
| `changed_symbols_promoted` | symbols sent now that the same request re-ranked without the bonus did not send |
| `changed_primary_promoted` | whether the bonus changed the primary symbol |
| `changed_baseline_status` | whether that comparison ran: `none`, `built`, `skipped_no_bonus`, or `failed` |

`changed_symbols_selected` answers "was the bonus in the context";
`changed_context_differs` answers "did it change the context", because the stage
builds the no-bonus context for the same request and compares the two composed
packages. The two `promoted` fields are detail on top of that difference: which
part of it the primary and the added symbols account for. Read together:

- `changed_files_signal=ok`, `changed_files_count >= 1`,
  `changed_baseline_status=built` and `changed_context_differs=true` - the bonus
  changed what was sent. That includes the reorder-only case, where
  `changed_primary_promoted=false` and `changed_symbols_promoted=0` while the
  same symbols went out in a different order - which for a flat bonus is the
  normal outcome, not an edge case;
- `changed_symbols_selected > 0` with `changed_context_differs=false` and a
  baseline status of `built` or `skipped_no_bonus` - the bonus was present and
  changed nothing, which the earlier four counters could not tell apart from a
  promotion;
- `changed_files_count > 0` with `changed_symbols_selected = 0` - the tree was
  dirty and nothing qualified, which is the selection gate, not a failure;
- `changed_baseline_status=failed` - the comparison could not be built, so the
  request is unmeasurable; it is neither a promotion nor a measured zero;
- `changed_files_signal=unavailable` - the source failed, so every other field on
  that record is a zero rather than a measurement;
- `changed_files_signal=off` on a request with `status` `disabled` or `degraded` -
  no source is configured, or the stage failed before reading it. A stage that
  did read the signal states what it read even when it assembled nothing, so
  `off` on a dirty tree means the feature is genuinely switched off.

All of them describe the final context - after budget trimming and delta
suppression - so a promoted candidate that did not survive the budget is not
counted. The comparison context is never sent, never stored, and never written to
a record. Building it costs a second full context build, which on a dirty tree
roughly doubles this stage - measured on this repository's real index of 328
modules with 8 changed, about 50 ms becomes about 105 ms - so it is built only
when the ranking pass gave the bonus to at least one candidate, and the cost of a
build that was made is what `changed_baseline_ms` states. Note that
`changed_files_signal` also appears in the startup line quoted above, where it
names the snapshot rather than a per-request state.

To read the counters across a run without opening a single prompt, answer or
path, use the session analyzer - the promotion is one section of its normal
report:

```powershell
.\uv.exe run python scripts\analyze_sessions.py logs\sessions.jsonl
```

Its `CHANGED-FILE PROMOTION` section tallies records by `changed_files_signal`
and by `changed_baseline_status`, counts the records with
`changed_files_count > 0` and with `changed_primary_promoted`, sums
`changed_symbols_promoted` and `changed_symbols_selected`, and splits the three
verdicts above: `proves a change` (broken down into `primary changed`,
`membership changed` and `reorder only`), `present but inert`, and `unmeasured`.
A record whose comparison `failed`, and one that never states the comparison
fields, land in `unmeasured` and in neither verdict. Records written before the
fields existed are listed as `predating the fields` and excluded from every rate,
so an old log can neither inflate nor deflate the measurement. Point it at the
path the gateway writes to (`APP_SESSION_LOG_PATH`, default
`logs/sessions.jsonl`); it reads files, never a config, and prints no path,
symbol or content.

That section replaces the old two-file A/B: one run now states whether the bonus
changed anything, so `logs\changed_files_off.jsonl` and
`logs\changed_files_on.jsonl` no longer need to exist side by side to answer the
question. A run that reads entirely as `present but inert` on a dirty tree means
the measured baseline and the sent context came out identical - which is a real
result, and a normal one for a query the changed module was going to lead on
anyway. It does not mean the requests bypassed the stage: `changed_files_signal=ok`
with `changed_files_count >= 1` and `changed_symbols_selected > 0` is only
producible by the stage and the signal having run. Requests that never reached the
stage read as `changed_files_signal=off`, or as records without the fields, and
`unmeasured` records say the comparison itself did not run.

Keep `APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS=0` (default) unless a
long-running session must notice edits made after startup. With `0` the snapshot
is taken once during lifespan startup, so "currently being edited" means
"dirty when the gateway started" - the same rule the repository index follows.
Any positive value schedules a background refresh at most once per window; the
refresh runs on a worker thread, never inside a request, and each Git call is
bounded by its own timeout.

The A/B is the scored probe, not the offline table. Both halves of each offline case
are registered in the normal fixed set, so the standard selection and replication
flags run them: `explain_changed_files_repository_index` (the case measured above as
a context loss, dirty `packages/repository/index/models.py`),
`explain_changed_files_contextbuilder` (its negative control, dirty
`packages/context/budget.py`), and `explain_changed_files_history_cap` (the case where
the changed file is the one the prompt asks about and the changed arm gains context,
dirty `packages/pipeline/history.py`). Give each pair to two gateways that differ in
nothing but `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED`, each with its own isolated
slice of the session log,
over a working tree in which that pair's module is dirty - and in which nothing else
the index can see is dirty, or the enabled arm's bonus is not the pair's module's
bonus; the run that needed that used a detached worktree, described below. Both arms
are sent the identical prompt, because each pair reads one shared prompt constant.

```powershell
# arm 1: gateway started with APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false
#        (and APP_REPOSITORY_CONTEXT_MAX_TOKENS=4096 on both arms: all three scored
#         implementation facts are lost at that configured budget)
.\uv.exe run python scripts\quality_harness.py --probe explain_changed_files_repository_index --repeat 3 --json --model qwen38-27b --max-tokens 8192 --timeout 300 --reasoning-model qwen38-27b > logs\quality_changed_files_off.json
# arm 2: restart with APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=true
.\uv.exe run python scripts\quality_harness.py --probe explain_changed_files_repository_index --repeat 3 --json --model qwen38-27b --max-tokens 8192 --timeout 300 --reasoning-model qwen38-27b > logs\quality_changed_files_on.json
.\uv.exe run python scripts\analyze_sessions.py logs\changed_files_on.jsonl
# the control pair, same two gateways, a different file dirty in the tree
.\uv.exe run python scripts\quality_harness.py --probe explain_changed_files_contextbuilder --repeat 3 --json --model qwen38-27b --max-tokens 8192 --timeout 300 --reasoning-model qwen38-27b > logs\quality_changed_files_control.json
# the benefit pair, same two gateways, dirty packages/pipeline/history.py: run both arms
# inside a temporary clean worktree so that file is the only dirty indexed module
.\uv.exe run python scripts\quality_harness.py --probe explain_changed_files_history_cap --repeat 3 --json --model qwen38-27b --max-tokens 8192 --timeout 300 --reasoning-model qwen38-27b > logs\quality_changed_files_gain.json
```

`--repeat 3` writes the repeat envelope (`{"repeat": 3, "runs": [...], "aggregate":
{...}}`), which `scripts/evaluate_quality_harness.py` does not read - it accepts a
single-run array or a `--compare-context` object. Score an envelope from its own
`aggregate.hit_rates`, or evaluate one run at a time by handing it
`runs[i]`. The aggregate is the per-fact hit pattern across repeats, so read it
next to the per-repeat `hits`/`misses` rather than instead of them.

`.env` sets `APP_SESSION_LOG_PATH` and is loaded with `override=True`, so a
per-arm shell value for it is ignored. Isolate the arms without editing `.env`
by recording the byte length of the file `.env` points at before each arm and
copying out only the bytes each arm appended:

```powershell
$start = (Get-Item logs\implement_budget_A_4096_20260801.jsonl).Length
# ... run the arm, then stop its gateway ...
$in = [IO.File]::Open((Resolve-Path 'logs\implement_budget_A_4096_20260801.jsonl'), 'Open', 'Read', 'ReadWrite')
[void]$in.Seek($start, 'Begin')
$out = [IO.File]::Create((Join-Path (Get-Location) 'logs\changed_files_off.jsonl'))
$in.CopyTo($out); $out.Close(); $in.Close()
```

Compare it per repeat rather than only in totals: the fact score out of 3, and in
the enabled arm's session log `primary_symbol`, `changed_context_differs`,
`changed_primary_promoted`, `changed_symbols_promoted` and
`changed_baseline_status`. Three repeats is the floor because one answer cannot be
told apart from sampling variance, and the session logs are isolated per arm so a
tally cannot mix them. On the discriminating pair, an answer that names a
`packages/repository/index/models.py` symbol instead of explaining the builder's
`PythonAstExtractor`, `RelationshipRegistry`, and `CallExtractor` collaborators is
the retrieval loss reaching the answer; the enabled arm's log should read
`changed_context_differs=true` and `changed_primary_promoted=true`.
`changed_symbols_promoted` stays small there - 0 for the single-module offline
injection, 1 in the live run over a tree with 18 dirty modules - because eviction
shows up as symbols leaving, not as new ones arriving, so read it beside
`symbols_selected` rather than as the signature itself. On the control pair, both arms should
score 3/3: the primary moves there and nothing is lost, so a score difference on that
probe would mean the arms ran on different trees, not that the bonus cost an answer
anything. An identical score in both arms with `changed_context_differs=false` means
both arms retrieved the same thing, and the comparison measured nothing.

The promotion reorders within the same budget, so `estimated_tokens` may shift
as different symbols take the same space - what must not happen is the promoted
arm exceeding `context.max_tokens` or admitting symbols the query never matched.
Treat either of those as a bug, not as the signal working.

Before scoring either arm, confirm the bonus actually reached the context. In the
enabled run's session log, the `CHANGED-FILE PROMOTION` section of
`scripts\analyze_sessions.py` must show at least one record with
`changed_files_signal="ok"`, `changed_files_count >= 1` and
`changed_context_differs=true`. That field is the one that decides it, because it
compares the two composed packages including order: an arm can show
`changed_symbols_promoted=0` and still have had its whole order changed by the
bonus - which is what the eviction pair now measures, since the guard restores the
file it used to lose rather than preventing the reorder - so
`changed_symbols_promoted` alone
understates it. A record with `changed_symbols_selected > 0` and
`changed_context_differs=false` is the other honest result - the bonus was present
and changed nothing - and it means the two arms measured the same retrieval twice.

Which live probes can show an effect at all is decided offline rather than guessed:
the cases in `CHANGED_FILE_PROBES` say what the bonus does to retrieval on this
repository's index, and to the facts each arm's context can support, and the scored
pairs above are the cases they license running live - one that must be able to
differ, one that must not, and one that must differ by an addition. The replicated
A/B of the first two ran on 2026-10-12; the benefit pair ran on 2026-10-13, in a
detached worktree so that one file was the only dirty module either gateway could
see; both results are below. A temporary dirty marker used to make an arm differ must
be one narrow file - that pair's own module - removed afterwards, and never committed.
Neither the harness nor the offline probes writes to the working tree or reads Git: the
probes inject the dirty module, so the tree only matters for the live arms.

### Replicated changed-file A/B, 2026-10-12

Backend `http://100.106.236.88:18300/v1` serving `qwen3.8-flash-next`
(`owned_by: vllm`), reached as gateway alias `qwen38-27b` through the `openai`
provider. Both arms: `APP_REPOSITORY_CONTEXT_MAX_TOKENS=4096`, the `EXPLAIN:4096`
intent budget, the registered `REPOSITORY_INDEX_BUILD_QUERY` prompt,
`--repeat 3 --max-tokens 8192 --timeout 300`. The working tree differed from a
clean checkout in the same way for both arms plus the one marker in
`packages/repository/index/models.py`; the two gateways differed only in
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED`.

| arm | repeat 1 | repeat 2 | repeat 3 | total |
|---|---|---|---|---|
| feature off | 3/3 | 3/3 | 3/3 | 9/9 |
| feature on | 0/3 | 0/3 | 0/3 | 0/9 |

Fact by fact, with the flag off `PythonAstExtractor`, `RelationshipRegistry` and
`CallExtractor` were each hit in all three repeats; with it on each was missed in
all three. Nothing about the retrieval was a coin flip: inside each arm the three
repeats sent identical context.

- off arm: 11 symbols, `estimated_tokens` 4091, `prompt_tokens` 3589
- on arm: 8 symbols, `estimated_tokens` 3934, `prompt_tokens` 3342, primary
  `packages/repository/index/models.RepositoryIndex`

The whole of `packages/repository/index/builder.py` left the enabled arm's
context, which is the offline eviction case appearing live. Enabled-arm session
records (3/3 each): `changed_files_signal=ok`, `changed_files_count=18`,
`changed_context_differs=true`, `changed_primary_promoted=true`,
`changed_symbols_promoted=1`, `changed_symbols_selected=8`,
`changed_baseline_status=built`. The disabled arm reports `off`, `none` and zeros,
so the counters are not the flag being read in the wrong place.

Two confounds stay recorded rather than smoothed over. The flag is global, so
`changed_files_count=18` means the bonus applied to every locally modified indexed
module in this working tree, not only to the experiment's marker; the live delta is
"bonus off versus bonus on over this tree", and the single-module isolation belongs
to the offline case. And two of the three changed-arm answers ran to the 8192-token
completion ceiling (one flagged `truncation_risk`), against 1478-3593 tokens in the
off arm - the enabled arm rambled rather than shrinking. The run measures a cost of
turning the signal on for this query; it does not price the benefit side, so
`RankingConfig.WEIGHT_CHANGED_FILE` stays `+25` and the feature stays off by
default.

### Isolated-worktree benefit A/B, 2026-10-13

The other half of that decision needed a tree with exactly one dirty file, because the
flag is global: the run above turned the bonus on across 18 locally modified indexed
modules and cannot say what one module is worth. It was run on 2026-10-13 on the pair
`gains_the_changed_file` / `explain_changed_files_history_cap`: prompt
`HISTORY_CAP_QUERY` ("How does the gateway cap conversation history before sending it
to the model?"), dirty file `packages/pipeline/history.py` (indexed module key
`packages/pipeline/history`), both arms at `APP_REPOSITORY_CONTEXT_MAX_TOKENS=4096`
with the `EXPLAIN:4096` intent budget, and the four facts `cap_history`,
`max_current_tool_result_tokens`, `_looks_like_cline_tool_result_message` and
`truncated by gateway history cap`.

The isolation is a detached worktree of the commit the main workspace is on, at
`..\lap-ab-histcap-4330e8f` (`4330e8f3521d7a4b9525bb62008b3f3b716a6e7f`), holding a
two-line comment marker in that one file for as long as both arms run. A worktree is
also how the arms stop inheriting `.env`: `apps/gateway/main.py` loads `.env` from its
own tree with `override=True`, and the worktree has none (it is gitignored), so every
value each gateway used is one its launcher set:

```powershell
git worktree add --detach ..\lap-ab-histcap-4330e8f 4330e8f
git -C ..\lap-ab-histcap-4330e8f status --short   # must be empty before the marker
# ... add the marker, then check what Git reports, which is what the stage reads:
#   git status --short      -> ` M packages/pipeline/history.py`, one line
#   scripts\git_change_snapshot.py --json .
#                            -> "clean": false, counts.unstaged 1, untracked 0
# start the arm's gateway with cwd inside the worktree, then from the main workspace:
.\uv.exe run python scripts\quality_harness.py --probe explain_changed_files_history_cap `
    --repeat 3 --json --model qwen38-27b --max-tokens 8192 --timeout 300 --reasoning-model qwen38-27b
# afterwards: git -C ..\lap-ab-histcap-4330e8f checkout -- packages/pipeline/history.py
#             git worktree remove ..\lap-ab-histcap-4330e8f
```

`scripts/ab_launcher.py` is what builds those two launcher environments now, and it is
configuration and validation only: `template` writes or prints an experiment and says
what the tree it names still lacks, `validate` reports every reason the arms must not
start yet, and `show` prints the PowerShell lines to paste into the two terminals, but
only after every check below has passed. It never starts a process, opens a
connection, or contacts the backend, so a rejected experiment costs nothing:

```powershell
.\uv.exe run python scripts\ab_launcher.py template --out configs\ab_experiments\histcap.json `
    --worktree ..\lap-ab-histcap-4330e8f
.\uv.exe run python scripts\ab_launcher.py validate --config configs\ab_experiments\histcap.json
.\uv.exe run python scripts\ab_launcher.py show --config configs\ab_experiments\histcap.json
.\uv.exe run python scripts\ab_launcher.py show --config configs\ab_experiments\histcap.json --arm on
.\uv.exe run python scripts\ab_launcher.py show --config configs\ab_experiments\histcap.json --diff
```

What it refuses is the part that was easy to get wrong by hand. The arms must not share
a port or a session log; `harness_timeout_seconds` must exceed
`provider_request_timeout_seconds` by at least 30 seconds - the relationship whose
absence produced the 503-timeout passes described below. `REQUEST_TIMEOUT` is carried in
the rendered gateway environment rather than left to the provider's 60-second fallback,
and the harness command carries `--timeout` for `harness_timeout_seconds`, a larger
number than `REQUEST_TIMEOUT` by that margin rather than the same number, so a printed
pair cannot disagree with the file it came from and the arm always gives up first. The
launcher writes no credential: a key named like one (`*_API_KEY`, `*_ACCESS_TOKEN`,
`*_TOKEN`, `*_SECRET`) is rejected in the experiment file, reported only as
set-or-not-set, and never printed.

The worktree gets the strictest check, because it is the one thing an arm inherits from
the terminal rather than from the file: it must exist, hold no `.env` (which
`apps/gateway/main.py` loads with `override=True`, silently replacing the settings under
test), and prove by its own markers that it is a detached `git worktree` checkout - a
`.git` file whose `gitdir:` line reaches an administration directory under `worktrees`,
a `HEAD` in that directory holding a commit id rather than `ref: refs/heads/...`, and the
tracked files both rendered commands start from. The tree both commands move into and
the shared `APP_REPOSITORY_PATH` the gateway indexes must also resolve to one directory;
they are two entries in one file, and comparing them textually would refuse a junction,
a `subst` drive or an 8.3 short name of the tree it already named, which is why both
sides are resolved first - the way `packages/repository/changed_files.py` compares a
Git working tree with a configured root. An ordinary directory, a clone sitting
on a moving branch, a worktree pruned from the main repository's `worktrees` directory, a
marker pointing anywhere else, and a tree missing a file the gateway or harness needs are
each refused by name. The launcher never runs Git to find this out; every check is a
directory entry or a small text file, which is also why it can print a verdict without
starting anything.

`template` is the one command that expects its worktree check to fail, because a starting
point names a tree that has usually not been made yet: it refuses to write a file whose
fields are already wrong, writes the one that is not, then prints what `validate` would
say about that tree right now - `can run either arm as it stands`, or the reasons it
cannot. That verdict goes to standard error, so the printed JSON of a template without
`--out` stays parseable, and it costs nothing to run.

Nothing the launcher renders touches the quality store: the harness only reads the log
its `--session-log-path` names, which is the file that arm's own gateway writes, and
scoring a run into the store is a separate step - `scripts/evaluate_quality_harness.py
--persist`, writing to the `--storage-path` it is given.

Both launchers set `APP_DEFAULT_MODEL=qwen38-27b`, `APP_DEFAULT_PROVIDER=openai`, the
single-entry `APP_MODELS_CONFIG` that routes `qwen38-27b` to backend model
`qwen3.8-flash-next` at `http://100.106.236.88:18300/v1` (`context_window=262144`,
`max_output_tokens=8192`, `chars_per_token=3.5`), `REQUEST_TIMEOUT=300`,
`APP_REPOSITORY_PATH` at the worktree, `APP_REPOSITORY_CONTEXT_MAX_TOKENS=4096`,
`APP_REPOSITORY_CONTEXT_INTENT_BUDGETS` with `EXPLAIN:4096`,
`APP_REPOSITORY_EXCLUDE_TESTS=false`, `APP_REPOSITORY_EXCLUDE_GLOBS=scripts/**`,
`APP_SESSION_LOG_ENABLED=true` and its own absolute `APP_SESSION_LOG_PATH`, and
`APP_HISTORY_CAP_ENABLED=true` with `APP_HISTORY_CAP_TOKENS=3000`. `template` writes those
and five more into `shared_env` because each one changes what a context contains or how
long it holds it, and none of them has a worktree to be read from:
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS=0`, so the changed-file set is the one
snapshot taken at startup rather than whatever a background refresh last made of it;
`APP_CONTEXT_INTENT_RULES={}`, so no leftover phrase sends one arm's request to another
intent; `APP_CONTEXT_DELTA_CACHE_SIZE=256`, so neither arm evicts a conversation and
re-sends symbols it had already sent; and `RELATIONSHIP_RANKING_ENABLED=true` with
`RELATIONSHIP_EXPANSION_ENABLED=true`, which are read outside the `APP_` settings at all -
`packages/context/builder.py:205,209` and `packages/context/ranking.py:193,197` each
compare the raw text to `"false"`, so only that exact lowercase word turns one off, and
`True`, `1` and `no` all leave a switch on that the experiment never declared. The
launcher spells out every setting both arms share, refuses a shared name that is missing,
empty, differently typed or spelled differently between them, and rejects any per-arm
override of a name that is not `APP_SESSION_LOG_PATH` or
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED`. They differ in exactly those two lines:
`APP_SESSION_LOG_PATH`, and
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED` (`false` for arm 1, `true` for arm 2).
Observed before the first request: backend `/v1/models` served one model,
`qwen3.8-flash-next` (`owned_by: vllm`, `max_model_len: 400000`); the gateway's
`/v1/models` listed the alias `qwen38-27b`; `/debug/runtime-context` reported
`routing_mode=models_config`, `default_model=qwen38-27b`,
`repository_context_max_tokens=4096` and the arm's own session log; and each gateway
indexed the same tree with the same numbers (`files=504 modules=504 symbols=8521
relationships=18096`). The enabled gateway's startup line is the one-file proof from
inside the process: `changed_files_signal enabled=true paths=1 captures=1 failures=0
outside_root=0 last_error=none`.

What the ranking should do on that tree was measured before the requests, and
re-measured against the worktree itself - `--changed-file-probe --repo-root
..\lap-ab-histcap-4330e8f` reproduces the same row as the main workspace's index, so
the live arms were not sent a prediction from a different tree. In stage order the
disabled arm sends `apps/gateway/api/models.list_models` first, then
`packages/pipeline/history._build_cap_groups.find` and `.union` - the changed file is
present at two symbols, neither of which is `cap_history`, and the other 17 of its 20
symbols are gateway plumbing. The enabled arm sends 7: `_build_cap_groups.find`,
`_build_cap_groups.union`, `apps/gateway/api/models.list_models`, `_build_cap_groups`,
`_cap_current_tool_result`, `cap_history`, `_estimate_tokens`. Those last four are
`changed_symbols_promoted=4`; `changed_context_differs=true`,
`changed_primary_promoted=true` and `changed_baseline_status=built`, and the facts the
two texts can support go `1/4` to `4/4` with `facts_lost` empty. The 17 gateway symbols
that leave are what pays for it - this is a different context, not the same one with
more in it.

Per repeat, on the clean pass (three requests per arm, one identical prompt, no
errors):

| arm | repeat 1 | repeat 2 | repeat 3 | total |
|---|---|---|---|---|
| feature off | 1/4 | 1/4 | 1/4 | 3/12 |
| feature on | 3/4 | 3/4 | 2/4 | 8/12 |

Fact by fact, on that pass: `cap_history` was named by all six answers - it is the
public function, and the disabled arm's call sites show the model where to look;
`max_current_tool_result_tokens` by 3/3 enabled against 0/3 disabled;
`_looks_like_cline_tool_result_message` by 2/3 enabled against 0/3 disabled. Pooling the
nine scored enabled answers from all four enabled passes against the six scored disabled
ones keeps that ordering - 7/9 and 6/9 against 0/6, with `cap_history` 9/9 against 6/6.
The fourth fact, `truncated by gateway history cap`, was quoted by none of those fifteen
answers, because scoring wants the marker verbatim and the model paraphrases it. So the
live gain is two of the three facts the offline case says arrive, and the third is a
scoring artifact rather than a retrieval failure: the string is in the enabled arm's
context, which is what `4/4` offline means.

Inside each arm the context was identical across repeats - disabled: 20 symbols,
`estimated_tokens` 2807, `prompt_tokens` 3060, primary
`apps/gateway/api/models.list_models`; enabled: 7 symbols, `estimated_tokens` 4087,
`prompt_tokens` 3955, primary `packages/pipeline/history._build_cap_groups.find`,
inside `packages/pipeline/history` as the offline case predicts. Every request sent to
either gateway - twenty in all, six of them in the pass above - carried one prompt text
(77 characters, the same SHA-256 prefix throughout), and the
enabled arm's session records read, on all three repeats: `changed_files_signal=ok`,
`changed_files_count=1`, `changed_symbols_selected=6`, `changed_context_differs=true`,
`changed_primary_promoted=true`, `changed_symbols_promoted=4`,
`changed_baseline_status=built`; the disabled arm's read `off`, `0`, `false`, `false`,
`0` and `none`. `scripts/analyze_sessions.py` over each arm's isolated slice agrees:
3/3 records "proves a change" with the primary and the membership both changed in the
enabled arm, 12 promoted and 18 selected symbols summed across three requests, and 0 in
every column of the disabled arm.

Two costs sit next to that. `changed_baseline_ms` was 402-507 ms per enabled request in
the enabled gateway's own log lines - the counterfactual re-rank, which is where the
counters come from - and the enabled prompt carried ~900 more tokens (3955 against 3060).

The timeout history belongs to the measurement, not to the feature. The first three
enabled passes lost one of their three repeats each to an HTTP 503 with a
`provider_stage ... status=error error=Request timed out` at 61.0-61.3 s: the
gateway/provider layer aborts a backend call at `REQUEST_TIMEOUT`, whose default is
60 s, well under the harness `--timeout 300`, and the isolated launcher had not set it
because there was no `.env` to set it (the main workspace's `.env` does, at 300). Three
of nine enabled requests and nought of five disabled ones were lost that way, which is
why the table reports the pass taken after `REQUEST_TIMEOUT=300` was set in both
launchers, with 0 errors on either side. No answer came near the 8192-token completion
ceiling in that pass (843-1218 tokens disabled, 904-1162 enabled) and nothing was
flagged `truncation_risk`, so neither the totals nor the per-fact pattern is a reading
of truncated text. The pre-fix passes are retained locally under the Git-ignored
`build/ab_history_cap` beside the arm slices; they are diagnostic evidence, not files
that will accompany this documentation in a commit. The two disabled-arm passes agree
with each other repeat for repeat.

How the pair was found, and what the search rejected. The candidate set was bounded by
scripts retained locally under the Git-ignored `build/cf_search`, not by a guess; those
scratch artifacts are not committed with this runbook. Stage 1 (`search1.py`, one
`q_*.json` per query) profiled 15 prose queries through the real stage and asked, for
each, which modules could earn the bonus at all; stage 2 (`search2.py`, `s2_rows.json`)
ran all 75 (query, module) pairs and recorded the shape of each - symbols added, symbols
removed, identifiers only the enabled arm's text carries - and 20 rows looked
benefit-shaped on that first, symbol-level test. Stage 5 (`search5.py`, `s5_rows.json`)
widened the query set to 22 (those 15, the two prompts already registered as pairs, and
five written for this search) and scored 93 rows by text rather than by symbol counts: 51
gained at least four new tokens from the dirty module's own source, and 61 lost no symbol
at all. `filter5.py` asked for both at once - nothing removed, at least 12 new tokens -
and 19 rows survived. Two of the 93 rows were the history-shaped candidates that mattered
here, both with `packages/pipeline/history` dirty: "How does the conversation memory store
persist and recall history?" (4 added, 2 removed) and "How does the pipeline engine trim
conversation history before a request?" (2 added, 7 removed). Neither passed
`filter5.py`: each takes symbols away from the disabled arm, so each measures a trade and
not a gain. `HISTORY_CAP_QUERY` was written after them, asking about the cap itself in
prose that names no symbol.

The pair that is registered would not survive that `removed == 0` filter either: 17
gateway symbols leave the enabled context. What it satisfies is the weaker condition an
answer actually depends on - the symbols that leave carry none of the four scored facts,
so `facts_lost` is empty while three facts arrive. That is why the search's filter became
the rule `run_changed_file_probe` applies, and why `search7.py` re-measures the registered
case through the shipped code path instead of through scratch arithmetic. `search8.py` and
`search9.py` hold the ordered per-arm symbol lists quoted above. Nothing was written down
in prose about rows that were counted and never revisited; the numbers above are what the
retained JSON says.

Verdict: the benefit side is measured, and it is real but narrow. On one query the
bonus buys two implementation facts the answer could not otherwise reach, at the price
of context that query did not ask for and half a second of baseline comparison; on
another it loses the answer outright (the run above). `RankingConfig.WEIGHT_CHANGED_FILE`
stays `+25`, unchanged by either run, and the feature stays off by default: the flag is
global, so the two effects arrive together for anyone who turns it on, and no per-query
rule decides between them yet. What has changed is the shape of the decision - it is no
longer "costs something, buys nothing measured", and the `gains_the_changed_file` row of
`--changed-file-probe` is the offline statement of what the live pair now measures.

### Isolated-worktree promotion-guard A/B, 2026-10-25 (roadmap B3)

What this run is for. B1 chose the promotion guard and B2 pinned it at the ranking,
builder and stage levels, which is all arithmetic on one in-process index. B3 answers
the question arithmetic cannot: whether the rule still holds once the context has been
through `ContextBuilder`'s own promotion passes, the serializer and a real provider
request, and what the guard costs on the pair that is meant to gain and the pair that
must not change. It measured the build at `57bd04504273c4c5ee227b4181d53b5754d64808`
and changed no production behaviour: `RankingConfig.WEIGHT_CHANGED_FILE` stayed `+25`,
and the feature stayed off by default, which is why the disabled arm of every pair is
the same code path with the flag read as `false`.

Identity of what was contacted, checked before any claim was made: backend
`http://100.106.236.88:18300/v1/models` served one model, `qwen3.8-flash-next`
(`owned_by: vllm`, `max_model_len: 400000`, root
`/hf/hub/models--nvidia--Qwen3.8-Flash-Next-NVFP4/snapshots/fc694b54fb0174e0913e6adf86691ef85a4ead47-fp8hybrid`);
the gateway listed the alias `qwen38-27b`, and `/debug/runtime-context` reported
`routing_mode=models_config`, `default_model=qwen38-27b`, `default_provider=openai`,
`models[0].backend_model=qwen3.8-flash-next`, `context_window=262144`,
`max_output_tokens=8192`, `chars_per_token=3.5`, `repository_context_max_tokens=4096`,
`repository_context_intent_budget_map` `EXPLAIN=4096` (`SEARCH/TEST/DEBUG=2048`,
`REFACTOR/IMPLEMENT=4096`), `context_delta_injection=true`, `history_cap_enabled=true`
with `history_cap_tokens=3000`, and each arm's own session log. Those are the values
`scripts/ab_launcher.py` rendered; the worktree holds no `.env`, so nothing else was in
reach. The main checkout's `.env` declares the same alias and the same `4096`, which is
what made the launcher block and the documented configuration agree.

The tree, and why it is the isolation this run needed:

```powershell
# 1. one detached worktree at the commit being measured, in a sibling path
git worktree add --detach ..\lap-ab-b3-57bd045 57bd045
git worktree list          # .../lap-ab-b3-57bd045  57bd045 (detached HEAD)
git -C ..\lap-ab-b3-57bd045 rev-parse --abbrev-ref HEAD   # HEAD, not a branch
git -C ..\lap-ab-b3-57bd045 status --short                # empty, before any marker
Test-Path ..\lap-ab-b3-57bd045\.env                       # False
# 2. its own environment from the lock, at the interpreter the baseline used
Set-Location ..\lap-ab-b3-57bd045
.\uv.exe sync --locked --python 3.13 --exact   # CPython 3.13.14, 32 packages, nothing extra
Set-Location ..\local-ai-platform
```

`--python 3.13` is the one place this run departed from the bare command, and it is a
measurement condition rather than a convenience: with no pin, `uv sync` created the
worktree environment from CPython 3.14.6, the newest interpreter on this machine, while
every documented baseline here - including the 2026-10-24 A1 run - was taken on
3.13.14. Re-running the sync with the pin produced 3.13.14 and `--exact` proved nothing
extraneous was left in the environment. `uv.lock` is tracked at this commit, so
`.\uv.exe lock --check` resolved 33 packages in the main checkout and the sync needed no
`UV_PROJECT_ENVIRONMENT` and borrowed no interpreter (the A1 workaround is not needed).

Both arms of every pair came from one validated experiment file per pair:

```powershell
# 3. configuration, validation, and the proof the arms are a pair
.\uv.exe run --frozen python scripts\ab_launcher.py template --name b3_evict --worktree ..\lap-ab-b3-57bd045 --out build\b3\20261025\evict.json
.\uv.exe run --frozen python scripts\ab_launcher.py validate --config build\b3\20261025\evict.json
.\uv.exe run --frozen python scripts\ab_launcher.py show --config build\b3\20261025\evict.json --diff
```

`template` wrote the shared block, `REQUEST_TIMEOUT=300`, harness `--timeout 345`,
`harness_repeat=3` and `harness_max_tokens=8192` as its runbook defaults; the only hand
edit was `harness_probes`, which names the pair being measured (`gain.json` and
`control.json` differ from the file above in `name` and that one list). `validate`
exited 0 for all three and said what mattered about the tree: it is a detached worktree
administered under `.git\worktrees`, it holds no `.env`, and the provider timeout sits
forty-five seconds under the harness timeout - `REQUEST_TIMEOUT=300` against
`--timeout 345`, which clears the `ab_launcher` floor of a thirty-second margin.
`show --diff` for each pair printed
exactly two lines, and nothing else, at every port:

```text
# arm differences in 'b3_evict' (off / on)
  APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED: false | true
  APP_SESSION_LOG_PATH: C:\Users\ovidi\lap-ab-b3-57bd045\logs\sessions_b3_evict_off.jsonl | C:\Users\ovidi\lap-ab-b3-57bd045\logs\sessions_b3_evict_on.jsonl
```

The rendered blocks were started as written - `Set-Location` into the worktree, the two
`New-Item` lines, the twenty-three `$env:` lines, the uvicorn command on port 8011 (off)
and 8012 (on), and the harness command against each - from a throwaway runner under the
ignored `build\b3\20261025\` that parses `show --arm` and launches what it finds, so no
flag entered a live arm by hand. Gateway stdout, gateway stderr, the repeat envelopes and
the copied-out session logs of every arm are under the ignored
`logs\b3\20261025\<pair>\`; `git status --short` was empty throughout, because none of it
is tracked. Every process started was stopped by the same runner's counterpart, which
matches on a command line containing both `uvicorn` and `apps.gateway.main:create_app`
across all three layers of the `uv -> python -> python3.13` chain, and each stop ended
with `no gateway or worktree-harness process left` and both ports free.

The three pairs, and what each one dirtied. Each pair began from the same clean detached
worktree, added one comment-only line (no code, no string, nothing a scored fact could
match) to exactly one tracked file, checked what Git reported before any request was
made, and reverted that one file with `git checkout -- <path>` after both arms were
stopped. `scripts\git_change_snapshot.py --json ..\lap-ab-b3-57bd045` reported
`"clean": false`, `counts.unstaged 1`, `counts.untracked 0` and the intended path each
time, and each enabled gateway printed
`changed_files_signal enabled=true paths=1 captures=1 failures=0 outside_root=0 last_error=none`
- one changed indexed path, no capture failure, nothing outside the repository root -
while its disabled twin printed no `changed_files_signal` line at all. Both gateways of
every pair indexed the same tree to the same numbers:
`files=506 modules=506 symbols=8631 relationships=18457 excluded_tests=0 excluded_globs=13`.

| pair | probe | the one dirty file | indexed module key | offline verdict and facts |
|---|---|---|---|---|
| eviction / guard | `explain_changed_files_repository_index` | `packages/repository/index/models.py` | `packages/repository/index/models` | SWAP, `3/3 -> 3/3`, `facts_lost` empty |
| gain | `explain_changed_files_history_cap` | `packages/pipeline/history.py` | `packages/pipeline/history` | MOVE, `1/4 -> 4/4`, `facts_lost` empty |
| negative control | `explain_changed_files_contextbuilder` | `packages/context/budget.py` | `packages/context/budget` | SWAP, `3/3 -> 3/3`, `facts_lost` empty |

Before each pair ran, `--changed-file-probe --repo-root ..\lap-ab-b3-57bd045` reproduced
the main checkout's table row for row - 23 compared lines, zero differences - so no arm
was sent a prediction from a different tree. The primaries the offline table named are
the primaries each arm actually sent, below, on all three repeats.

#### Eviction / guard pair, `explain_changed_files_repository_index`

Prompt `REPOSITORY_INDEX_BUILD_QUERY` (identical text in both arms), dirty
`packages/repository/index/models.py`, three repeats per arm, 3/3 of the
`PythonAstExtractor` / `RelationshipRegistry` / `CallExtractor` facts available in both
arms offline.

| arm | repeat 1 | repeat 2 | repeat 3 | total |
|---|---|---|---|---|
| feature off | 3/3 | 3/3 | 3/3 | **9/9** |
| feature on | 3/3 | 3/3 | 3/3 | **9/9** |

Per fact, all six answers: each of the three collaborators was hit in all three repeats
of both arms, with no misses anywhere. That is the gate: the enabled arm needed at least
8/9 and it took all nine, and the disabled arm kept its established 9/9 direction from
the 2026-10-12 run. The 2026-10-12 enabled arm scored 0/9 over a tree with eighteen dirty
indexed modules; this is the same pair over a tree with one, with the guard in the build,
and the difference the guard is meant to make is gone from the answer because it is gone
from the retrieval.

What each arm sent, on all three repeats (nothing in this row moved within an arm):

| arm | primary symbol | symbols | est. context / budget | prompt tokens | completion tokens | latency (s) | `changed_*` |
|---|---|---|---|---|---|---|---|
| off | `packages/repository/index/builder.RepositoryIndexBuilder` | 11 | 4091 / 4096 | 3551 | 905, 709, 702 | 31.2, 22.2, 18.2 | `off`, 0, 0, false, 0, false, `none`@0.0 ms |
| on | `packages/repository/index/models.RepositoryIndex` | 9 | 4069 / 4096 | 3436 | 852, 867, 726 | 33.7, 29.3, 23.2 | `ok`, 1, 8, true, 1, true, `built`@493.9, 571.5, 559.2 ms |

The enabled arm is a different context, not a bigger one: 9 symbols where the disabled
arm sent 11, 115 fewer prompt tokens, and the primary moved into the dirty file - the
`SWAP` the offline row describes, with `changed_context_differs=true` and
`changed_primary_promoted=true` on all three records and `changed_symbols_promoted=1`.
The guard's work is exactly what the extra 3/3 says: the symbol it restored to the second
content slot kept its source text, so the eviction that used to cost all three facts
costs none. `analyze_sessions.py` over the enabled arm's log reads 3/3 records
`proves a change`, `primary changed: 3`, `membership changed: 3`, `reorder only: 0`, sum
`changed_symbols_promoted` 3 and sum `changed_symbols_selected` 24; over the disabled
arm's log every column is 0 and `changed_files_signal` is `off` on all three.


#### Gain pair, `explain_changed_files_history_cap`

Prompt `HISTORY_CAP_QUERY` - prose that names no symbol - dirty
`packages/pipeline/history.py`, three repeats per arm, `1/4 -> 4/4` offline. This is
still the pair the opt-in is offered for, and it still separates the arms.

| arm | repeat 1 | repeat 2 | repeat 3 | total |
|---|---|---|---|---|
| feature off | 1/4 | 1/4 | 1/4 | **3/12** |
| feature on | 3/4 | 2/4 | 3/4 | **8/12** |

Per fact across the three repeats: `cap_history` 3/3 on against 3/3 off;
`max_current_tool_result_tokens` 2/3 against 0/3;
`_looks_like_cline_tool_result_message` 3/3 against 0/3; and
`[... truncated by gateway history cap ...]` 0/3 against 0/3. The enabled arm reached the
`at least 8/12` gate exactly, and the number is the same `8/12` the 2026-10-13 run
reached on the same pair, which is the useful coincidence: the guard changed nothing that
this pair measures.

| arm | primary symbol | symbols | est. context / budget | prompt tokens | completion tokens | latency (s) | `changed_*` |
|---|---|---|---|---|---|---|---|
| off | `apps/gateway/api/models.list_models` | 20 | 2807 / 4096 | 3025 | 644, 464, 560 | 19.9, 12.4, 17.1 | `off`, 0, 0, false, 0, false, `none`@0.0 ms |
| on | `packages/pipeline/history._build_cap_groups.find` | 7 | 4087 / 4096 | 3945 | 753, 694, 710 | 23.1, 22.6, 18.0 | `ok`, 1, 6, true, 4, true, `built`@477.0, 483.3, 427.6 ms |

Twenty symbols became seven and `changed_symbols_promoted=4` on every record: the four
newly sent are the cap's own definitions, which is where three of the four facts live.
The fourth, the truncation marker, is a scoring artifact rather than a retrieval failure
and stays reported that way: the offline row for this exact tree says the enabled arm's
serialized context supports 4/4, so the string reaches the prompt and the model
paraphrases it. No answer in this pair quoted it. The same reasoning applies to repeat 2's
miss of `max_current_tool_result_tokens`, where repeats 1 and 3 hit it: all three records of
that arm carry the same observable context fingerprint - 7 symbols, `estimated_tokens` 4087,
3945 prompt tokens, the same primary and the same `changed_*` counters - so what changed
between those requests was the model's wording, not what was retrieved. A session record does
not carry the ordered supporting-symbol list, so fingerprint identity is as far as the claim
about those two requests goes.
`analyze_sessions.py` reads 3/3 `proves a change` (primary and membership both changed on
all three) with sum `changed_symbols_promoted` 12 in the enabled arm and 0 everywhere in
the disabled arm.

#### Negative control, `explain_changed_files_contextbuilder`

Prompt `CONTEXT_BUILDER_BUDGET_QUERY`, dirty `packages/context/budget.py`, three repeats
per arm. Both arms had to stay intact and neither acquired an artificial difference.

| arm | repeat 1 | repeat 2 | repeat 3 | total |
|---|---|---|---|---|
| feature off | 3/3 | 3/3 | 3/3 | **9/9** |
| feature on | 3/3 | 3/3 | 3/3 | **9/9** |

| arm | primary symbol | symbols | est. context / budget | prompt tokens | completion tokens | latency (s) | `changed_*` |
|---|---|---|---|---|---|---|---|
| off | `packages/context/builder.ContextBuilder._enforce_budget` | 3 | 3988 / 4096 | 3466 | 412, 729, 729 | 15.4, 18.7, 21.7 | `off`, 0, 0, false, 0, false, `none`@0.0 ms |
| on | `packages/context/budget.ContextBudget` | 4 | 3779 / 4096 | 3345 | 357, 357, 357 | 15.3, 10.0, 11.3 | `ok`, 1, 2, true, 2, true, `built`@423.7, 428.4, 376.1 ms |

This is what a control is for: the enabled arm did change its retrieval - the primary
moved to `ContextBudget`, `changed_context_differs=true` and `changed_symbols_promoted=2`
on all three records, and the analyzer counts 3/3 `proves a change` with membership
changed - and the score did not move at all, because the bonus adds the budget file's two
symbols in front of the builder file's three instead of replacing them. A score
difference here would have meant the arms ran on different trees.

#### Determinism, cost, and what this run does not settle

Eighteen requests were measured - three repeats, two arms, three pairs - and every one
of them answered: no request errored, none reached a timeout, none was flagged
`truncation_risk`, and style was clean (`ok`, no reasoning preamble or tool chatter) in
all eighteen. The slowest was 33.7 s against a 300 s provider timeout and a 345 s client
timeout.

**The observable context fingerprint is identical inside each arm; the answers are not, and
that is the split this measurement is built on.** In all six arms, `primary_symbol`,
`symbols_selected`, `estimated_tokens`, `prompt_tokens` and the seven `changed_*` fields took
one value across all three repeats - the tables above list one row per arm because there is
nothing else to list. That is the fingerprint, not the context text: a session record carries
counts and the primary and deliberately no ordered supporting-symbol list, so the exact live
order the serializer emitted is neither recorded nor claimed here. Ordered determinism lives
offline and in tests instead - the `symbols=` lists the probe prints for the same tree, and
three checks: `tests/context/test_ranking.py::TestRankingEngine::test_ordering_deterministic`,
`tests/context/test_ranking_v2.py::TestDeterministicOrdering::test_repeated_runs_produce_same_order`
and `tests/context/test_changed_file_ranking.py::test_promotion_guard_is_deterministic_and_leaves_the_counter_alone`.
Answer text moved: three distinct answers in each of the four eviction/gain arms, two of three
in the control's disabled arm, and the same answer three running times in the control's enabled
arm. So the gain arm's repeat-2 miss of `max_current_tool_result_tokens`, where repeats 1 and 3
hit it, is model wording on an unchanged retrieval fingerprint, not retrieval flicker.

Cost, summed over the three repeats of each arm:

| pair | arm | prompt tokens | completion tokens | latency (s) | stage time (ms) | of which counterfactual baseline (ms) |
|---|---|---|---|---|---|---|
| eviction / guard | off | 10653 | 2316 | 71.6 | 1468.9 | 0 |
| eviction / guard | on | 10308 | 2445 | 86.2 | 3171.9 | 1624.6 |
| gain | off | 9075 | 1668 | 49.4 | 1543.2 | 0 |
| gain | on | 11835 | 2157 | 63.7 | 2742.5 | 1387.9 |
| negative control | off | 10398 | 1870 | 55.8 | 1293.8 | 0 |
| negative control | on | 10035 | 1071 | 36.6 | 2447.6 | 1228.2 |

Read as totals over the nine pairs of requests, the enabled arms spent 32178 prompt tokens
against 30126 (about +228 a request) and 5673 completion tokens against 5854, and took
186.5 s against 176.8 s - 9.7 s more in aggregate, about 1.1 s per enabled request, of which
4.24 s is `changed_baseline_ms` summed over the nine enabled requests (~471 ms each). The rest
is provider spread, and the spread runs both ways between pairs: the guard pair took 14.6 s
more with the feature on, the gain pair 14.3 s more, the control pair 19.2 s less. So the fair
statement is no unexplained or material latency regression in this sample, not no latency
regression. The stage is where the honest cost sits: 431-514 ms per disabled request against
816-1057 ms per enabled one, and `changed_baseline_ms` accounts for 409-542 ms of that, so
an enabled request spends most of its extra time re-ranking itself without the bonus to
produce a comparison nobody reads in production. That number is B4's target, not a B3
finding. Token movement is pair-specific and follows retrieval: the guard pair got 115
tokens cheaper per request with the feature on, the gain pair 920 dearer (the cap's own
definitions arriving where plumbing used to be), the control 121 cheaper. No arm exceeded
its budget - the highest estimated context in eighteen requests was 4091 of 4096 - and no
symbol was promoted that the query had not reached: the gate that admits each promotion is
the one the offline rows name, `[name match only]` on the eviction and gain pairs and
`[named in query]` on the control, and every enabled record pairs
`changed_symbols_selected > 0` with `changed_files_signal=ok` and `changed_files_count=1`.

Validity, stated field by field for the enabled arm of each pair, because a passing score
means nothing if the signal never ran: `changed_files_signal=ok` on all nine enabled
records; `changed_files_count=1` on all nine; `changed_baseline_status=built` on all nine
(the bonus was applied, so the comparison was owed and was made); `changed_context_differs=true`
on all nine, including all three records of the eviction pair, which is the field that
proves the reorder reached the final serialization; zero baseline failures anywhere; zero
budget overruns; and the disabled arm of each pair reading `off`, `0`, `false`, `false`,
`0`, `false`, `none` - so the counters are the signal, not the flag read in the wrong place.

What this run does not settle, kept where it belongs:

- **The offline table's symbol counts are not the live ones, and the reason is a budget
  input, not the guard.** Eviction measured `14 -> 10` offline and sent 11 then 9 live; the
  control measured `3 -> 5` and sent 3 then 4; the gain pair matched at `20 -> 7`. Live, the
  stage resolves `chars_per_token` from the model definition (`3.5` here) and estimates with
  it; offline, `_stage_arm` builds a bare `PipelineContext` with no `resolved_model`, so
  `packages/pipeline/stages/repository_context.py:882-901` falls back to the platform's
  `4.0`, and a context the gateway estimates at 4091 tokens the probe estimates one-eighth
  cheaper (the 3.5/4.0 ratio, 12.5% lower) and therefore fills with more symbols. It is the
  same in both arms and in both modes, so nothing above depends on it, but it is why the two
  views disagree. It is a separate gap from roadmap item A3, and not evidence about it either
  way: A3 is about making history capping use the resolved model's `chars_per_token`, whereas
  this is the offline probe having no resolved model to calibrate against, because `_stage_arm`
  builds a bare `PipelineContext`. A3 stays open and unchanged by this run.
- **Live order is asserted, not printed.** A session record deliberately carries no symbol
  list, so within an arm the order fingerprint is (`primary_symbol`, `symbols_selected`,
  `estimated_tokens`, `prompt_tokens`) plus the counters, and those matched to the unit. The
  ordered supporting-symbol list itself was not recorded live, so ordered determinism is what
  the offline probe's `symbols=` lists and the ranking unit tests establish, not this run.
- **One preliminary pass is kept aside, not counted.** The first eviction-disabled-arm run
  finished before the worktree's `logs\` directory had been confirmed created; its three
  records, its envelope (`*.aborted1.*`) and its answers are retained under
  `logs\b3\20261025\evict\` and `build\b3\20261025\`; its three records scored 9/9 on the same
  observable fingerprint the rerun's disabled arm reports - 11 symbols, `estimated_tokens`
  4091, 3551 prompt tokens, the same primary.
  The reported figures are the rerun's, taken with both arms writing their own isolated log
  from the first request.
- Sampling was not pinned (the harness sends no temperature), both gateways of a pair stayed
  up together against one backend, and each arm was measured one at a time - so latency is
  comparable inside a pair and not across pairs. `--reasoning-model` is not part of what
  `ab_launcher` renders; at `--max-tokens 8192` the warning it drives is inert, so the
  rendered command was run as rendered.
- The marker comment is the only thing that made these trees differ from a clean checkout.
  It is comment-only, it was reverted with `git checkout -- <that one file>` after each pair,
  the worktree was verified clean before `git worktree remove` deleted it, and it was never
  committed.

**Decision: B3 passes every gate and is closed.** Eviction/guard `9/9` against a gate of
`at least 8/9`, with the disabled arm at its documented `9/9`; gain `8/12` against `at
least 8/12`, with the disabled arm at `3/12`; negative control intact at `9/9` in both arms
with a real context difference and no score difference; the observable context fingerprint
identical across the three repeats of all six arms, ordered-symbol identity being an offline
and unit-test claim rather than a live one; no error, timeout, budget violation, token
explosion or style regression in any of the eighteen requests, and no unexplained or material
latency regression at that sample size - 9.7 s more across the nine enabled requests in
aggregate, 4.24 s of it the counterfactual build. The promotion guard therefore survives the
builder's own promotions, the serializer and a live provider request - the claim B1 made
offline and B2 pinned in code, now measured. What it does not authorize is the default: the
flag stays off,
`RankingConfig.WEIGHT_CHANGED_FILE` stays `+25`, and the counterfactual build still costs
about 450 ms of every enabled request, so B4 has to come before any default-on decision.

## Full Quality Baseline

Run the fixed 11-probe set (30 expected facts) against the current local backend:

```powershell
.\uv.exe run python scripts\quality_harness.py --json --model qwen38-27b --max-tokens 8192 --reasoning-model qwen38-27b > logs\quality_baseline_qwen3_8_flash_next_20261010.json
```

Use `--model qwen38-27b` (gateway alias for the vLLM-served
`qwen3.8-flash-next`) and
`--max-tokens 8192`; the model spends budget on hidden reasoning, so smaller
limits risk empty or truncated answers. Evaluate the saved JSON:

```powershell
.\uv.exe run python scripts\evaluate_quality_harness.py logs\quality_baseline_qwen3_8_flash_next_20261010.json --model qwen38-27b
```

Persist only on a clean pass (all expected facts, style clean, no errors or
timeouts):

```powershell
.\uv.exe run python scripts\evaluate_quality_harness.py logs\quality_baseline_qwen3_8_flash_next_20261010.json --model qwen38-27b --persist --notes "SGLang qwen3.8-flash-next baseline via gateway alias qwen38-27b"
```

The 2026-10-10 `qwen3.8-flash-next` baseline scored a clean TOTAL 20/20 with
style 8/8 ok (25093 prompt tokens, 99.2 seconds) and was persisted as session
`quality_harness-20261009T214258101237-9d6f90f9`. A same-backend
`--compare-context` run scored 20/20 with context versus 3/20 without it and
revalidated `chars_per_token=3.5`: all eight measured context costs stayed
below their estimates (`0.82x-0.96x`, zero budget overages).

Those figures were measured against the earlier 8-probe, 20-fact set. `PROBES` has
since gained `explain_changed_files_contextbuilder` and
`explain_changed_files_repository_index` (3 facts each) and
`explain_changed_files_history_cap` (4 facts), the scored halves of the change-aware
ranking decision, so the current set is 11 probes and 30 expected facts and a clean
pass reads 30/30 with style 11/11. Comparing a new run with a persisted 20/20 compares
denominators, not quality.

### Current controlled baseline, 2026-10-24 (roadmap A1)

Roadmap item A1 established that current denominator: one `--compare-context` run over
all 11 probes and 30 facts, against `qwen3.8-flash-next` on the vLLM backend through the
gateway alias `qwen38-27b`, started from a detached worktree of `0371d64` with the
configuration written by `scripts/ab_launcher.py` (item A2) and with changed-file
ranking off. `--compare-context` flips `repository_context_enabled` per request through
one gateway, so it needs exactly one arm and cannot be combined with `--repeat`; the
no-context half of the pair is not a second gateway.

Commands, in run order, from the main checkout:

```powershell
# 1. a detached worktree outside the checkout, holding no .env
git worktree add --detach ..\lap-ab-a1-0371d64 0371d64
# 2. the experiment, and what the launcher says about that tree
.\uv.exe run python scripts\ab_launcher.py template --name a1_vllm_baseline `
    --worktree ..\lap-ab-a1-0371d64 --out build\ab_a1\experiment.json
.\uv.exe run python scripts\ab_launcher.py validate --config build\ab_a1\experiment.json
.\uv.exe run python scripts\ab_launcher.py show --config build\ab_a1\experiment.json --arm off
# 3. Terminal 1 - arm 'off' only, exactly as that block renders it: port 8011,
#    APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false, REQUEST_TIMEOUT=300,
#    APP_REPOSITORY_PATH=C:\Users\ovidi\lap-ab-a1-0371d64, harness timeout 345 s
# 4. Terminal 2 - the measurement, from inside the same worktree
Set-Location ..\lap-ab-a1-0371d64
.\uv.exe run python scripts\quality_harness.py --base-url http://127.0.0.1:8011/v1 `
    --model qwen38-27b --max-tokens 8192 --timeout 345 `
    --reasoning-model qwen38-27b --compare-context --json `
    > C:\Users\ovidi\local-ai-platform\logs\quality_compare_qwen38_vllm_20261024.json
.\uv.exe run python scripts\evaluate_quality_harness.py `
    C:\Users\ovidi\local-ai-platform\logs\quality_compare_qwen38_vllm_20261024.json `
    --model qwen38-27b --gateway-commit 0371d64 --persist `
    --storage-path C:\Users\ovidi\local-ai-platform\data\engineering_memory\memory_v1.json `
    --notes "Current vLLM qwen3.8-flash-next 11-probe/30-fact compare-context baseline; changed-file ranking disabled; 2026-10-24"
```

Only step 3 is taken from the launcher as rendered. `show --arm off` prints a Terminal 2
line carrying `--repeat 3`, the launcher's default because an isolated-worktree A/B
measures three repeats per arm; `--compare-context` refuses that combination outright, so
step 4 replaces that line - one arm, every registered probe, once, with the context flag
flipped per request instead of across processes. The arm's environment block, port,
`REQUEST_TIMEOUT=300` and the 345-second client timeout all come from the validated file
unchanged.

One thing in that sequence is not what the launcher renders, and it is worth knowing
before repeating the run: as recorded on 2026-10-24, `uv.lock` was gitignored, so a bare
`uv run` inside a fresh worktree resolved whatever was current on the index rather than the
set every earlier measurement used, and that set contained no `httpx` (`pyproject.toml`
declared `httpx2` while `packages/providers/openai.py` imports `httpx`) - the arm stopped at
import with `ModuleNotFoundError: No module named 'httpx'`. The arm was therefore started
with `UV_PROJECT_ENVIRONMENT=C:\Users\ovidi\local-ai-platform\.venv` and `uv run --no-sync`:
the worktree's code, the main checkout's interpreter (CPython 3.13.14) and its installed
packages, and nothing installed or removed by the run. The worktree is still what the
gateway indexed, which is the isolation the run was after.

That workaround is history, not the procedure to copy. Both causes behind it were removed
the same day: `uv.lock` is tracked instead of ignored, `pyproject.toml` declares `httpx`
(the `httpx2` entry installed a package no module imports), and the dev group now declares
`pytest-asyncio`, which the async provider tests need and which until then only existed in
this checkout's `.venv`. The current procedure for an isolated arm is to add the worktree,
run `.\uv.exe sync --locked` inside it, and start the gateway from that environment - no
`UV_PROJECT_ENVIRONMENT` pointing at the main checkout, no `--no-sync`, and no borrowed
interpreter. The A1 numbers above were measured with the borrowed environment, so that set
of package versions is part of that measurement's condition; reproducing them does not
require reproducing the workaround.

What was checked before the measured requests, on `http://127.0.0.1:8011`:

- `/health` - `{"status":"ok","repository_context_enabled":true}`
- gateway `/v1/models` - the alias `qwen38-27b`; backend
  `http://100.106.236.88:18300/v1/models` - one model, `qwen3.8-flash-next`
  (`owned_by: vllm`, `max_model_len: 400000`)
- `/debug/runtime-context` - `routing_mode=models_config`, `default_model=qwen38-27b`,
  `default_provider=openai`, `models[0].backend_model=qwen3.8-flash-next`,
  `models[0].base_url=http://100.106.236.88:18300/v1`, `context_window=262144`,
  `max_output_tokens=8192`, `chars_per_token=3.5`, `repository_context_max_tokens=4096`,
  `repository_context_intent_budget_map` `SEARCH/TEST/DEBUG=2048` and
  `REFACTOR/IMPLEMENT/EXPLAIN=4096`, `context_delta_injection=true`,
  `history_cap_enabled=true`, `history_cap_tokens=3000`, and the arm's own session log
- the arm's startup line - `repository_index path=C:\Users\ovidi\lap-ab-a1-0371d64
  files=505 modules=505 symbols=8590 relationships=18309 excluded_tests=0
  excluded_globs=13 duration_ms=5871.5`, and no `changed_files_signal enabled=true`
  line, which is what an arm with the opt-in off prints
- one smoke request, whose session record read `changed_files_signal=off`,
  `changed_files_count=0`, `context.status=assembled`, `estimated_tokens=3918` - the
  proof from inside the stage that this arm measured repository context and not the
  changed-file feature. Its record was removed from the arm's log before the measured
  run, so that log holds only this run's 22 requests.

The result, from `evaluate_quality_harness.py` against
`logs\quality_compare_qwen38_vllm_20261024.json`:

| arm | facts | style | prompt tokens | seconds |
|---|---|---|---|---|
| repository context on | `25/30` | `11/11` ok | 33109 | 129.6 |
| repository context off | `4/30` | `11/11` ok | 2221 | 532.1 |
| delta | `+21` | - | +30888 | -402.5 |

Twenty-two requests in 11 minutes 2 seconds of wall clock (harness started 20:24:51,
its JSON complete 20:35:53 local; 661.7 s of summed per-probe latency). No request
errored and none reached either timeout; the longest was 193.8 s against a 345 s client
limit and a 300 s provider limit. Style was clean in both arms, so nothing in this run
is preamble or tool chatter.

The context arm's five misses are `select_last_task_text`
(`refactor_repository_context`, 1/2), `packages/context/builder.py`
(`explain_changed_files_contextbuilder`, 2/3), and three of the four history-cap facts -
`max_current_tool_result_tokens`, `_looks_like_cline_tool_result_message` and
`[... truncated by gateway history cap ...]` - the last probe scoring 1/4 with only
`cap_history` arriving. Split that way the arm scores 19 of the 20 facts that belong to
no changed-file pair and 6 of the 10 that do, and the two probes that already have a
documented feature-off number land on it: `3/3` on
`explain_changed_files_repository_index`, where the 2026-10-12 off arm scored `9/9` over
three repeats, and `1/4` on `explain_changed_files_history_cap`, where the 2026-10-13
isolated-worktree off arm scored `3/12` over three repeats. That is what an arm without
the changed-file bonus is expected to score on them.

One truncation signal, and it is a measurement rather than a failed request: the
no-context `explain_changed_files_history_cap` call spent all 8192 completion tokens on
hidden reasoning and returned an empty answer in 193.8 seconds, and is scored `0/4` for
that reason. It is the same shape the 2026-10-10 exploratory run recorded on
`explain_live_path`, where an arm exhausted all 8192 completion tokens and lost that
probe, and it is why `--max-tokens 8192` is the documented setting.

Persisted as engineering-memory session
`quality_harness_compare-20261024T173757728411-2a4297e1` (workflow
`quality_harness_compare`, `metadata.model=qwen38-27b`,
`metadata.gateway_commit=0371d64`) in `data\engineering_memory\memory_v1.json`, which is
Git-ignored local state; `config_snapshot` is empty because the evaluator has no flag to
fill it, so the configuration this run was taken under is the block above rather than a
field of the record. The `20/20` figures earlier in this file and in `docs/STATUS.md`
stay what they are - measurements of the earlier 8-probe set, one of them on the SGLang
deployment this alias no longer points at - and this run supplements rather than replaces
them.



## Interpreting long runs, timeouts, and failed execution

Three independent timeout layers can each produce a failure report. Identify
which layer fired before re-running anything:

| Layer | Where it is set | What a failure looks like |
|---|---|---|
| Agent command transport | agent/IDE dependent | "failed execution" report while the harness process may still be running |
| Harness per-probe client | `--timeout` (default `120`) | probe `error: TimeoutError: timed out after 120.0s (harness client timeout; gateway/backend may still be generating)` and `seconds ~= 120` |
| Gateway/provider | `REQUEST_TIMEOUT` in `.env` | gateway aborts the provider call; the harness records an HTTP error instead |

- Expected wall time for a full `--compare-context` on `qwen38-27b` is
  roughly 5-15 minutes: the current set is 11 probes, so 22 requests, and the
  no-context reasoning probes are the slow ones and are the ones that can hit the
  per-probe timeout. Measured on 2026-10-24 against the vLLM backend, the whole
  pair took 11 minutes 2 seconds - 129.6 s across the eleven context requests and
  532.1 s across the eleven without it, one of which spent the full 8192-token
  completion ceiling and answered nothing in 193.8 s. The 5-15 minute range was
  measured on the earlier SGLang deployment of that alias and carried forward as
  the planning estimate; this run confirms it on the current one.
- Prefer foreground harness runs with the JSON redirected to an artifact
  (`> logs\quality_compare_<tag>.json`). Do not run the harness detached.
- If the agent reports "failed execution" for a long harness command, check
  whether the JSON artifact was written and whether the harness process is
  still running before re-running. Re-running immediately doubles the probe
  load on the shared backend.
- For reasoning models, run with `--timeout 300` and set a matching
  `REQUEST_TIMEOUT=300` in `.env` so the gateway/provider layer does not abort
  the request at its own shorter limit. Restart the gateway after changing
  `.env` so the new value applies.
- A single timed-out probe can be re-run on its own instead of the full set:

  ```powershell
  .\uv.exe run python scripts\quality_harness.py --probe implement_health_flag --no-context --timeout 300 --json --max-tokens 8192 --reasoning-model qwen38-27b
  ```

- In comparison output, an errored arm shows as `ERR` and its delta is marked
  `*`: the delta for that probe is invalid, but the other arm's result remains
  a valid standalone measurement.
