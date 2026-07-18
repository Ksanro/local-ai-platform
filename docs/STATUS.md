# Local AI Platform — Status & Architecture

**Version:** 0.1.0
**License:** Apache 2.0
**Python:** 3.12+
**Last Updated:** 2026-07-18
**Latest Commit:** Change Impact Analyzer, Relationship Extraction, Planner Rules, Scoring Rules

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
   Request Pipeline      Context Engine
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
- **Error handling** — 501 for missing providers, 502 for provider errors, 503 for connection failures, 401 for auth failures
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

**Gateway Status Code Mapping:**

| Exception | HTTP Status |
|-----------|-------------|
| `UnknownProviderError` | 501 |
| `ProviderConnectionError` | 503 |
| `ProviderAuthenticationError` | 502 |
| `ProviderResponseError` | 502 |
| Other `PipelineError` | 501 |
| No exception (success) | 200 |

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

- Pipeline owns exception translation — all exceptions (including raised exceptions) are caught and converted to failed `PipelineStageResult`
- Gateway converts `PipelineError` → HTTP response with status code mapping:
  - `UnknownProviderError` → 501
  - `ProviderConnectionError` → 503
  - `ProviderAuthenticationError` → 502
  - `ProviderResponseError` → 502
  - Other `PipelineError` → 501
- Stage errors include stage name and original exception
- A stage that raises an exception yields `PipelineResponse.success=False` with `response.exception` set to the original exception (not wrapped in `StageError`)

**Logging:**

- Per-stage: `stage`, `duration`, `request_id`
- Per-request: `provider`, `model`, `status`

### 5. Repository Scanner

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

### 6. Symbol Graph

A language-independent representation of symbols and their relationships
extracted from source code. Provides the foundation for repository
intelligence — future features (Context Builder, Semantic Search,
Prompt Optimization) consume the symbol graph to understand code
structure.

**Architecture:**

```
Python AST
        │
        ▼
SymbolExtractor  (abstract interface)
        │
        ▼
SymbolGraph      (immutable data model)
```

The public API never exposes Python AST nodes. AST is strictly an
implementation detail of language-specific extractors.

**Data Model:**

| Model | Description |
|-------|-------------|
| `Language` | Programming language identifier (currently `PYTHON`) |
| `Symbol` | A single symbol (class, function, method) with `id`, `name`, `qualified_name`, `symbol_type`, `module`, `lineno`, `decorators` |
| `SymbolType` | `MODULE`, `CLASS`, `FUNCTION`, `METHOD` |
| `Relationship` | Directed relationship between two symbols (`source`, `target`, `type`) |
| `RelationshipType` | `DEFINES` (containment), `IMPORTS`, `INHERITS`, `CALLS` (reserved) |
| `Module` | All symbols and relationships in a single source file |
| `SymbolGraph` | Complete graph for a repository (dict of modules) |

**Public API (`SymbolGraphView`):**

| Method | Returns | Description |
|--------|---------|-------------|
| `modules()` | `Sequence[Module]` | All modules, sorted by path |
| `module(path)` | `Module \| None` | Module by path |
| `classes()` | `Sequence[Symbol]` | All CLASS symbols, sorted |
| `functions()` | `Sequence[Symbol]` | All FUNCTION symbols, sorted |
| `methods()` | `Sequence[Symbol]` | All METHOD symbols, sorted |
| `symbols()` | `Sequence[Symbol]` | All symbols, sorted |
| `find(name)` | `Sequence[Symbol]` | Match against `name` or `qualified_name` |
| `children(symbol)` | `Sequence[Symbol]` | Direct children via DEFINES only |
| `parents(symbol)` | `Sequence[Symbol]` | Direct parents via DEFINES only |
| `imports(module)` | `Sequence[str]` | Raw import text for a module |

**Rules:**

- `find()` always returns a list (never `None`)
- Matching is performed against both `name` and `qualified_name`
- Only `DEFINES` relationships are traversed by `children()` and `parents()`
- All public collections are sorted deterministically by `qualified_name`, then `lineno`

