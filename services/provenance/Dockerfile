# Build context: repo root
FROM python:3.12-slim AS builder
WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY services/provenance/pyproject.toml ./
RUN uv venv /opt/venv && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python \
      fastapi "uvicorn[standard]" httpx "pydantic>=2.7" pydantic-settings \
      "sqlalchemy[asyncio]" aiosqlite asyncpg alembic python-ulid

FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.description="ds-provenance — W3C PROV-O audit service"

WORKDIR /app
RUN groupadd -r app && useradd -r -g app -d /app app

COPY --from=builder /opt/venv /opt/venv
COPY services/provenance/src/ src/
COPY services/provenance/alembic.ini alembic.ini
COPY services/provenance/alembic/ alembic/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src"

USER app
EXPOSE 30000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:30000/health')"

CMD ["uvicorn", "provenance.main:app", "--host", "0.0.0.0", "--port", "30000", "--workers", "1"]
