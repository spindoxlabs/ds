"""An organisation's collector client, its audience, and a suspended organisation.

ADR-0026. The plain `svc-ds-onboarding` client's grants that act for one
organisation moved to that organisation's collector client,
`svc-ds-collector-<alias>`: `sub` = the organisation's DID, no default scope, and
each grant an optional scope that adds exactly one audience. So here:

* a collector token, minted for this registry, writes its own organisation's
  members and issues and revokes credentials linked to its own organisation;
* a token not minted for this registry (no `aud`), or minted for it **and**
  another ds service, is refused;
* a plain service token doing an organisation's credential act is refused
  outside `DS_ENV=dev`;
* a **suspended** organisation writes no membership, its rows are not counted by
  `/memberships/check`, and it is not accepted as collecting for itself.
"""

from __future__ import annotations

import pytest
from conftest import CUSTODIAN_DID, make_headers
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_membership_scope import org_client

from identity_registry.services import consent_collectors

ADMIN = make_headers("identity-registry.admin")
WRITE = "identity-registry.memberships.write"
CRED = "identity-registry.credentials.write"
IR = "svc-ds-identity-registry"
TA_DID = "did:web:trust-anchor.dataspaces.localhost"
MEMBER = "did:web:users.example.org:ex-00001"

REC = {
    "id": "example-rec",
    "type": "schema:Organization",
    "name": "Example REC",
    "did": CUSTODIAN_DID,
    "aliases": ["ex-rec"],
    "status": "verified",
    "verified_by": "test",
}
DSO = {
    "id": "example-dso",
    "type": "schema:Organization",
    "name": "Example DSO",
    "did": "did:web:dso.example.org",
    "aliases": [],
    "status": "verified",
    "verified_by": "test",
}


def collector(
    scope: str = WRITE, *, did: str = CUSTODIAN_DID, alias="example-rec", **kw
):
    return org_client(alias, did, scope, **kw)


@pytest.fixture
async def seeded(client):
    for owner in (REC, DSO):
        r = await client.post("/admin/owners", json=owner, headers=ADMIN)
        assert r.status_code in (200, 201), r.text
    for did, kind in ((MEMBER, "user"), (TA_DID, "participant")):
        r = await client.post(
            "/admin/dids", json={"did": did, "did_type": kind}, headers=ADMIN
        )
        assert r.status_code in (200, 201), r.text
    return client


async def _suspend(client, owner_id: str):
    r = await client.patch(
        f"/admin/owners/{owner_id}", json={"status": "suspended"}, headers=ADMIN
    )
    assert r.status_code == 200, r.text


async def _add(client, headers, org="example-rec"):
    return await client.post(
        "/admin/memberships",
        json={"user_did": MEMBER, "organization_alias": org},
        headers=headers,
    )


async def _is_member(client, org="example-rec") -> bool:
    r = await client.get(
        "/memberships/check",
        params={"user_did": MEMBER, "organization": org},
        headers=make_headers("identity-registry.membership.read"),
    )
    assert r.status_code == 200, r.text
    return r.json()["member"]


# ── memberships ──────────────────────────────────────────────────────────────


async def test_a_collector_token_registers_a_member_of_its_own_organisation(seeded):
    """Was a 403: the collector prefix was a plain service, naming no organisation."""
    r = await _add(seeded, collector())
    assert r.status_code == 201, r.text
    assert await _is_member(seeded) is True
    r = await seeded.delete(
        f"/admin/memberships/{MEMBER}/example-rec", headers=collector()
    )
    assert r.status_code == 204, r.text


async def test_a_collector_token_cannot_register_for_another_organisation(seeded):
    r = await _add(seeded, collector(), org="example-dso")
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("kind", ["collector", "connector"])
async def test_a_token_not_minted_for_this_registry_is_refused(seeded, kind):
    """Optional scopes do not stop replay; the audience does."""
    for aud in (None, "svc-ds-connector"):
        r = await _add(seeded, collector(kind=kind, aud=aud))
        assert r.status_code == 403, r.text
        assert "not minted for this service" in r.text
    assert await _is_member(seeded) is False


async def test_a_collector_token_minted_for_two_services_is_refused(seeded):
    r = await _add(seeded, collector(aud=[IR, "svc-ds-connector"]))
    assert r.status_code == 403, r.text
    assert "one act at a time" in r.text