**Python AST Extractor:**

Extracts from Python source using the standard library `ast` module:

- Modules (by file stem)
- Classes and their nested definitions
- Functions and methods (nested functions classified as `FUNCTION`, not `METHOD`)
- Inheritance relationships
- Decorators (simple names, attribute access, call syntax)
- Imports (stored as raw text, no resolution)

**Classification Rules:**

- `def` directly inside a class → `METHOD`
- nested `def` (not inside a class) → `FUNCTION`
- nested `class` → `CLASS`
- `async def` follows the same rule as `def`
- decorators never change `SymbolType`

**Known Limitations:**

1. No call resolution — CALLS relationships are not populated
2. No import resolution — imports stored as raw text
3. No type inference — parameter and return types not extracted
4. No control-flow analysis — only syntactic structure captured
5. Python only — the interface supports future extractors (Tree-sitter, etc.)

**Tests:** 82 tests (45 extractor + 32 API + 8 integration + 7 smoke)

### 7. Context Builder

Assembles repository context for future coding agents by enumerating symbols
from a `SymbolGraphView` and returning them in a deterministic order.

**Architecture:**

```
Repository
      │
      ▼
ContextBuilder
      │
      ▼
RankingEngine
      │
      ▼
ContextBudget
      │
      ▼
ContextResult
      │
      ▼
ContextComposer
      │
      ▼
ContextPackage
      │
      ▼
Provider
```

The Builder depends only on the public `SymbolGraphView` API.  It never
accesses the filesystem, parses source code, or touches AST objects.

**Components:**

| Component | File | Purpose |
|-----------|------|---------|
| `ContextBuilder` | `builder.py` | Orchestrates the full build pipeline |
| `RankingEngine` | `ranking.py` | Scores candidates against query text |
| `ContextBudget` | `budget.py` | Estimates token budget for context |
| `ContextComposer` | `composer.py` | Assembles ranked result into `ContextPackage` |
| `ContextQuery` | `query.py` | Query parameters (text, limits) |
| `ContextCandidate` | `models.py` | Individual symbol candidate with score |
| `ContextResult` | `models.py` | Final assembled context |
| `ScoringRules` | `scoring.py` | Additive scoring rules for ranking |

**Ranking Engine:**

Scores candidates against query text using additive rules:

| Rule | Score |
|------|------:|
| Exact symbol name match | +100 |
| Exact qualified name match | +90 |
| Partial symbol name match | +50 |
| Module name contains query token | +30 |
| Matching query token | +10 per token |
| Public symbol (name does not start with "_") | +5 |

**Budget Estimation:**

```
estimated_tokens = symbols * 80 + modules * 150
```

**Context Package:**

| Field | Type | Description |
|-------|------|-------------|
| `query` | `str` | The original user query |
| `modules` | `list[str]` | Ordered list of unique module names |
| `symbols` | `list[str]` | Ordered list of unique symbol qualified names |
| `metadata` | `dict[str, Any]` | Budget metadata |

### 8. Serialization Layer

Translates platform models into provider-specific request formats.

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

**OpenAI Serializer:**

Converts platform models into OpenAI Chat Completions format:

- System message describes the platform's role.
- Repository context includes symbols and modules.
- User messages are copied unchanged.
- Deterministic: identical input always produces identical output.

**Factory & Registry:**

- `SerializerFactory.create(ProviderType)` — creates a serializer by type
- `SerializerRegistry` — maintains global mapping of provider types to serializer classes
- Auto-registration at import time
- `register()`, `get_registry()`, `has_serializer()`, `unregister()`

**Adding a New Serializer:**

1. Create a new serializer class inheriting from `ProviderSerializer`.
2. Implement `provider` property and `_serialize()` method.
3. Register at import time: `register(ProviderType.new_type, NewSerializer)`.

No changes to Context Builder, Repository Intelligence, or Providers required.

### 9. Repository Index Service

A service layer over the repository scanner that builds a structured index
with symbol graph, relationships, and statistics.

**Components:**

