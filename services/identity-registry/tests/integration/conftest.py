"""Integration harness — one trust anchor, two participants, three processes.

What this layer exists to prove, and what neither the unit suite nor e2e can:

* **Unit tests stub the DID resolver.** They cannot show that a document this
  service *publishes* is one it can also *consume* — the two halves of did:web
  live in different modules and were written months apart.
* **e2e runs one anchor and reads it as authority.** A holder verifying a
  counterparty's signature could read the key out of its own database and pass.
  That is the defect shape this whole plan is about: a check that works only
  because dev is not the deployment.
* **Neither runs migrations.** The unit suite builds its schema with
  `create_all`, so a model change with no migration is invisible until a
  deployment fails.

## The topology, and why it changed (`T-2a`)

This harness used to start **two peer registries**, each its own trust anchor,
each bootstrapped with `ir-cli participant add --did … --sts-secret …`. That
command was removed by `D-51`: it minted a participant's DID keypair *and* its
STS client secret in the **anchor's** database, so the anchor could sign as any
participant and decided how each authenticated to a service it does not run.
That is the whole of the `§3.1` custody deviation.

Nothing ran this suite after the command went, so nothing said so — the suite
had simply been red on `main`. The same shape as `EDC-09` and `REV-01`, one
layer out: a check that exists and that no workflow invokes rots silently. It is
in `integration.yml` now.

So the harness follows the real handshake instead, and in doing so it stops
being a toy:

    anchor:       ir-cli bootstrap
                  ir-cli owner add --status verified …
                  ir-cli org enrolment-token --alias <owner> --roles provider
    participant:  ir-cli participant init --code <code>

**The participant generates its own key and never sends it.** The anchor
receives a *signature*, resolves the participant's DID document over real
did:web to get the public half, and checks it. Three processes, three databases,
one credential crossing between them.

Two consequences worth stating, because both are load-bearing here:

* **A participant must be serving before it can enrol.** The anchor fetches its
  `did.json` over HTTP; there is no local shortcut. `docker-compose.rec.yml`
  encodes the same order — `ir-rec-bootstrap` waits for `ir-rec` to be *healthy*.
* **The anchor is now genuinely a third party.** `the credential is signed by
  the trust anchor` used to compare two DIDs served by one process. It now names
  a key held in a database the holder cannot read.

Requires Postgres. `task -d services/identity-registry test:integration` runs
it; plain `test` does not, so the unit suite stays fast and dependency-free.
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
MEMBERSHIP_SCOPE = "org.eclipse.dspace.dcp.vc.type:MembershipCredential:read"

#: Every participant's STS secret in this harness.
#:
#: It is **the participant's own** now, set through
#: `IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET` on its own instance, and the anchor
#: never sees it — that is the `D-51` split. A shared literal is fine precisely
#: because each instance sets it for itself; it would not be if one process were
#: handing it to another.
STS_SECRET = "integration-test-sts-secret"

#: Scopes the enrolment code admits. `dataspaces.query` is what a provider needs
#: to be asked for a presentation; without it the exchange 401s on authorisation
#: rather than on identity, which reads like a signature failure.
ENROLMENT_SCOPES = ("dataspaces.query", "dataspaces.admin")


def _server_dsn_prefix() -> str:
    """The `scheme://user:pass@host:port` half of `ADMIN_DB_URL`.

    Derived rather than hardcoded, because the harness has to hand the *same*
    server to the processes it starts as it used to create their databases. It
    was `172.17.0.1:35432` in a literal here while `ADMIN_DB_URL` was already
    overridable — correct on a laptop, and in CI it would create the databases on
    one server and point three uvicorns at another. A failure that appears in no
    local run is exactly the kind this layer is supposed to remove.
    """
    prefix, _, _ = ADMIN_DB_URL.rpartition("/")
    return prefix


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _recreate_database(name: str) -> None:
    """Drop and recreate, at the **start** of a run rather than the end.

    Deliberately unlike `services/connector` and `services/provenance`, which
    generate a uuid name and drop it in teardown. The difference follows from the
    names: those are throwaway and would accumulate one database per run, while
    these four are fixed, so re-creating on entry is already idempotent and
    leaving them behind costs nothing. It buys the thing you want when a run
    fails — the anchor's issued credentials and the participants' keys are still
    there to inspect, and a harness that had wiped them on the way out would have
    taken the evidence with it.
    """
    with psycopg.connect(ADMIN_DB_URL, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')


def _run(args: list[str], env: dict) -> str:
    """Run an `ir-cli` step and return its stdout, refusing to continue on error."""
    result = subprocess.run(
        args, cwd=UNIT_DIR, env=env, capture_output=True, text=True, timeout=180
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(args)} failed ({result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


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


def _serve(database: str, port: int, env: dict) -> subprocess.Popen:
    return subprocess.Popen(
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


@dataclass
class Instance:
    """One running identity-registry process."""

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
        server it spawned listening, so a test that stops an instance to prove a
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


@dataclass
class Anchor(Instance):
    """The trust anchor: holds no participant key, issues every credential."""

    env: dict = None  # type: ignore[assignment]

    def enrolment_token(self, alias: str, *, roles: str = "provider") -> str:
        """Issue a code for *alias*, the way an operator does.

        Returned rather than written to a file, but with the same check the
        compose bootstrap learned the hard way: an **empty** code makes
        `participant init` take its "no code given" branch and report success
        having enrolled nothing, so the failure surfaces three tests later as a
        missing credential.
        """
        args = ["uv", "run", "ir-cli", "org", "enrolment-token",
                "--alias", alias, "--roles", roles]
        for scope in ENROLMENT_SCOPES:
            args += ["--scope", scope]
        code = _run(args, self.env).strip()
        if not code:
            raise RuntimeError(
                f"`ir-cli org enrolment-token --alias {alias}` printed nothing. "
                "The code is printed once and only hashed, so there is nothing "
                "to recover — the owner probably is not verified."
            )
        return code


@dataclass
class Registry(Instance):
    """One participant instance, holding its own key and acting as its own STS."""

    def sts_token(self, **form: str) -> dict:
        """Ask this participant's own STS for a self-issued token."""
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


