# Build context: repo root
FROM python:3.12-slim AS builder
WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY services/sts/pyproject.toml ./
RUN uv venv /opt/venv && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --python /opt/venv/bin/python \
      fastapi "uvicorn[standard]" "pydantic>=2.7" "pydantic-settings>=2.3" \
      "cryptography>=42" "python-jose[cryptography]>=3.3"

FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.description="ds-sts — Self-Issued Token Service (DCP)"

WORKDIR /app
RUN groupadd -r app && useradd -r -g app -d /app app

COPY --from=builder /opt/venv /opt/venv
COPY services/sts/src/ src/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src"

USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["uvicorn", "sts.main:app", "--host", "0.0.0.0", "--port", "8080"]
