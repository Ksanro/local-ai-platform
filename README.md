# Local AI Platform

A production-ready Python project structure for AI platform development.

## Project Structure

```
├── apps/
│   └── gateway/          # FastAPI gateway application
├── packages/
│   ├── config/           # Configuration management
│   ├── pipeline/         # Request processing pipeline (stages, engine, context)
│   ├── providers/        # AI provider implementations
│   ├── repository/       # Repository scanner and index
│   ├── advisors/         # Deterministic analysis and recommendations
│   └── telemetry/        # Telemetry and monitoring (stub)
├── tests/                # Test suite
│   ├── gateway/          # Gateway unit tests
│   ├── pipeline/         # Pipeline unit tests
│   ├── providers/        # Provider unit tests
│   ├── repository/       # Scanner unit tests
│   ├── advisors/         # Refactoring advisor tests
│   └── integration/      # End-to-end integration tests
├── scripts/              # Utility scripts
└── .github/              # GitHub Actions workflows
```

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Install dependencies
uv sync

# Run linter
ruff check .

# Run type checker
mypy .

# Run tests
pytest
```

## Running the Gateway

Start the gateway with uvicorn:

```bash
uvicorn apps.gateway.main:create_app --factory --reload
```

The gateway exposes the following endpoints:

| Method | Path                    | Description                    |
|--------|-------------------------|--------------------------------|
| GET    | `/health`               | Health check                   |
| GET    | `/version`              | Application version metadata   |
| POST   | `/v1/chat/completions`  | Chat completions (OpenAI API)  |

## Environment Variables

| Variable                        | Default            | Description                              |
|---------------------------------|--------------------|------------------------------------------|
| `APP_LOG_LEVEL`                 | `INFO`             | Logging level                            |
| `APP_REPOSITORY_CONTEXT_ENABLED`| `true`             | Enable repository intelligence           |
| `REPOSITORY_CONTEXT_MAX_SYMBOLS`| `20`               | Maximum symbols in context               |
| `REPOSITORY_CONTEXT_MAX_MODULES`| `10`               | Maximum modules in context               |
| `REPOSITORY_CONTEXT_MAX_TOKENS` | `4096`             | Maximum token budget                     |
| `GATEWAY_HOST`                  | `localhost`        | Gateway host for smoke / integration tests |
| `GATEWAY_PORT`                  | `8001`             | Gateway port for smoke / integration tests |
| `VLLM_BASE_URL`                 | `http://localhost:8000/v1` | vLLM server URL                    |
| `VLLM_API_KEY`                | `empty`            | vLLM API key                             |
| `DEFAULT_MODEL`                 | `default-model`    | Default model identifier                 |
| `REQUEST_TIMEOUT`               | `30`               | Request timeout in seconds               |

## Smoke Test

Run the quick smoke test to verify the gateway and vLLM integration:

```bash
python scripts/test_gateway.py
```

Expected output on success:

```
Local AI Platform - Gateway Smoke Test
  Gateway : http://localhost:8001
  vLLM    : http://localhost:8000/v1
  Model   : default-model

[PASS] Gateway reachable
[PASS] Chat successful
[PASS] Streaming successful
[PASS] Repository Intelligence pipeline

RESULT: PASSED
```

## Integration Tests

End-to-end integration tests live in `tests/integration/`. They require a running vLLM instance and skip automatically when `VLLM_BASE_URL` is not set:

```bash
VLLM_BASE_URL=http://localhost:8000/v1 pytest tests/integration/
```

## Tech Stack

- **Language:** Python 3.12
- **Framework:** FastAPI
- **Package Manager:** uv
- **Linter/Formatter:** Ruff
- **Type Checking:** mypy
- **Testing:** pytest
- **Containerization:** Docker Compose
- **CI/CD:** GitHub Actions

## License

Apache 2.0 - See [LICENSE](LICENSE) file for details.

## Bench context run results
Recording 12/14 vs 3/14 at commit 61cb266
