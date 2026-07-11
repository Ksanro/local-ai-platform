# Project Memory - Local AI Platform

## Commit #0001 - Project Skeleton

### Goal
Create a production-ready Python project structure with uv, ruff, mypy, pytest, Docker Compose, and GitHub Actions CI.

### Files Created
- Root: `README.md`, `LICENSE`, `pyproject.toml`, `.env.example`, `.gitignore`, `.editorconfig`, `.pre-commit-config.yaml`, `compose.yaml`
- GitHub: `.github/workflows/ci.yml`
- Packages: `packages/core/`, `packages/config/`, `packages/telemetry/` (each with `pyproject.toml` and `__init__.py`)
- Apps: `apps/gateway/` with `pyproject.toml`, `__init__.py`, `Dockerfile`
- Tests: `tests/__init__.py`, `tests/conftest.py`
- Docs: `docs/index.md`
- Scripts: `scripts/README.md`

### Verification
- `uv sync` - ✅ 14 packages resolved
- `ruff check .` - ✅ All checks passed
- `mypy .` - ✅ Success: no issues found in 6 source files
- `pytest` - ✅ 0 tests (skeleton only)

---

## Commit #0002 - Gateway Skeleton

### Goal
Implement a production-ready FastAPI gateway skeleton with thin routes, Pydantic settings, structured logging, request ID middleware, timing middleware, and CORS.

### Files Created
```
apps/gateway/
├── main.py              # FastAPI app factory with lifespan
├── api/
│   ├── __init__.py
│   ├── health.py        # GET /health → {"status": "ok"}
│   ├── version.py       # GET /version → {"name": "Local AI Platform", "version": "0.1.0"}
│   └── chat.py          # POST /v1/chat/completions → HTTP 501
├── core/
│   ├── __init__.py
│   ├── config.py        # Pydantic Settings (APP_ prefix)
│   └── logging.py       # Structured logging setup
├── middleware.py        # RequestID + Timing middleware
└── pyproject.toml
```

### Files Modified
- `apps/gateway/pyproject.toml` - Added pydantic dependency, dev dependencies
- `pyproject.toml` - Added httpx2, pydantic-settings, mypy overrides

### Endpoints
- `GET /health` → `{"status": "ok"}`
- `GET /version` → `{"name": "Local AI Platform", "version": "0.1.0"}`
- `POST /v1/chat/completions` → HTTP 501 `{"error": "Provider not configured"}`

### Verification
- `uv sync` - ✅ 31 packages
- `ruff check .` - ✅ All checks passed
- `mypy .` - ✅ Success: no issues found in 19 source files
- `pytest` - ✅ 3 passed (health, version, chat)

---

## Commit #0003 - Provider Abstraction

### Goal
Introduce a provider abstraction layer. The gateway must never know whether it is talking to vLLM, OpenAI, Ollama or LM Studio. Only registry and factory - no concrete providers.

### Files Created
```
packages/providers/
├── __init__.py          # Public API: Provider, create_provider, register, exceptions
├── base.py              # Abstract Provider class (health, chat, models - all async)
├── exceptions.py        # ProviderError, UnknownProviderError, ProviderConnectionError, ProviderAuthenticationError, ProviderResponseError
├── factory.py           # create_provider(name) - raises UnknownProviderError if not registered
└── registry.py          # register(name, provider_class), has_provider(name), get_registry()

tests/providers/
├── __init__.py
├── test_factory.py      # 3 tests: registered instance, unknown raises, after register
└── test_registry.py     # 5 tests: add, multiple, copy, all registered, missing
```

### Classes
- `Provider` - Abstract base with `health() -> dict`, `chat(**kwargs) -> dict`, `models() -> list`
- `register(name, provider_class)` - Register a provider class by name
- `create_provider(name) -> Provider` - Create instance or raise `UnknownProviderError`

### Exceptions
- `ProviderError` - Base exception
- `UnknownProviderError` - Provider not registered
- `ProviderConnectionError` - Connection failure
- `ProviderAuthenticationError` - Authentication failure
- `ProviderResponseError` - Invalid response

