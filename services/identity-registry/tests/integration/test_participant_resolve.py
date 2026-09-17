"""`GET /participants/resolve` against a migrated anchor and a really enrolled
participant (`C-19`).

The unit suite seeds a `Participant` row by hand. This proves the route answers
for a participant that got there the way a real one does, through enrolment,
on the schema Alembic builds, and that it agrees with the admin listing it
replaces for the connector.
"""

from __future__ import annotations

import time
from urllib.parse import quote

import httpx
import jwt as pyjwt
import pytest

pytestmark = pytest.mark.integration


def _headers(scope: str) -> dict[str, str]:
    now = int(time.time())
    token = pyjwt.encode(
        {
            "scope": scope,
            "sub": "it",
            # A client-credentials token: `scope` authorises only a service.
            "preferred_username": "service-account-svc-ds-connector-it",
            "iat": now,
            "exp": now + 300,
        },
        "integration-secret-long-enough-for-hs256-0000",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.rule("C-19")
def test_an_enrolled_participant_resolves_as_the_admin_listing_has_it(anchor, holder):
    read = _headers("identity-registry.read")
    resolved = httpx.get(
        f"{anchor.url}/participants/resolve",
        params={"did": holder.did},
        headers=read,
        timeout=10,
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert set(body) == {"did", "dsp_address", "roles"}

    listing = httpx.get(
        f"{anchor.url}/admin/participants", headers=read, timeout=10
    ).json()
    row = next(p for p in listing if p["did"] == holder.did)
    assert body == {
        "did": row["did"],
        "dsp_address": row["dsp_address"],
        "roles": row["roles"],
    }
    assert "provider" in body["roles"]

    if body["dsp_address"]:
        by_address = httpx.get(
            f"{anchor.url}/participants/resolve",
            params={"dsp_address": body["dsp_address"]},
            headers=read,
            timeout=10,
        )
        assert by_address.json() == body


def test_an_unknown_did_is_a_404_and_the_route_needs_the_read_scope(anchor, holder):
    unknown = httpx.get(
        f"{anchor.url}/participants/resolve",
        params={"did": f"{holder.did}:nobody"},
        headers=_headers("identity-registry.read"),
        timeout=10,
    )
    assert unknown.status_code == 404
    refused = httpx.get(
        f"{anchor.url}/participants/resolve?did={quote(holder.did, safe='')}",
        headers=_headers("identity-registry.membership.read"),
        timeout=10,
    )
    assert refused.status_code == 403


def test_a_participant_instance_does_not_serve_it(holder):
    """Anchor-only: a participant holds no dataspace-wide registry."""
    r = httpx.get(
        f"{holder.url}/participants/resolve",
        params={"did": holder.did},
        headers=_headers("identity-registry.read"),
        timeout=10,
    )
    assert r.status_code == 404
