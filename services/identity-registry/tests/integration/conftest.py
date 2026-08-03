"""Integration harness — two registries, two databases, two processes.

What this layer exists to prove, and what neither the unit suite nor e2e can:

* **Unit tests stub the DID resolver.** They cannot show that a document this
  service *publishes* is one it can also *consume* — the two halves of did:web
  live in different modules and were written months apart.
* **e2e runs one registry.** With a single instance serving every participant,
  a holder verifying a counterparty's signature could read the key out of its own
  database and pass. That is the defect shape this whole plan is about: a check
  that works only because dev is not the deployment.
* **Neither runs migrations.** The unit suite builds its schema with
  `create_all`, so a model change with no migration is invisible until a
  deployment fails.

So: two processes, two Postgres databases, each bootstrapped through the real
`ir-cli` path, resolving each other over real HTTP on real ports.

Requires Postgres. `task -d services/identity-registry test:integration` runs it;
plain `test` does not, so the unit suite stays fast and dependency-free.
"""
from __future__ import annotations

import base64
import json
import os
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import psycopg
import pytest

UNIT_DIR = Path(__file__).resolve().parents[2]

ADMIN_DB_URL = os.environ.get(
    "IDENTITY_REGISTRY_TEST_PG", "postgresql://postgres:postgres@172.17.0.1:35432/postgres"
)
ENCRYPTION_KEY = "integration-test-encryption-key"
MEMBERSHIP_SCOPE = "org.eclipse.dspace.dcp.vc.type:MembershipCredential:read"
STS_SECRET = "integration-test-sts-secret"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _recreate_database(name: str) -> None:
    with psycopg.connect(ADMIN_DB_URL, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')


@dataclass
class Registry:
    """One running identity-registry, hosting one participant."""

    name: str
    port: int
    did: str
    process: subprocess.Popen
    database: str

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        """Kill the whole process group.

        `uv run uvicorn` is a *wrapper*: killing the Popen handle leaves the
        server it spawned listening, so a test that stops a registry to prove a
        refusal watched it keep answering. Found exactly that way.
        """
        if self.process.poll() is None:
            os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
        self.process.wait(timeout=10)

    def is_running(self) -> bool:
        try:
            httpx.get(f"{self.url}/health", timeout=1)
            return True
        except httpx.HTTPError:
            return False

    def sts_token(self, **form: str) -> dict:
        """Ask this registry's STS for a self-issued token."""
        response = httpx.post(
            f"{self.url}/sts/{self.did}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.did,
                "client_secret": STS_SECRET,
                **form,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


def _env_for(database: str, port: int) -> dict:
    env = dict(os.environ)
    env.update(
        {
            "IDENTITY_REGISTRY_DATABASE_URL": (
                f"postgresql+asyncpg://postgres:postgres@172.17.0.1:35432/{database}"
            ),
            "IDENTITY_REGISTRY_ENCRYPTION_KEY": ENCRYPTION_KEY,
            # Both halves of did:web have to agree, and in a test everything is
            # plain HTTP on a loopback port — the same choice a dev stack makes
            # through Caddy, stated the same way the EDC states it.
            "IDENTITY_REGISTRY_DID_WEB_USE_HTTPS": "false",
            # The anchor is a *different* DID from the participant, served by the
            # same instance at the did:web path form
            # (`did:web:127.0.0.1%3A<port>:trust-anchor` →
            # `/trust-anchor/did.json`). Making them equal would have let a
            # participant appear to issue its own membership credential, and the
            # test asserting the issuer would have passed on that.
            "IDENTITY_REGISTRY_TRUST_ANCHOR_DOMAIN": f"127.0.0.1%3A{port}:trust-anchor",
            # Doubled prefix on purpose: the field is `identity_registry_public_url`
            # and the env prefix is `IDENTITY_REGISTRY_`. Same spelling as
            # docker-compose.yml and the chart use.
            "IDENTITY_REGISTRY_IDENTITY_REGISTRY_PUBLIC_URL": f"http://127.0.0.1:{port}",
            "DS_LOG_LEVEL": "WARNING",
        }
    )
    return env


def _run(args: list[str], env: dict) -> None:
    result = subprocess.run(
        args, cwd=UNIT_DIR, env=env, capture_output=True, text=True, timeout=180
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(args)} failed ({result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def _await_health(url: str, process: subprocess.Popen, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"{url} exited with {process.returncode} before becoming healthy"
            )
        try:
            if httpx.get(f"{url}/health", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"{url} did not become healthy within {timeout}s")


def _start_registry(name: str, *, other_port: int | None = None) -> Registry:
    """Bootstrap a database through `ir-cli`, then serve it.

    The port is allocated **before** bootstrap because the participant's DID is
    derived from it: `did:web:127.0.0.1%3A<port>` resolves to
    `http://127.0.0.1:<port>/.well-known/did.json`, which is this registry
    itself. That is what makes the resolution in these tests real rather than
    stubbed.
    """
    port = _free_port()
    database = f"ir_it_{name}"
    did = f"did:web:127.0.0.1%3A{port}"
    env = _env_for(database, port)

    _recreate_database(database)
    _run(["uv", "run", "alembic", "upgrade", "head"], env)
    _run(["uv", "run", "ir-cli", "bootstrap"], env)
    _run(
        [
            "uv", "run", "ir-cli", "participant", "add",
            "--did", did,
            "--roles", "provider",
            "--sts-secret", STS_SECRET,
            "--credential-service-url",
            f"http://127.0.0.1:{port}/credentials/{did}",
        ],
        env,
    )

    process = subprocess.Popen(
        [
            "uv", "run", "uvicorn", "identity_registry.main:app",
            "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
        ],
        cwd=UNIT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    registry = Registry(
        name=name, port=port, did=did, process=process, database=database
    )
    try:
        _await_health(registry.url, process)
    except Exception:
        registry.stop()
        raise
    return registry


def run_exchange(
    holder: Registry,
    verifier: Registry,
    *,
    scope: str = MEMBERSHIP_SCOPE,
    audience: str | None = None,
) -> str:
    """Run the DCP token exchange exactly as two EDCs do, and return the token.

    1. the **holder** asks its own STS for an SI token naming the verifier, with a
       `bearer_access_scope` — that mints the grant;
    2. the **verifier** takes the grant out of the `token` claim and asks its own
       STS to wrap it in an SI token naming the holder;
    3. that second token is what the credential service is called with.
    """
    dsp_token = holder.sts_token(audience=verifier.did, bearer_access_scope=scope)[
        "access_token"
    ]
    claims = json.loads(
        base64.urlsafe_b64decode(dsp_token.split(".")[1] + "===").decode()
    )
    return verifier.sts_token(audience=audience or holder.did, token=claims["token"])[
        "access_token"
    ]


@pytest.fixture(scope="session")
def holder() -> Registry:
    registry = _start_registry("holder")
    yield registry
    registry.stop()


@pytest.fixture(scope="session")
def verifier() -> Registry:
    registry = _start_registry("verifier")
    yield registry
    registry.stop()


@pytest.fixture
def ephemeral_verifier() -> Registry:
    """A verifier a test may stop, without taking the session's one down with it."""
    registry = _start_registry("ephemeral")
    yield registry
    registry.stop()


@pytest.fixture
def dcp_exchange(holder: Registry, verifier: Registry):
    def run(**kwargs) -> str:
        return run_exchange(holder, verifier, **kwargs)

    return run
