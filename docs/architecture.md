# Local AI Platform Architecture

Version: 0.1
Status: Draft
License: Apache 2.0

---

# Vision

Local AI Platform is a self-hosted developer intelligence platform that improves coding agents through repository intelligence, context optimization, long-term memory and a unified inference gateway.

The platform is model agnostic, provider agnostic and agent agnostic.

---

# Design Principles

- Local First
- Production Ready
- Simple Before Smart
- Performance First
- Measurable Improvements
- Provider Agnostic
- Agent Agnostic
- Stateless Components Where Possible
- Composition Over Coupling

---

# Goals

## Current

- OpenAI compatible Gateway
- Multiple Provider Support
- Repository Intelligence
- Context Builder
- Serialization Layer
- Repository Index Service
- Configuration Management
- Structured Logging
- Request Processing Pipeline

## Future

- Memory
- Semantic Search
- Agent Orchestration
- Multi-model Routing
- Prompt Optimization
- DSPARK Integration
- Metrics (Prometheus)

---

# High Level Architecture

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
   Request Pipeline      Context Engine
        │
        ▼
  Provider Layer
        │
        ▼
  vLLM / OpenAI / Ollama / LM Studio
```

---

# Components

## Gateway

A FastAPI-based HTTP gateway that proxies requests to backend LLM providers.

**Responsibilities**

- REST API (health, version, chat completions)
- Request validation (Pydantic models)
- Streaming (SSE) and non-streaming responses
- Request tracing (X-Request-ID, X-Process-Time headers)
- Structured logging
- CORS configuration
- Error handling with appropriate HTTP status codes

**Endpoints**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/version` | Application metadata |
| POST | `/v1/chat/completions` | OpenAI-compatible chat completions |

**Contains no business logic.** All logic lives in packages.

---

## Provider Layer

A pluggable provider system that decouples the gateway from any specific LLM backend.

**Responsibilities**

- Abstract `Provider` interface (health, chat, models)
- Provider registry (register, create, lookup)
- Factory pattern for provider instantiation
- Exception hierarchy (authentication, connection, response errors)
- Auto-registration at import time

**Supported providers**

- vLLM (implemented)

**Future**

- OpenAI
- Ollama
- LM Studio
- llama.cpp
- TensorRT-LLM

---

## Request Processing Pipeline

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

**Built-in Stages:**

| Stage | Responsibility |
|-------|---------------|
| `ProviderStage` | Resolve provider, call `provider.chat()`, return response |
| `RepositoryContextStage` | Enrich request with repository context, serialize to ProviderRequest |

**Future Stages (planned):**

| Stage | Responsibility |
|-------|---------------|
| `AuthenticationStage` | Validate API keys, rate limiting |
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

- Pipeline owns exception translation — all exceptions are caught and converted to failed `PipelineStageResult`
- Gateway converts `PipelineError` → HTTP response with status code mapping:
  - `UnknownProviderError` → 501
  - `ProviderConnectionError` → 503
  - `ProviderAuthenticationError` → 502
  - `ProviderResponseError` → 502
  - Other `PipelineError` → 501

---

## Context Engine

**Responsibilities**

- Build optimized prompts
- Remove redundant context
- Compress history
- Assemble repository information

**Implemented: Context Builder**

The Context Builder assembles repository context by enumerating symbols from a `SymbolGraphView` and returning them in a deterministic order.

Pipeline: `ContextBuilder → RankingEngine → ContextBudget → ContextComposer → ContextPackage`

**Future features**

- Semantic search
- DSPARK integration
- Memory injection
- Git awareness

---

## Repository Intelligence

**Responsibilities**

- Repository scanning
- Symbol graph
- Index service
- Dependency graph (future)
- Code search (future)

**Implemented: Symbol Graph Foundation**

A language-independent representation of symbols and their relationships. The `SymbolGraphView` public API provides sorted, deterministic access to classes, functions, methods, and relationships. The `SymbolExtractor` ABC supports future language-specific extractors (Tree-sitter, Scala, Java, etc.).

**Implemented: Repository Index Service**

A service layer over the repository scanner that builds a structured index with symbol graph, relationships, and statistics.

See `docs/symbol-graph.md` for full documentation.

---

## Serialization Layer

**Responsibilities**

