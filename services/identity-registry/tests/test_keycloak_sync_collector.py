"""Binding a login to a DID is an organisation's act, bounded to its members.

ADR-0026, amended 2026-10-05. `POST /admin/keycloak/sync` writes the
(realm, Keycloak user id) → DID mapping that a person route's login binding
reads (ADR-0024): whoever writes it decides which login acts as which person.
It was a grant of the shared `svc-ds-onboarding` client, across every
organisation. Now:

* the organisation's collector client asks for `identity-registry.keycloak.sync`
  alone, and the registry requires its own audience;
* it binds a login only to a DID holding a credential, not revoked, linked to
  that organisation — a membership row is not enough, because an organisation
  writes its own;
* it does not rebind a DID already bound to another login (the operator does);
* a suspended organisation binds nothing;
* the plain `svc-ds-onboarding` is accepted only under `DS_ENV=dev`;
* an administrator keeps the cross-organisation reach.
"""

from __future__ import annotations

import pytest
from conftest import CUSTODIAN_DID, make_headers
from test_collector_client import DSO, REC, TA_DID, _plain, _suspend
from test_membership_scope import org_client

ADMIN = make_headers("identity-registry.admin")
SYNC = "identity-registry.keycloak.sync"
CRED = "identity-registry.credentials.write"
WRITE = "identity-registry.memberships.write"
IR = "svc-ds-identity-registry"
DSO_DID = DSO["did"]
REALM = "example"
USER = "00000000-0000-4000-a000-000000000001"
OTHER_USER = "00000000-0000-4000-a000-000000000002"


def rec(scope: str = SYNC, **kw) -> dict:
    return org_client("example-rec", CUSTODIAN_DID, scope, **kw)


def dso(scope: str = SYNC, **kw) -> dict:
    return org_client("example-dso", DSO_DID, scope, **kw)


@pytest.fixture
async def seeded(client):
    for owner in (REC, DSO):
        r = await client.post("/admin/owners", json=owner, headers=ADMIN)
        assert r.status_code in (200, 201), r.text
    # The anchor's own DID: what issuance signs as.
    r = await client.post(
        "/admin/dids", json={"did": TA_DID, "did_type": "participant"}, headers=ADMIN
    )
    assert r.status_code in (200, 201), r.text
    return client


async def _issue(
    client, headers, *, linked=CUSTODIAN_DID, subject="member-001", role=None
):
    body = {"subject_id": subject, "linked_participant_did": linked}
    if role:
        body["role"] = role
    r = await client.post("/admin/credentials/data-subject", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _sync(client, headers, did, *, user=USER, email="a@example.org"):
    return await client.post(
        "/admin/keycloak/sync",
        json={
            "did": did,
            "keycloak_realm": REALM,
            "keycloak_user_id": user,
            "email": email,
        },
        headers=headers,
    )


@pytest.fixture
async def member(seeded):
    """A person the REC onboarded: its collector issued their credential."""
    return (await _issue(seeded, rec(CRED)))["subjectDid"]


async def test_a_collector_binds_a_login_to_its_own_member(seeded, member):
    r = await _sync(seeded, rec(), member)
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "synced", "did": member}


async def test_another_organisations_collector_may_not_bind_that_member(seeded, member):
    """Was a 200 for any holder of the grant: the mapping is who acts as whom."""
    r = await _sync(seeded, dso(), member)
    assert r.status_code == 403, r.text
    assert "own members" in r.text


async def test_a_membership_alone_does_not_make_somebody_your_member(seeded, member):
    """An organisation writes its own memberships, so a row it wrote is no proof."""
    r = await seeded.post(
        "/admin/memberships",
        json={"user_did": member, "organization_alias": "example-dso"},
        headers=dso(WRITE),
    )
    assert r.status_code == 201, r.text
    r = await _sync(seeded, dso(), member)
    assert r.status_code == 403, r.text


async def test_an_unknown_did_is_the_same_refusal_not_an_oracle(seeded):
    unknown = f"{CUSTODIAN_DID}:users:nobody"
    r = await _sync(seeded, rec(), unknown)
    assert r.status_code == 403, r.text
    # The administrator still learns that it does not exist.
    r = await _sync(seeded, ADMIN, unknown)
    assert r.status_code == 404, r.text


