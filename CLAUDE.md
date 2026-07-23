# CLAUDE.md

Context for AI agents working in this repository. Read this before making changes.

## What this project is

An OpenAI-compatible gateway that injects ranked repository context into prompts before forwarding
them to a self-hosted vLLM backend. Clients (Claude Code, Cline, curl) point at the gateway instead
of vLLM and get repo-aware responses without changing their own configuration.

## What actually runs

The live request path is **four pipeline stages**, registered in this order in
`apps/gateway/main.py` `lifespan()`:

1. `ModelResolutionStage` — maps the client `model` string to a backend; stores `resolved_model`
   (typed field) and `context_window` on `PipelineContext`
2. `PlanningStage` — detects intent, selects a ranking profile, stores `context_plan` in metadata
3. `RepositoryContextStage` — ranks symbols from the index, composes a `ContextPackage`, serializes
   a `ProviderRequest`
4. `ProviderStage` — translates `model` to `backend_model` and calls the provider

See `docs/execution-flow.mmd`.

## What does NOT run

These packages have **zero references** from `apps/` or from any pipeline stage. They are not
reachable from a request:

`capabilities`, `tasks`, `workflows`, `advisors`, `autonomous`, `verification`, `patches`,
`modification`, `session`, `bootstrap`, `controller`, `evaluation`, `platform`, `execution`,
`observability`, `architecture`, `benchmark`

That is roughly 20,000 lines. **Do not extend them, and do not assume documentation describing them
reflects running behaviour.** See `docs/engineering-controller-flow.mmd`, which is labelled unwired.

If you are about to create a new directory under `packages/`, stop — that is almost certainly wrong.

## Test baseline

`pytest -q` currently reports **42 failures** on Python 3.13 (48 on 3.12 — six immutability tests
depend on a CPython fix for `@dataclass(frozen=True, slots=True)`).

**42 failures is the expected baseline, not breakage.** They live in `autonomous` (26),
`observability` (12) and `integration/test_engineering_flow` (4) — all unreachable code.

A change is only clean if the count does not increase. Report the before and after number.

## Gate commands

```
uv run python -m pytest -q
uv run python -m ruff check <paths you changed>
uv run python -m mypy packages/providers packages/pipeline apps/gateway
```

Use `python -m` — the bare `pytest`/`ruff` shims are blocked by Windows Application Control on the
primary dev machine.

Repo-wide ruff currently reports ~211 pre-existing errors, mostly missing trailing newlines and
unused imports in unreachable packages. Scope ruff to the files you touched.

## Configuration — two systems, easy to confuse

| System | Prefix | Variables |
|---|---|---|
| Pydantic `Settings` (`apps/gateway/core/config.py`) | `APP_` | `log_level`, `default_provider`, `default_model`, `repository_path`, `repository_context_enabled`, `models_config` |
| Raw env in `packages/providers/vllm.py` | none | `VLLM_BASE_URL`, `VLLM_API_KEY`, `REQUEST_TIMEOUT`, `DEFAULT_MODEL` |

`DEFAULT_MODEL` and `APP_DEFAULT_MODEL` are **different variables**. Both usually need setting.

`main.py` calls `load_dotenv(override=True)`, so `.env` **overrides** shell environment variables —
the opposite of the usual convention. You cannot override `.env` from the command line.

`Settings` is `lru_cache`d and `.env` loads at import time, so environment changes require a restart.

## Model routing

`models_config` is a JSON array. `model` is the client-facing name; `backend_model` is what gets sent
upstream. They are deliberately different — clients keep a stable name while the served checkpoint
changes.

```json
[{"model":"qwen36","backend_model":"unsloth/Qwen3.6-35B-A3B-NVFP4","provider":"vllm",
  "base_url":"http://100.106.236.88:8001/v1","context_window":231072}]
```

Empty `models_config` falls back to single-provider mode, where any model string resolves.

## Error status mapping

`apps/gateway/api/chat.py::_status_for_exception`:

| Condition | Status |
|---|---|
| `UnknownModelError` | 404 + OpenAI-shaped body (`code: model_not_found`) |
| upstream 4xx | passed through unchanged |
| upstream 5xx | 502 |
| `ProviderConnectionError` | 503 |
| `UnknownProviderError`, `PipelineError` | 501 |

Upstream 4xx must not become 502 — that tells clients to retry a permanently invalid request.

## Rules

- Do not create new top-level packages.
- Do not weaken, delete, `xfail` or `skip` tests to make a suite pass. If a test seems wrong, stop
  and say so.
- Run the gate commands and paste real output. Do not report completion without running them.
- If an instruction seems wrong or infeasible, stop and report rather than improvising an
  alternative design.
- Stage-level failures are **returned** as `PipelineStageResult(success=False, exception=...)`, never
  raised. The engine halts on the first failure; `chat.py` maps `response.exception` to a status.