| Component | File | Purpose |
|-----------|------|---------|
| `RepositoryIndex` | `models.py` | Complete index with modules, symbols, relationships, statistics |
| `IndexBuilder` | `builder.py` | Builds the index from scanned files |
| `IndexHelpers` | `helpers.py` | Helper functions for index queries |

**Data Model:**

| Model | Description |
|-------|-------------|
| `RepositoryIndex` | Complete index (modules, symbols, relationships, statistics) |
| `Module` | All symbols and relationships in a single source file |
| `Symbol` | A single symbol with metadata |
| `Relationship` | Directed relationship between symbols |
| `RepositoryStatistics` | Aggregate statistics (module count, symbol counts, etc.) |

**Index Builder:**

- Takes a `SymbolGraph` and produces a `RepositoryIndex`
- Builds modules, symbols, relationships, and statistics
- Deterministic output — same input always produces same output

### 10. Repository Context Stage

Orchestrates the full repository intelligence pipeline within the request processing pipeline.

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

### 11. Configuration Management

**YAML Config Loading (`packages/config`):**

- Searches multiple directories for `config.yaml`
- Environment variables take precedence over file values
- Type-aware resolution (float, int, bool, string)

**Pydantic Settings (`apps.gateway.core.config`):**

- `APP_`-prefixed environment variables
- `lru_cache` singleton pattern for settings instance
- Configurable: `app_name`, `log_level`, `cors_origins`, `default_provider`

### 12. Structured Logging

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

### Repository Index Package (`packages.repository.index`)

```python
from packages.repository.index import (
    RepositoryIndex,           # Complete index with modules, symbols, relationships
    Module,                    # All symbols in a source file
    Symbol,                    # A single symbol
    Relationship,              # Directed relationship between symbols
    RepositoryStatistics,      # Aggregate statistics
    IndexBuilder,              # Build index from symbol graph
    get_file,                  # Look up file by path
    find_extension,            # Find files by extension
    find_language,             # Find files by language
    summary,                   # Human-readable summary
)
```

### Symbol Graph Package (`packages.repository.symbols`)

```python
from packages.repository.symbols import (
    SymbolGraphView,           # Read-only view over SymbolGraph
    Symbol,                    # A single symbol (class, function, method)
    SymbolType,                # MODULE, CLASS, FUNCTION, METHOD
    Relationship,              # Directed relationship between symbols
    RelationshipType,          # DEFINES, IMPORTS, INHERITS, CALLS
    Module,                    # All symbols in a source file
    SymbolGraph,               # Complete graph for a repository
    SymbolExtractor,           # Abstract extractor interface
    Language,                  # Programming language identifier
    PythonAstExtractor,        # Python AST implementation
)
```

**Module Layout:**

| Module | Contents |
|--------|----------|
| `models.py` | `Symbol`, `SymbolGraph`, `Module`, `Relationship`, `SymbolType`, `RelationshipType`, `Language` |
| `extractor.py` | `SymbolExtractor` ABC (`language`, `extract(path)`) |
| `python_ast.py` | `PythonAstExtractor` — AST-based implementation |
| `graph.py` | `SymbolGraphView` — sorted, deterministic public API |

### Context Package (`packages.context`)

```python
from packages.context import (
    ContextBuilder,            # Assemble repository context
    ContextComposer,           # Assemble result into ContextPackage
    ContextBudget,             # Estimate token budget
    RankingEngine,             # Score candidates against query
    ContextQuery,              # Query parameters
    ContextCandidate,          # Ranked symbol candidate
    ContextResult,             # Assembled context result
    ContextPackage,            # Final context package
    ContextBudgetResult,       # Budget estimate
    RankingReason,             # Explainability signal
)
```

### Serialization Package (`packages.serializers`)

