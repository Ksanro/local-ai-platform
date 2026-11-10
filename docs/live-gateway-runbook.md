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
$env:UV_CACHE_DIR="$env:TEMP\local-ai-platform-uv-cache"
$env:APP_SESSION_LOG_ENABLED='true'
$env:APP_SESSION_LOG_PATH='logs\sessions.jsonl'
$env:APP_CONTEXT_DELTA_INJECTION='true'
New-Item -ItemType Directory -Force logs | Out-Null
New-Item -ItemType File -Force logs\sessions.jsonl | Out-Null
.\uv.exe run python -m uvicorn apps.gateway.main:create_app --factory --port 8001
```

Leave this terminal running.

`UV_CACHE_DIR` points outside the repository on purpose. A cache directory inside the
checkout - `.uv-cache` at the workspace root is what an earlier version of this command
created - unpacks thousands of third-party `.py` and `.pyi` files next to the source, which
the repository scanner then walks: slow scans, and other projects' stubs reported as this
repository's code. `packages/repository/filters.py` now ignores a `.uv-cache` directory
wherever it appears and the scanner tests pin that, but keeping the cache in `$env:TEMP` is
what keeps the tree clean in the first place.

If the agent shell is Bash/Git Bash, start the same gateway with:

```bash
powershell.exe -NoProfile -Command "Set-Location 'C:\Users\ovidi\local-ai-platform'; `$env:UV_CACHE_DIR='C:\Users\ovidi\AppData\Local\Temp\local-ai-platform-uv-cache'; `$env:APP_SESSION_LOG_ENABLED='true'; `$env:APP_SESSION_LOG_PATH='logs\sessions.jsonl'; `$env:APP_CONTEXT_DELTA_INJECTION='true'; New-Item -ItemType Directory -Force logs | Out-Null; New-Item -ItemType File -Force logs\sessions.jsonl | Out-Null; .\uv.exe run python -m uvicorn apps.gateway.main:create_app --factory --port 8001"
```

That is the same command with `$env:TEMP` written out as its resolved path: a `$` inside a
string handed across two shells is a quoting trap the plain block above does not have.

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
  context-token estimation - the repository-context budget and, since roadmap
  A3, history capping (platform default 4.0; in fallback mode the platform
  default is reported)
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

### Context-selection determinism, 2026-08-22

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
qwen38/SGLang + `EXPLAIN:4096` context selection is deterministic within a
gateway process and across gateway restarts. Remaining run-to-run variance is
model-side sampling (answer wording, `completion_tokens`, wall-clock seconds).
No code fix was warranted.

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

### Intent budget measurements

The measured results behind the budget settings above, kept here as evidence.

The current live tuning baseline uses `SEARCH:2048`; in a same-prompt Cline A/B it
reduced median repository context from about `4013` to `2047` estimated tokens and median
prompt tokens from about `17,106` to `16,146`. The TEST baseline uses `2048`;
after enabling test indexing and clean Cline task extraction, a same-prompt
Cline validation preserved answer quality while reducing direct repository context from
about `2182` to `2020` estimated tokens and prompt tokens from about `15,397` to
`15,158` on the assembled turn. The DEBUG baseline uses
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

`multiturn_config_systems` had a repeatable 16/17 miss at the `2048` EXPLAIN
budget: the context trim dropped `apps/gateway/core/config.Settings`, so
`apps/gateway/core/config.py` never reached the answer. It was resolved on
2026-08-22 with two fixes - retrieval/promotion support for history-cap/config
symbols, and the EXPLAIN repository-context intent budget raised from `2048` to
`4096`. The probe now scores 2/2 consistently; the gateway log records
`modules_selected=9` and `estimated_tokens=3861` for the scored EXPLAIN turn.

### Token-estimate investigation, 2026-08-10

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
run-to-run variance already noted above (`explain_live_path` ranged 1119-1975 tokens
across 3 replicates at the same 2048 budget on 2026-08-09) - a
context-selection determinism question, not a token-estimation-accuracy one.
That question was closed on 2026-08-22; see "Context-selection determinism,
2026-08-22" under "Repeated Probe (--repeat)".

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
or goes into the promotion-observability fields. The index it measures over is this
repository's real one: 508 modules, 8571 symbols on this checkout.

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
  control**, and both arms of its live pair are expected to score 3/3. `ContextBudget`
  sits 15 points behind and sorts first on the tie-break - so the ceiling for that case
  is the gap itself, not the gap plus one.
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
a slot and not a membership. Measured again on 2026-10-25 with the guard in place, the
same run still sends 10 symbols, still moves the primary into the dirty file, and loses
nothing; and at 6144 tokens, where both files' symbols fit either way, the two arms now
agree on all three facts as well.

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
than containment. That pairing is the fix for the flaw in the first version of this
comparison, which appended its own wording to the scored probe and then attributed a
retrieval difference to the bonus.

Start the gateway with the flag set (`.env` is loaded with `override=True`, so
put it in `.env` or make sure `.env` does not already define it):

```powershell
$env:APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED='true'
.\uv.exe run python -m uvicorn apps.gateway.main:create_app --factory --port 8001
```

That is all a normal enabled request needs. To also measure what the bonus
*changed* - the counterfactual this section's tables are read from - set the
second flag, which roadmap B4 made opt-in and off by default:

```powershell
$env:APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED='true'
$env:APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED='true'
.\uv.exe run python -m uvicorn apps.gateway.main:create_app --factory --port 8001
```

Without it the stage composes and sends the change-aware context once and never
builds the no-bonus one, so every request whose bonus fired records
`changed_baseline_status=not_sampled` and the three difference fields are
placeholders. The comparison setting alone turns on neither the ranking bonus nor
the Git capture, and never changes what is sent.

Check that startup captured something - the line reports counts only, never
paths or contents:

```powershell
# in the gateway terminal
changed_files_signal enabled=true paths=5 captures=1 failures=0 outside_root=0 last_error=none
changed_files_comparison enabled=false
```

The second line states the effective comparison setting, and it is stated whether
or not the signal above it is enabled, because it can only ever be inert without
the feature. `paths=0` means a clean tree (expected on a freshly committed
checkout); take the
same number from `scripts\git_change_snapshot.py --json .` to cross-check.
`last_error` names an exception type only, and a non-zero `failures` value means
ranking fell back to its normal behaviour. A non-zero `outside_root` with
`paths=0` means Git's working tree and `APP_REPOSITORY_PATH` do not resolve to
the same directory - only the count is reported, never the paths.

Per-request lines carry the same bound, and name the promotion in counts only:

```text
repository_context request_id=... context_status=ok ... estimated_tokens=1840 changed_files_signal=ok changed_files_count=5 changed_symbols_selected=2 changed_primary_promoted=True changed_symbols_promoted=1 changed_context_differs=True changed_baseline_status=built changed_baseline_ms=0.4 duration_ms=...
```

That line is a request whose run asked for the comparison. The ordinary enabled
request today is the same line with
`changed_baseline_status=not_sampled changed_baseline_ms=0.0`: the changed-file
counters are still exact, and the three difference fields say nothing.

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
| `changed_baseline_status` | whether that comparison ran, and if not, why: `none` (nothing needed comparing), `built` (compared), `skipped_no_bonus` (no candidate carried the bonus, so the two arms cannot differ), `not_sampled` (the bonus fired and the comparison was not asked for - the ordinary enabled request since roadmap B4), or `failed` (it was asked for and could not be built) |

`changed_symbols_selected` answers "was the bonus in the context";
`changed_context_differs` answers "did it change the context", because the stage
can build the no-bonus context for the same request and compare the two composed
packages - and since roadmap B4 only when
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED=true` says to. The two
`promoted` fields are detail on top of that difference: which part of it the
primary and the added symbols account for. Only `built` and `skipped_no_bonus`
make those three fields readings; on `not_sampled` and `failed` they are
placeholders that the status field unmasks. Read together:

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
- `changed_baseline_status=not_sampled` - the bonus fired, the context went out
  once, and nobody built the no-bonus one. Every counter that does not need the
  comparison is exact; the three that do are placeholders, and this record is not
  evidence that the bonus changed nothing;
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
modules with 8 changed, about 50 ms becomes about 105 ms, and B3's live pairs
measured roughly 450 ms of request time - so since roadmap B4 it is made only when
the run asks for it, and then only when the ranking pass gave the bonus to at
least one candidate, and the cost of a build that was made is what
`changed_baseline_ms` states - `0` on a request that was never compared. Note that
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
Those counts have two denominators, because the two kinds of field are not
equally available: `changed_files_count > 0` and `changed_symbols_selected` are
directly observable and are tallied over every record stating the fields, while
`changed_primary_promoted` and `changed_symbols_promoted` need a comparison, so
they are tallied over the `measured` records only - a status of `built` or
`skipped_no_bonus` under an `ok` signal - and the printed rate says `of N
measured` rather than `of fielded`. Averaging a `not_sampled` placeholder `false`
into that rate would report a request nobody compared as a measured no-change.
A record whose comparison `failed` or was `not_sampled`, and one that never states
the comparison fields, land in `unmeasured` and in neither verdict - which since
roadmap B4 is where an ordinary production request sits, so a log of normal traffic
says nothing either way about the bonus and must not be read as if it said
"inert". Records written before the
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
Both arms also set `APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED=true`:
since roadmap B4 an enabled arm that does not ask for the counterfactual still sends
the bonus and still ranks with it, but records `not_sampled` and leaves
`changed_context_differs`, `changed_primary_promoted` and
`changed_symbols_promoted` as placeholders, so the promotion gates below could not be
read at all. `scripts/ab_launcher.py` declares that setting in the shared block of
every experiment it renders and refuses a changed-file pair that declines it.

