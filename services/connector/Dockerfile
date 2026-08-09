# Build context: repo root
# Build command: docker build -f services/connector/Dockerfile .

# ── Builder ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Shared libraries first, installed BY PATH so they land non-editable: the
# runtime stage carries only /opt/venv, and an editable install leaves a .pth
# pointing at a /build that no longer exists there.
COPY libs/governance/ /build/governance/
COPY libs/ds-auth/ /build/ds-auth/
COPY libs/ds-edc/ /build/ds-edc/
COPY libs/ds-obs/ /build/ds-obs/
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python \
      /build/governance /build/ds-auth /build/ds-edc '/build/ds-obs[tracing]'

# Everything else comes from pyproject.toml and from nowhere else. There is no
# fallback list: a dependency this service declares but the image lacks must
# fail the build, not fail at import in a container that looked like it built.
#
# --no-sources makes uv treat the ds-* entries as plain requirements instead of
# following [tool.uv.sources] to ../../libs — the installs above already satisfy
# them, and without it uv reinstalls them editable and breaks the runtime stage.
COPY services/connector/pyproject.toml /build/
RUN uv pip install --python /opt/venv/bin/python --no-sources -r /build/pyproject.toml

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.source="https://github.com/spindoxlabs/ds" \
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