async def test_a_person_of_two_organisations_is_each_ones_member(seeded, member):
    """One human, one DID: the second organisation's credential (another role)
    reuses the DID in the first one's namespace, and that credential is what
    makes the person its member too — the namespace alone would refuse it."""
    second = await _issue(seeded, dso(CRED), linked=DSO_DID, role="consumer")
    assert second["subjectDid"] == member
    r = await _sync(seeded, rec(), member)
    assert r.status_code == 200, r.text
    # The same login, re-synced by the other organisation.
    r = await _sync(seeded, dso(), member, email="b@example.org")
    assert r.status_code == 200, r.text


async def test_the_same_role_twice_is_refused_not_the_first_organisations_credential(
    seeded, member
):
    """A second issuance for the **same role** matches the first organisation's
    credential (ds#30). Re-delivering it handed that credential to the second
    organisation; it is refused instead (`test_same_role_two_organisations`), so
    the second one holds no record of this person and binds nothing. A residual
    of ADR-0026's amendment, stated here so a change to either rule shows up."""
    r = await seeded.post(
        "/admin/credentials/data-subject",
        json={"subject_id": "member-001", "linked_participant_did": DSO_DID},
        headers=dso(CRED),
    )
    assert r.status_code == 409, r.text
    r = await _sync(seeded, dso(), member)
    assert r.status_code == 403, r.text


async def test_an_organisation_does_not_rebind_a_did_to_another_login(seeded, member):
    r = await _sync(seeded, rec(), member)
    assert r.status_code == 200, r.text
    # The same login with a corrected address: the ordinary re-sync.
    r = await _sync(seeded, rec(), member, email="new@example.org")
    assert r.status_code == 200, r.text
    # Another login: the operator's act, not the organisation's.
    r = await _sync(seeded, rec(), member, user=OTHER_USER)
    assert r.status_code == 403, r.text
    assert "operator" in r.text
    r = await _sync(seeded, ADMIN, member, user=OTHER_USER)
    assert r.status_code == 200, r.text


async def test_a_revoked_credential_makes_nobody_a_member(seeded):
    issued = await _issue(seeded, rec(CRED))
    r = await seeded.delete(
        f"/admin/credentials/{issued['credentialId']}", headers=rec(CRED)
    )
    assert r.status_code == 204, r.text
    r = await _sync(seeded, rec(), issued["subjectDid"])
    assert r.status_code == 403, r.text


async def test_a_suspended_organisation_binds_no_login(seeded, member):
    await _suspend(seeded, "example-rec")
    r = await _sync(seeded, rec(), member)
    assert r.status_code == 403, r.text
    assert "suspended" in r.text


@pytest.mark.parametrize("aud", [None, "svc-ds-connector", [IR, "svc-ds-connector"]])
async def test_a_sync_token_not_minted_for_this_registry_alone_is_refused(
    seeded, member, aud
):
    r = await _sync(seeded, rec(aud=aud), member)
    assert r.status_code == 403, r.text


async def test_the_connector_client_does_not_hold_the_grant(seeded, member):
    """The sync scope is a collector act; the org's connector client never asks
    for it, and a token without the scope is refused like any other."""
    r = await _sync(seeded, rec("identity-registry.read", kind="connector"), member)
    assert r.status_code == 403, r.text


async def test_the_plain_onboarding_client_binds_only_under_dev(
    seeded, member, monkeypatch
):
    monkeypatch.setenv("DS_ENV", "dev")
    r = await _sync(seeded, _plain(SYNC), member)
    assert r.status_code == 200, r.text
    monkeypatch.setenv("DS_ENV", "production")
    r = await _sync(seeded, _plain(SYNC), member)
    assert r.status_code == 403, r.text
    assert "svc-ds-collector" in r.text


async def test_the_administrator_binds_across_organisations(seeded, member):
    r = await _sync(seeded, ADMIN, member)
    assert r.status_code == 200, r.text
