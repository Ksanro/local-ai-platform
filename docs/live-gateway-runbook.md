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

Current local backend: SGLang serves `qwen3.8-flash-next` at
`http://100.106.236.88:18300/v1`, exposed through the gateway as
`qwen38-27b` with provider `openai`. The Codex sandbox may fail direct TCP
checks to this port with `Bad access`; retry endpoint checks with approved
unsandboxed `curl.exe` before treating SGLang as unavailable.

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
- backend unavailable or crashed (SGLang, vLLM, or other OpenAI-compatible)
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
is.

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

To A/B it, run the fixed probe set twice against the same backend with only this
flag changed, on a deliberately dirty tree, and compare both score and
`context.estimated_tokens`:

```powershell
.\uv.exe run python scripts\quality_harness.py --json --model qwen38-27b --max-tokens 8192 --reasoning-model qwen38-27b > logs\quality_changed_files_off.json
# restart the gateway with APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=true
.\uv.exe run python scripts\quality_harness.py --json --model qwen38-27b --max-tokens 8192 --reasoning-model qwen38-27b > logs\quality_changed_files_on.json
.\uv.exe run python scripts\evaluate_quality_harness.py logs\quality_changed_files_on.json --model qwen38-27b
```

The promotion reorders within the same budget, so `estimated_tokens` may shift
as different symbols take the same space - what must not happen is the promoted
arm exceeding `context.max_tokens` or admitting symbols the query never matched.
Treat either of those as a bug, not as the signal working.

Before scoring either arm, confirm the bonus actually reached the context. In the
enabled run's session log, the `CHANGED-FILE PROMOTION` section of
`scripts\analyze_sessions.py` must show at least one record with
`changed_files_signal="ok"`, `changed_files_count >= 1` and either
`changed_symbols_promoted >= 1` or `changed_primary_promoted=true`. A record with
`changed_symbols_selected > 0` and `changed_symbols_promoted = 0` is the other
honest result - the bonus was present and changed nothing - and it means the two
arms measured the same retrieval twice.

## Full Quality Baseline

Run the fixed 8-probe set against the current local backend:

```powershell
.\uv.exe run python scripts\quality_harness.py --json --model qwen38-27b --max-tokens 8192 --reasoning-model qwen38-27b > logs\quality_baseline_qwen3_8_flash_next_20261010.json
```

Use `--model qwen38-27b` (gateway alias for SGLang `qwen3.8-flash-next`) and
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

## Interpreting long runs, timeouts, and failed execution

Three independent timeout layers can each produce a failure report. Identify
which layer fired before re-running anything:

| Layer | Where it is set | What a failure looks like |
|---|---|---|
| Agent command transport | agent/IDE dependent | "failed execution" report while the harness process may still be running |
| Harness per-probe client | `--timeout` (default `120`) | probe `error: TimeoutError: timed out after 120.0s (harness client timeout; gateway/SGLang may still be generating)` and `seconds ~= 120` |
| Gateway/provider | `REQUEST_TIMEOUT` in `.env` | gateway aborts the provider call; the harness records an HTTP error instead |

- Expected wall time for a full `--compare-context` on qwen38-27b/SGLang is
  roughly 5-15 minutes (16 probes; the no-context reasoning probes are the
  slow ones and are the ones that can hit the per-probe timeout).
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
