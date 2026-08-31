"""Integration harness — `ds_auth` against a real Keycloak realm.

## The gap this closes

`docs/development/testing.md` names it directly: *authentication against a real
Keycloak, not a stubbed verifier*. Two suites exist and neither can see it.

* **`tests/test_verify.py` mints its own key.** It generates an EC keypair,
  signs its own claims and stubs the JWKS lookup. That proves the decision logic
  — expiry, issuer, audience, the `insecure_dev` carve-out `AUTH-01` fixed — and
  it proves nothing about a token Keycloak actually issues. A real one is RS256
  with a `kid` the realm publishes, an `aud` that is a **list**, and a `scope`
  claim built by mappers. None of that shape has ever met `verify_token`.
* **`tests/test_vocabulary.py` compares two committed files.** `clients.yaml`
  against `ds_auth.bundles`, and its own docstring names the failure it cannot
  catch: *"a bundle granting a name the realm never defines — a grant that
  matches nothing, discovered at 403 time."* It compares declarations with
  declarations. **What applies them is `celine-policies keycloak sync`**, and
  nothing anywhere checks its result.

So between `clients.yaml` and a running realm there is an unverified step, and
its failure mode is silent: the file says a client holds `connector.provider.read`,
the sync was never run — or ran without the overlay that declares it — and
the service 403s at runtime with both suites green. `KC-01` is the same shape
already recorded once: *a realm synced before the variable was set still holds
the client id*.

## What it needs

A **running Keycloak with the dev realm** — `task docker:restart`, or any stack
where `keycloak.dataspaces.localhost` answers. Not collected by `task test`
(`norecursedirs`), so the unit suite stays fast and dependency-free.

Addressed through the Caddy domain rather than `172.17.0.1:9080`, and that is
not a style choice: `verify_token` checks `iss`, the realm mints
`http://keycloak.dataspaces.localhost/realms/dataspaces`, and a token fetched
from the other address carries that same issuer — so the host-binding rule's
"OIDC issuer" row is the one that applies here.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
CLIENTS_YAML = REPO_ROOT / "services" / "keycloak" / "clients.yaml"

ISSUER = os.environ.get(
    "DS_AUTH_TEST_ISSUER",
    "http://keycloak.dataspaces.localhost/realms/dataspaces",
)

TOKEN_URL = f"{ISSUER}/protocol/openid-connect/token"


def _dev_secret(client_id: str) -> str:
    """The dev secret for a client.

    `clients.yaml` spells every one as `${SVC_…_SECRET:-<client_id>}`, so the
    dev default *is* the client id — the convention the root guide states and
    `ProductionGuard.forbidSecretEqualToClientId` exists to stop reaching
    production. Overridable per client for a stack that set real secrets.
    """
    env_name = client_id.upper().replace("-", "_") + "_SECRET"
    return os.environ.get(env_name, client_id)


def declared_clients() -> list[dict]:
    """Service clients `clients.yaml` declares scopes for.

    Read from ds's own two files — `clients.yaml` and `clients.dataspaces.yaml` —
    and **not** from the domain overlay passed beside them: a deployment's overlay
    adds clients and grants of its own, and what this suite asserts is the
    contract *ds* declares. A realm granting more than ds asks for is a
    deployment's business; granting less is the defect.

    Both files, because the realm this runs against is one ds owns, and the
    harness the suite most wants covered — `svc-ds-e2e` — is declared in the
    second. Grants are merged per client, as the sync merges them.
    """
    merged: dict[str, dict] = {}
    for path in (CLIENTS_YAML, CLIENTS_YAML.with_name("clients.dataspaces.yaml")):
        if not path.is_file():
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for client in document.get("clients", []) or []:
            entry = merged.setdefault(
                client["client_id"],
                {"client_id": client["client_id"], "default_scopes": []},
            )
            entry["default_scopes"] += client.get("default_scopes") or []
    return [c for c in merged.values() if c["default_scopes"]]


def fetch_token(client_id: str) -> str:
    """A real `client_credentials` token, or skip with a reason that helps."""
    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": _dev_secret(client_id),
            },
            timeout=10,
        )
    except httpx.HTTPError as exc:
        pytest.skip(f"Keycloak is not reachable at {TOKEN_URL}: {exc}")

    if response.status_code != 200:
        # Not a skip. A realm that is up and refuses a client `clients.yaml`
        # declares is precisely the drift this suite is for — most likely the
        # client was never synced, or its service account is disabled.
        raise AssertionError(
            f"{client_id} could not obtain a token ({response.status_code}): "
            f"{response.text.strip()[:200]}\n"
            f"ds's declaration names it. Check the realm was synced with every "
            f"file that declares it — see `keycloak-sync` in docker-compose.yml."
        )
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def keycloak_is_up() -> None:
    """Skip on a laptop with no stack; **fail** in CI.

    `CI-02`'s rule, and this is the same shape one layer out: an absent
    dependency has two meanings and they are not the same. On a developer's
    machine *no realm is running* is a supported mode — skip, loudly, with the
    command that fixes it. In CI the realm is provisioned by the job itself
    (`integration.yml`), so its absence is a **broken job**, and skipping would
    report green for a suite that asserted nothing.

    Without this, the workflow's whole value is conditional on a step that could
    silently stop working — which is the failure this repository keeps finding.
    """
    try:
        response = httpx.get(f"{ISSUER}/.well-known/openid-configuration", timeout=5)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        message = f"No Keycloak realm at {ISSUER} ({exc})."
        if os.environ.get("CI"):
            pytest.fail(
                f"{message} The `keycloak` job in .github/workflows/integration.yml "
                "starts and provisions one before this runs, so this is a broken "
                "workflow rather than a missing prerequisite.",
                pytrace=False,
            )
        pytest.skip(f"{message} Start one with `task docker:restart`.")