def _base_env(database: str) -> dict:
    env = dict(os.environ)
    env.update(
        {
            "IDENTITY_REGISTRY_DATABASE_URL": (
                f"{_server_dsn_prefix().replace('postgresql://', 'postgresql+asyncpg://')}"
                f"/{database}"
            ),
            # Both halves of did:web have to agree, and in a test everything is
            # plain HTTP on a loopback port — the same choice a dev stack makes
            # through Caddy, stated the same way the EDC states it.
            "IDENTITY_REGISTRY_DID_WEB_USE_HTTPS": "false",
            "DS_ENV": "dev",
            "DS_LOG_LEVEL": "WARNING",
        }
    )
    return env


def _start_anchor(port: int) -> Anchor:
    """Bootstrap and serve the trust anchor.

    Its DID is `did:web:127.0.0.1%3A<port>`, resolving to this instance's own
    `/.well-known/did.json`. It no longer needs the `:trust-anchor` path suffix
    the old harness used: that existed to keep the anchor's DID distinct from the
    participant's *on one instance*, and they are separate instances now.
    """
    database = "ir_it_anchor"
    did = f"did:web:127.0.0.1%3A{port}"
    env = _base_env(database)
    env.update(
        {
            "IDENTITY_REGISTRY_TRUST_ANCHOR_DOMAIN": f"127.0.0.1%3A{port}",
            # Doubled prefix on purpose: the field is
            # `identity_registry_public_url` and the env prefix is
            # `IDENTITY_REGISTRY_`. Same spelling as docker-compose.yml and the
            # chart use. It is what goes *inside* issued credentials — above all
            # the StatusList a verifier must fetch — so it has to be an address
            # that answers, not the `https://` default.
            "IDENTITY_REGISTRY_IDENTITY_REGISTRY_PUBLIC_URL": f"http://127.0.0.1:{port}",
            "IDENTITY_REGISTRY_ENCRYPTION_KEY": "integration-anchor-encryption-key",
        }
    )

    _recreate_database(database)
    _run(["uv", "run", "alembic", "upgrade", "head"], env)
    _run(["uv", "run", "ir-cli", "bootstrap"], env)

    process = _serve(database, port, env)
    anchor = Anchor(
        name="anchor", port=port, did=did, process=process, database=database, env=env
    )
    try:
        _await_health(anchor.url, process)
    except Exception:
        anchor.stop()
        raise
    return anchor