```powershell
# arm 1: gateway started with APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false
#        and APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED=true
#        (and APP_REPOSITORY_CONTEXT_MAX_TOKENS=4096 on both arms: all three scored
#         implementation facts are lost at that configured budget)
.\uv.exe run python scripts\quality_harness.py --probe explain_changed_files_repository_index --repeat 3 --json --model qwen38-27b --max-tokens 8192 --timeout 300 --reasoning-model qwen38-27b > logs\quality_changed_files_off.json
# arm 2: restart with APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=true
#        (keeping APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED=true)
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
Roadmap B4 later added a sixth line to the shared block -
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED=true` - which both arms of a
re-run receive identically, so a re-run still differs in exactly those same two lines;
this run predates the setting, when the counterfactual was not optional and every
enabled request that fired the bonus paid for it. That is why the enabled arm's records
below carry `changed_baseline_status=built`, and why a present-day ordinary request
would instead read `not_sampled`.
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
| gain | `explain_changed_files_history_cap` | `packages/pipeline/history.py` | `packages/pipeline/history` | MOVE, `1/4 -> 4/4`, `facts_lost` empty (whole-module delivery; since `bc87179`'s per-symbol spans the same pair is `0/4 -> 3/4` offline - see *Phase G*) |
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

## Conversation File Activity (roadmap C1)

The second measurement the gateway makes about context, on the same record and for
the same reason - to answer a question no single request can. The change-aware
fields above ask *what the working tree changed about what we sent*. These fields
ask *what the conversation's own agent then did with files*: which files its tool
results say it read, which it wrote, and whether it opened the ones we had already
put in front of it.

It is wired unconditionally: `apps/gateway/main.py` builds one
`FileActivityTracker(maxsize=settings.context_delta_cache_size)` during `lifespan()`
and hands it to `RepositoryContextStage` with the repository root. There is no
feature flag for it, because it reads no Git, decides nothing about what is sent, and
changes no prompt. Startup says so once, in counts:

```text
file_activity enabled=true transcript_states=256 files_per_state=256
```

`transcript_states` is `APP_CONTEXT_DELTA_CACHE_SIZE` - the same number the symbol-delta
tracker is sized with, deliberately, so the two caches that hold client-supplied history
cannot drift apart. It is a count of stored transcript-prefix states, **not** of
conversations: one conversation adds a state per request that answered one of its earlier
prefixes, so a long conversation spends many of them and an older prefix can be evicted
while the conversation is still running. `files_per_state` is the cap on each file set
inside one state. An earlier wording of this line said `conversations=256`, which promised
a bound the store does not have.

### The grammar it reads

A Cline conversation endpoint reports every tool result back to the model as a
user-role message whose first line is an anchored header (`packages/pipeline/cline_activity.py`):

```text
[read_file for 'apps/gateway/session_log.py'] Result:
<the result body - examined for 200 characters and for nothing but a status token>
```

Nothing else counts as an envelope: the header must start the message after leading
whitespace, its tool must be a member of `CLINE_FILE_ACTIVITY_TOOLS`, and it must close
within `MAX_ENVELOPE_HEADER_CHARS` (2048) with `"] Result:"` - or with a trailing `"]"`,
which is the form the gateway's own history cap leaves behind when it truncates the body. A
header found *inside* a result body is never seen, because the parser stops at the
terminator; that is what makes a file containing a quoted envelope unable to report an
operation. `read_file` reads; `write_to_file` and `replace_in_file` modify;
`search_files`, `list_files` and `execute_command` are recognized as agent activity
that names no file - their target is a pattern, a directory or a command line, and the
files inside their output belong to the result body, which is not scanned.

That recognition set is deliberately wider than the set the rest of the pipeline *reacts*
to, and the difference is one table with two views of it.
`packages/pipeline/user_messages.py` holds the registry - `CLINE_ENVELOPE_SPECS`, one entry
per tool, each carrying the activity it names and a `bookkeeping` flag - and derives both
views from it: `CLINE_FILE_ACTIVITY_TOOLS` for measurement, and
`CLINE_TOOL_RESULT_PREFIXES` for the two older consumers, task-text selection in planning
and the current-tool-result cap in `packages/pipeline/history`. The flag is set for exactly
the four tools those consumers recognized before C1 (`read_file`, `search_files`,
`list_files`, `execute_command`) plus the `[attempt_completion]` and `[ERROR] You did not
use a tool` bodies, so a `[write_to_file for x.py]` or `[replace_in_file for x.py]` result
is counted here and forwarded whole, byte-identical, exactly as it was before the
measurement existed. C1 widened what the gateway can see; it changed nothing about what the
gateway sends, and this is the boundary where that had to be proved.

Every target is normalized before it is counted - slashes, `.` segments, relative and
in-repository-absolute spellings, Windows drive letters, NTFS streams, Unicode
composition - and then checked for containment against the resolved repository root,
`realpath` on both sides with `strict=False` so a modification target that does not
exist yet is still measurable. A refused target yields one token and one counter
(`paths_rejected`): `empty`, `quoting`, `nul`, `control`, `length`, `drive`, `stream`,
`outside`, `self`, `root`. The counter is one per envelope, never one per path, because
remembering a path would defeat the boundary. A target that does not exist on disk is still
measurable by that `realpath(strict=False)` containment - the file a write is about to create
measures like one already there - and only a root the filesystem refuses to name at all marks
the measurement unavailable. The one spelling that was ever wrong is fixed: a Windows
drive-absolute target (`C:\Users\dev\repo\x.py`) was the one spelling that used to be read as
relative and joined onto the root, landing outside it; it is now recognized as absolute before
any joining is attempted.

Resolution is memoized at two levels. Within a request, `resolve_file_activity_events`
keeps a local map from target spelling to resolved identity, so the forty copies of one
envelope a re-sending transcript carries cost one lexical check and one lookup rather
than forty; it is bounded by `MAX_ENVELOPES_PER_REQUEST`. Across requests (since roadmap
E3, 2026-11-03), `RepositoryPathNormalizer` keeps the filesystem answers - what
`realpath` and `relpath` returned for a lexically checked candidate - in a bounded
least-recently-used map (`MAX_RESOLVED_PATHS`, 4096 entries). This replaced the earlier
rule that no client path outlives its request, on purpose: re-resolving every file a
conversation had named cost about 150 us per path per request on Windows and was the
largest remaining part of C1's cost. A client can choose which paths are looked up, never
what they resolve to; a `realpath` that raises is not remembered; nothing in either map is
logged or returned. The accepted cost is staleness: a symlink or junction re-pointed while
the gateway runs keeps its old answer until evicted or restarted. The containment rules,
the rejections and the counts are unchanged.

Measured on this machine (one throwaway script, 25 repetitions per shape, median of a
`resolve_file_activity_events()` call over a temporary repository, before and after the change;
not a test, and no timing assertion belongs in the suite):

| transcript shape | envelopes | distinct target spellings | before | after |
| --- | --- | --- | --- | --- |
| three writers over eight files, one spelling each | 256 | 8 | 43.2 ms | 2.9-3.2 ms |
| absolute in-repository reads of 32 files, each repeated eight times | 256 | 32 | 51.8 ms | 7.9-9.1 ms |
| reads and searches, short transcript | 64 | 9 | 5.8 ms | 1.0-1.2 ms |

The gain is `realpath` calls avoided - 256 to 8, 256 to 32 and 64 to 9 respectively - so it
grows with how much of a transcript repeats itself, which is exactly what a re-sending client
produces. It is a claim about this function on this filesystem, not about request latency: C1's
end-to-end cost is still unmeasured, and measuring it needs a feature-off arm (see *Verification
status*).

### Native tool calls (Cline 4.x)

Cline 4.x writes no envelopes. A 2026-11-02 wire capture of Cline 4.1.26 (29 requests, kept
outside the repository) shows OpenAI native tool calling: an assistant turn with
`content: null` and `tool_calls` naming the tool and its JSON `arguments`, answered by a
`role: "tool"` message with the matching `tool_call_id` whose content is a JSON string.
`NATIVE_TOOL_ACTIVITY` in `packages/pipeline/cline_activity.py` maps the tools:

| Tool | Activity | Targets | Status read from the result |
| --- | --- | --- | --- |
| `read_files` | read | `files[].path` (or a single `path`/`file_path`) | per-file list entry, by position |
| `editor` | modified | `path` | the result object |
| `search_codebase`, `run_commands` | no file | - | - |

Only the decoded result's `error` and `success` keys are read: `success: true` confirms,
`success: false` or an `error` key fails (a denied edit is `not_modified`, a rejected
read is a failed read), and anything else - no status, text that is not JSON, a list whose
length does not match the call's files - is `unknown`. The `result` text is never
examined. Targets go through the same normalizer as envelope targets, so Cline's absolute
`c:\...` paths inside the repository become repository-relative and anything outside is
rejected. Tools outside the table (`ask_question`, `fetch_web_content`) and results for a
call the transcript never announced are not activity. A file a model changes through
`run_commands` is not attributed, exactly as `execute_command` never was.

Replayed over that capture offline, the parser reports 3 confirmed reads, 1 confirmed
modification and 16 file-less events on the final request, and every request's snapshot
is non-decreasing: the same transcript resent restates its activity rather than adding to
it.

**Native-Cline live validation (roadmap E2, 2026-11-02).** Run `e2native-20261102-0939Z`
at `b6d4a58`: an isolated worktree, a gateway on port 8031 indexing that worktree and
logging to its own file (confirmed through `/debug/runtime-context` and a config check
before the first request), and a real Cline 4.1.26 task in Act mode with auto-approve off.
Six turns asked for, in order: a read, a search, creating a marker file (approved), a read
of a missing file, an edit to the marker (rejected), and a tool-free answer. The model ran
no shell command. Results:

| Record | `n_messages` | What it shows |
| --- | --- | --- |
| 1 | 2 | `state=none`, `correlation=no_prior_context` - nothing done yet |
| 2 | 4 | 1 confirmed read; `correlation=measured`, `touched_without_context=1` |
| 4 | 8 | the search, as `other_events=1` |
| 6 | 12 | 1 confirmed modification, `files_touched=2` |
| 8 | 16 | the missing file: `read_attempts=2`, `reads_failed=1` |
| 9-12 | 18-25 | unchanged snapshot through the rejected edit and the final answer |

The final record matches Cline's own saved task record call for call: `read_files` twice
(one success, one failure), `search_codebase` once, `editor` twice (the creation, then the
rejected edit, which cannot undo the confirmed modification of the same file), and
`ask_question` once, which is not activity. 12 requests produced 12 records, every one
with usage figures and `context.status=assembled`, so repository context survived the
tool messages. `scripts/analyze_sessions.py` over the log exits 0, reaches `END OF REPORT`,
and its FILE ACTIVITY section contains no path. Evidence, including the raw log, stays in
`C:\Users\ovidi\lap-e2-evidence\e2native-20261102-0939Z`. This validates counting only;
it measures no latency and no ranking or answer quality.

### Attempts and outcomes are separate numbers

A header says an operation was attempted. The client's own result line says what
happened, and its wording is client-authored prose, so the read is narrow and closed:
`successfully saved` is a confirmed write; `tool execution failed` and `no changes
were made` are a write that did not happen; a read whose head *begins* with `the tool
execution failed` is a failed read and any other non-empty read body is content, hence
a confirmed read; anything else is `unknown`. Each file then gets **one** outcome per
operation kind by precedence over every envelope the transcript holds - confirmed if
any result for that file confirmed, else not-modified/failed if any did, else unknown -
so a failure followed by a success is confirmed and a success followed by a failure
stays confirmed. The precedence decides which counter a file lands in, never how many
times it is counted:

```text
read_attempts          == files_read + reads_failed + reads_unknown
modification_attempts  == files_modified + modifications_not_modified + modifications_unknown
files_touched          == the union of the confirmed read and write sets
```

None of it is filesystem truth, and `unknown` is the honest answer rather than a
failure to measure: a client that words its results differently lands there instead of
in either claim.

### A snapshot, not a tally

Cline re-sends the whole prior conversation inside every request, so the transcript
*is* the history and there is nothing for a counter to accumulate. Everything
describing what the client reported is recomputed from the events of the request being
answered and nothing else, which gives the property the tests pin:

```text
same transcript + same supplied-context state = byte-identical output dict
```

The earlier claim-based model counted on every observation, so a file read on turn one
was fifteen reads by turn fifteen, and it needed a `replay_suppressed` counter to
explain the difference. That field is gone, along with `file_events`, because the
numbers no longer drift and there is nothing left to suppress.

The one question a transcript cannot answer is genuinely temporal - *was this file
already in front of the agent when it opened it?* - and `context_files_touched` is the
only quantity that consults remembered state. Four rules are what make it a measurement
rather than an artifact:

- a file is credited only when the successful operation on it is **new** to this
  conversation; an operation an earlier transcript already showed the tracker is
  history being re-sent, not an agent acting on what it was just given;
- the current request's supplied files join the remembered set **after** correlation,
  so context that arrives on the same request that reports touching a file proves only
  that the context arrived;
- correlation never reconsiders a historical event against context supplied later,
  which is the retroactive-attribution bug those two rules exist to stop;
- **a gap in a lineage is sticky.** The request that finds its prefix missing marks the
  state it stores discontinuous, and every descendant inherits that mark, so the
  conversation keeps reporting `tracker_miss` instead of resuming `measured` on the turn
  after the eviction, restart or rewritten history. What was supplied before the gap is
  permanently unknown here, and a partition of the touched set would have been a guess.

`touched_without_context` is `files_touched` minus `context_files_touched`, so the pair
partitions the touched set and cannot disagree - and both are zero while the lineage is
discontinuous, which is what `correlation` is there to say.

Conversation identity is a fingerprint of the complete message prefix, **assistant
turns included** - not the user-only key `packages.context.delta` uses, because the
activity being measured is the agent's and a key blind to the assistant's turns merges
two conversations that differ only there. Each request looks up the state keyed by the
transcript *before* its newest turn and stores the derived state under what it just
sent, which is what lets a replay find its own numbers. The honest limitation: the
fingerprint is content, not identity. Two independent conversations whose transcripts
are byte-identical are, to this module, one conversation, and nothing in a
chat-completions request carries a conversation ID that could tell them apart.

What that keying costs is worth stating plainly, because the bound is written as a
count of entries: the store holds **transcript-prefix states, not conversations**. One
conversation contributes one entry per request that answered one of its earlier
prefixes, so a five-turn session occupies five slots, and a tracker sized to 256 is a
tracker that holds about 256 requests' worth of lineage across all conversations - not
256 long conversations. That is deliberate: keeping a state per prefix is what lets a
retry or a branch of an older turn find the lineage that was current when it was sent.

### What a record carries

`context.file_activity` is one nested dict, seventeen keys, count-only. The path out is
`RepositoryContextStage` metadata, then `sanitize_file_activity` in the chat endpoint,
then the session logger; a file path crosses none of those boundaries.

| field | meaning |
| --- | --- |
| `state` | whether the transcript was read: `measured`, `none` (nothing recognizable - what a client that sends no envelopes reports), `partial` (a bound kept something out, so the totals are a floor), `unavailable` (the measurement did not run - no tracker, no root the OS can name, or a stage that failed) |
| `correlation` | whether the two correlation counters are a measurement: `measured`, `no_prior_context` (the conversation is remembered and nothing was ever supplied - a real zero), `tracker_miss` (an earlier request existed that this tracker cannot reconstruct: eviction, restart, or a rewritten history - and every later request in that conversation reports it too, because the gap does not close), `unavailable` |
| `files_read` | unique files whose read result confirmed |
| `files_modified` | unique files whose write result confirmed |
| `files_touched` | the union of the two above |
| `read_attempts` | unique files a read header named, whatever the result said |
| `reads_failed` | read-attempted files whose every result said the read failed |
| `reads_unknown` | read-attempted files whose results could not be classified, including a body the history cap truncated away |
| `modification_attempts` | unique files a modification header named, whatever the result said |
| `modifications_not_modified` | attempted writes whose results said nothing was written, with no later confirmation for that file |
| `modifications_unknown` | attempted writes whose results could not be classified |
| `context_files_touched` | successfully touched files this conversation had already been *supplied* as context on an earlier request |
| `touched_without_context` | the rest of the touched set |
| `changed_files_touched` | touched files the working-tree signal also reports as modified; zero whenever that signal is off or clean |
| `paths_rejected` | file-naming envelopes in the retained window whose target the repository refused - one per envelope, never one per path |
| `other_events` | recognized envelopes in that window naming no file: `search_files`, `list_files`, `execute_command` - counted as events, not as tool kinds |
| `events_beyond_bound` | recognized envelopes a bound kept out of this request's window, plus files a per-state bound would not hold |

Two of those states are easy to read wrongly. `state=none` and `state=unavailable` both
report zeroes, and only one of them means the gateway looked. A tracker miss reports the
correlation pair as zero, which is why `correlation` exists at all: an evicted
conversation and a conversation that genuinely never saw context would otherwise differ
by nothing - and a miss now stays reported for the whole rest of that conversation rather
than for the single request that happened to notice it. `events_beyond_bound` is what
separates "this session touched nothing" from "this session was not counted", and a file
dropped because a bound was reached is counted *there* and not in `paths_rejected` - the
path was fine, the bound was not.

Because the totals are rebuilt from the transcript on every request, both of those
counters count envelopes, not the shapes of envelopes: fifty refusals of the same kind are
`paths_rejected=50`, and nine searches, listings and commands are `other_events=9`. That
was not true before this pass, when each was the size of a set of tool-and-reason pairs,
and the only reason it can be true now is that nothing has to be remembered to make it
so - the transcript is the tally, and no refused string is kept anywhere.

The bounds, all of them forced by the transcript being client-supplied: 256 transcript-prefix
states per tracker (configured, from `APP_CONTEXT_DELTA_CACHE_SIZE`), 256 unique files per
set within a state (`MAX_UNIQUE_FILES_PER_STATE`), 256 envelopes per request
(`MAX_ENVELOPES_PER_REQUEST`), 2048 header characters (`MAX_ENVELOPE_HEADER_CHARS`), 512
path characters (`MAX_PATH_CHARS`), a 200-character result head
(`MAX_RESULT_HEAD_CHARS`), and 2048 fingerprint characters over the newest 256 messages
(`MAX_FINGERPRINT_CHARS` / `MAX_FINGERPRINT_MESSAGES`). What a bound forces out is
counted, and it is the *oldest* envelopes that fall out of a bounded parse, so what the
conversation just did stays visible.

An observation that cannot be made never costs the request anything: everything that
decides what the turn sends has already happened by the time the stage records activity,
so a tracker with no root, an unresolvable root, or a measurement that raises writes
`state=unavailable` and lets the context through unchanged.

### Reading the records offline (roadmap E1)

The section above is what a record carries; this is what to do with a log of them. No
gateway has to be running, no request has to be made, and nothing on the live path
changes:

```powershell
.\uv.exe run python scripts/analyze_sessions.py logs\c1_live_validation_20261025.jsonl
```

The analyzer prints a `FILE ACTIVITY` section beside its changed-file promotion section.
It is count-only and reads nothing outside the seventeen documented keys.

**The headline rule: every counter in it is a per-record transcript snapshot, and none
of them is ever summed across records.** C1 recomputes all fifteen counters from the
complete transcript the request carried, and a Cline client re-sends its whole
conversation on every turn, so a file read once on turn one is stated again by every
later record. A "total files read" would count that read once per later turn - the
double-counting C1's snapshot model replaced - so the report gives, for each counter,
how many records can answer (`eligible`), how many answered above zero (`nonzero`), and
the median and maximum a *single* record reached. There is no cross-record total to
read, and a session that touched one file across fifty turns has fifty records at `1`,
not a `50`.

How the awkward records are handled, all of them kept distinguishable rather than
folded into a zero:

| case | what the analyzer does |
| --- | --- |
| no `file_activity` key at all | counted as *predating C1* and excluded from every distribution and statistic, so an old log can neither inflate nor deflate a finding |
| `state=measured` | counted, and its counters are readings |
| `state=none` | counted, and its zeros are readings: the transcript was looked at and held nothing the gateway recognizes. This is not `state=unavailable`, and it is not the changed-file feature's own `changed_files_signal=off`, which means that feature was switched off |
| `state=partial` | counted, with every value labelled a **floor**, because a bound kept events out of the parse; the state distribution shows how many records are partial |
| `state=unavailable` | counted in the state distribution and excluded from the activity statistics, because nothing was measured |
| `correlation=measured` / `no_prior_context` | the two correlation counters `context_files_touched` and `touched_without_context` are read; `no_prior_context` is a real zero - nothing had been supplied earlier in that conversation |
| `correlation=tracker_miss` / `unavailable` | counted in the correlation distribution and excluded from the two correlation counters, whose zeros there describe a lineage gap rather than a conversation that never saw context |
| an object missing a required key | counted as *incomplete* and excluded, because a partially deployed writer states some fields and not others |
| a non-object, a non-string token, or a counter that is a float, a bool or a negative | counted as *malformed* and excluded, because coercing one would turn an unreadable value into a confident zero |

A record is placed in exactly one coverage case, in that order: not-an-object, then a
missing key, then an unreadable value. An unrecognized *string* token is not malformed -
it is a valid record whose token this script has never seen, and it lands in the
`unknown` bucket of its distribution, which excludes it from the statistics without
erasing the fact that the writer emitted it.

Privacy is structural, not a filter: only the seventeen keys are ever indexed, unknown
nested keys are ignored rather than enumerated, token values are matched against the
documented sets and printed as bucket names, and nothing else from the section reaches
the output - no path, module name, symbol, result body or envelope text. Tests plant
path-like, module-like, symbol-like, body-like and envelope-like values under unknown
keys and assert they never appear.

**Offline validation on retained evidence (2026-10-31).** The analyzer was run over four
retained logs, all of them records C1 had already written before this item existed - so
these runs read old evidence and measure nothing new, and no gateway was started and no
backend request was made for any of them. Each run is the complete command over the whole
log, and counts as a pass only when the process exits 0 and the output reaches
`END OF REPORT`: a section that prints and a report that finishes are different claims,
and the milestone needs the second.

| retained log | records | stating `file_activity` | `state` | `correlation` |
| --- | --- | --- | --- | --- |
| `logs/c1_live_validation_20261025.jsonl` (the 2026-10-26 probe above) | 4 | 4 | 3 measured, 1 none | 2 measured, 2 no_prior_context |
| `build/a3/20261030/sessions_base.jsonl` (roadmap A3 control arm) | 9 | 9 | 3 measured, 6 none | 3 measured, 3 no_prior_context, 3 tracker_miss |
| `build/a3/20261030/sessions_cand.jsonl` (roadmap A3 candidate arm) | 9 | 9 | 3 measured, 6 none | 3 measured, 3 no_prior_context, 3 tracker_miss |
| `logs/implement_budget_A_4096_20260801.jsonl` (pre-C1 traffic) | 592 | 1 | 1 none, 591 predating C1 | 1 no_prior_context |

The A3 pair shows the two exclusion rules doing their work on genuine traffic. All nine
records are eligible for the thirteen transcript-only counters: `files_read`,
`files_touched` and `read_attempts` each read 9 eligible / 3 nonzero / median 0.0 /
max 1. Three of the nine requests reported one read, and a cross-record sum would have
printed `3` - a number no record ever claimed - so the report gives the median and the
maximum of what single records said instead. The correlation pair is eligible for only
six of the nine, because three carry `correlation=tracker_miss`: an A/B restarts the
gateway between arms, so the tracker had lost part of each conversation's lineage, and
those zeros are excluded rather than averaged in as "nothing was supplied earlier". Where
the lineage held, `context_files_touched` reads 0 nonzero of 6 and
`touched_without_context` reads 3 nonzero of 6 - the touched files had not been supplied
as context before, which under `measured`/`no_prior_context` is a finding and not a gap.

The older `logs/implement_budget_A_4096_20260801.jsonl` is the pre-C1 case: 592 records,
591 of them counted as predating C1 and excluded from every distribution, and the one
record that does state the section is a stray later probe appended to that file. The
section printed cleanly for all four logs and carried no path, module, symbol, body or
envelope content: an automated check for `/`, `\`, `.py`, `apps/`, `packages/`,
`Result:`, `environment_details` and `def ` inside the printed section found no match in
any of them.

**The defect these runs surfaced, and the fix E1 made for it.** That fourth log holds 33
records with `status=error`, and 27 of them store `error: null` - what the gateway logs
when a failed response carried nothing parseable. The `ERROR REQUESTS` block rendered
that with `r.get("error", "unknown")[:120]`, which slices `None`, so the run died after
printing every section above and never reached `END OF REPORT`. Running HEAD's own copy
of the script over the same four logs reproduces exactly that - exit 1 on this log at
that statement, exit 0 on the other three - so the defect predates the file-activity
work and this repair changes the outcome of one run out of four; it is fixed here rather
than left as a follow-up because a milestone cannot claim to have validated a log whose
analysis does not finish. Each field is now converted
to text before it is truncated: a null or absent `request_id` or `error` prints
`unknown`, a null or absent `last_user_message` prints empty, and a number, bool or
container prints its `str` form. The widths stay 12, 120 and 80 characters, the two lines
per record keep their shape, and no error classification or record selection moved - the
27 null-error records print `error=unknown` and the 6 that logged real text print the
same text they printed before. All four runs now exit 0 and reach `END OF REPORT`, and
the 8 tests added to `tests/scripts/test_analyze_sessions_activity.py` for this cover the
fallbacks, the widths, the conversion of non-string values, and that the report still
finishes with a path-bearing record in it.

### Verification status

Everything above is pinned offline, and only offline: `tests/pipeline/test_file_activity.py`
(grammar, containment, snapshot idempotency, outcome partitioning, the four temporal
regression directions, sticky lineage, bounds, eviction and restart, sanitization,
fingerprint identity, stage integration, failure-keeps-request),
`tests/pipeline/test_user_messages.py` (the registry's two derived views, and the
pre-C1 behavior of task-text and query selection) and the envelope-capping cases in
`tests/pipeline/test_history.py`, plus `tests/gateway/test_session_log.py` for the record's
shape, and `tests/scripts/test_analyze_sessions_activity.py` for the offline report above.

**What C1 does not change, and where that was almost lost.** The activity path is
observational: it decides nothing about what a request sends, and by the time the stage
records activity the composed context has already been chosen. That was not true of the
first version of C1. `CLINE_TOOL_RESULT_PREFIXES` - the set the history cap truncates and
planning text selection ignores - had been derived from the widened envelope table, which
quietly made a `write_to_file` or `replace_in_file` result a truncation target and removed
it from query-text selection. Both were behavior changes outside C1's scope, and both are
now reverted: the registry keeps one entry per tool with a `bookkeeping` flag, and the
flag is set for exactly the four tools the pipeline treated that way before C1. A writer's
result is measured and reaches the model whole; `tests/pipeline/test_history.py` and
`tests/pipeline/test_user_messages.py` assert both halves of that sentence, and
`test_the_compatibility_prefixes_are_exactly_the_pre_c1_set` fails the moment the derived
set drifts.

**C1 received its first restarted-gateway live validation on 2026-10-26, and it passed.** A
gateway started from `f74d16d` wrote four session records, and every live criterion held:
the `file_activity enabled=true` startup line appeared, `context.file_activity` carried
exactly the seventeen documented keys in a real record, a request with no envelope reported
`state=none`, the request after it reported `state=measured` with
`correlation=measured` (not `tracker_miss`), and the replay reported the identical
dictionary rather than a doubled one. What this does *not* validate is any quality, ranking or
performance effect: C1 decides nothing about what a request sends and no ranker reads it, and
the run carried no feature-off arm beside it, so it says nothing about what the measurement
costs.

**Those four requests were hand-scripted, not native Cline traffic.** They were composed by a
probe and `POST`ed to the gateway, so they prove the pipeline parses, correlates and records
the envelopes it was given. They do not prove that a real Cline client sends that shape. That
gap is what the log survey below is for.

### Real Cline traffic in the existing records

Before extending the grammar to any new wording, the repository's own session records were
searched - counts and envelope headers only, no path and no body text reported - for
anchored Cline tool-result envelopes:

Counted once per record and header, deduplicated across the fields of a record so that an
envelope mirrored from `last_user_message` into `planning` is one envelope and not two: 515
records carry at least one.

| envelope | occurrences | what the gateway makes of it |
| --- | --- | --- |
| `[read_file for ...]` | 315 | 284 `confirmed`, 31 `failed` by the anchored read-failure prefix |
| `[search_files for ...]` | 108 | recognized, names no file |
| `[list_files for ...]` | 49 | recognized, names no file |
| `[execute_command for ...]` | 29 | recognized, names no file |
| `[replace_in_file for ...]` | 5 | `modified` / `confirmed` |
| `[write_to_file for ...]` | 2 | `modified` / `confirmed` |
| `[ask_followup_question for ...]` | 6 | **not** recognized: no grammar is claimed for it, so it yields no event |
| a header that never closed in the window | 1 | not an envelope: `execute_command`, parsed to nothing |

Every one of them sits in a user-role message: the corpus stores the turn in the gateway's
`last_user_message` field, and no record carries an envelope under a `tool` role. That is the
assumption C1's grammar rests on, and it is as far as these records can speak to it - they hold
no message list with roles, so a client that delivered results as `role="tool"` would leave no
trace here to search for.

The writer rows are the load-bearing ones: every writer result found begins
`The content was successfully saved to <path>.`, which contains this gateway's one
confirmed-write marker, `successfully saved`. Seven for seven, real Cline write results
classify as confirmed modifications under the closed grammar, and the header form is the
`'<target>'] Result:` the parser expects. Reader results split the way the documentation
already says they must - a successful read's body is the file's own text, so only a head
*beginning* with the failure prefix is a failed read, and the read total is an upper bound.
Envelope headers that appear only *inside* another message's body - the shape a quoted
envelope in a file or an answer produces - were found too (9 of them) and parsed as nothing,
which is the injection rule working as documented.

Two findings are recorded and deliberately not acted on. **72 of the 315 real `read_file`
results begin `[DUPLICATE READ] You have already read '<path>' N times in this conversation`,
whose own wording says the content was not sent again.** Under the anchored read rule that head
is not a failure prefix, so each of those counts as a confirmed read, and `files_read` is
correspondingly a count of successful read *attempts* rather than of files whose text reached
the model on that turn. That is a change to what a counter means, so it is not made on the
strength of a survey - it is recorded here for the next pass, which has a number attached to it.
And `[ask_followup_question for ...]` (6 occurrences) is a Cline tool the gateway sees in its own
traffic and does not recognize, which is the correct behavior for an unverified grammar and a
reminder that the registry is a closed set by choice. Nothing else was added: no "the user denied
this operation" wording (0 occurrences in these records), no save-after-user-edit wording, and no
`role="tool"` handling.

The corpus spans 2026-07-28 to 2026-10-26 and is dominated by records from late July and
August 2026; the October tail is the synthetic probe below. A short live task run through the
restarted gateway with the currently installed Cline was **not** possible at the time of
writing: the gateway was not running, nothing was connected to it as a client, and the newest
task in the installed Cline's own history predates this work by two months. Driving the
extension means driving a VS Code UI, which is not available here, so the check stopped at the
log survey rather than being answered with another synthetic request relabelled as real
traffic.

### The procedure, as it was run

Start a gateway from the committed tree. `apps/gateway/main.py` loads `.env` at import with
`override=True` and `get_settings()` is `lru_cache`d, so a shell variable set before startup
loses to the `APP_SESSION_LOG_PATH` on disk - which also means the `$env:APP_SESSION_LOG_PATH`
line in *Start Gateway* above only wins when the tree has no `.env` file. To keep this probe's
records apart from ordinary traffic without editing `.env`, the run served the real app out of a
scratch launcher kept outside the repository: `%TEMP%\c1_live\launch_gateway.py`, a file that
was deleted when the probe ended and has never existed in the tree. Everything it needs to
contain is this:

```python
"""Serve the real gateway app against one dedicated session-log file."""
import os