@pytest.mark.parametrize("kind", ["collector", "connector"])
async def test_a_suspended_organisation_writes_no_membership(seeded, kind):
    r = await _add(seeded, ADMIN)
    assert r.status_code == 201, r.text
    await _suspend(seeded, "example-rec")

    r = await _add(seeded, collector(kind=kind))
    assert r.status_code == 403, r.text
    r = await seeded.delete(
        f"/admin/memberships/{MEMBER}/example-rec", headers=collector(kind=kind)
    )
    assert r.status_code == 403, r.text
    # The administrator still can — that is how a suspended organisation's
    # rows are cleaned up.
    r = await seeded.delete(f"/admin/memberships/{MEMBER}/example-rec", headers=ADMIN)
    assert r.status_code == 204, r.text


async def test_a_suspended_organisations_rows_are_not_counted(seeded):
    r = await _add(seeded, ADMIN)
    assert r.status_code == 201, r.text
    assert await _is_member(seeded) is True
    await _suspend(seeded, "example-rec")
    assert await _is_member(seeded) is False
    assert await _is_member(seeded, "ex-rec") is False


async def test_a_suspended_holder_does_not_collect_for_itself(seeded, engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        answer = await consent_collectors.check(db, CUSTODIAN_DID, CUSTODIAN_DID)
        assert answer.accepted
    await _suspend(seeded, "example-rec")
    async with factory() as db:
        answer = await consent_collectors.check(db, CUSTODIAN_DID, CUSTODIAN_DID)
    assert not answer.accepted
    assert answer.reason == "the holder is not a verified organisation"


# ── credentials ──────────────────────────────────────────────────────────────


async def _issue(client, headers, linked=CUSTODIAN_DID, subject="member-001"):
    return await client.post(
        "/admin/credentials/data-subject",
        json={"subject_id": subject, "linked_participant_did": linked},
        headers=headers,
    )


async def test_a_collector_issues_and_revokes_its_own_members_credential(seeded):
    r = await _issue(seeded, collector(CRED))
    assert r.status_code == 201, r.text
    cred_id = r.json()["credentialId"]
    r = await seeded.delete(f"/admin/credentials/{cred_id}", headers=collector(CRED))
    assert r.status_code == 204, r.text


async def test_a_collector_may_not_issue_for_another_organisation(seeded):
    r = await _issue(seeded, collector(CRED), linked="did:web:dso.example.org")
    assert r.status_code == 403, r.text
    r = await _issue(seeded, collector(CRED), linked=None)
    assert r.status_code == 403, r.text


async def test_a_collector_may_not_revoke_another_organisations_credential(seeded):
    r = await _issue(seeded, ADMIN)
    assert r.status_code == 201, r.text
    cred_id = r.json()["credentialId"]
    other = collector(CRED, did="did:web:dso.example.org", alias="example-dso")
    r = await seeded.delete(f"/admin/credentials/{cred_id}", headers=other)
    assert r.status_code == 403, r.text
    # Not an oracle: an unknown id is the same refusal.
    r = await seeded.delete("/admin/credentials/urn:uuid:nope", headers=other)
    assert r.status_code == 403, r.text


async def test_a_suspended_organisation_issues_no_credential(seeded):
    await _suspend(seeded, "example-rec")
    r = await _issue(seeded, collector(CRED))
    assert r.status_code == 403, r.text


async def test_a_credential_token_not_minted_for_this_registry_is_refused(seeded):
    r = await _issue(seeded, collector(CRED, aud="svc-ds-provenance"))
    assert r.status_code == 403, r.text


def _plain(scope: str, aud=IR) -> dict:
    import time

    import jwt as pyjwt

    now = int(time.time())
    token = pyjwt.encode(
        {
            "iat": now,
            "exp": now + 300,
            "sub": "svc-uuid",
            "azp": "svc-ds-onboarding",
            "preferred_username": "service-account-svc-ds-onboarding",
            "scope": scope,
            "aud": aud,
        },
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


async def test_a_plain_onboarding_token_issues_only_under_dev(seeded, monkeypatch):
    """The transition: accepted, logged, in dev; refused anywhere else."""
    monkeypatch.setenv("DS_ENV", "dev")
    r = await _issue(seeded, _plain(CRED))
    assert r.status_code == 201, r.text
    monkeypatch.setenv("DS_ENV", "production")
    r = await _issue(seeded, _plain(CRED), subject="member-002")
    assert r.status_code == 403, r.text
    assert "svc-ds-collector" in r.text