```python
from packages.serializers import (
    SerializerFactory,         # Create serializer by type
    register,                  # Register a serializer class
    get_registry,              # Get registry copy
    has_serializer,            # Check if registered
    unregister,                # Remove a serializer
    ProviderSerializer,        # Abstract serializer base class
    ProviderRequest,           # Provider-specific request payload
    ProviderType,              # Provider type enum
    UnknownSerializerError,    # Serializer not registered
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
    PipelineStageResult,       # Per-stage result (from result.py)
    PipelineStage,             # Abstract base class
    PipelineError,             # Base exception
    StageError,                # Stage failure
    PipelineExecutionError,    # Execution failure
)
from packages.pipeline.stages import (
    ProviderStage,             # Built-in provider stage
    RepositoryContextStage,    # Repository context stage
)
```

**Module Layout:**

| Module | Contents |
|--------|----------|
| `result.py` | `PipelineStageResult` dataclass (success, data, error, exception, duration) |
| `response.py` | `PipelineResponse` class (wraps final response with all stage results) |
| `context.py` | `PipelineContext` class (mutable shared state across stages) |
| `engine.py` | `PipelineEngine` class (orchestrates stage execution) |
| `base.py` | `PipelineStage` ABC (before, execute, after hooks) |
| `stages.py` | `ProviderStage` (resolves provider, calls `chat()`) |
| `stages/repository_context.py` | `RepositoryContextStage` (orchestrates context → serialize → provider) |
| `exceptions.py` | `PipelineError`, `StageError`, `PipelineExecutionError` |
| `request.py` | `PipelineRequest` dataclass |

### Impact Package (`packages.repository.impact`)

```python
from packages.repository.impact import (
    ChangeImpactAnalyzer,        # Analyze impact of symbol changes
    ImpactNode,                  # Single impacted symbol node
    ImpactReport,                # Complete impact analysis report
)
```

### Relationship Package (`packages.repository.relationships`)

```python
from packages.repository.relationships import (
    RelationshipExtractor,       # Abstract base class
    RelationshipRegistry,        # Registry of extractors
)
from packages.repository.relationships.call_extractor import (
    CallExtractor,               # CALLS relationship extractor
)
```

### Planning Package (`packages.planning`)

```python
from packages.planning import (
    ContextPlanner,              # Intent detection + planning
    ContextPlan,                 # Immutable planning result
    Intent,                      # Intent enum
)
from packages.planning.rules import (
    PlanningRule,                # Deterministic planning rule
    RuleEngine,                  # Rule evaluation engine
    BUILTIN_RULES,               # Built-in planning rules
)
```

### Benchmark Package (`packages.benchmark`)

```python
from packages.benchmark import (
    BenchmarkRunner,             # Run benchmarks
    BenchmarkCase,               # Single benchmark case
    BenchmarkResult,             # Per-case result
    BenchmarkReport,             # Aggregate report
    BenchmarkEngine,             # Pipeline execution engine
)
```

### Context Scoring Package (`packages.context`)

