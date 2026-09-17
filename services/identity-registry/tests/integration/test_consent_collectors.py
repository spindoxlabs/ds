"""Consent collectors on a migrated anchor with a really enrolled holder.

Plan `a-collector-registers-consent-at-the-holder`. The unit suite runs on SQLite
with hand-seeded rows; this proves migration `0018` builds the table on Postgres,
that `ir-cli collector add` (the dev bootstrap's path) and the admin API agree,
and that the connector's check answers from the same rows.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import httpx
import jwt as pyjwt
import pytest

pytestmark = pytest.mark.integration

COLLECTOR_DID = "did:web:collector.example.org"
UNIT_DIR = Path(__file__).resolve().parents[2]


def _run(args: list[str], env: dict) -> str:
    """An `ir-cli` step against the anchor's database; a failure stops the test."""
    result = subprocess.run(
        args, cwd=UNIT_DIR, env=env, capture_output=True, text=True, timeout=180
    )
    assert result.returncode == 0, f"{args}: {result.stdout}\n{result.stderr}"
    return result.stdout


def _headers(scope: str) -> dict[str, str]:
    now = int(time.time())
    token = pyjwt.encode(
        {
            "scope": scope,
            "sub": "it",
            "preferred_username": "service-account-svc-ds-connector-it",
            "iat": now,
            "exp": now + 300,
        },
        "integration-secret-long-enough-for-hs256-0000",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _check(anchor, holder_did: str, collector_did: str) -> dict:
    r = httpx.get(
        f"{anchor.url}/consent-collectors/check",
        params={"holder_did": holder_did, "collector_did": collector_did},
        headers=_headers("identity-registry.read"),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.rule("D-21")
def test_the_cli_the_admin_api_and_the_check_agree(anchor, holder):
    _run(
        [
            "uv",
            "run",
            "ir-cli",
            "owner",
            "add",
            "--id",
            "it-collector",
            "--name",
            "Integration collector",
            "--did",
            COLLECTOR_DID,
            "--status",
            "verified",
            "--verified-by",
            "integration-harness",
            "--evidence-ref",
            "tests/integration/test_consent_collectors.py",
        ],
        anchor.env,
    )
    assert _check(anchor, holder.did, COLLECTOR_DID)["accepted"] is False

    _run(
        [
            "uv",
            "run",
            "ir-cli",
            "collector",
            "add",
            "--holder-did",
            holder.did,
            "--collector-did",
            COLLECTOR_DID,
        ],
        anchor.env,
    )
    body = _check(anchor, holder.did, COLLECTOR_DID)
    assert body["accepted"] is True
    assert body["collector_owner"] == "it-collector"

    # The holder's own organisation, with nothing recorded.
    own = _check(anchor, holder.did, holder.did)
    assert own["accepted"] is True
    assert own["collector_owner"] == "holder-org"

    write = _headers("identity-registry.collectors.write")
    listed = httpx.get(
        f"{anchor.url}/admin/consent-collectors",
        params={"holder_did": holder.did},
        headers=write,
        timeout=10,
    ).json()
    assert [(r["collector_did"], r["status"]) for r in listed] == [
        (COLLECTOR_DID, "active")
    ]

    revoked = httpx.post(
        f"{anchor.url}/admin/consent-collectors/revoke",
        json={
            "holder_did": holder.did,
            "collector_did": COLLECTOR_DID,
            "reason": "integration revoke",
        },
        headers=write,
        timeout=10,
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revocation_reason"] == "integration revoke"
    assert _check(anchor, holder.did, COLLECTOR_DID)["accepted"] is False

    # And back, through the API this time: the same row.
    again = httpx.post(
        f"{anchor.url}/admin/consent-collectors",
        json={"holder_did": holder.did, "collector_did": COLLECTOR_DID},
        headers=write,
        timeout=10,
    )
    assert again.status_code == 201, again.text
    assert _check(anchor, holder.did, COLLECTOR_DID)["accepted"] is True


def test_a_participant_instance_does_not_serve_the_check(holder):
    r = httpx.get(
        f"{holder.url}/consent-collectors/check",
        params={"holder_did": holder.did, "collector_did": COLLECTOR_DID},
        headers=_headers("identity-registry.read"),
        timeout=10,
    )
    assert r.status_code == 404
