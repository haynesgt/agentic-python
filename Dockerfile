# syntax=docker/dockerfile:1.6

# Base image with common env/config
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100
WORKDIR /app

# Install build deps once and keep layer small
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry and cache dependencies
FROM base AS deps
ENV POETRY_VERSION=2.2.1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PATH="/root/.local/bin:${PATH}"

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-warn-script-location --user "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock* ./
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/pypoetry \
    poetry install --with dev --no-root --no-interaction --no-ansi

# Final runtime image
FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:${PATH}"
WORKDIR /app

COPY --from=deps /usr/local /usr/local
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM app AS server
ARG PORT=8000
ENV PORT=${PORT}
EXPOSE ${PORT}
CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-8000}"]

FROM server AS server-debug
CMD ["sh", "-c", "PYDEVD_DISABLE_FILE_VALIDATION=1 debugpy --listen 0.0.0.0:5678 -m uvicorn --log-level debug app.server:app --reload --host 0.0.0.0 --port ${PORT:-8000}"]

FROM app AS worker
CMD ["python", "-m", "app.temporal_worker"]
