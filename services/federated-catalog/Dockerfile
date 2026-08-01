# Build context: repo root
FROM python:3.12-slim AS builder
WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Shared libraries first, installed BY PATH so they land non-editable: the
# runtime stage carries only /opt/venv, and an editable install leaves a .pth
# pointing at a /build that no longer exists there.
COPY libs/ds-auth/ /build/ds-auth/
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python /build/ds-auth

# Everything else comes from pyproject.toml and from nowhere else. The list this
# replaces had drifted: it omitted `typer`, which cli/main.py imports.
# --no-sources makes uv treat ds-auth as a plain requirement instead of
# following [tool.uv.sources] to ../../libs; the install above satisfies it, and
# without it uv reinstalls it editable and breaks the runtime stage.
COPY services/federated-catalog/pyproject.toml ./
RUN uv pip install --python /opt/venv/bin/python --no-sources -r /build/pyproject.toml

FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.description="ds-federated-catalog — DCAT-AP federated catalog crawler"

WORKDIR /app
# uid/gid pinned: kubelet cannot verify runAsNonRoot against a named USER
RUN groupadd -r -g 10001 app && useradd -r -u 10001 -g app -d /app app

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