def _register_owner(anchor: Anchor, alias: str) -> None:
    """Owners first: a participant enrols **as** a verified organisation.

    `status=verified` needs `--verified-by`; the DB CHECK, the admin API and
    `ir-cli owner import` all enforce that pairing, so a verified owner always
    records because of what. Stated honestly here, as the dev seed does.
    """
    _run(
        [
            "uv", "run", "ir-cli", "owner", "add",
            "--id", alias,
            "--name", f"Integration {alias}",
            "--status", "verified",
            "--verified-by", "integration-harness",
            "--evidence-ref", "tests/integration/conftest.py",
        ],
        anchor.env,
    )


def _start_participant(name: str, anchor: Anchor) -> Registry:
    """Serve a participant, then enrol it. The order is not negotiable.

    The anchor verifies the enrolment request by resolving this instance's DID
    document **over did:web** — there is no local shortcut — so the server has to
    be answering before `participant init --code` runs. Enrolling from an
    instance that is up but not routed fails with a resolution error naming the
    URL it could not fetch.
    """
    port = _free_port()
    database = f"ir_it_{name}"
    did = f"did:web:127.0.0.1%3A{port}"
    env = _base_env(database)
    env.update(
        {
            "IDENTITY_REGISTRY_ROLE": "participant",
            "IDENTITY_REGISTRY_PARTICIPANT_DID": did,
            "IDENTITY_REGISTRY_IDENTITY_REGISTRY_PUBLIC_URL": f"http://127.0.0.1:{port}",
            "IDENTITY_REGISTRY_TRUST_ANCHOR_DOMAIN": f"127.0.0.1%3A{anchor.port}",
            "IDENTITY_REGISTRY_TRUST_ANCHOR_URL": anchor.url,
            # This participant's own secret, held only here (`D-51`).
            "IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET": STS_SECRET,
            # Its own encryption key, so the private half it generates is
            # unreadable by the anchor even if they shared a database.
            "IDENTITY_REGISTRY_ENCRYPTION_KEY": f"integration-{name}-encryption-key",
        }
    )

    _recreate_database(database)
    _run(["uv", "run", "alembic", "upgrade", "head"], env)

    process = _serve(database, port, env)
    registry = Registry(
        name=name, port=port, did=did, process=process, database=database
    )
    try:
        _await_health(registry.url, process)
        alias = f"{name}-org"
        _register_owner(anchor, alias)
        code = anchor.enrolment_token(alias)
        # One command, two steps: it generates and commits the identity, then
        # presents it. The commit happens before the POST, which is what lets
        # the anchor resolve the DID document this call just published.
        _run(["uv", "run", "ir-cli", "participant", "init", "--code", code], env)
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
def anchor() -> Anchor:
    """The one trust anchor every participant in this suite enrols with."""
    instance = _start_anchor(_free_port())
    yield instance
    instance.stop()


@pytest.fixture(scope="session")
def holder(anchor: Anchor) -> Registry:
    registry = _start_participant("holder", anchor)
    yield registry
    registry.stop()


@pytest.fixture(scope="session")
def verifier(anchor: Anchor) -> Registry:
    registry = _start_participant("verifier", anchor)
    yield registry
    registry.stop()


@pytest.fixture
def ephemeral_verifier(anchor: Anchor) -> Registry:
    """A verifier a test may stop, without taking the session's one down with it."""
    registry = _start_participant("ephemeral", anchor)
    yield registry
    registry.stop()


@pytest.fixture
def dcp_exchange(holder: Registry, verifier: Registry):
    def run(**kwargs) -> str:
        return run_exchange(holder, verifier, **kwargs)

    return run
