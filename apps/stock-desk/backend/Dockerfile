# Backend image for stock-desk: Python 3.12 + uv, dependencies locked by uv.lock.
FROM python:3.12-slim

# Install uv (version manged by the base image tag on rebuild; uv resolves deps from uv.lock only).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app

# Install the project itself.
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
