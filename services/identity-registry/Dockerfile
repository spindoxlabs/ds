# ---- Builder ----
FROM python:3.12-slim AS builder
WORKDIR /build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Shared libraries first, installed BY PATH so they land non-editable: the
# runtime stage carries only /opt/venv, and an editable install leaves a .pth
# pointing at a /build that no longer exists there.
COPY libs/ds-auth/ /build/ds-auth/
COPY libs/ds-obs/ /build/ds-obs/
# `ds-governance` joined this list when the owner registry started resolving
# participants from governance ownership. The Dockerfile was not updated with it,
# and the failure is invisible outside a container build: `[tool.uv.sources]`
# points at ../../libs so every host-run install resolves it, while the install
# below passes --no-sources and cannot. So `task dev:*` was green throughout and
# `task build` had been failing on this image since `6e6d231` with
# "ds-governance was not found in the package registry".
COPY libs/governance/ /build/governance/
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python \
        /build/ds-auth '/build/ds-obs[tracing]' /build/governance

COPY services/identity-registry/pyproject.toml ./
COPY services/identity-registry/src/ src/

# The project and its declared dependencies, from pyproject.toml and nowhere
# else. --no-sources makes uv treat ds-auth, ds-obs and ds-governance as plain
# requirements instead of following [tool.uv.sources] to ../../libs; the install
# above satisfies them, and without it uv reinstalls them editable and breaks the
# runtime stage.
#
# The corollary is the trap above: a path dependency added to pyproject.toml and
# not to the COPY list resolves everywhere except here.
RUN uv pip install --python /opt/venv/bin/python --no-sources .

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

# Where enrolment codes are handed from the trust anchor's bootstrap to each
# participant's. Created here and owned by `app` so that a **fresh named volume**
# mounted at this path inherits that ownership — Docker copies the image's
# directory ownership into an empty volume, which is what makes this work without
# any host-side chown. A bind mount from `./data/` would not: the host directory
# belongs to the developer's uid and the container runs as 10001.
RUN mkdir -p /enrolment && chown app:app /enrolment

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src"

USER app
EXPOSE 30005
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:30005/health')"

CMD ["uvicorn", "identity_registry.main:app", "--host", "0.0.0.0", "--port", "30005", "--workers", "1"]
