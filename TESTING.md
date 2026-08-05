# TESTING.md — how to run and request tests

This file defines how tests and measurements are handed off in this project. It exists so a testing
request produces something runnable top-to-bottom, not prose to interpret.

## Format contract (for whoever writes the test steps)

When providing a test or measurement, always give, in this order:

1. **Exact commands, in run order.** PowerShell (Windows). Every `uv` call starts with `.\uv`. No
   "then do X" prose between commands that could be folded into a command.
2. **One exact Cline task string** (verbatim, in a code block) when the test needs a live agent
   session — never "run a real task". The same string is reused across compared runs so results are
   comparable.
3. **The specific numbers to read** from the output, and the pass/fail line to watch.
4. **Minimal surrounding text.** Extra context invites unplanned variation. Say what to run, what to
   look for, stop.

Two runs that are being compared must differ in **exactly one variable** (e.g. one env flag). Same
Cline task, same files, same order. If two things change, the comparison is meaningless.

## Environment facts

- Config uses Pydantic with `env_prefix = "APP_"`. A field `history_cap_enabled` is set via the env
  var `APP_HISTORY_CAP_ENABLED`. Set these in `.env` (loaded with `override=true`, so `.env` beats
  shell env).
- Settings are read at **startup** and cached. Any `.env` change requires a **gateway restart** to
  take effect.
- Relevant flags:
  - `APP_SESSION_LOG_ENABLED` (default false) — must be `true` to capture anything to analyze.
  - `APP_SESSION_LOG_PATH` (default `logs/sessions.jsonl`).
  - `APP_HISTORY_CAP_ENABLED` (default **true** - verify current default in `config.py`).
  - `APP_HISTORY_CAP_TOKENS` (default 0 = derive from context window; set a number to force a budget).
  - `APP_REPOSITORY_CONTEXT_ENABLED` (default true).
- Per request, `/v1/chat/completions` accepts `repository_context_enabled` to override repository
  context for that call. The quality harness uses this for context-on/context-off comparison.

## Log hygiene — always

- **Delete the log before every measurement run:**
  `Remove-Item logs\sessions.jsonl -ErrorAction SilentlyContinue`
- A mixed log (old + new records) silently corrupts every average. One run = one clean log.
- Redirect each run's analysis to its own file (`> run_A.txt`) so runs are not overwritten.

## Deterministic checks (no gateway, no vLLM, no model)

Use these to confirm code is correct before any live run. Fast, repeatable, no noise.

```powershell
.\uv run python -m pytest -q
.\uv run python -m pytest tests\pipeline tests\gateway tests\test_protocol_invariant.py -q
.\uv run python -m ruff check packages apps
.\uv run python -m mypy packages\pipeline apps\gateway
.\uv run python scripts\check_fixes.py
.\uv run python scripts\bench_context.py
.\uv run python scripts\quality_harness.py
.\uv run python -m pytest tests\evaluation tests\scripts tests\engineering_memory tests\observability\test_quality_harness.py tests\observability\test_quality_history.py -q
```

Baseline: the full suite has a known failure count (all in unreachable dead-code packages). A clean
change must **not increase** it. Confirm the current baseline number before claiming a change is
clean.

## Live measurement (gateway + vLLM required)

Start the gateway (leave running in its own terminal):

```powershell
.\uv run uvicorn apps.gateway.main:create_app --factory --port 8001
```

Confirm it is up (second terminal):

```powershell
curl http://localhost:8001/v1/models
```

Drive traffic, then analyze:

```powershell
.\uv run python scripts\analyze_sessions.py logs\sessions.jsonl
```

Run deterministic answer-quality probes:

```powershell
.\uv run python scripts\quality_harness.py
.\uv run python scripts\quality_harness.py --compare-context
.\uv run python scripts\quality_harness.py --delta-context --session-log-path logs\sessions.jsonl
```

Read the `TOTAL` line. `--compare-context` changes exactly one variable per
probe: repository context on versus off through the same gateway/provider path.
Recent baselines were `14-15/15` with context and `2/15` without context, on
the original 6 single-turn probes — the probe set now also includes 2
multi-turn probes (`multiturn_history_cap_budget`, `multiturn_config_systems`)
that send prior user/assistant turns before the scored final prompt, so a
fresh baseline run is needed to include them (`total_maximum` moves from `15`
to `20`).
The quality table also reports a separate style signal: `ok` means no known
reasoning preamble or tool/thinking marker was detected, while `bad` means the
answer still contained that chatter even if the required facts were present.