import uvicorn

import apps.gateway.main as gateway_main  # the import resolves .env, override=True included

os.environ["APP_SESSION_LOG_PATH"] = os.path.join("logs", "c1_live_validation_20261025.jsonl")
gateway_main.get_settings.cache_clear()  # drop the Settings instance built from .env
uvicorn.run(gateway_main.create_app(), host="127.0.0.1", port=8001, log_level="info")
```

`create_app()` is the same factory the documented
`python -m uvicorn apps.gateway.main:create_app --factory --port 8001` serves, so nothing about
the request path was specific to this probe - only the destination of the session records was.
The launcher that ran additionally printed the resolved path, which is where the
`session_log_path` line below came from. It was started from the repository root, hidden, with
its streams redirected to diagnostics files:

```powershell
$env:UV_CACHE_DIR="$env:TEMP\local-ai-platform-uv-cache"
.\uv.exe run python $env:TEMP\c1_live\launch_gateway.py
```

The probe as run set that variable to `C:\Users\ovidi\local-ai-platform\.uv-cache` instead,
and the cost of that showed up afterwards in `tests/repository/test_scanner.py`: the cache
holds real `.py` and `.pyi` files, the scanner walked them, and two of its tests failed on
them. The command above is the corrected form, and `.uv-cache` is now ignored by the scanner
wherever it grows.

The supported alternative, with no scratch file involved, is to point `APP_SESSION_LOG_PATH` in
`.env` itself at a dedicated file, start the gateway with the plain `uvicorn` command from
*Start Gateway*, and restore `.env` when the probe is over.

Before sending anything, confirm health, and that startup said the tracker is wired - in
counts:

```powershell
curl http://127.0.0.1:8001/health
```

```text
{"status":"ok","repository_context_enabled":true}
file_activity enabled=true transcript_states=256 files_per_state=256
```

The record of the run below shows that line in its older wording,
`conversations=256 files_per_conversation=256`, which is what the `f74d16d` binary printed:
the tracker is an LRU of transcript-prefix *states*, not of conversations, and the startup
line now says so.

Then four `POST /v1/chat/completions` requests to model `qwen38-27b` (`temperature=0.0`,
`max_tokens=1024`, `stream=false`), each carrying an explicit `X-Request-ID` so its record can
be found by name:

| step | `X-Request-ID` | transcript |
| --- | --- | --- |
| 1 | `c1live20261025b-r1` | one user question naming `packages/pipeline/file_activity.py` and `FileActivityTracker.observe`; no envelope |
| 2 | `c1live20261025b-r2` | request 1's user turn, request 1's real assistant reply, then one user-role `[read_file for 'packages/pipeline/file_activity.py'] Result:` envelope whose body is plain content |
| 3 | `c1live20261025b-r3` | request 2 unchanged, under a third ID - the replay |
| 4 | `c1live20261025b-control` | a fresh one-request conversation that supplies the file *and* reports reading it on the same request |

Then read the records back from `APP_SESSION_LOG_PATH`:

```powershell
Get-Content logs\c1_live_validation_20261025.jsonl |
  ForEach-Object { $r = $_ | ConvertFrom-Json; '{0}: {1}' -f $r.request_id, ($r.context.file_activity | ConvertTo-Json -Compress) }
