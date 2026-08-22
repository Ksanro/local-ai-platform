# Local AI Platform

Local AI Platform is an OpenAI-compatible gateway for coding agents.
Agents such as Cline, Claude Code, and curl point at this gateway instead
of talking directly to the backend. The gateway resolves the requested model,
adds ranked repository context, optionally caps forwarded chat history,
and forwards the request to the backend provider.

The project currently optimizes one live path: making local coding-agent
requests faster and more repository-aware while preserving OpenAI protocol
compatibility.

## What Runs

The live request path is registered in `apps/gateway/main.py`:

```text
FastAPI /v1/chat/completions
  -> ModelResolutionStage
  -> PlanningStage
  -> RepositoryContextStage
  -> history capping in PipelineEngine
  -> ProviderStage
  -> OpenAI-compatible backend (SGLang)
```

Large parts of `packages/` are future scaffolding and are not reachable
from the gateway. Treat `CLAUDE.md` as the operational source of truth for
what runs and what is dormant.

## Core Features

- OpenAI-compatible `/v1/chat/completions` endpoint
- vLLM provider with streaming and non-streaming support
- Generic OpenAI-compatible provider (`provider: "openai"`) for any OpenAI-compatible backend
- model registry with client-facing `model` and upstream `backend_model`
- repository index built at gateway startup
- deterministic planning and intent detection
- ranked repository-context injection
- normalized request boundary preserving OpenAI protocol fields
- optional history capping to reduce backend prefill latency
- JSONL session logging and analyzer for real Cline measurements

## Setup

```powershell
.\uv.exe sync
```

Create or edit `.env`. A minimal local configuration looks like:

```env
OPENAI_BASE_URL=http://100.106.236.88:30000/v1
OPENAI_API_KEY=empty
REQUEST_TIMEOUT=120

APP_DEFAULT_PROVIDER=openai
APP_DEFAULT_MODEL=qwen38-27b
APP_REPOSITORY_PATH=.
APP_REPOSITORY_CONTEXT_ENABLED=true
APP_REPOSITORY_CONTEXT_MAX_TOKENS=4096
APP_REPOSITORY_CONTEXT_INTENT_BUDGETS=SEARCH:2048,TEST:2048,DEBUG:2048,REFACTOR:4096,IMPLEMENT:4096,EXPLAIN:4096
APP_CONTEXT_INTENT_RULES={}
APP_SESSION_LOG_ENABLED=true
APP_HISTORY_CAP_ENABLED=true
APP_HISTORY_CAP_TOKENS=10000
APP_MODELS_CONFIG=[{"model":"qwen38-27b","backend_model":"qwen3.8-27b","provider":"openai","base_url":"http://100.106.236.88:30000/v1","context_window":262144,"max_output_tokens":8192}]
APP_QUALITY_REASONING_MODELS=qwen38-27b
APP_QUALITY_REASONING_MIN_TOKENS=2048
```

Provider raw env vars (for example `OPENAI_BASE_URL` for the `openai`
provider) and the `APP_` gateway settings are different systems. When
`APP_MODELS_CONFIG` is set, routing comes from that JSON model definition.

## Run The Gateway

```powershell
.\uv.exe run uvicorn apps.gateway.main:create_app --factory --port 8001
```

Check it:

```powershell
curl http://localhost:8001/v1/models
```

Point Cline or another OpenAI-compatible client at:

```text
http://localhost:8001/v1
```

## Session Logs

With `APP_SESSION_LOG_ENABLED=true`, requests are written to
`logs/sessions.jsonl`.

Analyze them with:

```powershell
.\uv.exe run python scripts\analyze_sessions.py logs\sessions.jsonl
```

The analyzer reports prompt tokens, latency, provider wait time, context
status, intent distribution, and history-capping behavior.

## Quality Harness

Run the live gateway quality smoke test after starting the gateway:

```powershell
.\uv.exe run python scripts\quality_harness.py
```

The harness sends fixed low-token prompts for the live intents and scores
answers by expected repository facts. By default it sends `context_intent`
overrides so retrieval quality can be measured independently from intent
detection. Use `--no-context` to disable repository-context injection for
one run, `--compare-context` to compare context-on versus context-off, and
`--no-intent-overrides` to test detector behavior too.

## Focused Gates

Use focused gates for live-path work:

```powershell
.\uv.exe run python -m pytest tests\pipeline tests\gateway tests\providers tests\planning tests\context tests\repository -q
.\uv.exe run python -m ruff check apps\gateway packages\pipeline packages\providers packages\planning packages\context packages\repository scripts
.\uv.exe run python -m mypy packages\providers packages\pipeline apps\gateway
```

The full repository still contains dormant packages with known failures and
lint debt. Do not use a green full-repo run as the definition of live-path
correctness until CI is realigned.

## Documentation

- `CLAUDE.md` - operational truth for agents and contributors
- `TESTING.md` - live measurement and A/B testing protocol
- `docs/STATUS.md` - current runtime status snapshot
- `docs/roadmap.md` - current goals and deferred work
- `docs/index.md` - documentation map, including dormant/future docs

## License

Apache 2.0. See `LICENSE`.
