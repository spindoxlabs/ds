# Build context: repo root
FROM python:3.12-slim AS builder
WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install shared libraries (local path deps)
COPY libs/ds-auth/ /build/ds-auth/
RUN uv venv /opt/venv && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python \
      /build/ds-auth

COPY services/federated-catalog/pyproject.toml ./
RUN sed -i '/ds-auth/d' /build/pyproject.toml && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python \
      fastapi "uvicorn[standard]" httpx "pydantic>=2.7" pydantic-settings pyyaml

FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.description="ds-federated-catalog — DCAT-AP federated catalog crawler"

WORKDIR /app
RUN groupadd -r app && useradd -r -g app -d /app app

COPY --from=builder /opt/venv /opt/venv
COPY services/federated-catalog/src/ src/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src"

USER app
EXPOSE 30003
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:30003/health')"

CMD ["uvicorn", "federated_catalog.main:app", "--host", "0.0.0.0", "--port", "30003", "--workers", "1"]
