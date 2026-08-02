# Build context: repo root
FROM python:3.12-slim AS builder
WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Shared libraries (local path deps) — ds_auth.ServiceTokenProvider, and
# ds.governance for the `/internal/dataplane/authorize` decision shape.
#
# Installed BY PATH so they land non-editable: the runtime stage carries only
# /opt/venv, and an editable install leaves a .pth pointing at a /build that no
# longer exists there.
COPY libs/ds-auth/ /build/ds-auth/
COPY libs/governance/ /build/governance/
COPY libs/ds-obs/ /build/ds-obs/
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python \
      /build/ds-auth /build/governance /build/ds-obs

# Everything else comes from pyproject.toml and from nowhere else. --no-sources
# makes uv treat the ds-* entries as plain requirements instead of following
# [tool.uv.sources] to ../../libs; the installs above already satisfy them.
COPY services/dataset-api-mock/pyproject.toml /build/
RUN uv pip install --python /opt/venv/bin/python --no-sources -r /build/pyproject.toml

FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.description="mock dataset-api for standalone dataspace tests"

WORKDIR /app
RUN groupadd -r app && useradd -r -g app -d /app app

COPY --from=builder /opt/venv /opt/venv
COPY services/dataset-api-mock/src/ src/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src"

USER app
EXPOSE 30002
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:30002/health')"

CMD ["uvicorn", "dataset_api_mock.main:app", "--host", "0.0.0.0", "--port", "30002"]