```

### What the four records said

| request | `state` | `correlation` | `read_attempts` | `files_read` | `files_touched` | `context_files_touched` | `touched_without_context` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `c1live20261025b-r1` | `none` | `no_prior_context` | 0 | 0 | 0 | 0 | 0 |
| `c1live20261025b-r2` | `measured` | `measured` | 1 | 1 | 1 | 1 | 0 |
| `c1live20261025b-r3` | `measured` | `measured` | 1 | 1 | 1 | 1 | 0 |
| `c1live20261025b-control` | `measured` | `no_prior_context` | 1 | 1 | 1 | 0 | 1 |

Every other key was `0` in all four records. Each record carried exactly the seventeen keys
in the documented order, every value was a non-negative integer or one of the six closed
tokens, and no path, filename, module name, result body or envelope text appeared anywhere
inside `context.file_activity`. `changed_files_signal` was `off` and `changed_files_touched`
was `0`, so nothing from the working tree entered the correlation either.

The same four objects exactly as the read-back prints them, so the table above can be checked
against the bytes on disk:

```text
c1live20261025b-r1: {"state":"none","correlation":"no_prior_context","files_read":0,"files_modified":0,"files_touched":0,"read_attempts":0,"reads_failed":0,"reads_unknown":0,"modification_attempts":0,"modifications_not_modified":0,"modifications_unknown":0,"context_files_touched":0,"touched_without_context":0,"changed_files_touched":0,"paths_rejected":0,"other_events":0,"events_beyond_bound":0}
c1live20261025b-r2: {"state":"measured","correlation":"measured","files_read":1,"files_modified":0,"files_touched":1,"read_attempts":1,"reads_failed":0,"reads_unknown":0,"modification_attempts":0,"modifications_not_modified":0,"modifications_unknown":0,"context_files_touched":1,"touched_without_context":0,"changed_files_touched":0,"paths_rejected":0,"other_events":0,"events_beyond_bound":0}
c1live20261025b-r3: {"state":"measured","correlation":"measured","files_read":1,"files_modified":0,"files_touched":1,"read_attempts":1,"reads_failed":0,"reads_unknown":0,"modification_attempts":0,"modifications_not_modified":0,"modifications_unknown":0,"context_files_touched":1,"touched_without_context":0,"changed_files_touched":0,"paths_rejected":0,"other_events":0,"events_beyond_bound":0}
c1live20261025b-control: {"state":"measured","correlation":"no_prior_context","files_read":1,"files_modified":0,"files_touched":1,"read_attempts":1,"reads_failed":0,"reads_unknown":0,"modification_attempts":0,"modifications_not_modified":0,"modifications_unknown":0,"context_files_touched":0,"touched_without_context":1,"changed_files_touched":0,"paths_rejected":0,"other_events":0,"events_beyond_bound":0}
```

The timings as each record wrote them, verbatim from `logs/c1_live_validation_20261025.jsonl`:

| request | `total_ms` | `pipeline_ms` | `provider_wait_ms` | `repository_context_ms` |
| --- | --- | --- | --- | --- |
| `c1live20261025b-r1` | 6905.3 | 691.9 | 6206.5 | 689.5 |
| `c1live20261025b-r2` | 3066.0 | 677.4 | 2385.5 | 675.5 |
| `c1live20261025b-r3` | 3104.0 | 710.3 | 2391.1 | 708.3 |
| `c1live20261025b-control` | 3793.6 | 897.4 | 2893.5 | 895.3 |

All four requests completed: HTTP 200, `status=ok`, a real assistant answer, and no
`file_activity` failure anywhere in the gateway log. That is where the performance evidence
ends. There was no feature-off arm and no with-C1/without-C1 pair, so this probe did not
isolate or measure the incremental latency C1 adds; the numbers above describe stage and
provider work on four individual requests - the `repository_context` stage spanning
675.5-895.3 ms, which is 689.5, 675.5 and 708.3 ms on the three conversation requests and
895.3 ms on the control, against provider waits of 2385.5-6206.5 ms - and they are recorded so
that a later run can compare against them, not as evidence that measuring is cheap.
**C1's performance overhead remains unmeasured**; the supported claim is only that measuring
did not stop any of the four requests from completing.

`primary_symbol` was `packages/pipeline/file_activity.FileActivityTracker.observe` in every
record, so request 1 demonstrably supplied the file request 2 later reported reading - the
`context_files_touched=1` credit is temporal and not self-serving. The control row shows the
other half of the ordering rule: supplied and touched on one and the same request credits
nothing, and lands in `touched_without_context` instead.

The replay's dictionary was identical to request 2's by value, by key order and as serialized
JSON. Nothing doubled, and no `tracker_miss` appeared on a conversation that was never
evicted.

Evidence: `logs/c1_live_validation_20261025.jsonl` - four lines, one per request ID above, in
gitignored diagnostics. One earlier start of the same gateway resolved `.env`'s path before
the override above was written, so a single prior record - `c1live20261025a-r1`, identical in
shape to `c1live20261025b-r1` - sits at the end of
`logs/implement_budget_A_4096_20260801.jsonl`. It was left in place rather than edited out.

Still offline-only after this pass: `state=partial`, `state=unavailable` and
`correlation=tracker_miss`, eviction once a 257th conversation arrives, and the failure paths
that mark a record unavailable - all constructs a single healthy restart cannot produce.


## Calibrated History-Cap Estimation (roadmap A3)

What this run is for, and what the change is. History capping decides what reaches the provider by
reading conversation text and asking what it is worth, and until A3 that question was answered by one
global constant - `packages/context/budget.py:CHARS_PER_TOKEN = 4.0` - whatever model the request
routed to, while the same request's repository-context budget had been answering it per model since
2026-09-09. A3 makes the cap use the resolved model's `chars_per_token`
(`packages/providers/models.py:ModelDefinition.chars_per_token`, default `4.0`, `qwen38-27b`
configured `3.5`). Nothing else about the cap's *sizing* moved: `APP_HISTORY_CAP_TOKENS` still says how many
tokens to keep and still wins over the derived budget, and the derivation still subtracts the
generation reserve, the repository reserve and the safety margin - though which window it subtracts
them from is a separate matter, and it is recorded below. A change that resized the budget
would be a different change with different consequences; this one only changes what the characters in
front of the cap are worth.

One fix had to come first. `cap_history` has accepted an `estimate` callable since it was written,
and `_apply_history_cap` had been handing it one on every request - and nothing ever called it.
Message counting went through the module-level `_estimate_tokens` and the global constant, so the
argument was a knob that turned nothing, and this repository's own tests had been passing a real
estimator to a parameter the production code ignored. Calibrating the cap by passing a calibrated
lambda through that same argument would therefore have changed no bytes on the wire. The callable is
now applied to every text field that is counted - `content`, `name`, `reasoning_content`, and each
tool call's name and arguments - and the same ratio converts the current-envelope token budget back
into characters, so the truncation marker lands at the calibration the keeping decision used.

The change stayed inside three files, and one of them for a reason worth keeping.
`packages/pipeline/history.py` gained no new module-level or nested definition, because its index
symbol set is what
`tests/observability/test_quality_harness.py::test_changed_file_ab_benefit_case_gains_the_file_the_question_asks_about`
pins for the changed-file pair that dirties that file: a first cut that added a
`normalize_chars_per_token` helper failed exactly that test, by displacing `_estimate_tokens` from
the four definitions a `+25` bonus buys at a 4096-token budget. So the range guard is inline in
`cap_history`, with `RATIO_MIN`/`RATIO_MAX` as constants, and `packages/pipeline/engine.py` holds
`_resolve_history_chars_per_token`, which reads the ratio off `ResolvedModel.definition` - the shape
`ModelResolutionStage` stores - and falls back to `4.0` for a missing model, a missing definition, or
a value outside the range the provider registry validates.

What A3 also corrected on the way past. The derived budget used to begin with
`getattr(resolved_model, "context_window", 8192)`, and a real `ResolvedModel` carries its window one
level down on `definition`, so that read returned `8192` for every routed request rather than this
alias's `262144`; a request with `max_tokens` at 8192 or more therefore derived a non-positive budget
and capped nothing at all. A3's acceptance requirement is that budgeting use the resolved model's
actual context window, so the derivation now reads `resolved_model.definition.context_window` first,
falls back to a `context_window` attribute on the resolved object itself for the older shape that read
was written against, and uses `8192` only when neither path supplies a positive finite number. The
three reserves it subtracts, and the `APP_HISTORY_CAP_TOKENS` precedence, are unchanged.
This is a behaviour change wherever the budget is derived: at the default 2048-token generation
reserve the old read budgeted `8192 - 3584 = 4608` history tokens, and the corrected read budgets
`262144 - 3584 = 258560` for this alias, so with `APP_HISTORY_CAP_TOKENS` at `0` the history cap
effectively stops trimming routed requests. Every live session record surveyed on 2026-10-31 ran the
explicit `3000` budget, so the running gateway is unaffected; set `APP_HISTORY_CAP_TOKENS` explicitly
whenever capping is meant to bite.

The live arms below all ran `APP_HISTORY_CAP_TOKENS=3000`, which selects the explicit branch before any
window is consulted, so this correction is verified offline and no measurement here had to be repeated:
`tests/pipeline/test_history.py` derives budgets from a real `ModelDefinition`/`ResolvedModel` pair
(four of its cases fail against the old read), and one focused case forwards the same calibrated
transcript under three different windows - `262144`, `8192`, and one too small to derive a budget -
and requires byte-identical results, which is what licenses reading the explicit-budget A/B below as
current.

Identity of what was contacted, checked before any measurement was sent. Backend
`http://100.106.236.88:18300/v1/models` served one model, `qwen3.8-flash-next` (`owned_by: vllm`,
`max_model_len: 400000`, root
`/hf/hub/models--nvidia--Qwen3.8-Flash-Next-NVFP4/snapshots/fc694b54fb0174e0913e6adf86691ef85a4ead47-fp8hybrid`),
the same deployment the 2026-10-24 A1 baseline measured. Both arms' `/debug/runtime-context` reported
`routing_mode=models_config`, `default_model=qwen38-27b`, `default_provider=openai`,
`models[0].backend_model=qwen3.8-flash-next`, `context_window=262144`, `chars_per_token=3.5`,
`repository_context_max_tokens=4096` with `EXPLAIN=4096`, `context_delta_injection=true`,
`history_cap_enabled=true` and `history_cap_tokens=3000`, each arm on its own port and its own session
log. Those are the values `scripts/ab_launcher.py` rendered and validated from
`build/ab_a3/experiment_base.json` and `build/ab_a3/experiment_cand.json`; neither worktree holds a
`.env`, so nothing else was in reach. The two files' shared blocks differ in exactly one key,
`APP_REPOSITORY_PATH`, because a code A/B has each gateway index the tree it runs from.

```powershell
# 1. two detached worktrees of one commit, only one of them carrying A3
git worktree add --detach ..\lap-ab-a3base-c161999 c161999
git worktree add --detach ..\lap-ab-a3cand-c161999 c161999
git -C ..\lap-ab-a3base-c161999 rev-parse --abbrev-ref HEAD   # HEAD, not a branch, for both
Test-Path ..\lap-ab-a3cand-c161999\.env                       # False, for both
# candidate: the reviewed A3 source and tests as one clearly named scratch commit - engine.py,
# history.py and tests/pipeline/test_history.py, nothing else, --no-verify because the pre-commit
# hook runs the live-path gate and that gate was run here once, on its own, in the main checkout
git -C ..\lap-ab-a3cand-c161999 commit -q --no-verify -m 'scratch(A3): calibrated history-cap estimation (temporary; not for merge)'
git -C ..\lap-ab-a3cand-c161999 rev-parse HEAD   # f0a77df4203882695347eda27a487d392d4251f7
git -C ..\lap-ab-a3cand-c161999 status --short   # empty: the scratch commit is the whole delta
git -C ..\lap-ab-a3cand-c161999 diff c161999 HEAD > build\a3\20261030\a3_scratch.patch

# 2. one launcher file per tree; the started arm of each is the 'off' arm, so changed-file ranking
#    is off on both sides and the ports and logs are the only differences the arms were given
.\uv.exe run python scripts\ab_launcher.py template --name a3_base --worktree ..\lap-ab-a3base-c161999 --out build\ab_a3\experiment_base.json
.\uv.exe run python scripts\ab_launcher.py template --name a3_cand --worktree ..\lap-ab-a3cand-c161999 --out build\ab_a3\experiment_cand.json
.\uv.exe run python scripts\ab_launcher.py validate --config build\ab_a3\experiment_base.json
.\uv.exe run python scripts\ab_launcher.py validate --config build\ab_a3\experiment_cand.json
.\uv.exe run python scripts\ab_launcher.py show --config build\ab_a3\experiment_base.json --arm off
.\uv.exe run python scripts\ab_launcher.py show --config build\ab_a3\experiment_cand.json --arm off

# 3. what each tree resolves for the live alias, using that tree's own code
powershell -NoProfile -ExecutionPolicy Bypass -File build\a3\20261030\check_arms.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File build\a3\20261030\run_boundary_check.ps1

# 4. both gateways, started detached exactly as rendered, then measured one arm at a time
powershell -NoProfile -ExecutionPolicy Bypass -File build\a3\20261030\start_arms.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File build\a3\20261030\run_phases.ps1   # 18 requests, then teardown
```

Step 4's runner is a throwaway under the Git-ignored `build\a3\20261030\`. It parses `show --arm off`
rather than restating it, so no flag entered a live arm by hand; it waits for `/health` on 8011 and
8012, runs the focused probe and then the scripted transcript against one arm and then the other, so
the shared backend served one workload at a time, and it ends by stopping every gateway it started -
matching command lines containing both `uvicorn` and `apps.gateway.main:create_app`, and printing
`no gateway process left`, `port 8011 free`, `port 8012 free`. Nothing on port 30000 was contacted.
Neither arm installed anything: both run the main checkout's interpreter and installed packages
through `UV_PROJECT_ENVIRONMENT` plus `uv run --no-sync`, which is the documented A1 workaround and
keeps the two arms' dependencies identical (CPython 3.13.14, the version every baseline here used).
Each gateway's own startup line records the tree it indexed - baseline
`files=511 modules=511 symbols=8836 relationships=19072`, candidate
`files=511 modules=511 symbols=8867 relationships=19178`; the 31 extra symbols are A3's own new test
functions plus `_resolve_history_chars_per_token`, and they are the confound the results section
below separates rather than hides.

The two measurement workloads, and the transcript they share. Item A is the roadmap's named probe,
`multiturn_history_cap_budget`, three repeats per arm at the settings the 2026-10-24 baseline
documents - alias `qwen38-27b`, `--max-tokens 8192`, client timeout 345 s against the arms'
`REQUEST_TIMEOUT=300`, repository context on with the documented intent budgets, history cap on at
3000 tokens. Item B is a scripted Cline session, three repeats per arm of two requests each: a seed
question, then the same session replayed with Cline tool-result envelopes in the user role, which is
what a Cline client sends every turn. Its shape is the one the C1 procedure documents, and its sizes
were chosen before it was run, not after: a 63-character system turn, a 90-character user turn, a
58-character assistant reply, three 3,600-character `[read_file|search_files|list_files for ...]
Result:` envelopes, and a 214-character final question. That is 10,948 cappable characters, which
4.0 characters per token reads as 2,736 tokens and 3.5 reads as 3,125 - one side of the 3,000-token
budget and the other side of it, from the same bytes.

### Item A: focused probe, `multiturn_history_cap_budget`

| arm | commit | estimate | facts (3 repeats) | style | errors / timeouts | prompt tokens | completion | seconds | cap applied | budget | dropped | `history_tokens_after` | context est. | symbols |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | `c161999` | fixed `4.0` | `3/3`, `3/3`, `3/3` | ok ×3 | 0 / 0 | 3683, 3683, 3683 | 210 ×3 | 10.8, 9.6, 9.6 | yes | 3000 | **0, 0, 0** | 4453 ×3 | 4046 | 7 |
| candidate | `f0a77df4` | resolved `3.5` | `3/3`, `3/3`, `3/3` | ok ×3 | 0 / 0 | 3451, 3451, 3451 | 217 ×3 | 11.1, 8.0, 7.8 | yes | 3000 | **0, 0, 0** | 4743 ×3 | 3750 | 6 |

Six requests. Every repeat inside both arms is byte-stable on the deterministic side (prompt tokens,
estimated context, dropped count and tokens-after, to the unit), and all three expected facts -
`_apply_history_cap`, `packages/pipeline/engine.py`, `APP_HISTORY_CAP_TOKENS` - arrive in both arms.
The cap dropped nothing on this probe in either arm: its canned two-turn history is about 550
characters, worth 137 tokens at 4.0 and 157 at 3.5, nowhere near the 3,000-token budget. Item A
therefore shows that A3 costs this probe nothing; it does not show the calibration doing anything, and
this item is not claimed as live-discriminated by the probe. The `4453` against `4743` in the two
arms' `history_tokens_after` is the same field read through the two ratios, and the 232-token prompt
gap is the two trees' retrieved context (4046 against 3750 estimated, 7 symbols against 6) - not the
cap, which fired identically and dropped nothing on both sides.

### Item B: controlled Cline A/B

Twelve requests, six per arm: three repeats of a seed turn, three of the accumulating turn that
carries the envelopes.

| turn | arm | prompt tokens | dropped | `history_tokens_after` | applied / budget | context est. | primary symbol | seconds | completion | facts / style |
|---|---|---|---|---|---|---|---|---|---|---|
| seed | baseline | 2469 ×3 | 0, 0, 0 | 2846 ×3 | yes / 3000 | 2394 | `apps/gateway/api/models.list_models` | 24.0, 24.1, 22.2 | ~1024 (ceiling) | 4/4, style ok |
| seed | candidate | 2469 ×3 | 0, 0, 0 | 3253 ×3 | yes / 3000 | 2394 | `apps/gateway/api/models.list_models` | 30.9, 36.4, 36.8 | ~1024 (ceiling) | 4/4, style ok |
| accumulating | baseline | 4905 ×3 | **0, 0, 0** | 6971 ×3 | yes / 3000 | 4046 | `packages/pipeline/engine._apply_history_cap` | 19.5, 20.6, 15.8 | 507, 517, 472 | 4/4, style ok |
| accumulating | candidate | 4167 ×3 | **3, 3, 3** | 6550 ×3 | yes / 3000 | 3750 | `packages/pipeline/engine._apply_history_cap` | 25.4, 24.4, 27.0 | 696, 696, 742 | 4/4, style ok |

The forwarding difference is exactly the boundary, and it is stable: three repeats of the same turn
produce the same dropped count in both arms, and the candidate forwarded four of the seven messages
where the baseline forwarded all seven - the 3,600-character `read_file` envelope and the
90-character user turn and 58-character assistant reply ahead of it, which is what a newest-first walk
drops when the same 10,948 characters cross from 2,736 estimated tokens to 3,125. Nothing else moved:
the budget field says 3000 in both arms, `cap_applied` is true in both, no record errored, no record
timed out, no request approached the 262,144-token window, and both arms answered all four facts with
the harness's own style rule clean on all six scored turns.

The seed turn is the parity control. Both arms were sent the same two messages and both forwarded them
whole - identical `prompt_tokens` (2469), identical repository context (2394 estimated, the same
primary symbol) - while the size the cap recorded differs by precisely the ratio: `2846 x 4.0 =
11,384` characters against `3253 x 3.5 = 11,385`, the same forwarded bytes read through two
calibrations. That is A3's claim about the metadata on its own, with no boundary in the way.

Latency is not claimed in either direction. The candidate's accumulating turn forwarded 738 fewer
prompt tokens and took 24.4-27.0 s against the baseline's 15.8-20.6 s, but it also answered at length
- 696-742 completion tokens against 472-517, in a reasoning model whose visible answer is preceded by
hidden ones - and three paired samples of a model that is not sampling-deterministic does not price a
saving. What the run establishes is the forwarding difference, which is deterministic, and that it
costs nothing observable in quality.

### The same boundary without a gateway, a backend, or an index

Because the two arms indexed trees that differ by A3's own files, the boundary was measured again with
everything that is not the cap taken out: the identical transcript bytes, one 3,000-token budget, a
model definition carrying `chars_per_token=3.5`, and whichever cap code the tree running the check
holds. No HTTP, no index, no provider.

| tree | resolver present | ratio used | forwarded | dropped | budget | tokens after |
|---|---|---|---|---|---|---|
| `c161999` | no (`tree_has_calibrated_resolver: false`) | 4.0 | 7 of 7 | 0 | 3000 | 2804 |
| `f0a77df4` | yes | 3.5 | 4 of 7 | 3 | 3000 | 2135 |

Same dropped count, same three messages, same direction as the live pair - and here there is no index
in either arm to attribute anything to. `build\a3\20261030\boundary_base.json` and `boundary_cand.json`
carry the forwarded roles and per-message character counts for both sides.

### Verification, artifacts, and what this run does not settle