Use `--delta-context` for the server-side delta-context smoke test. It sends
two sequential live requests, then reads the session JSONL context metadata and
expects the follow-up request to report `symbols_suppressed > 0`. Keep session
logging enabled and point `--session-log-path` at the gateway's
`APP_SESSION_LOG_PATH` value.

Optionally, pipe `--json` output through `scripts\evaluate_quality_harness.py`
to get a structured evaluation (score, missing facts, prompt-token cost,
latency, style violations, and — in `--compare-context` mode — per-probe context delta) via
`packages.evaluation.quality_harness_report`:

```powershell
.\uv run python scripts\quality_harness.py --json | .\uv run python scripts\evaluate_quality_harness.py -
.\uv run python scripts\quality_harness.py --compare-context --json | .\uv run python scripts\evaluate_quality_harness.py -
.\uv run python scripts\quality_harness.py --delta-context --json --session-log-path logs\sessions.jsonl
```

Add `--persist --model <name> [--gateway-commit <sha>] [--notes "..."]` to
store the evaluation as a deterministic `EngineeringSessionRecord` via
`packages.engineering_memory.quality_harness_records`, e.g.:

```powershell
.\uv run python scripts\quality_harness.py --json | .\uv run python scripts\evaluate_quality_harness.py - --persist --model qwen36 --notes "post history-cap tuning"
```

Records land in `data/engineering_memory/memory_v1.json` by default (override
with `--storage-path`).

Read persisted quality-harness history with:

```powershell
.\uv run python scripts\quality_history.py
.\uv run python scripts\quality_history.py --json
```

Add `--quality-run [--quality-run-path <file>]` instead to get a flat
`QualityRun` summary (run_id, model, mode, totals, per-probe rows with
context-delta fields when in `--compare-context` mode) printed as JSON or
written to a file — no dashboard, no `EngineeringMemory` involvement:

```powershell
.\uv run python scripts\quality_harness.py --json | .\uv run python scripts\evaluate_quality_harness.py - --quality-run --model qwen36
```

## A/B measurement recipe (the standard shape)

To measure the effect of one setting, run the identical Cline task twice, changing only that setting,
with a clean log each time.

```powershell
# --- RUN A (control) ---
notepad .env                                              # set the ONE flag to its A value, save
Remove-Item logs\sessions.jsonl -ErrorAction SilentlyContinue
.\uv run uvicorn apps.gateway.main:create_app --factory --port 8001
#   -> paste the exact Cline task, let it finish, Ctrl+C the gateway
.\uv run python scripts\analyze_sessions.py logs\sessions.jsonl > run_A.txt
type run_A.txt

# --- RUN B (treatment) ---
notepad .env                                              # flip the ONE flag to its B value, save
Remove-Item logs\sessions.jsonl -ErrorAction SilentlyContinue
.\uv run uvicorn apps.gateway.main:create_app --factory --port 8001
#   -> paste the SAME Cline task, let it finish, Ctrl+C the gateway
.\uv run python scripts\analyze_sessions.py logs\sessions.jsonl > run_B.txt
type run_B.txt
```

Compare `run_A.txt` and `run_B.txt` on the specific metrics named in the test request.

## Cline task strings — rules

- Provide the task as a verbatim code block; the operator pastes it unchanged.
- Reference specific files by path so the token load is reproducible across runs.
- Keep it a fixed, bounded task (read these files, explain this) — not open-ended ("improve the
  code"), whose token load varies run to run and breaks the comparison.
- After a live run, note in prose whether Cline **completed the task correctly** — tool calls
  executed, answer coherent. A latency win that breaks Cline's behaviour is not a win.

## The core discipline

The recurring failure mode in this project is **green tests certifying inert code** — a feature wired
to the wrong slot passes every test and does nothing. The reliable way to catch it is to demand a
**measurable effect** (a number that must move), not to ask the suite whether the code is correct.
Every live measurement should name, in advance, the number that proves the feature ran at all
(e.g. `history_dropped_count > 0`). If that number does not move, the feature did not run — regardless
of a green suite.
