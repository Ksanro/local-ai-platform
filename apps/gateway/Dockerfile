FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy project
COPY pyproject.toml .
COPY apps/ apps/
COPY packages/ packages/

# Install dependencies
RUN uv sync --no-dev

# Run the application
CMD ["uvicorn", "apps.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]