`tests/pipeline/test_history.py` is 67 tests; the live-path gate
(`scripts/precommit_test_gate.sh`) reported `2345 passed` and no failure, and the
full baseline gate (`scripts/precommit_test_gate.sh --full`) reported
`43 failed, 4947 passed, 3 skipped` with `full suite OK (43 failures, baseline 43)` -
the same count and the same composition `CLAUDE.md` documents (26 `autonomous`, 12
`observability`, 4 `integration/test_engineering_flow`, 1
`modification/test_engine.py`), with nothing new in `tests/pipeline` or
`tests/gateway`. Both ran from the working tree these measurements came from.
That state still holds after the derived-budget correction recorded above, and no live request was
re-sent for it: on the corrected tree `tests/pipeline/test_history.py` is 79 tests, the live-path gate
reported `2357 passed` with no failure, and the full gate reported `43 failed, 4959 passed, 3 skipped`
with `full suite OK (43 failures, baseline 43)` - the same 43 failures in the same composition, twelve
more passing tests, nothing new failing. Re-running the A/B would have measured the same explicit
branch it already measured, because every arm forced `APP_HISTORY_CAP_TOKENS=3000`, and the case that
forwards one calibrated transcript under three different windows is what shows the correction cannot
reach that branch.
Artifacts, all under the Git-ignored `build\a3\20261030\`:
`base_probe.json` and `cand_probe.json` (harness repeat envelopes), `cline_base.json` and
`cline_cand.json` (full transcript answers), `sessions_base.jsonl` and `sessions_cand.jsonl` (the two
arms' session records), `measured.json` with `compare.out` (the tables above), `calibration_base.log`
and `calibration_cand.log` (what each tree resolves, from that tree's own code), `phases.log` (the
timeline - 18 requests in 6 min 48 s), `a3_scratch.patch` (the candidate commit's content, kept so the
evidence outlives the worktree), `gate_live2.log` and `gate_full.log`, and, from the derived-budget
correction, `gate_live_fix.log`, `gate_full_fix.log` and the confirming re-run `gate_live_fix2.log`.
The experiment files are
`build\ab_a3\experiment_base.json` and `experiment_cand.json`. Neither result was persisted to
engineering memory.

What it does not settle: the calibration is measured on one alias, at one budget, with one transcript,
against one model on one backend, and the transcript is scripted - the envelopes are real in shape and
invented in content, in the sense the C1 section gives that phrase. No number here prices `3.5` in
latency; the `2736` against `3125` split says what it is worth in tokens, which is the claim the change
makes. And the derived-budget path - what would run if `APP_HISTORY_CAP_TOKENS` were `0` - is measured
by none of these arms: every arm forced 3000, and the window read that path depends on is corrected and
verified offline, as recorded above.

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
them. Roadmap Phase F step F1 re-ran this exact shape at `ebb98f9` on 2026-11-06; see
"Phase F1 reproduction of the A1 baseline, 2026-11-06 (roadmap F1)" below for what moved.



### Phase F1 reproduction of the A1 baseline, 2026-11-06 (roadmap F1)

Roadmap Phase F step F1: A1's command shape and configuration re-measured at the current
commit `ebb98f9`, from a detached worktree, over the whole 11-probe / 30-fact
`--compare-context` pair against `qwen3.8-flash-next` on the vLLM backend through the
`qwen38-27b` alias. Its job is to reproduce the live behaviour and record what moved, not
to classify anything: the phase does not require a run to land on `25/30` and `4/30`
before its evidence may be used, because the answer side of this measurement is variable
at 11 samples (roadmap B5 re-ran a single probe for exactly that reason).

Nothing in the runtime path differs between the two measurements. The main checkout's
uncommitted work is documentation only, the worktree holds the committed tree at
`ebb98f9`, and `scripts/ab_launcher.py`'s template is A1's configuration unchanged.

Commands, in run order:

```powershell
# 1. detached worktree at the commit under measurement, holding no .env
git worktree add --detach ..\lap-f1-ebb98f9 ebb98f9                  # exit 0
# 2. that tree's own environment, from the tracked lock (the procedure above)
Set-Location ..\lap-f1-ebb98f9; .\uv.exe sync --locked; Set-Location ..\local-ai-platform
# 3. the experiment, validated, and rendered for the arm that measures context
.\uv.exe run python scripts\ab_launcher.py template --name f1_a1_reproduction `
    --worktree ..\lap-f1-ebb98f9 --out build\f1\experiment_f1.json    # exit 0
.\uv.exe run python scripts\ab_launcher.py validate `
    --config build\f1\experiment_f1.json                             # exit 0
.\uv.exe run python scripts\ab_launcher.py show `
    --config build\f1\experiment_f1.json --arm off                   # exit 0
# 4. the arm 'off', exactly as that block renders it: port 8011,
#    APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false, REQUEST_TIMEOUT=300,
#    APP_REPOSITORY_PATH=C:\Users\ovidi\lap-f1-ebb98f9, its own session log
# 5. the live-path gate, run in the worktree before any measured request
Set-Location ..\lap-f1-ebb98f9
& 'C:\Program Files\Git\bin\bash.exe' scripts/precommit_test_gate.sh
#     2519 passed, 1 warning in 206.11s - "pre-commit: live gate OK", exit 0
# 6. the measurement, then the read-only report over its JSON
.\uv.exe run python scripts\quality_harness.py --base-url http://127.0.0.1:8011/v1 `
    --model qwen38-27b --max-tokens 8192 --timeout 345 `
    --reasoning-model qwen38-27b --compare-context --json `
    > C:\Users\ovidi\local-ai-platform\build\f1\quality_compare_qwen38_vllm_20261106.json
.\uv.exe run python scripts\evaluate_quality_harness.py `
    C:\Users\ovidi\local-ai-platform\build\f1\quality_compare_qwen38_vllm_20261106.json `
    --model qwen38-27b --gateway-commit ebb98f9                      # exit 0
