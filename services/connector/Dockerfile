# Build context: repo root
# Build command: docker build -f services/connector/Dockerfile .

# ── Builder ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install shared libraries (local path deps)
COPY libs/governance/ /build/governance/
COPY libs/ds-auth/ /build/ds-auth/
COPY libs/ds-edc/ /build/ds-edc/
RUN uv venv /opt/venv && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python \
      /build/governance /build/ds-auth /build/ds-edc

# Install connector dependencies.
#
# The second command is a fallback for when `-r pyproject.toml` cannot be
# resolved, and it must list every runtime dependency the first one would have
# installed — a package missing here does not fail the build, it fails at
# import, in a container that looked like it built. `pyjwt[crypto]` was missing:
# it is what verifies every JWT this service accepts.
COPY services/connector/pyproject.toml /build/
RUN sed -i '/ds-governance/d; /ds-auth/d; /ds-edc/d' /build/pyproject.toml && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python \
      -r /build/pyproject.toml 2>/dev/null || \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python \
      fastapi "uvicorn[standard]" httpx "pydantic>=2.7" pydantic-settings \
      pyyaml tenacity "sqlalchemy[asyncio]" aiosqlite asyncpg alembic aiosmtplib \
      cryptography "pyjwt[crypto]"

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.source="https://github.com/spindoxlabs/dataspaces" \
      org.opencontainers.image.description="ds-connector — EDC orchestration and consent service"

WORKDIR /app
# uid/gid pinned: kubelet cannot verify runAsNonRoot against a named USER
RUN groupadd -r -g 10001 app && useradd -r -u 10001 -g app -d /app app

COPY --from=builder /opt/venv /opt/venv
COPY services/connector/src/ src/
COPY services/connector/alembic.ini alembic.ini
COPY services/connector/alembic/ alembic/

# One image, two instances: the provider serves 30001 and the consumer 31001.
# The port is a single variable so the server and the health check cannot
# disagree — the health check used to probe 30001 unconditionally, so a consumer
# container reported unhealthy forever while serving correctly, and `depends_on:
# service_healthy` waited on it.
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src" \
    CONNECTOR_PORT=30001

USER app
EXPOSE 30001
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/health' % os.environ['CONNECTOR_PORT'])"

# `exec` so uvicorn is pid 1 and receives SIGTERM directly; the shell is only
# here to expand the port.
CMD ["sh", "-c", "exec uvicorn connector.main:app --host 0.0.0.0 --port ${CONNECTOR_PORT} --workers 1"]