### Verification
- `ruff check .` - ✅ All checks passed
- `mypy .` - ✅ Success: no issues found in 27 source files
- `pytest tests/providers/` - ✅ 8 passed (3 factory + 5 registry)

---

## Commit #0004 - vLLM Provider

### Goal
Implement the first real provider: vLLM (OpenAI-compatible). POST /v1/chat/completions must proxy requests to the configured vLLM server.

### Files Created
```
packages/providers/
└── vllm.py              # VLLMProvider implementation

tests/providers/
└── test_vllm_provider.py  # 25 tests for vLLM provider

packages/config/
├── __init__.py          # Config loading with env var override
└── config.yaml          # vLLM configuration
```

### Configuration
Read from `config.yaml` with environment variable override:
- `VLLM_BASE_URL` - vLLM server URL (default: `http://localhost:8000/v1`)
- `VLLM_API_KEY` - API key (default: `empty`)
- `REQUEST_TIMEOUT` - Request timeout in seconds (default: `60.0`)
- `DEFAULT_MODEL` - Default model name (default: `default-model`)

### Implementation
```python
class VLLMProvider(Provider):
    def __init__(self) -> None
    def _get_client(self) -> httpx.AsyncClient
    async def _ensure_client(self) -> httpx.AsyncClient
    async def health(self) -> dict[str, Any]
    async def models(self) -> list[str]
    async def chat(self, **kwargs: Any) -> dict[str, Any]
    async def _stream_chat(self, client, kwargs) -> dict[str, Any]
    async def create_streaming_response(self, result) -> StreamingResponse
    async def close(self) -> None
```

### HTTP Client
- Uses `httpx.AsyncClient` with singleton pattern (created once, reused)
- Sets `Authorization: Bearer {API_KEY}` header
- Configures timeout from `REQUEST_TIMEOUT`

### chat()
- Accepts OpenAI-compatible payload
- Forwards payload unchanged to `/chat/completions` endpoint
- Returns response unchanged (no JSON transformation)
- Supports `stream=true` (returns dict with generator for StreamingResponse)

### Error Handling
- `401` → `ProviderAuthenticationError`
- `5xx` → `ProviderResponseError`
- Timeout → `ProviderConnectionError`
- Connection refused → `ProviderConnectionError`

### Auto-Registration
- Automatically registers as "vllm" via `register("vllm", VLLMProvider)`

### Tests (25 total)
- Registration: `test_vllm_registered`, `test_vllm_provider_class`
- Health: `test_health_healthy`, `test_health_unhealthy_status`, `test_health_connect_error`, `test_health_timeout`
- Models: `test_models_success`, `test_models_empty`, `test_models_response_error`, `test_models_timeout`
- Chat: `test_chat_success`, `test_chat_forwards_payload_unchanged`, `test_chat_401`, `test_chat_500`, `test_chat_timeout`, `test_chat_connection_error`
- Streaming: `test_streaming_returns_generator`, `test_streaming_error_handling`, `test_streaming_connection_error`
- Helpers: `test_create_streaming_response_success`, `test_create_streaming_response_no_generator`
- Close: `test_close_client`
- Config: `test_config_loads_from_file`, `test_env_overrides_config`, `test_config_with_float_conversion`

### Verification
- `pytest tests/providers/test_vllm_provider.py` - ✅ 25 passed
- `ruff check packages/providers/vllm.py tests/providers/test_vllm_provider.py` - ✅ All checks passed
- `mypy packages/providers/vllm.py tests/providers/test_vllm_provider.py` - ✅ Success: no issues found

---

## Summary

| Commit | Description | Files Created | Tests | Status |
|--------|-------------|---------------|-------|--------|
| #0001 | Project Skeleton | 20+ | 0 | ✅ |
| #0002 | Gateway Skeleton | 12 | 3 | ✅ |
| #0003 | Provider Abstraction | 9 | 8 | ✅ |
| #0004 | vLLM Provider | 4 | 25 | ✅ |

Total: 45+ files, 36 tests, all passing.