# Build context: repo root
# Build command: docker build -f services/connector/Dockerfile .

# ── Builder ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install governance library (local dep)
COPY services/governance/ /build/governance/
RUN uv venv /opt/venv && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python \
      /build/governance

# Install connector dependencies
COPY services/connector/pyproject.toml /build/
RUN sed -i '/ds-governance/d' /build/pyproject.toml && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python \
      -r /build/pyproject.toml 2>/dev/null || \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python \
      fastapi "uvicorn[standard]" httpx "pydantic>=2.7" pydantic-settings \
      pyyaml tenacity "sqlalchemy[asyncio]" aiosqlite asyncpg alembic aiosmtplib

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.source="https://github.com/spindoxlabs/dataspaces" \
      org.opencontainers.image.description="ds-connector — EDC orchestration and consent service"

WORKDIR /app
RUN groupadd -r app && useradd -r -g app -d /app app

COPY --from=builder /opt/venv /opt/venv
COPY services/connector/src/ src/
COPY services/connector/alembic.ini alembic.ini
COPY services/connector/alembic/ alembic/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src"

USER app
EXPOSE 30001
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:30001/health')"

CMD ["uvicorn", "connector.main:app", "--host", "0.0.0.0", "--port", "30001", "--workers", "1"]
