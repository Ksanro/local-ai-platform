# Local AI Platform

A production-ready Python project structure for AI platform development.

## Project Structure

```
├── apps/
│   └── gateway/          # FastAPI gateway application
├── packages/
│   ├── core/             # Core business logic
│   ├── config/           # Configuration management
│   ├── providers/        # AI provider implementations
│   └── telemetry/        # Telemetry and monitoring
├── tests/                # Test suite
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

| Variable          | Default            | Description                              |
|-------------------|--------------------|------------------------------------------|
| `APP_LOG_LEVEL`   | `INFO`             | Logging level                            |
| `GATEWAY_HOST`    | `localhost`        | Gateway host for smoke / integration tests |
| `GATEWAY_PORT`    | `8000`             | Gateway port for smoke / integration tests |
| `VLLM_BASE_URL`   | `http://localhost:8000/v1` | vLLM server URL                    |
| `VLLM_API_KEY`    | `empty`            | vLLM API key                             |
| `DEFAULT_MODEL`   | `default-model`    | Default model identifier                 |
| `REQUEST_TIMEOUT` | `30`               | Request timeout in seconds               |

## Smoke Test

Run the quick smoke test to verify the gateway and vLLM integration:

```bash
python scripts/test_gateway.py
```

Expected output on success:

```
Local AI Platform – Gateway Smoke Test
  Gateway : http://localhost:8000
  vLLM    : http://localhost:8000/v1
  Model   : default-model

✓ Gateway reachable
✓ Provider healthy
✓ Chat successful
✓ Streaming successful

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