- Translate platform models (`ContextPackage`) into provider-specific request formats (`ProviderRequest`)
- Own formatting rules (ordering, system messages, context injection)
- Remain pure functions: deterministic, no side effects

**Architecture:**

```
ContextPackage (platform model)
       │
       ▼
  Serializer (provider-specific)
       │
       ▼
  ProviderRequest (provider payload)
       │
       ▼
  Provider (executes inference)
```

**Key constraints:**

- Providers never consume `ContextPackage` directly.
- Serializers never access repositories, the filesystem, or providers.
- `ProviderRequest` is the stable boundary between serialization and execution.
- The pipeline stores `ProviderRequest` in context metadata so the ProviderStage can consume it.

---

## Memory

**Responsibilities**

- Long-term conversation memory
- Project memory
- User preferences
- Repository knowledge

**Status:** Planned.

---

# Request Flow

```
Agent
  ↓
Gateway
  ↓
Pipeline (stages in order)
  ↓
Provider
  ↓
LLM
  ↓
Response
  ↓
Gateway
  ↓
Agent
```

Pipeline stages execute in order: `before()` → `execute()` → `after()`. Each stage receives a mutable context and returns a `PipelineStageResult`.

## Complete Request Lifecycle

```
Incoming Chat Completion Request
            │
            ▼
    Gateway (FastAPI)
            │
            ▼
    PipelineEngine.execute()
            │
            ├── RepositoryContextStage
            │       │
            │       ├── ContextBuilder    (enumerate & rank symbols)
            │       ├── RankingEngine     (score candidates)
            │       ├── ContextBudget     (estimate tokens)
            │       └── ContextComposer   (assemble package)
            │       │
            │       ▼
            │   ContextPackage
            │       │
            │       ▼
            │   OpenAISerializer
            │       │
            │       ▼
            │   ProviderRequest
            │       │
            │   stored in PipelineContext.metadata
            │
            ├── ProviderStage
            │       │
            │       ├── Read ProviderRequest from context
            │       ├── Convert to kwargs (ProviderRequest.to_dict())
            │       └── Call provider.chat(**kwargs)
            │
            ▼
    Provider (vLLM / OpenAI / etc.)
            │
            ▼
    LLM Inference
            │
            ▼
    Response (unchanged)
            │
            ▼
    Gateway → Agent
```

## Feature Flags

Repository Intelligence is controlled by environment variables:

| Variable | Default | Description |
|---|---|---|
| `APP_REPOSITORY_CONTEXT_ENABLED` | `true` | Enable/disable repository context |
| `REPOSITORY_CONTEXT_MAX_SYMBOLS` | `20` | Maximum symbols in context |
| `REPOSITORY_CONTEXT_MAX_MODULES` | `10` | Maximum modules in context |
| `REPOSITORY_CONTEXT_MAX_TOKENS` | `4096` | Maximum token budget |

When disabled, the `RepositoryContextStage` returns a no-op result and the pipeline continues directly to the `ProviderStage`.

## Logging

Structured logging includes:

- `request_id` — unique request identifier
- `provider` — provider name
- `model` — model identifier
- `repository_context_enabled` — feature flag state
- `selected_symbols` — count of selected symbols
- `selected_modules` — count of selected modules
- `estimated_tokens` — token budget estimate
- `serialization_duration_ms` — serialization time
- `provider_duration_ms` — provider execution time
- `total_duration_ms` — total pipeline time

**Never** log repository contents or source code.

## RepositoryContextStage

**Responsibility:** Assembles repository context for the request by orchestrating the Context Builder pipeline (Builder → Ranking → Budget → Composer), serializes the resulting `ContextPackage` into a `ProviderRequest`, and attaches both to the `PipelineContext`.

**Execution order:** Runs before `ProviderStage`. Never performs inference.

**Behavior:**

- If repository context is disabled (`context_enabled=False`), the stage returns a no-op result and the pipeline continues.
- On any exception, the stage logs the error, leaves `context_package` as `None`, and returns a successful result so the pipeline continues to the provider stage.
- Structured logging includes: `request_id`, `context_enabled`, `symbols_selected`, `modules_selected`, `estimated_tokens`, `duration_ms`.

**Constraints:**

- Must not call providers.
- Must not inspect provider configuration.
- Must not access Gateway internals.
- Serializes only into `ProviderRequest` — never raw JSON or HTTP payloads.
- Orchestrates existing Context components only.

---

