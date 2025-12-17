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

# Dependency layer; cached as long as requirements.txt is unchanged
FROM base AS deps
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install --no-warn-script-location --user -r requirements.txt

# Final runtime image
FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH
WORKDIR /app

COPY --from=deps /root/.local /root/.local
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM app AS server
CMD ["uvicorn", "app.main:server", "--host", "0.0.0.0", "--port", "8000"]

FROM app AS worker
CMD ["uvicorn", "app.main:worker", "--host", "0.0.0.0", "--port", "8000"]
