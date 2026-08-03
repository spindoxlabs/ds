"""Onboarding authorization: narrow grants work, and admin still satisfies them.

`identity-registry.admin` used to be the only way to reach any of this, which meant
an operator console could not be given "review applications" without also being
given DID and key management. These scopes name what they permit.

Two properties matter and both are easy to break:

1. a narrow grant reaches its own endpoints and **nothing else** — otherwise the
   split is decoration;
2. `identity-registry.admin` still reaches everything, because `ir-cli` and the
   bootstrap authenticate with it and a regression there breaks deployment.
"""
from __future__ import annotations

import pytest
from conftest import make_headers, register_did

ORG_READ = "identity-registry.organizations.read"
ORG_WRITE = "identity-registry.organizations.write"
ORG_PROMOTE = "identity-registry.organizations.promote"
AGREEMENTS_READ = "identity-registry.agreements.read"
PARTICIPANTS_WRITE = "identity-registry.participants.write"
CREDENTIALS_WRITE = "identity-registry.credentials.write"
MEMBERSHIPS_WRITE = "identity-registry.memberships.write"
KEYCLOAK_SYNC = "identity-registry.keycloak.sync"
ADMIN = "identity-registry.admin"


def h(scope: str) -> dict:
    return make_headers(scope=scope)


# ── the narrow grants reach their own endpoints ───────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [ORG_READ, ADMIN])
async def test_org_read_lists_applications(client, scope):
    r = await client.get("/admin/organizations/applications", headers=h(scope))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [ORG_WRITE, ADMIN])
async def test_org_write_registers_an_application(client, scope):
    r = await client.post(
        "/admin/organizations/applications",
        headers=h(scope),
        json={
            "alias": f"acme-{scope[-5:]}",
            "legal_name": "Acme",
            "roles": ["consumer"],
        },
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [AGREEMENTS_READ, ADMIN, "identity-registry.read"])
async def test_agreements_read_lists_agreements(client, scope):
    r = await client.get("/agreements", headers=h(scope))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [PARTICIPANTS_WRITE, ADMIN])
async def test_participants_write_registers_a_participant(client, db_session, scope):
    # Registering is now separate from creating: the DID exists because its
    # holder enrolled (`D-51`), and this route records the participant.
    await register_did(db_session, f"did:web:{scope.split('.')[-1]}.example.test")
    r = await client.post(
        "/admin/participants",
        headers=h(scope),
        json={
            "did": f"did:web:{scope.split('.')[-1]}.example.test",
            "dsp_address": "http://example.test/protocol/2025-1",
            "roles": ["consumer"],
        },
    )
    assert r.status_code in (200, 201), r.text


# ── and reach nothing else ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_org_read_cannot_write(client):
    """Read access to the review queue is not permission to register anything."""
    r = await client.post(
        "/admin/organizations/applications",
        headers=h(ORG_READ),
        json={"alias": "acme-nope", "legal_name": "Acme", "roles": ["consumer"]},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_org_write_cannot_promote(client):
    """Marking an application verified is reviewable clerical work; promotion turns
    an applicant into a DSP counterparty. Deliberately separate grants."""
    r = await client.post(
        "/admin/owners/acme/promote",
        headers=h(ORG_WRITE),
        json={"dsp_address": "http://example.test/protocol/2025-1"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_org_grants_do_not_reach_participant_writes(client):
    r = await client.post(
        "/admin/participants",
        headers=h(ORG_WRITE),
        json={
            "did": "did:web:sneaky.example.test",
            "dsp_address": "http://example.test/protocol/2025-1",
            "roles": ["consumer"],
        },
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_onboarding_grants_do_not_reach_key_management(client):
    """The reason for the split: an onboarding reviewer must not inherit the DID and
    key surface that `identity-registry.admin` carries."""
    for scope in (
        ORG_READ,
        ORG_WRITE,
        ORG_PROMOTE,
        AGREEMENTS_READ,
        CREDENTIALS_WRITE,
        MEMBERSHIPS_WRITE,
        KEYCLOAK_SYNC,
    ):
        r = await client.post(
            "/admin/dids",
            headers=h(scope),
            json={"did": "did:web:x.example.test", "did_type": "participant"},
        )
        assert r.status_code == 403, f"{scope} reached DID creation"


@pytest.mark.asyncio
async def test_unrelated_scope_is_refused(client):
    r = await client.get(
        "/admin/organizations/applications", headers=h("some.other.scope")
    )
    assert r.status_code == 403


# ── T28 — what an onboarding service actually does ────────────────────────────
#
# These three are the reason `svc-ds-onboarding` had to hold
# `identity-registry.admin`: P6 split organisations and agreements out of it but
# left credentials, memberships and keycloak-sync behind, which is most of what
# such a service calls. Dropping the admin grant is only safe if each of these
# reaches its own endpoints and none reaches anything else.

MEMBER_DID = "did:web:users.example.test:someone"


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [MEMBERSHIPS_WRITE, ADMIN])
async def test_memberships_write_registers_a_membership(client, scope):
    """404 (unknown DID) proves the guard let the request through — the point
    here is reachability, not the endpoint's own preconditions."""
    r = await client.post(
        "/admin/memberships",
        headers=h(scope),
        json={
            "user_did": f"{MEMBER_DID}-{scope.split('.')[-1]}",
            "organization_alias": "example-org",
        },
    )
    assert r.status_code != 403, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [KEYCLOAK_SYNC, ADMIN])
async def test_keycloak_sync_is_reachable(client, scope):
    """404 (unknown DID) proves the guard let the request through; a 403 would
    not distinguish "refused" from "no such DID"."""
    r = await client.post(
        "/admin/keycloak/sync",
        headers=h(scope),
        json={
            "did": "did:web:users.example.test:nobody",
            "realm": "dataspaces",
            "user_id": "00000000-0000-4000-a000-000000000001",
        },
    )
    assert r.status_code != 403, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [CREDENTIALS_WRITE, ADMIN])
async def test_credentials_write_reaches_data_subject_issuance(client, scope):
    r = await client.post(
        "/admin/credentials/data-subject",
        headers=h(scope),
        json={"subject_id": "someone", "role": "DataSubject"},
    )
    assert r.status_code != 403, r.text


@pytest.mark.asyncio
async def test_credentials_write_cannot_register_a_participant(client):
    """Issuing a person's credential is not authority to admit a DSP counterparty."""
    r = await client.post(
        "/admin/participants",
        headers=h(CREDENTIALS_WRITE),
        json={
            "did": "did:web:sneaky2.example.test",
            "dsp_address": "http://example.test/protocol/2025-1",
            "roles": ["consumer"],
        },
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_memberships_write_cannot_enumerate_the_roster(client):
    """Registering a membership is not permission to read who belongs to what —
    that stays on admin, and `membership.read` answers one pair at a time."""
    r = await client.get("/admin/memberships", headers=h(MEMBERSHIPS_WRITE))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_keycloak_sync_cannot_issue_a_credential(client):
    r = await client.post(
        "/admin/credentials/data-subject",
        headers=h(KEYCLOAK_SYNC),
        json={"subject_id": "someone", "role": "DataSubject"},
    )
    assert r.status_code == 403
