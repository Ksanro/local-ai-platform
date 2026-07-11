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

## Summary

| Commit | Description | Files Created | Tests | Status |
|--------|-------------|---------------|-------|--------|
| #0001 | Project Skeleton | 20+ | 0 | ✅ |
| #0002 | Gateway Skeleton | 12 | 3 | ✅ |
| #0003 | Provider Abstraction | 9 | 8 | ✅ |

Total: 41+ files, 11 tests, all passing.