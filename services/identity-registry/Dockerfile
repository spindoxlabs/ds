# ---- Builder ----
FROM python:3.12-slim AS builder
WORKDIR /build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install shared libraries (local path deps)
COPY libs/ds-auth/ /build/ds-auth/
RUN uv venv /opt/venv && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python \
      /build/ds-auth

COPY services/identity-registry/pyproject.toml ./
COPY services/identity-registry/src/ src/

RUN sed -i '/ds-auth/d' /build/pyproject.toml && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python .

# ---- Runtime ----
FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.description="ds-identity-registry — DID lifecycle, VC issuance, participant registry"

WORKDIR /app
# uid/gid pinned: kubelet cannot verify runAsNonRoot against a named USER
RUN groupadd -r -g 10001 app && useradd -r -u 10001 -g app -d /app app

COPY --from=builder /opt/venv /opt/venv
COPY services/identity-registry/src/ src/
COPY services/identity-registry/alembic.ini alembic.ini
COPY services/identity-registry/alembic/ alembic/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src"

USER app
EXPOSE 30005
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:30005/health')"

CMD ["uvicorn", "identity_registry.main:app", "--host", "0.0.0.0", "--port", "30005", "--workers", "1"]
