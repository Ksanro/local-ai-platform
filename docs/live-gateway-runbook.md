# Live Gateway Runbook

Use this when an agent or operator needs to run live gateway probes from a
fresh terminal.

Run `uv` as `.\uv.exe` from the repo root. `uv` is not assumed to be on `PATH`.
Commands below are PowerShell-first because the project is normally operated on
Windows. If an agent is in Bash/Git Bash/WSL, either run these through
`powershell.exe -Command "..."` or use the Bash equivalents below.

Important: `apps/gateway/main.py` loads `.env` with `override=True`. Values in
`.env` can override shell environment variables passed when starting the
gateway. Before live probes, check `.env` for `APP_SESSION_LOG_PATH` and either
use that same path in `--session-log-path` or update `.env` for the run.

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

Bash/Git Bash equivalent:

```bash
export UV_CACHE_DIR='C:\Users\ovidi\local-ai-platform\.uv-cache'
export APP_SESSION_LOG_ENABLED='true'
export APP_SESSION_LOG_PATH='logs\sessions.jsonl'
export APP_CONTEXT_DELTA_INJECTION='true'
mkdir -p logs
: > logs/sessions.jsonl
./uv.exe run python -m uvicorn apps.gateway.main:create_app --factory --port 8001
```

## Check Gateway

In a second terminal:

```powershell
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/v1/models
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

Bash/Git Bash equivalent:

```bash
mkdir -p logs
: > logs/sessions.jsonl
./uv.exe run python scripts/quality_harness.py --delta-context --session-log-path logs/sessions.jsonl
```

If `.env` points at `logs/implement_budget_A_4096_20260801.jsonl`, use that
same path in Bash too:

```bash
./uv.exe run python scripts/quality_harness.py --delta-context --session-log-path logs/implement_budget_A_4096_20260801.jsonl
```

Pass means:

- `ok: True`
- first request scores all expected facts
- follow-up request scores all expected facts
- follow-up context has `symbols_suppressed > 0`

Blocked means:

- gateway unavailable
- vLLM unavailable or crashed
- backend timeout/API 500/context-size error
- `session_log_records_not_found` after the harness completes

A missing log file before the first chat request is not a failure. The gateway
creates and writes the file on completed `/v1/chat/completions` requests.