```python
from packages.context.scoring import (
    score_candidate,             # Lexical scoring
    score_relationship,          # Relationship scoring
    RankingReason,               # Explainability signals
    normalise_query_text,        # Query normalisation
    WEIGHT_EXACT_MATCH,          # Scoring constants
    WEIGHT_DIRECT_CALLER,
    WEIGHT_DIRECT_CALLEE,
    WEIGHT_SHARED_MODULE,
    WEIGHT_SHARED_CLASS,
    WEIGHT_SHARED_PARENT,
    WEIGHT_TOKEN_OVERLAP,
    WEIGHT_PUBLIC_SYMBOL,
    WEIGHT_MODULE,
    WEIGHT_QUALIFIED_NAME,
)
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
│   ├── repository/                 # Repository scanner + symbol graph
│   │   ├── models.py               # Dataclasses (SourceFile, Directory, etc.)
│   │   ├── scanner.py              # scan() function
│   │   ├── filters.py              # gitignore + hardcoded ignores
│   │   ├── index.py                # Legacy helper functions
│   │   ├── languages.py            # Extension → language mapping
│   │   │
│   │   ├── index/                  # Repository index service
│   │   │   ├── __init__.py         # Package exports
│   │   │   ├── models.py           # RepositoryIndex, Module, Symbol, etc.
│   │   │   ├── builder.py          # IndexBuilder
│   │   │   └── helpers.py          # Index helper functions
│   │   │
│   │   ├── symbols/                # Symbol graph (language-independent)
│   │   │   ├── __init__.py         # Package exports
│   │   │   ├── models.py           # Symbol, SymbolGraph, Module, etc.
│   │   │   ├── extractor.py        # SymbolExtractor ABC
│   │   │   ├── python_ast.py       # Python AST implementation
│   │   │   └── graph.py            # SymbolGraphView public API
│   │   │
│   │   ├── relationships/          # Relationship extraction
│   │   │   ├── __init__.py         # Package exports
│   │   │   ├── base.py             # RelationshipExtractor ABC
│   │   │   ├── registry.py         # RelationshipRegistry
│   │   │   └── call_extractor.py   # CallExtractor (CALLS)
│   │   │
│   │   ├── dependencies/           # Workspace dependency graph
│   │   │   ├── __init__.py         # Package exports
│   │   │   ├── models.py           # NodeType, GraphEdgeType, GraphNode, GraphEdge
│   │   │   ├── graph.py            # WorkspaceDependencyGraph
│   │   │   └── builder.py          # DependencyGraphBuilder
│   │   │
│   │   ├── diagnostics/            # Repository diagnostics
│   │   │   ├── __init__.py         # Package exports
│   │   │   ├── engine.py           # DiagnosticsEngine
│   │   │   ├── models.py           # RepositoryDiagnostics, analyser models
│   │   │   └── analyzers/          # Individual analyzers
│   │   │       ├── base.py         # DiagnosticsAnalyzer ABC
│   │   │       ├── dead_code.py    # DeadCodeAnalyzer
│   │   │       ├── large_module.py # LargeModuleAnalyzer
│   │   │       ├── orphan.py       # OrphanAnalyzer
│   │   │       ├── module_stats.py # ModuleStatisticsAnalyzer
│   │   │       └── graph_stats.py  # GraphStatisticsAnalyzer
│   │   │
│   │   ├── impact/                 # Change impact analysis
│   │   │   ├── __init__.py         # Package exports
│   │   │   ├── analyzer.py         # ChangeImpactAnalyzer
│   │   │   └── models.py           # ImpactNode, ImpactReport
│   │
│   ├── context/                    # Context Builder
│   │   ├── __init__.py             # Package exports
│   │   ├── builder.py              # ContextBuilder (orchestrates build)
│   │   ├── ranking.py              # RankingEngine (scores candidates)
│   │   ├── budget.py               # ContextBudget (token estimation)
│   │   ├── composer.py             # ContextComposer (assembles package)
│   │   ├── models.py               # ContextCandidate, ContextResult, etc.
│   │   ├── package.py              # ContextPackage
│   │   ├── query.py                # ContextQuery
│   │   └── scoring.py              # ScoringRules, RankingReason, weights
│   │
│   ├── capabilities/               # Developer-facing capability framework
│   │   ├── __init__.py             # Package exports
│   │   ├── base.py                 # Capability ABC, PlannerIntent
│   │   ├── models.py               # CapabilityResult, RetrievalProfile
│   │   ├── registry.py             # CapabilityRegistry
│   │   ├── factory.py              # CapabilityFactory
│   │   ├── explain.py              # ExplainCapability
│   │   ├── debug.py                # DebugCapability
│   │   └── refactor.py             # RefactorCapability
│   │
│   ├── planning/                   # Context Planning Engine
│   │   ├── __init__.py             # Package exports
│   │   ├── plan.py                 # ContextPlan model
│   │   ├── intent.py               # Intent enum + detection
│   │   ├── rules.py                # PlanningRule, RuleEngine, BUILTIN_RULES
│   │   └── planner.py              # ContextPlanner
│   │
│   ├── benchmark/                  # Deterministic pipeline benchmarking
│   │   ├── __init__.py             # Package exports
│   │   ├── models.py               # BenchmarkCase, BenchmarkResult, BenchmarkReport
│   │   ├── metrics.py              # Scoring functions
│   │   ├── engine.py               # Pipeline execution engine
│   │   └── runner.py               # Public API
│   │
│   ├── serializers/                # Serialization Layer
│   │   ├── __init__.py             # Package exports
│   │   ├── base.py                 # ProviderSerializer ABC
│   │   ├── factory.py              # SerializerFactory
│   │   ├── registry.py             # SerializerRegistry
│   │   ├── models.py               # ProviderRequest
│   │   ├── types.py                # ProviderType enum
│   │   ├── exceptions.py           # UnknownSerializerError
│   │   └── openai.py               # OpenAISerializer
│   │
│   ├── pipeline/                   # Request processing pipeline
│   │   ├── __init__.py             # Exports
│   │   ├── base.py                 # PipelineStage ABC
│   │   ├── context.py              # PipelineContext
│   │   ├── engine.py               # PipelineEngine
│   │   ├── exceptions.py           # PipelineError hierarchy
│   │   ├── request.py              # PipelineRequest
│   │   ├── response.py             # PipelineResponse
│   │   ├── result.py               # PipelineStageResult
│   │   ├── stages.py               # ProviderStage
│   │   └── stages/
│   │       ├── __init__.py         # Stage exports
│   │       ├── stages.py           # ProviderStage
│   │       └── repository_context.py # RepositoryContextStage
│   │
│   ├── config/                     # YAML config loading
│   │   ├── __init__.py             # load_config, get_env_or_config
│   │   └── config.yaml             # Default configuration
│   │
│   ├── core/                       # Core business logic
│   └── telemetry/                  # Telemetry/monitoring
│
├── tests/                          # Test suite
│   ├── conftest.py                 # Shared fixtures
│   ├── context/                    # Context Builder tests
│   ├── gateway/                    # Gateway unit tests
│   ├── integration/                # E2E integration tests
│   ├── pipeline/                   # Pipeline unit tests
│   ├── providers/                  # Provider unit tests
│   ├── repository/                 # Scanner unit tests
│   │   └── index/                  # Repository index tests
│   ├── serializers/                # Serialization tests
│   └── repository/symbols/         # Symbol graph tests
│
├── scripts/
│   └── test_gateway.py             # Smoke test script
│
├── docs/
│   ├── STATUS.md                   # Status & architecture overview (main)
│   ├── architecture.md             # Architecture documentation
│   ├── capabilities.md             # Capability framework documentation
│   ├── context-builder.md          # Context Builder documentation
│   ├── context-package.md          # Context Package v2 documentation
│   ├── context-planning.md         # Context Planning Engine documentation
│   ├── benchmark-framework.md      # Benchmark Framework documentation
│   ├── relationship-ranking.md     # Relationship-aware ranking documentation
│   ├── relationship-extraction.md  # Relationship extraction documentation
│   ├── repository-diagnostics.md   # Repository diagnostics documentation
│   ├── planner-rules.md            # Planning rules documentation
│   ├── scoring-rules.md            # Scoring rules documentation
│   ├── serialization.md            # Serialization Layer documentation
│   ├── symbol-graph.md             # Symbol Graph documentation
│   ├── workspace-dependency-graph.md # Workspace dependency graph documentation
│   ├── change-impact.md            # Change impact analysis documentation
│   └── index.md                    # Documentation index
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
| Gateway | 11 | Health, version, chat (all stubbed — no network calls) |
| Pipeline | 62 | Engine, stages, ordering, context, ProviderStage, RepositoryContextStage, exception handling, HTTP status mapping |
| Providers | 31 | Factory, registry, vLLM provider (health, models, chat, streaming, config) |
| Repository | 176 | Scanner (20+), filters, language detection, statistics, index service, symbol graph (82) |
| Context | 118 | Builder integration, ranking engine, budget estimation, composer, scoring rules |
| Serializers | 37 | Factory, registry, OpenAI serializer, edge cases, determinism |
| Integration | 31 | E2E gateway → vLLM (3), repository intelligence pipeline (23), symbol graph integration (8) |
| Planning | 24 | Intent detection, planning rules, context planner, planning stage |
| Capabilities | 30 | Explain, debug, refactor capabilities, registry, factory, profiles |
| Benchmark | 18 | Engine, metrics, runner, scoring, golden snapshots |
| Impact | 57 | Direct impact, transitive impact, confidence, max depth, edge cases, test discovery |
| Relationships | 20 | Extractor base, registry, call extractor |
| Dependencies | 15 | Graph construction, traversal, determinism, hash stability |
| Diagnostics | 25 | Engine, analyzers, statistics, deterministic ordering |

**Total: 966 tests**

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

# Context tests only
pytest tests/context/

# Serializer tests only
pytest tests/serializers/

# Integration tests (requires running vLLM + gateway)
VLLM_BASE_URL=http://localhost:8000/v1 pytest tests/integration/

# Smoke test
python scripts/test_gateway.py
```

