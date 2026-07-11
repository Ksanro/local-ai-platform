# Local AI Platform

A production-ready Python project structure for AI platform development.

## Project Structure

```
├── apps/
│   └── gateway/          # FastAPI gateway application
├── packages/
│   ├── core/             # Core business logic
│   ├── config/           # Configuration management
│   └── telemetry/        # Telemetry and monitoring
├── tests/                # Test suite
├── docs/                 # Documentation
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
</path>
<task_progress>
- [ ] Create root-level files (README.md, LICENSE, pyproject.toml, .env.example, .gitignore, .editorconfig)
- [ ] Create .pre-commit-config.yaml
- [ ] Create GitHub Actions CI workflow
- [ ] Create compose.yaml
- [ ] Create packages/core/ with pyproject.toml and __init__.py
- [ ] Create packages/config/ with pyproject.toml and __init__.py
- [ ] Create packages/telemetry/ with pyproject.toml and __init__.py
- [ ] Create apps/gateway/ with pyproject.toml and __init__.py
- [ ] Create tests/ structure with conftest.py and pytest.ini
- [ ] Create docs/ and scripts/ directories with placeholder files
- [ ] Verify project builds with uv sync, pytest, ruff check, mypy
</task_progress>
</write_to_file>