# Current Status

This file is the current runtime snapshot. It intentionally describes only
what matters for the live gateway path and calls out dormant code explicitly.

Last reviewed: 2026-07-28.

## Product Shape

Local AI Platform is an OpenAI-compatible gateway for coding agents. It sits
between agents and a self-hosted vLLM backend, injects ranked repository
context, optionally caps forwarded chat history, and records session logs for
measurement.

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
  -> vLLM
```

### ModelResolutionStage

Resolves the client-facing `model` to a `ResolvedModel` using either
`APP_MODELS_CONFIG` or fallback single-provider mode. The resolved definition
contains provider, backend model, context window, max output tokens, and
capability metadata.

### PlanningStage

Extracts user text, including OpenAI list-form content used by Cline, detects
intent deterministically, and stores a `ContextPlan` for repository-context
selection.

### RepositoryContextStage

Uses the startup repository index to select ranked symbols and modules, then
injects repository context into the provider-bound messages. Delta injection
suppresses symbols already sent in the conversation.

`APP_REPOSITORY_CONTEXT_MAX_TOKENS` controls the token budget passed to
repository-context ranking, relationship expansion, and final assembled
context trimming. The builder preserves the primary symbol first, drops
lower-ranked supporting symbols, and trims oversized primary source when
needed. Session logs record both `context.estimated_tokens` and
`context.max_tokens` so context size can be measured separately from full
provider prompt tokens.

`APP_REPOSITORY_CONTEXT_INTENT_BUDGETS` can override the default by planner
intent, for example `SEARCH:4096,TEST:3072,DEBUG:4096,EXPLAIN:8192`. Explicit
request metadata still wins over intent defaults.

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

### ProviderStage

Builds the provider payload from `NormalizedRequest`, swaps `model` to
`backend_model`, preserves protocol fields, and calls the resolved provider.

## What Is Implemented And Reachable

- FastAPI gateway endpoints: `/health`, `/version`, `/v1/models`,
  `/v1/chat/completions`
- vLLM provider
- provider registry and factory
- model registry and model router
- normalized request boundary
- protocol compatibility tests
- repository index builder
- planning and intent detection
- repository-context injection
- delta context injection
- history capping
- session JSONL logging
- session log analyzer
- live Cline/vLLM A/B measurement protocol

## What Exists But Is Dormant

These packages are not part of the live gateway path unless explicitly wired
later:

- `packages.capabilities`
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
- `packages.evaluation`
- `packages.execution`
- `packages.observability`
- `packages.architecture`
- `packages.benchmark`
- `packages.engineering_memory`

They may contain tests and useful designs, but they should not be treated as
runtime behavior.

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
dormant packages with known failures and pre-existing lint debt.

Recommended live-path checks:

```powershell
.\uv run python -m pytest tests\pipeline tests\gateway tests\providers tests\planning tests\context tests\repository -q
.\uv run python -m ruff check apps\gateway packages\pipeline packages\providers packages\planning packages\context packages\repository scripts
.\uv run python -m mypy packages\providers packages\pipeline apps\gateway
```

## Current Open Issues

- CI still runs broad repo checks and should be realigned to the documented
  baseline or cleaned up.
- Repository context can dominate prompt size; history capping alone is not the
  full latency lever. Configurable repository-context budget enforcement now
  exists; the next step is live tuning by intent/model.
- Token estimates still use `CHARS_PER_TOKEN = 4.0`, not model-specific
  tokenizers.
- Only vLLM is implemented as a concrete provider; true multi-provider
  operation is not product-proven.
