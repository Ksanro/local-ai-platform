# Local AI Platform — Status & Architecture

**Version:** 0.1.0
**License:** Apache 2.0
**Python:** 3.12+
**Last Updated:** 2026-07-14

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Implemented Features](#implemented-features)
- [Public APIs](#public-apis)
- [Package Structure](#package-structure)
- [Testing](#testing)
- [Configuration](#configuration)
- [Roadmap](#roadmap)
- [Non-Goals](#non-goals)

---

## Overview

Local AI Platform is a self-hosted developer intelligence platform that provides a unified inference gateway for AI models, repository intelligence, context optimization, long-term memory, and a unified inference gateway.

The platform is **model agnostic**, **provider agnostic**, and **agent agnostic**. It sits between coding agents (VS Code, Cline, Claude Code) and LLM backends (vLLM, OpenAI, Ollama, LM Studio), forwarding requests with structured logging, request tracing, and streaming support.

---

## Architecture

### High-Level Diagram

```
        VS Code / Cline / Claude Code
                    │
                    ▼
        ┌─────────────────────┐
        │  Local AI Gateway   │  FastAPI
        │  (REST API)         │
        └──────────┬──────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
   Request Pipeline      Context Engine (future)
        │
        ▼
  Provider Layer
        │
        ▼
  vLLM / OpenAI / Ollama / LM Studio
```

### Design Principles

- **Local First** — runs entirely on-premise or in a private cloud
- **Production Ready** — structured logging, request tracing, health checks
- **Simple Before Smart** — no unnecessary abstractions
- **Performance First** — async, streaming, connection pooling
- **Provider Agnostic** — swap backends without changing the gateway
- **Agent Agnostic** — works with any agent that speaks OpenAI-compatible API
- **Stateless Components Where Possible** — each request is independent
- **Composition Over Coupling** — packages are independently testable

### Dependency Rules

```
Gateway → Packages → Providers
```

- Providers **never** import Gateway
- Applications **never** import other Applications
- No circular imports

---

## Implemented Features

### 1. OpenAI-Compatible Gateway

A FastAPI-based HTTP gateway that proxies requests to backend LLM providers.

| Method | Path                    | Description                          |
|--------|-------------------------|--------------------------------------|
| GET    | `/health`               | Health check (gateway alive)         |
| GET    | `/version`              | Application metadata                 |
| POST   | `/v1/chat/completions`  | Chat completions (OpenAI API shape)  |

**Capabilities:**

- **Non-streaming responses** — returns full JSON response from the provider
- **Streaming responses** — Server-Sent Events (SSE) with per-token streaming
- **Request tracing** — every response includes `X-Request-ID` and `X-Process-Time` headers
- **Structured logging** — every request logs `provider`, `model`, `duration`, `status`, `request_id`
- **Error handling** — 501 for missing providers, 502 for provider errors, 401 for auth failures
- **CORS** — configurable origins (default `*`)
- **Pydantic validation** — `ChatCompletionRequest` validates `messages`, `model`, `stream`, `temperature`, `max_tokens`

### 2. Provider Abstraction Layer

A pluggable provider system that decouples the gateway from any specific LLM backend.

**Abstract Interface (`Provider` ABC):**

```python
class Provider(ABC):
    async def health(self) -> dict[str, Any]    # Health check
    async def chat(self, **kwargs) -> dict      # Chat completion
    async def models(self) -> list[str]         # Model listing
```

**Registry System:**

- `register(name, provider_class)` — register a provider by name
- `create_provider(name)` — instantiate a provider, raises `UnknownProviderError` if not registered
- `has_provider(name)` — check if a provider is registered
- `get_registry()` — get a copy of the current registry

**Exception Hierarchy:**

```
ProviderError
├── UnknownProviderError       # Provider not registered
├── ProviderConnectionError    # Network timeout, connection refused
├── ProviderAuthenticationError # Invalid/expired API key (HTTP 401)
└── ProviderResponseError      # Non-2xx status, malformed response
```

**Auto-Registration:** Provider modules register themselves as a side effect of being imported. The gateway calls `_load_providers()` at startup to trigger all registrations.

### 3. vLLM Provider

The first concrete provider implementation. Proxies OpenAI-compatible requests to a vLLM server.

**Features:**

- Singleton `httpx.AsyncClient` with connection pooling
- Authorization header: `Bearer {API_KEY}`
- Configurable timeout from `REQUEST_TIMEOUT`
- Health check via `/models` endpoint
- Chat completion forwarding (both streaming and non-streaming)
- Model listing from `/models` endpoint
- Graceful client shutdown via `close()`

**Error Mapping:**

| HTTP Status | Exception |
|-------------|-----------|
| 401 | `ProviderAuthenticationError` |
| 5xx | `ProviderResponseError` |
| Timeout | `ProviderConnectionError` |
| Connection refused | `ProviderConnectionError` |

**Streaming:** Returns an async generator that yields SSE-formatted events. Error events are wrapped as `data: {"error": {...}}\n\n` for client compatibility.

### 4. Request Processing Pipeline

A pluggable stage-based pipeline that processes requests between the gateway and the provider. Stages execute in order, each receiving a mutable context and returning a result.

**Architecture:**

```
Gateway → Pipeline (stages in order) → Provider
```

**Abstract Interface (`PipelineStage` ABC):**

```python
class PipelineStage(ABC):
    async def before(context) -> PipelineStageResult | None  # Prepare / short-circuit
    async def execute(context) -> PipelineStageResult        # Primary work
    async def after(context, result) -> None                 # Post-process
```

**Pipeline Engine:**

```python
engine = PipelineEngine()
engine.register(ProviderStage())
response = await engine.execute(request)
```

**Execution Model:**

1. `before()` — prepare, validate, short-circuit (return early)
2. `execute()` — perform the primary work
3. `after()` — post-process, clean up, record metrics

**Built-in Stage:**

| Stage | Responsibility |
|-------|---------------|
| `ProviderStage` | Resolve provider, call `provider.chat()`, return response |

**Future Stages (planned):**

| Stage | Responsibility |
|-------|---------------|
| `AuthenticationStage` | Validate API keys, rate limiting |
| `RepositoryContextStage` | Enrich request with repository context |
| `MemoryStage` | Inject conversation memory |
| `PromptOptimizationStage` | Optimize prompts before sending |
| `DSPARKStage` | DSPARK framework integration |
| `MetricsStage` | Collect per-request metrics |
| `ResponsePostProcessorStage` | Transform responses |

**Data Flow:**

- `PipelineRequest` — typed request with provider, model, messages, stream, kwargs
- `PipelineContext` — mutable shared state (request_id, metadata, stage results)
- `PipelineStageResult` — per-stage result (success, data, error, duration)
- `PipelineResponse` — final response with all stage results and timing

**Error Handling:**

- Pipeline owns exception translation
- Gateway converts `PipelineError` → HTTP response
- Stage errors include stage name and original exception

**Logging:**

- Per-stage: `stage`, `duration`, `request_id`
- Per-request: `provider`, `model`, `status`

### 6. Repository Scanner

Walks a directory tree, collects file and directory metadata, classifies files by language, and produces a structured index.

**Core Function:**

```python
def scan(path: Path) -> RepositoryIndex
```

**Data Models:**

| Model | Description |
|-------|-------------|
| `SourceFile` | File metadata (path, extension, language, size, mtime) |
| `Directory` | Directory metadata (path, file count, subdirectories) |
| `LanguageSummary` | Per-language file count and total size |
| `Statistics` | Aggregate stats (total files, source files, languages, largest files) |
| `RepositoryIndex` | Complete scan result (root, directories, files, statistics) |

**Filtering:**

- Hardcoded ignored directories: `.git`, `.venv`, `venv`, `node_modules`, `dist`, `build`, `target`, `coverage`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `__pycache__`
- `.gitignore` pattern parsing (top-level only)
- Supports glob patterns, directory-only patterns, prefix patterns, and basename patterns

**Language Detection:** Maps file extensions to 20+ programming languages including Python, Java, Scala, Kotlin, C#, C++, Rust, Go, JavaScript, TypeScript, YAML, JSON, TOML, Markdown, SQL, Shell, and Dockerfile.

**Helper Functions:**

- `get_file(index, relative_path)` — look up a file by path
- `find_extension(index, extension)` — find all files with a given extension
- `find_language(index, language)` — find all files of a given language
- `summary(index)` — human-readable summary dict

### 7. Configuration Management

**YAML Config Loading (`packages/config`):**

- Searches multiple directories for `config.yaml`
- Environment variables take precedence over file values
- Type-aware resolution (float, int, bool, string)

**Pydantic Settings (`apps.gateway.core.config`):**

- `APP_`-prefixed environment variables
- `lru_cache` singleton pattern for settings instance
- Configurable: `app_name`, `log_level`, `cors_origins`, `default_provider`

### 8. Structured Logging

- Timestamp, logger name, level, and message format
- Output directed to stdout for containerized environments
- Per-request logging with `provider`, `model`, `duration`, `status`, `request_id`
- Streaming duration and TTFT (time-to-first-token) logging

---

## Public APIs

### Gateway Endpoints

#### `GET /health`

Returns gateway health status.

```json
{"status": "ok"}
```

#### `GET /version`

Returns application metadata.

```json
{"name": "Local AI Platform", "version": "0.1.0"}
```

#### `POST /v1/chat/completions`

OpenAI-compatible chat completions endpoint.

**Request Body:**

```json
{
  "messages": [{"role": "user", "content": "Hello"}],
  "model": "default-model",
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 100
}
```

**Response (non-streaming):** OpenAI-compatible JSON with `choices`, `id`, `object`, `created`, `model`, `usage` fields.

**Response (streaming):** Server-Sent Events with `data: {...}` lines and `[DONE]` terminator.

### Provider Package (`packages.providers`)

```python
from packages.providers import (
    Provider,                    # Abstract base class
    create_provider,             # Create instance by name
    register,                    # Register a provider class
    ProviderError,               # Base exception
    UnknownProviderError,        # Not registered
    ProviderConnectionError,     # Network failure
    ProviderAuthenticationError, # Auth failure
    ProviderResponseError,       # Invalid response
)
```

### Repository Package (`packages.repository`)

```python
from packages.repository import (
    scan,                      # Scan a directory tree
    SourceFile,                # File metadata model
    Directory,                 # Directory metadata model
    LanguageSummary,           # Per-language summary
    Statistics,                # Aggregate statistics
    RepositoryIndex,           # Complete scan result
    parse_gitignore,           # Parse .gitignore patterns
    should_ignore_path,        # Check if path should be ignored
    find_extension,            # Find files by extension
    find_language,             # Find files by language
    get_file,                  # Look up file by path
    summary,                   # Human-readable summary
)
```

### Config Package (`packages.config`)

```python
from packages.config import (
    load_config,               # Load YAML config file
    get_env_or_config,         # Env var > config > default
)
```

### Pipeline Package (`packages.pipeline`)

```python
from packages.pipeline import (
    PipelineEngine,            # Pipeline execution engine
    PipelineRequest,           # Typed request model
    PipelineResponse,          # Typed response model
    PipelineContext,           # Mutable shared state
    PipelineStageResult,       # Per-stage result
    PipelineStage,             # Abstract base class
    PipelineError,             # Base exception
    StageError,                # Stage failure
    PipelineExecutionError,    # Execution failure
)
from packages.pipeline.stages import ProviderStage  # Built-in provider stage
```

---

## Package Structure

```
.
├── apps/
│   └── gateway/                    # FastAPI gateway application
│       ├── main.py                 # App factory + lifespan
│       ├── middleware.py           # Request ID + timing middleware
│       ├── api/
│       │   ├── chat.py             # POST /v1/chat/completions
│       │   ├── health.py           # GET /health
│       │   └── version.py          # GET /version
│       └── core/
│           ├── config.py           # Pydantic Settings
│           └── logging.py          # Structured logging setup
│       └── Dockerfile              # Container image
│
├── packages/
│   ├── providers/                  # Provider abstraction + vLLM impl
│   │   ├── base.py                 # Provider ABC
│   │   ├── exceptions.py           # Exception hierarchy
│   │   ├── factory.py              # create_provider()
│   │   ├── registry.py             # register() / get_registry()
│   │   └── vllm.py                 # VLLMProvider implementation
│   │
│   ├── repository/                 # Repository scanner
│   │   ├── models.py               # Dataclasses (SourceFile, Directory, etc.)
│   │   ├── scanner.py              # scan() function
│   │   ├── filters.py              # gitignore + hardcoded ignores
│   │   ├── index.py                # Helper functions
│   │   └── languages.py            # Extension → language mapping
│   │
│   ├── config/                     # YAML config loading
│   │   ├── __init__.py             # load_config, get_env_or_config
│   │   └── config.yaml             # Default configuration
│   │
│   ├── pipeline/                   # Request processing pipeline
│   │   ├── __init__.py             # Exports
│   │   ├── base.py                 # PipelineStage ABC
│   │   ├── context.py              # PipelineContext, PipelineStageResult
│   │   ├── engine.py               # PipelineEngine
│   │   ├── exceptions.py           # PipelineError hierarchy
│   │   ├── request.py              # PipelineRequest
│   │   ├── response.py             # PipelineResponse
│   │   └── stages.py               # ProviderStage
│   │
│   ├── core/                       # Core business logic (stub)
│   └── telemetry/                  # Telemetry/monitoring (stub)
│
├── tests/                          # Test suite
│   ├── conftest.py                 # Shared fixtures
│   ├── gateway/                    # Gateway unit tests
│   ├── providers/                  # Provider unit tests
│   ├── repository/                 # Scanner unit tests
│   └── integration/                # E2E integration tests
│
├── scripts/
│   └── test_gateway.py             # Smoke test script
│
├── docs/
│   └── architecture.md             # Architecture documentation
│
├── compose.yaml                    # Docker Compose (gateway, redis, postgres)
├── pyproject.toml                  # Root project config
└── .github/workflows/ci.yml        # CI: lint, type-check, test
```

---

## Testing

### Test Coverage

| Area | Tests | Description |
|------|-------|-------------|
| Gateway | 6 | Health, version, chat (mocked + real vLLM) |
| Pipeline | 32 | Engine, stages, ordering, context, ProviderStage |
| Providers | 33 | Factory, registry, vLLM provider (health, models, chat, streaming, config) |
| Repository | 20+ | Scanner, filters, language detection, statistics |
| Integration | 3 | End-to-end gateway → vLLM (health, chat, streaming) |
| Smoke | 3 | Manual smoke test (gateway reachable, chat, streaming) |

### Running Tests

```bash
# All tests
pytest

# Provider tests only
pytest tests/providers/

# Pipeline tests only
pytest tests/pipeline/

# Repository tests only
pytest tests/repository/

# Integration tests (requires running vLLM + gateway)
VLLM_BASE_URL=http://localhost:8000/v1 pytest tests/integration/

# Smoke test
python scripts/test_gateway.py
```

### CI Pipeline

GitHub Actions runs three parallel jobs on every push/PR to `main`:

1. **Lint** — `ruff check` + `ruff format --check`
2. **Type Check** — `mypy` (strict mode)
3. **Test** — `pytest`

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `local-ai-platform` | Application name |
| `APP_LOG_LEVEL` | `INFO` | Logging level |
| `APP_CORS_ORIGINS` | `["*"]` | CORS allowed origins |
| `APP_DEFAULT_PROVIDER` | `vllm` | Default provider name |
| `VLLM_BASE_URL` | `http://localhost:8000/v1` | vLLM server URL |
| `VLLM_API_KEY` | `empty` | vLLM API key |
| `REQUEST_TIMEOUT` | `60.0` | Request timeout in seconds |
| `DEFAULT_MODEL` | `default-model` | Default model identifier |

### Configuration File (`config.yaml`)

Provider settings are loaded from `config.yaml` with environment variable override:

```yaml
providers:
  default: vllm
  vllm:
    base_url: "http://localhost:8000/v1"
    api_key: "empty"
    request_timeout: 60.0
    default_model: "default-model"
```

Priority: **Environment Variable > Config File > Hardcoded Default**

---

## Roadmap

### Completed (Sprint 0)

- [x] Project bootstrap (uv, ruff, mypy, pytest, Docker Compose, GitHub Actions)
- [x] FastAPI gateway with health, version, and chat endpoints
- [x] Provider abstraction layer (ABC, registry, factory, exceptions)
- [x] vLLM provider implementation (streaming, health, models, chat)
- [x] Repository scanner (directory walking, language detection, gitignore)
- [x] Configuration management (YAML + env var override)
- [x] Structured logging with request tracing
- [x] Smoke test and integration test scripts
- [x] Request processing pipeline (stages, engine, context, ProviderStage)

### Planned (Future Sprints)

| Sprint | Feature | Description |
|--------|---------|-------------|
| Sprint 1 | Repository Indexer | Full repository indexing with symbol graphs and dependency graphs |
| Sprint 1 | Context Builder | Build optimized prompts from repository context |
| Sprint 2 | Memory | Long-term conversation memory and project memory |
| Sprint 2 | Semantic Search | Vector-based code search and retrieval |
| Sprint 3 | DSPARK Integration | DSPARK framework integration for prompt engineering |
| Sprint 4 | Multi-model Routing | Route requests across multiple providers based on cost, latency, or quality |
| Future | Agent Orchestration | Coordinate multiple AI agents for complex tasks |
| Future | Prompt Optimization | Automatic prompt tuning and optimization |

### Architecture Components (Not Yet Implemented)

| Component | Status | Description |
|-----------|--------|-------------|
| Context Engine | Planned | Build optimized prompts, remove redundant context, compress history |
| Repository Intelligence | Planned | Symbol graph, dependency graph, code search, metadata extraction |
| Memory | Planned | Long-term conversation memory, project memory, user preferences |
| Metrics | Planned | Prometheus-compatible metrics (latency, tokens/sec, cache hits) |
| Authentication | Planned | API key authentication for gateway endpoints |

---

## Non-Goals

The platform is **not**:

- An LLM — it routes to existing models
- A training framework — it works with inference only
- A vector database — it may integrate with one in the future
- A Kubernetes platform — it runs anywhere Python runs
- A cloud service — it is self-hosted

---

## Definition of Done

A feature is complete only if:

- [x] Tests pass
- [x] Code is typed (mypy strict)
- [x] Code is documented (docstrings)
- [x] Code is benchmarked (where applicable)
- [x] Code is reviewed (peer review)

---

## Quick Start

```bash
# Install dependencies
uv sync

# Run linter
ruff check .

# Run type checker
mypy .

# Run tests
pytest

# Start the gateway
uvicorn apps.gateway.main:create_app --factory --reload
```

The gateway starts at `http://localhost:8000` (or `8001` for test configuration).
