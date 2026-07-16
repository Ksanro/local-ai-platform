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
- Long-term Memory
- Metrics
- Benchmarks

## Future

- DSPARK Integration
- Semantic Retrieval
- Agent Orchestration
- Multi-model Routing
- Prompt Optimization

---

# High Level Architecture

```
                VS Code

                   │

          Cline / Claude Code

                   │

        Local AI Platform Gateway

                   │

        ┌──────────┴──────────┐

        │                     │

 Context Engine        Provider Layer

        │                     │

 Repository        vLLM / Ollama / OpenAI

        │

     Memory
```

---

# Components

## Gateway

Responsibilities

- REST API
- Authentication
- Validation
- Streaming
- Metrics
- Logging

Contains no business logic.

---

## Provider Layer

Responsibilities

- Unified inference interface
- Provider registration
- Health checks
- Model discovery
- Request forwarding

Supported providers

- vLLM
- OpenAI
- Ollama
- LM Studio

Future

- llama.cpp
- TensorRT-LLM

---

## Context Engine

Responsibilities

- Build optimized prompts
- Remove redundant context
- Compress history
- Assemble repository information

Future feature.

---

## Repository Intelligence

Responsibilities

- Repository indexing
- Symbol graph
- Dependency graph
- Code search
- Metadata extraction

**Implemented: Symbol Graph Foundation**

A language-independent representation of symbols and their relationships.
The `SymbolGraphView` public API provides sorted, deterministic access to
classes, functions, methods, and relationships. The `SymbolExtractor` ABC
supports future language-specific extractors (Tree-sitter, Scala, Java, etc.).

See `docs/symbol-graph.md` for full documentation.

---

## Memory

Responsibilities

- Long-term conversation memory
- Project memory
- User preferences
- Repository knowledge

Future feature.

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

Current

```
Agent

↓

Gateway

↓

RepositoryContextStage

↓

ProviderStage

↓

LLM
```

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

## Serialization Boundary

The Serialization Layer sits between Repository Intelligence and the
Provider layer:

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
- The pipeline stores `ProviderRequest` in context metadata so the
  ProviderStage can consume it.

## Feature Flags

Repository Intelligence is controlled by environment variables:

| Variable | Default | Description |
|---|---|---|
| `APP_REPOSITORY_CONTEXT_ENABLED` | `true` | Enable/disable repository context |
| `REPOSITORY_CONTEXT_MAX_SYMBOLS` | `20` | Maximum symbols in context |
| `REPOSITORY_CONTEXT_MAX_MODULES` | `10` | Maximum modules in context |
| `REPOSITORY_CONTEXT_MAX_TOKENS` | `4096` | Maximum token budget |

When disabled, the `RepositoryContextStage` returns a no-op result and
the pipeline continues directly to the `ProviderStage`.

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
- Serializes only into ``ProviderRequest`` — never raw JSON or HTTP payloads.
- Orchestrates existing Context components only.

Future

```
Agent

↓

Gateway

↓

AuthenticationStage

↓

RepositoryContextStage

↓

MemoryStage

↓

ProviderStage

↓

LLM
```

---

# Package Structure

```
apps/

packages/

tests/

docs/
```

Applications contain entry points only.

Business logic belongs inside packages.

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
├── stages.py                  # ProviderStage (built-in)
└── stages/
    └── repository_context.py  # RepositoryContextStage
```

`PipelineStageResult` lives in its own module (`result.py`) to break the circular import between `response.py` and `context.py`.

## Repository Package

```
packages/repository/
├── models.py               # SourceFile, Directory, LanguageSummary, Statistics, RepositoryIndex
├── scanner.py              # scan() function
├── filters.py              # gitignore + hardcoded ignores
├── index.py                # Helper functions (get_file, find_extension, find_language, summary)
└── languages.py            # Extension → language mapping

packages/repository/symbols/
├── __init__.py             # Package exports
├── models.py               # Symbol, SymbolGraph, Module, Relationship, SymbolType, RelationshipType, Language
├── extractor.py            # SymbolExtractor ABC
├── python_ast.py           # Python AST implementation
└── graph.py                # SymbolGraphView public API
```

`SymbolGraphView` provides sorted, deterministic read-only access to the symbol graph. All public collections are sorted by `qualified_name`, then `lineno`.

---

# Dependency Rules

Allowed

Gateway

↓

Packages

↓

Providers

Forbidden

Providers importing Gateway

Applications importing Applications

Circular imports

---

# Configuration

Environment variables only.

Configuration is loaded through Pydantic Settings.

---

# Logging

Structured logging.

Every request includes

- request_id
- duration
- provider
- model

---

# Metrics

Prometheus compatible.

Future metrics include

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

Sprint 0

- Bootstrap
- Gateway
- Provider

Sprint 1

- Repository Indexer
- Context Builder

Sprint 2

- Memory
- Semantic Search

Sprint 3

- DSPARK

Sprint 4

- Multi-model Routing

---

# Non Goals

The platform is not

- an LLM
- a training framework
- a vector database
- a Kubernetes platform
- a cloud service

---

# Definition of Done

A feature is complete only if

- tests pass
- typed
- documented
- benchmarked
- reviewed

---

# Architecture Decision Record

Major architectural decisions are recorded in `/docs/adr`.

This document describes the current architecture.

ADRs explain why decisions were made.