# Package Structure

```
apps/
    gateway/                    # FastAPI gateway application
        main.py                 # App factory + lifespan
        middleware.py           # Request ID + timing middleware
        api/
            chat.py             # POST /v1/chat/completions
            health.py           # GET /health
            version.py          # GET /version
        core/
            config.py           # Pydantic Settings
            logging.py          # Structured logging setup

packages/
    providers/                  # Provider abstraction + vLLM impl
    repository/                 # Repository scanner + symbol graph
    context/                    # Context Builder
    serializers/                # Serialization Layer
    pipeline/                   # Request processing pipeline
    config/                     # YAML config loading
    core/                       # Core business logic
    telemetry/                  # Telemetry/monitoring

tests/
docs/
scripts/
```

Applications contain entry points only. Business logic belongs inside packages.

## Providers Package

```
packages/providers/
├── __init__.py                # Provider ABC, factory, registry, exception exports
├── base.py                    # Provider ABC (health, chat, models)
├── exceptions.py              # ProviderError hierarchy
├── factory.py                 # create_provider()
├── registry.py                # register() / get_registry()
└── vllm.py                    # VLLMProvider implementation
```

**Exception Hierarchy:**

```
ProviderError
├── UnknownProviderError       # Provider not registered
├── ProviderConnectionError    # Network timeout, connection refused
├── ProviderAuthenticationError # Invalid/expired API key (HTTP 401)
└── ProviderResponseError      # Non-2xx status, malformed response
```

**Auto-Registration:** Provider modules register themselves as a side effect of being imported. The gateway calls `_load_providers()` at startup to trigger all registrations.

## Pipeline Package

```
packages/pipeline/
├── __init__.py                # Public exports
├── base.py                    # PipelineStage ABC
├── context.py                 # PipelineContext (mutable shared state)
├── engine.py                  # PipelineEngine (orchestrates stages)
├── exceptions.py              # PipelineError hierarchy
├── request.py                 # PipelineRequest
├── response.py                # PipelineResponse
├── result.py                  # PipelineStageResult
└── stages/
    ├── __init__.py            # Stage exports
    ├── stages.py              # ProviderStage
    └── repository_context.py  # RepositoryContextStage
```

`PipelineStageResult` lives in its own module (`result.py`) to break the circular import between `response.py` and `context.py`.

## Repository Package

```
packages/repository/
├── models.py                  # SourceFile, Directory, LanguageSummary, Statistics, RepositoryIndex
├── scanner.py                 # scan() function
├── filters.py                 # gitignore + hardcoded ignores
├── index.py                   # Legacy helper functions
├── languages.py               # Extension → language mapping
├── index/                     # Repository index service
│   ├── __init__.py            # Package exports
│   ├── models.py              # RepositoryIndex, Module, Symbol, Relationship, Statistics
│   ├── builder.py             # IndexBuilder
│   └── helpers.py             # Index helper functions
└── symbols/                   # Symbol graph (language-independent)
    ├── __init__.py            # Package exports
    ├── models.py              # Symbol, SymbolGraph, Module, Relationship, SymbolType, RelationshipType, Language
    ├── extractor.py           # SymbolExtractor ABC
    ├── python_ast.py          # Python AST implementation
    └── graph.py               # SymbolGraphView public API
```

`SymbolGraphView` provides sorted, deterministic read-only access to the symbol graph. All public collections are sorted by `qualified_name`, then `lineno`.

## Context Package

```
packages/context/
├── __init__.py                # Package exports
├── builder.py                 # ContextBuilder (orchestrates build pipeline)
├── ranking.py                 # RankingEngine (scores candidates against query)
├── budget.py                  # ContextBudget (token estimation)
├── composer.py                # ContextComposer (assembles ContextPackage)
├── models.py                  # ContextCandidate, ContextResult, ContextBudgetResult
├── package.py                 # ContextPackage
├── query.py                   # ContextQuery
└── scoring.py                 # ScoringRules
```

The Context Builder assembles repository context by enumerating symbols, ranking them against a query, estimating token budget, and composing the final `ContextPackage`.

## Serialization Package

```
packages/serializers/
├── __init__.py                # Package exports
├── base.py                    # ProviderSerializer ABC
├── factory.py                 # SerializerFactory
├── registry.py                # SerializerRegistry
├── models.py                  # ProviderRequest
├── types.py                   # ProviderType enum
├── exceptions.py              # UnknownSerializerError
└── openai.py                  # OpenAISerializer
```