```

`show --arm off` prints a Terminal 2 line carrying `--repeat 3`, which `--compare-context`
refuses; step 6 replaces that line exactly as A1's step 4 did. The environment block,
port, `REQUEST_TIMEOUT=300` and the 345-second client timeout are the validated file's.
Step 6's evaluator ran without `--persist`, so this measurement neither wrote nor read an
`EngineeringMemory` record. The harness itself was started detached, so its exit code was
not captured; the evidence that it completed is a well-formed 22-record document and an
empty (0-byte) stderr, with `--fail-under` left at its default of 0.

Artifacts, all under the Git-ignored `build\f1\`:

| file | what it is |
|---|---|
| `quality_compare_qwen38_vllm_20261106.json` | the harness's raw `--compare-context --json` document, 22 probe records |
| `sessions_f1_a1_reproduction_off_20261106.jsonl` | copy of the arm's session log - 22 records, this run only, nothing removed |
| `a1_sessions_a1_vllm_baseline_off_20261024.jsonl` | copy of A1's log, so the per-request comparison does not depend on `..\lap-ab-a1-0371d64` surviving |
| `experiment_f1.json`, `show_arm_off.txt`, `arm_off_gateway.ps1` | the validated experiment, its rendered `off` arm, and the block that started it |
| `f1_analysis.py`, `f1_analysis_20261106.txt` | the A1-to-F1 comparison and its output, which produced the tables below |
| `f1_evaluation_20261106.txt` | `evaluate_quality_harness.py`'s report for the run |
| `harness_start_20261106.txt`, `harness_end_20261106.txt` | 19:21:04.410 and 19:33:56.914 local - 772.5 s of wall clock |
| `gate_20261106_out.txt`, `gateway_20261106_out.txt`, `gateway_20261106_err.txt`, `harness_20261106_err.txt`, `sync_20261106_out.txt`, `sync_20261106_err.txt` | transcripts of the gate, the arm and the environment build |

The arm ran from `C:\Users\ovidi\lap-f1-ebb98f9` and wrote to
`logs\sessions_f1_a1_reproduction_off.jsonl` inside that tree; the worktree was left in
place, as A1's was. The configuration as validated is A1's: `chars_per_token=3.5`,
`repository_context_max_tokens=4096`, intent budgets `SEARCH/TEST/DEBUG=2048` and
`REFACTOR/IMPLEMENT/EXPLAIN=4096`, history cap on at 3000 tokens, delta injection on,
changed-file ranking off with its counterfactual build on,
`RELATIONSHIP_RANKING_ENABLED`/`RELATIONSHIP_EXPANSION_ENABLED` true,
`APP_REPOSITORY_EXCLUDE_TESTS=false`, `APP_REPOSITORY_EXCLUDE_GLOBS=scripts/**`,
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS=0`, `APP_CONTEXT_INTENT_RULES={}`,
`APP_CONTEXT_DELTA_CACHE_SIZE=256`.

What was checked before any measured request, on `http://127.0.0.1:8011`:

- `/health` - `{"status":"ok","repository_context_enabled":true}`
- gateway `/v1/models` - the alias `qwen38-27b`; backend
  `http://100.106.236.88:18300/v1/models` - exactly one model, `qwen3.8-flash-next`
  (`owned_by: vllm`, `max_model_len: 400000`, root
  `/hf/hub/models--nvidia--Qwen3.8-Flash-Next-NVFP4/snapshots/fc694b54fb0174e0913e6adf86691ef85a4ead47-fp8hybrid`).
  That is the backend identity confirmation the phase asks for, and it was taken before
  the first scored request. Port `30000` was never contacted, and nothing was listening
  on `8001` to begin with.
- `/debug/runtime-context` - `routing_mode=models_config`, `default_model=qwen38-27b`,
  `default_provider=openai`, `models[0].backend_model=qwen3.8-flash-next`,
  `base_url=http://100.106.236.88:18300/v1`, `context_window=262144`,
  `max_output_tokens=8192`, `chars_per_token=3.5`, `repository_context_max_tokens=4096`,
  the intent-budget map above, `context_delta_injection=true`, `history_cap_enabled=true`,
  `history_cap_tokens=3000`, and the arm's own session-log path
- the arm's startup line - `repository_index path=C:\Users\ovidi\lap-f1-ebb98f9
  files=515 modules=515 symbols=9022 relationships=19720 excluded_tests=0
  excluded_globs=15 duration_ms=10693.3`, and no `changed_files_signal enabled=true` line
- no separate smoke request was sent. A1 used one to prove the changed-file feature was
  off, then deleted its record; the same proof here is the startup line above plus
  `context.changed_files_signal=off` on all 22 records, so the log holds exactly this
  run's 22 requests with nothing removed from it.
- the live-path gate - `2519 passed, 1 warning in 206.11s (0:03:26)`, exit 0, run from the
  worktree before the measurement.

The result, from `build\f1\f1_analysis_20261106.txt` over the two harness documents:

| arm | facts A1 -> F1 | style | prompt tokens A1 -> F1 | summed seconds A1 -> F1 | longest A1 -> F1 | errors / timeouts |
|---|---|---|---|---|---|---|
| repository context on | `25/30` -> `25/30` | `11/11` ok in both | 33109 -> 32716 | 129.6 -> 188.0 | 24.0 -> 29.4 | 0 / 0 in both |
| repository context off | `4/30` -> `2/30` | `11/11` ok in both | 2221 -> 2221 | 532.1 -> 553.3 | 193.8 -> 187.0 | 0 / 0 in both |

Twenty-two requests in 772.5 s of wall clock (19:21:04.410 to 19:33:56.914 local), 741.3 s
of summed per-probe latency. Provider wait, read from the arm's own records: context on
155.7 s summed, 14.2 s mean, 27.1 s longest against A1's 116.6 / 10.6 / 23.4; context off
553.1 s / 50.3 s / 187.0 s against A1's 531.9 / 48.4 / 193.8. Stage time inside the context
arm (`timing.stages.repository_context_ms`) summed 32.2 s with a 5788.3 ms maximum on
`debug_streaming_preview`, where A1's same eleven requests summed 12.8 s and peaked at
2694.2 ms; in the no-context half it is 0.6-1.0 ms per request, which is the per-request
flag doing what it is meant to. No request errored and none reached either ceiling. The
no-context `explain_changed_files_history_cap` call repeated A1's shape - all 8192
completion tokens spent on hidden reasoning, an empty answer,
`metadata.truncation_risk=true`, 187.0 s - and is scored 0/4 for that reason.

Per probe, context arm, A1 -> F1 (estimated tokens and symbol counts are the arm's own
session records):

| probe | facts | prompt tokens | seconds | estimated context tokens | symbols selected |
|---|---|---|---|---|---|
| `search_answer_preview` | 2 -> 2 | 2017 -> 1988 | 6.3 -> 6.0 | 2046 -> 2046 | 1 -> 1 |
| `debug_streaming_preview` | 3 -> 2 | 2058 -> 2029 | 8.6 -> 28.5 | 2046 -> 2046 | 1 -> 1 |
| `test_list_content` | 2 -> 2 | 2008 -> 2008 | 3.5 -> 8.5 | 2027 -> 2027 | 5 -> 5 |
| `explain_live_path` | 4 -> 4 | 2479 -> 2492 | 14.5 -> 19.9 | 2868 -> 2868 | 4 -> 4 |
| `refactor_repository_context` | 1 -> 1 | 3220 -> 3584 | 9.6 -> 29.4 | 3658 -> 4049 | 1 -> 1 |
| `implement_health_flag` | 2 -> 2 | 3469 -> 2921 | 5.5 -> 8.0 | 3678 -> 3122 | 5 -> 4 |
| `multiturn_history_cap_budget` | 3 -> 3 | 3683 -> 3451 | 14.1 -> 16.4 | 4046 -> 3750 | 7 -> 6 |
| `multiturn_config_systems` | 2 -> 2 | 4133 -> 4133 | 9.6 -> 12.3 | 4054 -> 4054 | 18 -> 18 |
| `explain_changed_files_contextbuilder` | 2 -> 3 | 3466 -> 3466 | 21.2 -> 27.4 | 3988 -> 3988 | 3 -> 3 |
| `explain_changed_files_repository_index` | 3 -> 3 | 3551 -> 3551 | 24.0 -> 20.4 | 4091 -> 4091 | 11 -> 11 |
| `explain_changed_files_history_cap` | 1 -> 1 | 3025 -> 3093 | 12.7 -> 11.4 | 2807 -> 2861 | 20 -> 20 |

Totals: 32716 prompt tokens for 25 scored facts (1309 per scored fact), against the
no-context half's 2221 for 2 - a `+30495` prompt delta for `+23` converted facts (1326
per converted fact). The stage's own `context.estimated_tokens` summed 34902 over the same
eleven context-on requests, where A1's summed 35309; per scored fact that is 1396, per
converted fact 1517. Both bases are reported because they are different quantities: the
estimate runs 2186 tokens above what the provider charged for the whole of this arm's
context-on prompts, and 4407 above the arm's measured prompt delta.

The five facts A1's context arm did not deliver, as measured now:

| fact | probe | scored, A1 -> F1 | what this run records | left for F2 |
|---|---|---|---|---|
| `select_last_task_text` | `refactor_repository_context` | miss -> miss (1/2 both days) | the context-on record selected 1 symbol, 4049 estimated tokens against a 4096 budget, primary `packages/pipeline/stages/repository_context.RepositoryContextStage`; A1's same request selected the same single symbol at 3658 estimated tokens, so what was sent is the same file 391 estimated tokens larger. This answer named `_extract_last_task_text`; no such callable exists in the tree - `select_last_task_text` is defined at `packages/pipeline/user_messages.py:153` and is a promotion target at `packages/context/builder.py:412` | whether `packages/pipeline/user_messages` is in the candidate set for that query at all, and whether one 4049-token symbol leaves room for a second |
| `packages/context/builder.py` | `explain_changed_files_contextbuilder` | miss -> **hit** (2/3 -> 3/3) | converted on a request identical to A1's in every recorded field: 3466 prompt tokens, 3988 estimated context tokens, 3 symbols, primary `packages/context/builder.ContextBuilder._enforce_budget`; the answer quotes line 773 of the file | whether A1's miss was ever reachable from the context side - the recorded context shape did not change, so this is a question about the matcher and the answer, not about ranking |
| `max_current_tool_result_tokens` | `explain_changed_files_history_cap` | miss -> miss (1/4 both days) | the package carried 20 symbols at 2861 estimated tokens under a 4096 budget; 20 is also the stage's `ContextQuery(max_symbols=20)` (`packages/pipeline/stages/repository_context.py:601`), but the session count sums supporting symbols with the primary (`:835-838`), so the log cannot say which of the two bound it. Primary `apps/gateway/api/models.list_models`; A1 sent the same count at 2807 estimated. `history.dropped_count=0` in all 22 records of both runs | whether the helper is among `packages/pipeline/history`'s indexed candidates for this query, and whether the count cap or the budget is what ends the selection |
| `_looks_like_cline_tool_result_message` | same probe | miss -> miss | the same record; the answer named the module's constants instead (`CHARS_PER_TOKEN = 4.0`, `RATIO_MIN = 0.5`, `RATIO_MAX = 20.0`) and `cap_history`'s signature | as above |
| `[... truncated by gateway history cap ...]` | same probe | miss -> miss | because capping dropped nothing in either run, this literal's only route into a prompt is inside a selected symbol's source; 20 symbols at 2861 estimated tokens is wide and thin | whether `packages/pipeline/history.cap_history`'s source, which holds that literal, reached the package |

Two probes sent the same context on both days and their facts moved in opposite directions.
`debug_streaming_preview`, which holds none of the five, carried 2046 estimated tokens and 1
symbol with primary `apps/gateway/session_log._extract_answer_preview` in both runs, and lost
`_choice_content` here. `explain_changed_files_contextbuilder`, which holds one of them,
carried 3988 estimated tokens and 3 symbols with primary
`packages/context/builder.ContextBuilder._enforce_budget` in both runs, and converted
`packages/context/builder.py` here. Same recorded context, different answer. That is the
answer-side variance this step assumes rather than fights, and it is why the context arm
reproducing `25/30` exactly is not evidence that retrieval held steady: the total is the
same because one gain and one loss cancelled.

`refactor_repository_context` is not in that group. Its selected symbol is the same file
but 391 estimated tokens larger at `ebb98f9`, and the probe scores 1/2 on both days.
Whether that growth is what left no room for the second name is an offline question.

On `explain_changed_files_history_cap` the package carried 20 symbols with 1235 estimated
tokens of the 4096 budget unspent, and the primary symbol recorded is
`apps/gateway/api/models.list_models`, which the question does not ask about. Whether that 20
is the stage's `ContextQuery(max_symbols=20)` ceiling
(`packages/pipeline/stages/repository_context.py:601`) or one supporting symbol below it is
not readable from a log whose count adds the primary to
the supporting list (`:835-838`). F2 has to say whether the two mechanism helpers are
reachable from that query's ranking at all, reached and cut by a count, or reached and
delivered thin.

The conditions that are not A1's, which do not change what the arm measured but do move the
numbers around it: the indexed tree is ten files larger (515 files, 9022 symbols and 19720
relationships against A1's 505, 8590 and 18309) and reports 15 exclude globs where A1
reported 13; answer times rose on both halves with prompt counts unchanged, so a shared
backend is the only candidate for that; and the repository-context stage took 2.5 times
A1's summed time over the same eleven requests, 32.2 s against 12.8 s. F5's latency floor
must therefore be quoted against a same-day control arm - A1's 11.8 s per request is a
historical reference, not a target.

No fact above is classified. Nothing in this step required that it be: the five classes are
deterministic-evidence claims, and they belong to F2's offline `_stage_arm()` and
`context_facts_available()` replay of these three probes - including whether
`_promote_repository_context_stage_symbols` reaches
`packages/pipeline/user_messages.select_last_task_text` the way the history-cap and
config-system promotions reach their named targets. That replay ran the same day, offline; the
section below records what each of the five facts turned out to be, and the promotion question
answered out to be a non-cause.

### Phase F2 offline classification of the five A1 fact misses, 2026-11-06 (roadmap F2)

Roadmap Phase F step F2: the five facts A1's context arm did not deliver, classified into the
phase's five classes from deterministic evidence only. No gateway was started, no request was
sent, nothing on port 8011 or 30000 was contacted, and no runtime source or test was changed.
`build\f2\f2_classification.py` - disposable, Git-ignored, under `build\` - imports the detached
worktree's own `scripts\quality_harness.py` and runs that tree's real `RepositoryIndex`,
`PlanningStage`, `RepositoryContextStage`, `ContextBuilder`, `RankingEngine`, `ContextBudget`,
`ContextComposer`, `OpenAISerializer`, `_stage_arm()`, `context_facts_available()` and
`score_answer` over the three probes that hold the five facts, with `changed_modules` empty. It
records, in order, the raw index matches, the ranked candidates before any query-specific
promotion, the candidates after the promotions and `_ensure_named_candidates`, what
`max_symbols=20` cut, what `_enforce_budget` dropped, the delivered representation of every
selected symbol, and each fact's exact text in the serialized prompt.

Commands, in run order:

```powershell
# 1. the tree under measurement: detached, exactly ebb98f9, holding no .env
git -C ..\lap-f1-ebb98f9 rev-parse HEAD          # ebb98f9c42562747f5a27e9ae716b8e53dfadd1f
git -C ..\lap-f1-ebb98f9 symbolic-ref -q HEAD    # exit 1, so the worktree is detached
git -C ..\lap-f1-ebb98f9 status --short          # empty
Test-Path ..\lap-f1-ebb98f9\.env                 # False
# 2. the replay, twice, with that tree's lock-matched interpreter. stdout and stderr go
#    to build\f2\f2_runN_out.txt and build\f2\f2_runN_err.txt; both _err files are 0 bytes.
$exe = '..\lap-f1-ebb98f9\.venv\Scripts\python.exe'
& $exe build\f2\f2_classification.py --out-prefix build\f2\f2_run1    # exit 0
& $exe build\f2\f2_classification.py --out-prefix build\f2\f2_run2    # exit 0
# 3. determinism: the two runs, byte for byte
Get-FileHash -Algorithm SHA256 -LiteralPath build\f2\f2_run1.json,build\f2\f2_run2.json,`
    build\f2\f2_run1.txt,build\f2\f2_run2.txt
# 4. the focused suites the exercised seam owns; runtime code is unchanged, so no test
#    was added. .venv here is this checkout's, whose source is identical to ebb98f9's.
.\.venv\Scripts\python.exe -m pytest tests\context\test_builder.py `
    tests\context\test_ranking.py tests\pipeline\test_repository_context_stage.py `
    tests\observability\test_quality_harness.py -q
#    248 passed in 26.13s
```

The hashes, identical across the runs and re-confirmed by a third run that was then deleted:

| artifact | sha256 |
|---|---|
| `build\f2\f2_run1.json`, `build\f2\f2_run2.json` | `B150BE7A25BF49468ECC15E0204A60AA3D2225293061CB098B0AC8BD4B361DE1` |
| `build\f2\f2_run1.txt`, `build\f2\f2_run2.txt` | `D81B26E401564AB82147E87D6A06D25C897661C89E4466494E91E8758D0F726D` |

Both shapes index the same tree the F1 arm indexed - 515 modules, 9022 symbols, 19720
relationships, `exclude_tests=False`, `exclude_globs=scripts/**`, read through the harness's own
`repository_index_settings()` - and both take their budgets from the validated
`build\f1\experiment_f1.json` rather than from a `.env`: `SEARCH/TEST/DEBUG=2048`,
`REFACTOR/IMPLEMENT/EXPLAIN=4096`, `repository_context_max_tokens=4096`, `max_symbols=20`,
`max_modules=10`. Shape A is `_stage_arm()` unchanged: a bare `PipelineContext` with no resolved
model and no plan, so `RepositoryContextStage._resolve_chars_per_token` returns the 4.0
fallback. Shape B runs the same stage behind the real `ModelResolutionStage` (the alias's
`ModelRegistry.from_json` entry, `chars_per_token=3.5`, `context_window=262144`,
`backend_model=qwen3.8-flash-next`) and the real `PlanningStage`. Classification follows the
production shape.

Shape B is also the shape the live run agrees with, record for record:

| probe | F1 session record | shape B replay |
|---|---|---|
| `refactor_repository_context` | `REFACTOR`, assembled, primary `packages/pipeline/stages/repository_context.RepositoryContextStage`, 1 symbol, 4049 estimated of 4096 | same intent, same primary, 1 of 20 candidates kept, 4049 estimated |
| `explain_changed_files_contextbuilder` | `EXPLAIN`, assembled, primary `packages/context/builder.ContextBuilder._enforce_budget`, 3 symbols, 3988 estimated | same intent, same primary, 3 of 20 kept, 3988 estimated |
| `explain_changed_files_history_cap` | `EXPLAIN`, assembled, primary `apps/gateway/api/models.list_models`, 20 symbols, 2861 estimated | same intent, same primary, 20 kept, 2861 estimated |

The classes, one per fact, with the evidence line each rests on. "owners" are the symbols that
could deliver the fact - the symbol that defines it where one exists, otherwise every symbol
whose own source carries its text; the index's `get_symbol_source()` returns the module's text,
so a holder's offset is an offset into that module file.

| fact | class | where it stood in the replay, and what the answer did |
|---|---|---|
| `select_last_task_text` | (b) retrieved and trimmed | 116 owners, 115 of them among the 4127 candidates that cleared the score floor; the defining symbol `packages/pipeline/user_messages.select_last_task_text` was hoisted by `_promote_repository_context_stage_symbols` to candidate position 2 and survived the cut of 20; `_enforce_budget` then took the package from 20 symbols to 1 (the primary at 4049 of 4096), dropping it. Prompt occurrences 0, `context_facts_available()` does not list it. A1 and F1 both missed it |
| `packages/context/builder.py` | (d) delivered and unused | 33 owners of `packages/context/builder` ranked, all 33 in the candidate list, 15 cut at 20 and 15 dropped by the budget, 3 selected (primary `ContextBuilder._enforce_budget` at 7168 source + 6817 docstring + 19 signature characters, then `ContextBuilder` as a 1814-character preview and `.build` signature-only). The context message carries the module key 8 times and `context_facts_available()` lists the fact. A1 missed it, F1 scored it, on records the replay reproduces exactly - and the string with `.py` on the end appears 0 times, so what the matcher accepts is the variant without it |
| `max_current_tool_result_tokens` | (c) selected and thin | 250 owners, 116 ranked, 114 of them cut at `max_symbols=20`; 2 selected - `packages/pipeline/history._build_cap_groups.find` as a 1814-character `source_preview` and `.union` signature-only (0 delivered characters) - and the literal sits at offset 5842 of the 18056-character module text, so the delivered form stops 3628 characters short. Prompt occurrences 0; missed by both answers |
| `_looks_like_cline_tool_result_message` | (b) retrieved and trimmed | its defining symbol ranked and entered the candidate list and was one of the 25 owners cut at `max_symbols=20`; no delivered symbol carried it (0 prompt occurrences); missed by both answers. It is in no promotion target list |
| `[... truncated by gateway history cap ...]` | (c) selected and thin | no symbol is named for it, so the ladder runs on the 244 symbols that carry it: 111 ranked, 109 cut at 20, the same 2 selected in preview and signature form, literal at module-text offset 5842. Delivered, therefore 0 prompt occurrences. This is the fact F1 could only describe as "wide and thin"; the number for "thin" is 1814 of 18056 characters, and it is a class (c) only because a representation actually containing the literal was never sent |

Nothing is class (a): every fact's symbol or carrier reached the builder's candidate list at
least once, so "not retrieved" describes none of them. Nothing is class (e): the two answers
that missed `select_last_task_text` named `_extract_last_task_text` and
`select_context_query_text`, neither of which states the fact, and the history-cap answers named
`cap_history`, its signature and module constants, which is why `cap_history` scored and the
mechanism did not. The matcher was not loosened to reach these verdicts - it is
`scripts\quality_harness.py`'s own `score_answer`, run over the stored A1 and F1 answer text and
over the serialized prompt.

The promotion asymmetry the roadmap flagged as "checkable offline and not yet a conclusion" is
now a conclusion. `named-symbol calls` for `refactor_repository_context` records the three
targets of `_promote_repository_context_stage_symbols` with `appended: []`,
`targets_missing_from_candidates: []` and `target_positions_after` of 0, 1 and 2: it reordered,
it did not append, and it had nothing to append because ranking had already found all three - so
the missing `_ensure_named_candidates` call at `packages/context/builder.py:398-414` cost no
fact here.
For `explain_changed_files_history_cap` the record is `named-symbol calls: []` and
`ensure_named_candidates calls: []`, because `_query_targets_history_cap` returns false for that
prompt - it asks how the gateway "cap[s] conversation history", which matches none of the
predicate's seven clauses - so the history-cap promotion at `:433-447` never ran and its append
path was never reached. Both history-cap facts were lost earlier than any promotion: at the
`max_symbols=20` slice and at preview depth.

The 4.0-versus-3.5 comparison changes no class. `same_class` is true for all five facts; what
moves is the amount of text a character budget admits. Shape A reports 3799, 3810 and 2567
estimated tokens for the three probes where shape B and the live records report 4049, 3988 and
2861, and the same 512-token supporting preview is 2070 characters at 4.0 against 1814 at 3.5 -
shorter at the calibrated ratio, which is why the production-shaped replay is the one that
decides. The selection is identical in both shapes for all three probes (1, 3 and 20 symbols,
the same primaries), so the classes do not rest on which ratio was in force.

Artifacts, all under the Git-ignored `build\f2\`:

| file | what it is |
|---|---|
| `f2_classification.py` | the disposable analysis script - in-process wrappers around the real builder and ranking seam, no runtime edit |
| `f2_run1.json`, `f2_run2.json` | the evidence: both shapes of all three probes, the step-by-step candidate lists, per-fact positions, serialized-prompt occurrences, matcher results against the A1 and F1 answers, and the replay-to-record parity |
| `f2_run1.txt`, `f2_run2.txt` | the same as a report, in a fixed order, byte-identical between the two runs |
| `f2_run1_out.txt`, `f2_run2_out.txt` | the script's stdout: the five class lines and the artifact sizes; the matching `_err.txt` files are empty |
| `_peek.py`, `_peek_repo.txt`, `_peek_cb.txt`, `_peek_hc.txt` | a second disposable helper, one dump per probe: it imports the analysis script and prints the frozen compare record - the answer text, `prompt_tokens`, and the `hits`/`misses` the matcher scored - unmodified, which is what the per-fact quotes about what the model said are taken from. The compare record holds no request block; the request-shape parity is the session log's, which the analysis script reads in `session_evidence()` |

Four of the five facts are context-side and open - two (b) and two (c) - so **F3 is
authorized**. The single bounded variable this step proposes, and does not implement, is the
primary symbol's share of the unchanged budget: `ContextBuilder`'s `primary_symbol_max_tokens`
from 2048 to 1536 tokens. Its predicted effect is one conversion, `select_last_task_text`,
because that is the fact whose symbol reached the package and was popped for want of room - the
primary is 7168 source characters plus a 6817-character docstring, 4049 estimated tokens of a
4096 ceiling, and 512 tokens of primary source freed is the 512-token supporting preview that
carries the helper. Predicted token cost is about zero, since the ceiling is not raised. It
predicts no conversion for the two history-cap facts, which are cut at the count of 20 before
the budget is spent, and none for the builder file, which is already delivered; reaching those
two would need `max_symbols` or the supporting pool, which are separate variables that buy
facts with tokens.


### Phase F3/F4 offline measurement of the primary-allowance candidate, 2026-11-06 (roadmap F3, F4)

Roadmap Phase F steps F3 and F4: the one authorized variable - `ContextBuilder`'s default
`primary_symbol_max_tokens`, 2048 to 1536 at `packages/context/builder.py:99` - implemented,
tested and measured offline. No gateway was started, no backend was contacted, no configuration
default was touched and the context ceiling is unchanged at 4096. F5 was not run. The candidate
was rejected and reverted on 2026-11-07 - see *Rejection and reversion (roadmap F6)* at the end of
this section; the shipped value is 2048.

**The measured answer is that the candidate does not convert `select_last_task_text`.** It stays
class (b) in both shapes, its literal appears 0 times in the serialized prompt of both arms, and
the reason is a prefix property of `_enforce_budget` that F2's arithmetic did not account for.

Commands, in run order. `build\f3\f3_classification.py` re-runs `build\f2\f2_classification.py`
byte-identically - F2's script is not edited, so F2's pinned hashes stay reproducible - behind an
import finder that resolves `packages` and `apps` from the checkout named by `--code-root`. The
measured corpus stays the detached worktree in every run, so `modules=515 symbols=9022
relationships=19720` is the same tree F1 ran live and F2 classified, and the only thing that
differs between a `worktree` run and a `main` run is the runtime code.

```powershell
git -C ..\lap-f1-ebb98f9 status --short          # empty, detached at ebb98f9
Test-Path ..\lap-f1-ebb98f9\.env                 # False
git --no-pager diff --stat -- packages           # builder.py | 2 +-

# 1. the control: the shipped code, which must reproduce F2 byte for byte
.\.venv\Scripts\python.exe -X utf8 build\f3\f3_classification.py `
    --code-root worktree --out-prefix build\f3\f3_base_run1      # exit 0
.\.venv\Scripts\python.exe -X utf8 build\f3\f3_classification.py `
    --code-root worktree --out-prefix build\f3\f3_base_run2      # exit 0
# 2. the candidate, twice
.\.venv\Scripts\python.exe -X utf8 build\f3\f3_classification.py `
    --code-root main --out-prefix build\f3\f3_cand_run1          # exit 0
.\.venv\Scripts\python.exe -X utf8 build\f3\f3_classification.py `
    --code-root main --out-prefix build\f3\f3_cand_run2          # exit 0
# 3. all eleven fixed probes, both shapes, both arms, in one artifact per run
.\.venv\Scripts\python.exe -X utf8 build\f3\f3_probe_delta.py --out-prefix build\f3\f3_delta_run1
.\.venv\Scripts\python.exe -X utf8 build\f3\f3_probe_delta.py --out-prefix build\f3\f3_delta_run2
# 4. why the conversion fails: the cost of each deliverable prefix, and the allowance sweep
.\.venv\Scripts\python.exe -X utf8 build\f3\f3_prefix_costs.py
.\.venv\Scripts\python.exe -X utf8 build\f3\f3_gradient.py
# 5. determinism, then fail-before and pass-after
Get-FileHash -Algorithm SHA256 -LiteralPath build\f3\f3_cand_run1.json,build\f3\f3_cand_run2.json,`
    build\f3\f3_cand_run1.txt,build\f3\f3_cand_run2.txt
.\.venv\Scripts\python.exe -m pytest `
    tests\context\test_builder.py::TestDefaultPrimaryAllowanceAgainstTotalBudget `
    tests\pipeline\test_repository_context_stage.py::TestPrimaryAllowanceAtTheStageBoundary -q
```

Byte-identical outputs. The two control runs reproduce F2's artifacts exactly - the same JSON and
report hashes `build\f2\f2_run1.json` carries - which is what licenses reading the difference in
the candidate runs as the candidate and nothing else.

| artifact pair | sha256 | equals |
|---|---|---|
| `f3_base_run1.json`, `f3_base_run2.json` | `B150BE7A25BF49468ECC15E0204A60AA3D2225293061CB098B0AC8BD4B361DE1` | `f2_run1.json` |
| `f3_base_run1.txt`, `f3_base_run2.txt` | `D81B26E401564AB82147E87D6A06D25C897661C89E4466494E91E8758D0F726D` | `f2_run1.txt` |
| `f3_cand_run1.json`, `f3_cand_run2.json` | `07F14E0F32E65E77E5CC789E5E2B6314329844A8D391A212B829966AC555AE24` | - |
| `f3_cand_run1.txt`, `f3_cand_run2.txt` | `62F2FC0221571AFC2E974EF16CC810050F6D47BEA40A7CCE2653D79FD89FE59C` | - |
| `f3_delta_run1.json`, `f3_delta_run2.json` | `F6A5C712FE774F9BF44DAA622E4A669DB3E1AD8BABDD5F7C1D0500AB25B49917` | - |
| `f3_delta_run1.txt`, `f3_delta_run2.txt` | `36E5C12F7FCFA8629BF90B20D756544F03C9F0C5907EF1F07BB1733A7BCF1A10` | - |

The five F2 facts, replayed. Classes come from the production shape; the 4.0 seam shape agrees on
every one of them in both arms, and the literal counts are the serialized context message.

| fact | class 2048 -> 1536 | occurrences in the context 2048 -> 1536 | estimated tokens 2048 -> 1536 |
|---|---|---|---|
| `select_last_task_text` | (b) -> **(b)** | 0 -> 0 | 4049 -> 3537 |
| `packages/context/builder.py` | (d) -> (d) | 8 -> 8 | 3988 -> 3957 |
| `max_current_tool_result_tokens` | (c) -> (c) | 0 -> 0 | 2861 -> 2861 |
| `_looks_like_cline_tool_result_message` | (b) -> (b) | 0 -> 0 | 2861 -> 2861 |
| `[... truncated by gateway history cap ...]` | (c) -> (c) | 0 -> 0 | 2861 -> 2861 |

No fact changed class. `packages/context/builder.py` is still delivered, now on a request that
carries a fourth symbol from that file instead of three. The three history-cap facts are
untouched because their probe is nowhere near the budget - 2,861 estimated tokens of 4,096, with
the primary being `apps/gateway/api/models.list_models` at 1,102 characters - so the allowance
never binds and the loss happens at `max_symbols=20` and at preview depth, as F2 recorded.

Why the predicted conversion did not happen. `_enforce_budget` keeps the primary and pops candidates
off the tail, so the only packages it can hand the composer are prefixes of the order the
promotions built - and on this probe that order is `RepositoryContextStage`, then
`RepositoryContextStage._extract_query`, then `select_last_task_text`. A symbol's estimated cost
includes its module docstring, and a second symbol in the same file is charged that same 6,817
characters again. So the helper is never the symbol the walk discards; it goes on the way past a
predecessor no affordable prefix contains:

| delivered prefix | at 2048 | at 1536 | at 512 | at 1 |
|---|---:|---:|---:|---:|
| `[stage]` | 4,049 fits | 3,537 fits | 2,513 fits | 2,002 fits |
| `[stage, _extract_query]` | 6,561 over | 6,049 over | 5,025 over | 4,514 over |
| `[stage, _extract_query, select_last_task_text]` | 6,968 over | 6,456 over | 5,432 over | 4,921 over |

The ceiling is 4,096 in every column, and the delivered row is the longest prefix that fits, which
is the first row everywhere. With the primary allowed a single token - a package carrying nothing
of the stage file but its module docstring - the prefix that would hold the helper is still 4,921
tokens over. `f3_gradient.txt` is the same sweep in the other direction, 2048 through 512, and it
returns one delivered symbol at every value. The variable that reaches `select_last_task_text` is
the order the promotion builds, or the module docstring charged twice per symbol of a file, not the
size of the primary's allowance.

All eleven probes, both arms. 16 of the 22 probe/shape rows differ, across eight probes -
`explain_changed_files_history_cap`, `implement_health_flag` and `test_list_content` are delivered
identically in both arms. Five probes gain a supporting symbol, no probe's primary changed, no
expected fact was gained and none was lost, and no row exceeded the unchanged 4096 ceiling in
either arm - the highest estimate anywhere is 4096 exactly, the baseline's
`explain_changed_files_repository_index` seam shape, which the candidate brings down to 4009.

| probe | shape A / B, symbols 2048 -> 1536 | shape A / B, estimated tokens | shape A / B, serialized context chars |
|---|---|---|---|
| `search_answer_preview` | 1 -> 1 / 1 -> 1 | 4053 -> 3541 / 2046 -> 2046 | 17244 -> 15040 / 8064 -> 7998 |
| `debug_streaming_preview` | 1 -> 1 / 1 -> 1 | 4053 -> 3541 / 4094 -> 3828 | 17244 -> 15040 / 15258 -> 14232 |
| `test_list_content` | 20 -> 20 / 5 -> 5 | identical | identical |
| `explain_live_path` | 4 -> **5** / 4 -> 4 | 2829 -> 4072 / 2868 -> 2356 | 13300 -> 18252 / 11906 -> 9946 |
| `refactor_repository_context` | 1 -> 1 / 1 -> 1 | 3799 -> 3287 / 4049 -> 3537 | 16455 -> 14171 / 15319 -> 13351 |
| `implement_health_flag` | 5 -> 5 / 4 -> 4 | identical | identical |
| `multiturn_history_cap_budget` | 7 -> **9** / 6 -> **8** | 3986 -> 3907 / 3750 -> 3874 | 18708 -> 18734 / 15492 -> 16236 |
| `multiturn_config_systems` | 15 -> **18** / 14 -> **16** | 3905 -> 4078 / 4023 -> 3977 | 19237 -> 20279 / 17396 -> 17379 |
| `explain_changed_files_contextbuilder` | 3 -> **4** / 3 -> **4** | 3810 -> 3718 / 3988 -> 3957 | 17674 -> 17253 / 16270 -> 16129 |
| `explain_changed_files_repository_index` | 14 -> 14 / 11 -> **12** | 4096 -> 4009 / 4091 -> 3944 | 19132 -> 18742 / 16873 -> 16297 |
| `explain_changed_files_history_cap` | 20 -> 20 / 20 -> 20 | identical | identical |

The gained symbols are ordinary previews of modules that were already in the package or newly
admitted: on `explain_changed_files_contextbuilder`, `ContextBuilder._estimate_candidate_tokens_for_ranking`
in both shapes; on `multiturn_history_cap_budget`, `history._build_cap_groups` and
`context.models.ContextBudgetResult`; on `multiturn_config_systems`, three more in the seam shape
and two in the production one. On `explain_live_path` only the seam shape gains -
`RepositoryContextStage._serialize` - and on `explain_changed_files_repository_index` only the
production shape gains - `RepositoryIndex.get_symbol_full_context`. One literal count moved with
the wider package: `cap_history` appears 14 times in the 2048 arm's production-shaped
history-cap context and 18 times in the candidate's, the seam shape being 18 in both.

Tests, and the arm that fails. Four tests were added; the two that carry the claim were run against
the unchanged 2048 tree first and failed there, naming the absence rather than a number:

```
FAILED tests/context/test_builder.py::TestDefaultPrimaryAllowanceAgainstTotalBudget::
    test_promoted_supporting_symbol_reaches_the_package_at_the_default
  AssertionError: the budget pass dropped the promoted supporting symbol:
    selected=['packages/pipeline/stages/repository_context.RepositoryContextStage'],
    estimated_tokens=3920 of 4096
FAILED tests/pipeline/test_repository_context_stage.py::TestPrimaryAllowanceAtTheStageBoundary::
    test_trimmed_primary_hands_the_pool_to_the_promoted_helper
  AssertionError: the promoted supporting symbol was trimmed out of the package:
    sent=[], estimated_tokens=3920 of 4096
2 failed, 2 passed in 0.14s
```

After the one-line edit the same command reads `4 passed`. No test compares
`primary_symbol_max_tokens` to any number. What makes the flipped assertions meaningful is the
partner each one sits beside:
`TestDefaultPrimaryAllowanceAgainstTotalBudget.test_a_larger_primary_allowance_crowds_the_supporting_symbol_out`
takes one step above whatever the default currently is, read from the signature, and shows the
symbol crowded straight back out;
`TestPrimaryAllowanceAtTheStageBoundary.test_a_symbol_ahead_of_the_helper_costs_the_pool_over`
rebuilds the live ordering - a method from the primary's own file promoted ahead of the helper -
and shows the serialized request containing `select_last_task_text` at neither allowance. That last
one passes before and after, which is its use: it is the measured reason F3's prediction failed,
pinned in the suite that owns what the stage sends. All four keep the surrounding invariants -
the primary delivered first, the total budget still 4096, the un-promoted ordering unchanged, the
same-file neighbour still rejected - so nothing here is carried by a weakened assertion.

Gates.

| command | result |
|---|---|
| `-m pytest tests\context\test_builder.py tests\context\test_ranking.py tests\pipeline\test_repository_context_stage.py tests\observability\test_quality_harness.py -q` | 4 failed, 248 passed, exit 1 |
| `-m pytest tests\context tests\pipeline -q` (the documented context/pipeline gate) | 817 passed, exit 0 |
| `-m pytest -q` (full suite) | 47 failed, 5075 passed, 3 skipped - four above the documented 43 baseline |
| `-m ruff check packages\context\builder.py tests\context\test_builder.py tests\pipeline\test_repository_context_stage.py` | All checks passed, exit 0 |
| `-m mypy packages\providers packages\pipeline apps\gateway` (documented live-path gate) | Success: no issues found in 46 source files, exit 0 |
| `-m mypy packages\context` (the changed surface) | Success: no issues found in 14 source files, exit 0 |
| `& 'C:\Program Files\Git\bin\bash.exe' scripts/precommit_test_gate.sh` | 4 failed, 2519 passed - "pre-commit: live gate FAILED (pytest exit 1)" |

The four failures are not in the new tests, and they are not corpus drift. At 2048 in this same
checkout all ten `test_changed_file_ab_*` cases pass; the candidate breaks four, and
`f3_ab_guards.txt` shows the same four counters moving over the clean `ebb98f9` corpus as well,
with `facts_lost` empty in every case: `symbols_promoted` 0 to 2 on the eviction case and 4 to 6 on
the gain case, the negative control's `context_differs` false to true with three delivered symbols
becoming four and five, and the eviction pair's strict-subset relation broken by two extra symbols
in the changed arm. They are Phase B's measurements pinned at the allowance Phase B measured, and
per `CLAUDE.md` they were left failing - not re-baselined, weakened, skipped or edited. The
live-path gate blocks on them, so this candidate cannot be carried to a commit as it stands.

Artifacts, all under the Git-ignored `build\f3\`.

| file | what it is |
|---|---|
| `f3_classification.py` | the replay launcher: the import finder, plus a `.provenance.json` sidecar naming the code root, the builder's origin file, the allowance in force and the artifact hashes |
| `f3_base_run1.*`, `f3_base_run2.*` | the control - F2's script over the shipped code, byte-identical to F2's own artifacts |
| `f3_cand_run1.*`, `f3_cand_run2.*` | the same script over the candidate: classes, step-by-step candidate lists, serialized-prompt occurrences |
| `f3_probe_delta.py`, `f3_delta_run1.*`, `f3_delta_run2.*` | all eleven probes, both shapes, both arms in one process, plus the per-field difference table |
| `f3_prefix_costs.py`, `f3_prefix_costs.txt` | the cost of each deliverable prefix at four allowances - the arithmetic that says no value of this variable converts the fact |
| `f3_gradient.py`, `f3_gradient.txt` | the allowance swept from 2048 to 512 on the REFACTOR probe: one delivered symbol at every value |
| `f3_ab_guards.py`, `f3_ab_guards.txt` | the three changed-file cases over the clean corpus in both arms, which separates the four test failures from drift |
| `fail_before.txt`, `fail_before_all.txt`, `u_fail_before.txt`, `pytest_builder_after.txt`, `gate_full_out.txt`, `gate_livepath_out.txt` | the captured pytest output behind the fail-before block and the gate table |
| `abguards_at_2048.txt`, `abguards_at_1536.txt`, `gate_ctxpipe_final.txt` | the ten `test_changed_file_ab_*` cases run twice - 10 passed with the constant back at 2048, 4 failed and 6 passed at 1536 - and the 817-test context/pipeline gate at the candidate |

What this does not settle: whether a live request answers differently. F5 was not run - the
offline result says a live A/B would measure a smaller primary and a wider package on eight probes
rather than a conversion, and the live-path gate did not pass with the candidate in the tree. The
decision this section left open was taken on 2026-11-07, below.

#### Rejection and reversion (roadmap F6), 2026-11-07

**Rejected and reverted; Phase F closes as a measured negative result with no runtime change.**
The candidate failed every condition it could be judged on before F5: no conversion of
`select_last_task_text`, no expected fact gained across the 11 probes, context composition
changed on 8 of them, and four established Phase B tests broken, taking the full suite from 43
failures to 47. Re-baselining those four tests was not authorized and not justified by a
candidate that gains nothing.

Reverted with `git checkout -- packages/context/builder.py tests/context/test_builder.py
tests/pipeline/test_repository_context_stage.py`. The default is back at
`primary_symbol_max_tokens: int = 2048` (`packages/context/builder.py:99`), and both test files
are byte-for-byte their pre-F3 state: all four F4 tests above were removed, the "tripwire"
included, because it asserted the current prefix-only delivery (`supporting_symbols == []`) as
expected behaviour and would fail a future fix of it. The `build\f3\` artifacts and this section
are the record.

Verification after reversion (Git Bash, `uv run python -m ...`):

| command | result |
|---|---|
| `pytest tests/context/test_builder.py tests/context/test_ranking.py tests/pipeline/test_repository_context_stage.py tests/observability/test_quality_harness.py -q` | 248 passed, exit 0 |
| `pytest tests/context tests/pipeline -q` | 813 passed, exit 0 (817 with the four F4 tests) |
| `scripts/precommit_test_gate.sh` | 2519 passed, "pre-commit: live gate OK", exit 0 |
| `scripts/precommit_test_gate.sh --full` | 43 failed, 5075 passed, 3 skipped, "pre-commit: full suite OK (43 failures, baseline 43)", exit 0 |
| `ruff check packages/context/builder.py tests/context/test_builder.py tests/pipeline/test_repository_context_stage.py` | All checks passed, exit 0 |
| `mypy packages/providers packages/pipeline apps/gateway` | no issues in 46 source files, exit 0 |
| `mypy packages/context` | no issues in 14 source files, exit 0 |

Found by the phase and recorded for a future milestone only, not proposed here: `_enforce_budget`
can deliver only a prefix of the promoted order, so a promoted symbol behind an unaffordable
predecessor is unreachable by any allowance; and a symbol in the primary's own file is charged
that file's module docstring a second time. Promotion order, docstring accounting, `max_symbols`
and preview depth would each need their own milestone, an F2-style classification of the
reachable set before any prediction, and their own authorization.

### Phase G: per-symbol source spans and module import lines, 2026-11-08/09 (roadmap Phase G)

Roadmap Phase G changed what one delivered symbol carries, then repaired the one regression
that change caused. Two runtime commits: `bc87179` (spans) and `67a7f7f` (import lines). Every
offline measurement below ran from the main checkout with the gateway's own index settings
(`exclude_tests=False`, `exclude_globs="scripts/**,build/**"`), at the production budget shape
(4096-token ceiling, `chars_per_token=3.5`), through the real `RepositoryContextStage`. Each
alternative arm was injected by patching `ContextBuilder` in
`packages/pipeline/stages/repository_context.py` with a scratch subclass. Before any arm was
measured, a fidelity gate required the subclass running the shipped behaviour to serialize
byte-identically to the unpatched stage on all 12 runs (11 probes plus the changed-file arm
of `explain_changed_files_history_cap`). Every matrix ran twice to the same SHA-256. Scripts
and raw output are under the Git-ignored `build\phase_g_spans\`,
`build\phase_g_preview_allocation\`, `build\phase_g3_imports\`, `build\phase_g_live\` and
`build\phase_g_iextra_live\`.

**G1 - spans (`bc87179`).** Before this commit, `RepositoryIndex.get_symbol_source`, the
docstring accessor and the location accessor answered with the symbol's whole module, so a
supporting preview usually began at the module header, and the primary window began with
module text that was not the symbol's own. `Symbol` now records `start_lineno` (earliest
decorator) and `end_lineno`. The accessors return that span, the signature line, the span's
own docstring, `(path, lineno, end_lineno)` and the extractor's decorators. A symbol without
`end_lineno` keeps the legacy whole-module answer. Results:

| measure | before | after |
| --- | --- | --- |
| span accuracy | - | 9,117 of 9,117 symbols match the AST span (0 ambiguous) |
| implementation chars, 11 probes | 15,257 | 55,483 |
| chars from unrelated file text | 61,969 | 0 |
| implementation-contained facts | 6 | 14 |

`tests/observability/test_quality_harness.py` was re-baselined for counts and lists only, with
no expected fact lost. For example, the benefit case now promotes 9 symbols and carries 3 of
the 4 history-cap facts in its changed arm.

Live at `bc87179`, two `--compare-context` runs from the `lap-g-bc87179` worktree on
`127.0.0.1:8011`, with the A1 configuration `scripts/ab_launcher.py` renders for the `off` arm:

- Context on: `24/30` in both runs. Context off: `2/30`.
- `refactor_repository_context` gained one fact.
- `explain_changed_files_history_cap` went `1/4 -> 0/4`.
- `explain_live_path` went `4/4 -> 2/4`, missing `ModelResolutionStage` and `PlanningStage`.

An offline trace of that request located the cause. The primary is
`apps/gateway/main.lifespan`, an 8,723-char span cut at the 7,168-char window (2048 tokens at
3.5). Both stage names sit just past the cut (offsets 7,167 and 7,208). Whole-module delivery
had carried them for free in `main.py`'s import lines 40-41.

**G2 - supporting-preview allocation: no winner.** Ten arms held the supporting pool, ceiling
and order fixed, and changed only how the pool is split:

- per-symbol caps of 64 to 512 tokens
- an equal share
- round-robin
- a docstring-aware start with caps

None restored the history-cap truncation marker. It sits in `_truncate_message_content`,
253 preview tokens deep, at rank 11 of 20. `HISTORY_CAP_QUERY` misses
`_query_targets_history_cap`, so it takes the plain 512-token, uncapped pool, and no split of
512 tokens funds ten symbols plus that one. Two other options were measured and not adopted:

- Widening `_query_targets_history_cap` to match this probe's wording: rejected as fitting the
  probe rather than the code.
- A 2048-token pool: labelled diagnostic, not a candidate, because it breaks "pool unchanged".

Full table: `build\phase_g_preview_allocation\report.md`.

**G3 - restoring module import lines.** Arms compared:

- docstring-skip variants of the primary window (P, PE)
- the same with import lines added (PEI)
- I-extra: each delivered module's top-level `Import`/`ImportFrom` statements, once, on its
  first delivered candidate, on top of the cap and charged by `_enforce_budget`

Only I-extra passed every rule. P/PE moved facts out of implementation text and held
`explain_live_path` by a 162-char margin. I-extra's offline cost over the 11 probes:

| measure | value |
| --- | --- |
| implementation chars | -0.85% |
| import-block chars | +10,028 (about 912 per request) |
| symbols dropped by budget enforcement | 42 -> 52 |
| max estimated tokens | 4,048 of 4,096 |

`67a7f7f` implements it in `ContextBuilder._enrich_with_source_data` and
`_module_import_block`. Equivalence: on the modified tree, production output matched the
scratch I-extra arm on 12/12 runs. It matched the pre-change recording on 8/12. The other 4
differ only because `packages/context/builder.py` and the new test file are themselves indexed,
and the same facts come through in all 4.

**Live confirmation, 2026-11-09.** The `lap-g-bc87179` worktree with the I-extra diff applied
(the committed `67a7f7f` moves `import ast` to module level; no other difference), the same
environment, gateway index `modules=517 symbols=9101 relationships=19917`, two runs
(08:35-08:48 and 08:48-09:00), driven by `build\phase_g_iextra_live\run_all.ps1`:

| | A1 `0371d64` | F1 `ebb98f9` | G `bc87179` (x2) | I-extra (x2) |
| --- | --- | --- | --- | --- |
| context on | 25/30 | 25/30 | 24, 24 | **26, 26** |
| context off | 4/30 | 2/30 | 2, 2 | 2, 2 |
| `explain_live_path` | 4/4 | 4/4 | 2/4, 2/4 | **4/4, 4/4** |
| `explain_changed_files_history_cap` | 1/4 | 1/4 | 0/4, 0/4 | 0/4, 0/4 |
| context-arm prompt tokens | 33,109 | 32,716 | 33,433 | 33,777 |

Across the two I-extra runs:

- No probe scored lower than at `bc87179`.
- Nothing errored, and the harness's stderr was empty.
- Both runs scored identically, probe by probe.

`explain_live_path` itself fell from 3,635 to 3,483 prompt tokens.
`explain_changed_files_history_cap` (0/4) is the open item; G2 shows the existing pool cannot
buy it.

Gates at `67a7f7f`:

- Live gate: 2567 passed.
- `--full`: 43 failed, 5123 passed, 3 skipped (baseline 43).
- Ruff on the changed files: clean.
- mypy (live-path scope): no issues in 46 source files.

### Phase H1: probe-set expansion, 2026-11-09/10 (roadmap Phase H)

Roadmap Phase H1 grew `PROBES` from 11 probes and 30 facts to 25 probes and 66 facts, so that
one fact stops deciding a change. No runtime code changed: the diff is
`scripts/quality_harness.py` and `tests/observability/test_quality_harness.py` only. The 11
original probes keep their ids, prompts, facts and positions; the 14 new ones are the tail
named by `EXPANSION_PROBE_IDS`.

**Configuration.** Worktree `C:\Users\ovidi\lap-g-bc87179` (the name is historical: it is
checked out at `4d98e13`, with the same uncommitted H1 harness diff as `main`, and holds no
`.env` and no `build\`). Gateway on `127.0.0.1:8011`, gateway index
`modules=517 symbols=9113 relationships=19938`. Environment, as set by
`build\phase_h1_final\run_all.ps1`:

```text
APP_MODELS_CONFIG=[{"model":"qwen38-27b","backend_model":"qwen3.8-flash-next","provider":"openai",
  "base_url":"http://100.106.236.88:18300/v1","context_window":262144,"max_output_tokens":8192,
  "chars_per_token":3.5}]
APP_DEFAULT_MODEL=qwen38-27b  APP_DEFAULT_PROVIDER=openai  DEFAULT_MODEL=qwen38-27b
APP_REPOSITORY_PATH=C:\Users\ovidi\lap-g-bc87179
APP_REPOSITORY_EXCLUDE_GLOBS=scripts/**,build/**  APP_REPOSITORY_EXCLUDE_TESTS=false
APP_REPOSITORY_CONTEXT_ENABLED=true  APP_REPOSITORY_CONTEXT_MAX_TOKENS=4096
APP_REPOSITORY_CONTEXT_INTENT_BUDGETS=SEARCH:2048,TEST:2048,DEBUG:2048,REFACTOR:4096,IMPLEMENT:4096,EXPLAIN:4096
APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false  APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED=true
APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS=0
APP_CONTEXT_DELTA_INJECTION=true  APP_CONTEXT_DELTA_CACHE_SIZE=256  APP_CONTEXT_INTENT_RULES={}
APP_HISTORY_CAP_ENABLED=true  APP_HISTORY_CAP_TOKENS=3000
RELATIONSHIP_RANKING_ENABLED=true  RELATIONSHIP_EXPANSION_ENABLED=true  REQUEST_TIMEOUT=300
APP_SESSION_LOG_ENABLED=true
```

Harness, run twice per launch: `uv run python scripts\quality_harness.py --base-url
http://127.0.0.1:8011/v1 --model qwen38-27b --max-tokens 8192 --timeout 345
--reasoning-model qwen38-27b --compare-context --json`.

**Repetitions and scores.**

| launch | registry | exclude globs | runs | context on | context off |
| --- | --- | --- | --- | --- | --- |
| `build\phase_h1_live\` (2026-11-09 23:41 - 00:32) | with `test_vllm_think_block_strip` | `scripts/**` | 2 | 51/66, 51/66 | 3/66, 3/66 |
| `build\phase_h1_replace\` (2026-11-10) | `test_vllm_auth_error_mapping` only, `--probe` | `scripts/**` | 1 | 2/2 | 0/2 |
| `build\phase_h1_final\` (2026-11-10 10:40 - 11:29) | current, 25 probes | `scripts/**,build/**` | 2 | **53/66, 53/66** | **3/66, 3/66** |

In every launch the runs within it returned identical answers on all 50 requests, nothing errored, and
the harness's stderr was empty. In the final launch the original 11 scored `26/30` with 33,777
context-arm prompt tokens, matching Phase G's `67a7f7f` record exactly. The gateway index
was the same in all launches, so the glob change was a configuration correction with no
measured effect. Context-arm prompt tokens for all 25 probes: 74,132; the context-off arm
hit the 8,192-token output cap on 2 probes.

The 14 expansion probes, final launch (both runs identical):

| probe | intent | context on | context off | prompt tokens |
| --- | --- | --- | --- | --- |
| `implement_runtime_debug_route_path` | IMPLEMENT | 2/3 | 0/3 | 3,524 |
| `implement_settings_singleton_accessor` | IMPLEMENT | 3/3 | 0/3 | 3,081 |
| `debug_provider_exception_status` | DEBUG | 2/2 | 0/2 | 2,074 |
| `debug_vllm_stream_prefix` | DEBUG | 1/3 | 0/3 | 2,482 |
| `test_history_group_capping_guard` | TEST | 1/2 | 0/2 | 2,470 |
| `test_vllm_auth_error_mapping` | TEST | 2/2 | 0/2 | 2,645 |
| `search_delta_sentinel_value` | SEARCH | 1/3 | 0/3 | 2,035 |
| `search_file_activity_two_modules` | SEARCH | 1/2 | 0/2 | 1,722 |
| `explain_runtime_context_two_modules` | EXPLAIN | 2/2 | 0/2 | 3,620 |
| `explain_changed_file_promotion_two_modules` | EXPLAIN | 2/3 | 0/3 | 3,307 |
| `refactor_changed_file_promotion_counts` | REFACTOR | 2/3 | 0/3 | 3,553 |
| `refactor_changed_files_signal` | REFACTOR | 3/3 | 0/3 | 3,831 |
| `multiturn_cline_envelope_tools` | DEBUG | 2/2 | 0/2 | 2,360 |
| `multiturn_session_record_builder` | EXPLAIN | 3/3 | 1/3 | 3,651 |

**Miss classification.** Of the 13 context-on misses in the final launch, four are
`explain_changed_files_history_cap` (open since Phase G) and five were annotated "known
delivery gap: measured absent" in the probe definitions before any live run, all missing as
annotated. The other four, together with the replaced probe's
`test_chat_strips_leading_empty_think_block`, were the five misses the first launch left
unannotated. They were put on the F2 ladder offline (`build\phase_h1_ladder\ladder.py`).
That replay reproduced each live session record's primary, symbol count and estimated
tokens, and all five landed in class (d), delivered and unused; each now carries a
"measured delivered and unused" annotation. The replayed prompts were then sent straight to the backend
(`build\phase_h1_ladder\raw_replay.py`), and `prompt_tokens` and answers matched the live run:

- `debug_vllm_stream_prefix`: both helper names are delivered, and the backend's `reasoning`
  field names both correctly. The visible content is cut where the model starts writing the
  think-block tag (see "Stop-token investigation" below).
- `test_vllm_think_block_strip` (since replaced): the content was empty after 198 completion
  tokens, ending the same way while still in reasoning. Its expected fact was also wrong: the
  prompt asks for the streaming test and the fact named the non-streaming one.
- `max_current_tool_result_tokens`: one occurrence, a keyword argument in a supporting test
  preview; `cap_history`'s own signature was not delivered.
- `_hash_user_turns`: delivered as signature only, behind its caller `conversation_key`, which
  the answer named.

`debug_vllm_stream_prefix` stays in the set as an end-to-end probe. `test_vllm_think_block_strip`
was replaced in place by `test_vllm_auth_error_mapping`, which asks about the live-path vLLM
provider without asking about think tags.

**Stop-token investigation, 2026-11-10 (roadmap Phase H item 2).** Read-only: requests and
`/tokenize`/`/detokenize` calls against the backend, no serving change. The H1 prompts were
rebuilt by the offline replay and sent with `"skip_special_tokens": false,
"return_token_ids": true` (`build\stoptoken\replay_tokens.py`):

| request | completion tokens | stray `<\|im_start\|>` (248045) | last token |
| --- | --- | --- | --- |
| `debug_vllm_stream_prefix` | 240 | at 237 | `<\|im_end\|>` (248046) |
| `test_vllm_think_block_strip` (replaced) | 198 | at 194 | `<\|im_end\|>` (248046) |
| `test_history_group_capping_guard` (control) | 207 | none | `<\|im_end\|>` (248046) |

All three have `finish_reason=stop` and `stop_reason=null`: generation ends on the normal
end-of-turn token, not on a stop string, and the stop configuration needs no change. Single
special tokens on this tokenizer include `<|endoftext|>` 248044, `<|im_start|>` 248045,
`<|im_end|>` 248046, `<think>` 248068, `</think>` 248069, `<tool_call>` 248058,
`<tool_response>` 248066, `<|file_sep|>` 248065 and `<|repo_name|>` 248064.
`/tokenize` on the full serialized requests (`build\stoptoken\prompt_tokens.py`) shows the
literal tags in injected source arriving as those tokens: `debug_vllm_stream_prefix` carries
2 `<think>` and 1 `</think>` from the context besides the template's own, the replaced probe
3 and 3, the control none.

A/B with one variable, the tags in the serialized messages defused by a zero-width space
(`build\stoptoken\defuse_ab.py`):

| probe | as is | defused |
| --- | --- | --- |
| `debug_vllm_stream_prefix` | 240 tokens, cut at the stray tag, 1/3 | 325 tokens, complete, 3/3 |
| `test_vllm_think_block_strip` | 198 tokens, empty content | 708 tokens, complete, names the streaming test |

No stray `<|im_start|>` was generated in either defused arm. The zero-width character
appeared in the defused answer's quoted tag, which is why it is a diagnostic only. Backend
launch arguments and `generation_config` were not inspected. The proposed fix is roadmap
Phase H item 3 (H2).

Artifacts (Git-ignored):

- `build\phase_h1_probes\`: probe design and offline validation (`h1_validate.py`)
- `build\phase_h1_live\`: first launch, `run_all.ps1`, `quality_compare_run{1,2}.json`,
  `sessions_h1_live_off.jsonl`, `gateway_out.txt`
- `build\phase_h1_ladder\`: `ladder.py`/`ladder.json`, `raw_replay.py`/`raw_replay.json`,
  `check_new.py`
- `build\phase_h1_replace\`: the replacement probe's single live run
- `build\phase_h1_final\`: the recorded baseline, `run_all.ps1`,
  `quality_compare_run{1,2}.json`, `sessions_h1_final.jsonl`, `gateway_out.txt`
- `build\stoptoken\`: the stop-token investigation, `replay_tokens.py`, `prompt_tokens.py`,
  `defuse_ab.py` and their JSON

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
