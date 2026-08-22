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

Current local backend: SGLang serves `qwen3.8-27b` at
`http://100.106.236.88:30000/v1`, exposed through the gateway as
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

## Full Quality Baseline

Run the fixed 8-probe set against the current local backend:

```powershell
.\uv.exe run python scripts\quality_harness.py --json --model qwen38-27b --max-tokens 8192 --reasoning-model qwen38-27b > logs\quality_baseline_qwen38_27b_after_fixes.json
```

Use `--model qwen38-27b` (gateway alias for SGLang `qwen3.8-27b`) and
`--max-tokens 8192`; the model spends budget on hidden reasoning, so smaller
limits risk empty or truncated answers. Evaluate the saved JSON:

```powershell
.\uv.exe run python scripts\evaluate_quality_harness.py logs\quality_baseline_qwen38_27b_after_fixes.json --model qwen38-27b
```

Persist only on a clean pass (all expected facts, style clean, no errors or
timeouts):

```powershell
.\uv.exe run python scripts\evaluate_quality_harness.py logs\quality_baseline_qwen38_27b_after_fixes.json --model qwen38-27b --persist --notes "SGLang qwen3.8-27b full quality baseline after retrieval and EXPLAIN budget fixes"
```

The 2026-08-22 baseline scored a clean TOTAL 20/20 with style 8/8 ok
(28013 prompt tokens, 144.6 seconds) and was persisted as session
`quality_harness-20260821T214629502370-6d519523`.