### Network Guard

All unit tests are isolated from network calls via an autouse fixture in `tests/conftest.py` that monkeypatches `httpx.AsyncClient.send` to raise `AssertionError` if any non-integration test attempts to open an HTTP connection. Integration tests under `tests/integration/` are exempt.

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
| `APP_REPOSITORY_CONTEXT_ENABLED` | `true` | Enable repository intelligence |
| `REPOSITORY_CONTEXT_MAX_SYMBOLS` | `20` | Maximum symbols in context |
| `REPOSITORY_CONTEXT_MAX_MODULES` | `10` | Maximum modules in context |
| `REPOSITORY_CONTEXT_MAX_TOKENS` | `4096` | Maximum token budget |
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
- [x] Symbol Graph Foundation — language-independent symbol representation, Python AST extractor, 82 tests
- [x] Configuration management (YAML + env var override)
- [x] Structured logging with request tracing
- [x] Smoke test and integration test scripts
- [x] Request processing pipeline (stages, engine, context, ProviderStage)
- [x] Unified pipeline failure path — all exceptions caught and converted to failed results
- [x] Network isolation — unit tests cannot make real network calls
- [x] Circular import fix — `PipelineStageResult` extracted to dedicated module
- [x] Repository Context Stage — orchestrates context → serialize → provider
- [x] Context Builder — ranking engine, budget estimation, context composer
- [x] Serialization Layer — OpenAI serializer, factory, registry
- [x] Repository Index Service — builder, helpers, models
- [x] Repository Intelligence integration tests — 23 tests covering full pipeline
- [x] Change Impact Analyzer — deterministic impact analysis with confidence scoring, BFS traversal, max_depth, test discovery
- [x] Relationship Extraction — language-independent extractors (CallExtractor), registry pattern, pluggable architecture
- [x] Planner Rules — PlanningRule dataclass, RuleEngine with deterministic rule evaluation, BUILTIN_RULES
- [x] Scoring Rules — RankingReason enum, score_candidate(), score_relationship(), normalise_query_text(), additive scoring model
- [x] Workspace Dependency Graph — immutable graph from RepositoryIndex with deterministic traversal, BFS, cycle prevention
- [x] Repository Diagnostics Engine — DeadCodeAnalyzer, LargeModuleAnalyzer, OrphanAnalyzer, ModuleStatisticsAnalyzer, GraphStatisticsAnalyzer
- [x] Benchmark Framework — deterministic pipeline benchmarking without LLM calls, scoring, golden snapshots
- [x] Context Planning Engine — intent detection, ContextPlan, PlanningStage, single source of truth for retrieval configuration
- [x] Capability Framework — ExplainCapability, DebugCapability, RefactorCapability, CapabilityRegistry, CapabilityFactory, RetrievalProfile
- [x] Relationship-Aware Context Ranking — relationship signals (DIRECT_CALLER, DIRECT_CALLEE, SHARED_MODULE, SHARED_CLASS, SHARED_PARENT), context expansion

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
| Context Engine | In Progress | Context Builder implemented (v1). Full context optimization planned |
| Repository Intelligence | In Progress | Symbol graph + index service implemented. Dependency graph, code search planned |
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