The Serialization Layer translates platform models (`ContextPackage`) into provider-specific request formats (`ProviderRequest`). Serializers are registered by provider type and created via a factory pattern.

## Config Package

```
packages/config/
├── __init__.py                # load_config, get_env_or_config
```

Provides utilities for loading YAML configuration files from multiple search paths and resolving environment variable overrides.

## Core Package

```
packages/core/
├── __init__.py                # Core business logic
```

Holds core business logic for the platform.

## Telemetry Package

```
packages/telemetry/
├── __init__.py                # Telemetry/monitoring
```

Handles telemetry and monitoring for the platform.

---

# Dependency Rules

Allowed:

```
Gateway → Packages → Providers
```

Forbidden:

- Providers importing Gateway
- Applications importing Applications
- Circular imports

---

# Configuration

Environment variables only.

Configuration is loaded through Pydantic Settings.

**Key variables:**

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `local-ai-platform` | Application name |
| `APP_LOG_LEVEL` | `INFO` | Logging level |
| `APP_CORS_ORIGINS` | `["*"]` | CORS allowed origins |
| `APP_DEFAULT_PROVIDER` | `vllm` | Default provider name |
| `APP_REPOSITORY_CONTEXT_ENABLED` | `true` | Enable repository intelligence |
| `REPOSITORY_CONTEXT_MAX_SYMBOLS` | `20` | Maximum symbols in context |
| `REPOSITORY_CONTEXT_MAX_MODULES` | `10` | Maximum modules in context |
| `REPOSITORY_CONTEXT_MAX_TOKENS` | `4096` | Maximum token budget |
| `VLLM_BASE_URL` | `http://localhost:8000/v1` | vLLM server URL |
| `VLLM_API_KEY` | `empty` | vLLM API key |
| `REQUEST_TIMEOUT` | `60.0` | Request timeout in seconds |
| `DEFAULT_MODEL` | `default-model` | Default model identifier |

---

# Logging

Structured logging.

Every request includes:

- request_id
- duration
- provider
- model

---

# Metrics

Prometheus compatible.

Future metrics include:

- latency
- tokens/sec
- cache hits
- context size
- provider health

---

# Testing Strategy

- Unit tests — all isolated from network calls (autouse fixture blocks `httpx.AsyncClient.send`)
- Integration tests — under `tests/integration/`, exempt from network guard
- Gateway tests — use stub pipelines, never touch real providers
- Provider tests — use mocked httpx client
- Symbol Graph tests — 82 tests covering extractor, API, and integration
- Benchmark tests — performance regression tests

Network isolation: `tests/conftest.py` contains an autouse fixture that raises `AssertionError` if any non-integration test attempts to open an HTTP connection.

---

# Roadmap

### Completed (Sprint 0)

- Project bootstrap (uv, ruff, mypy, pytest, Docker Compose, GitHub Actions)
- FastAPI gateway with health, version, and chat endpoints
- Provider abstraction layer (ABC, registry, factory, exceptions)
- vLLM provider implementation (streaming, health, models, chat)
- Repository scanner (directory walking, language detection, gitignore)
- Symbol Graph Foundation — language-independent symbol representation, Python AST extractor
- Configuration management (YAML + env var override)
- Structured logging with request tracing
- Request processing pipeline (stages, engine, context, ProviderStage)
- Network isolation — unit tests cannot make real network calls
- Repository Context Stage — orchestrates context → serialize → provider
- Context Builder — ranking engine, budget estimation, context composer
- Serialization Layer — OpenAI serializer, factory, registry
- Repository Index Service — builder, helpers, models
- Repository Intelligence integration tests

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

---

# Non Goals

The platform is not:

- an LLM — it routes to existing models
- a training framework — it works with inference only
- a vector database — it may integrate with one in the future
- a Kubernetes platform — it runs anywhere Python runs
- a cloud service — it is self-hosted

---

# Definition of Done

A feature is complete only if:

- tests pass
- typed (mypy strict)
- documented (docstrings)
- benchmarked (where applicable)
- reviewed (peer review)

---

# Architecture Decision Record

Major architectural decisions are recorded in `/docs/adr`.

This document describes the current architecture.

ADRs explain why decisions were made.
