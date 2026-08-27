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


@pytest.mark.rule("P-1")
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


@pytest.mark.rule("P-1")
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


# ── `GET /owners/resolve` — the operation the realm entry already names ───────
#
# `svc-ds-onboarding` is granted `identity-registry.organizations.read` with the
# annotation *"Resolve the bound community's organisation at boot"*, and the route
# that resolves an owner by alias refused it: the guard was
# `require_admin_or_read_scope`, from before these grants existed. The caller fell
# back to `GET /admin/owners/{alias}`, which matches on `Owner.id` and 404s on an
# alias — indistinguishable, on that side, from *no such organisation*.
#
# The fix is on the endpoint, not on the client. Adding `identity-registry.read`
# to the onboarding client would undo the split P6 made deliberately, because that
# scope also reaches the participant registry and the presentation queries. So the
# assertions come in pairs: the resolve works, and the participant registry stays
# shut to the same token.

@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [ORG_READ, "identity-registry.read", ADMIN])
async def test_owner_resolve_by_id(client, scope):
    """Three grants reach it, and each has a caller: the onboarding service by
    `organizations.read`, the connector's owner-alias registry by `read`, and
    `ir-cli` by `admin`."""
    await client.post(
        "/admin/owners",
        headers=h(ADMIN),
        json={"id": "example-org", "name": "Example", "aliases": ["example"]},
    )
    r = await client.get("/owners/resolve", params={"alias": "example-org"}, headers=h(scope))
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "example-org"


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [ORG_READ, "identity-registry.read", ADMIN])
async def test_owner_resolve_by_alias(client, scope):
    """The half `GET /admin/owners/{owner_id}` cannot do, and the reason this
    route exists: an alias is not an id, and 404 on an alias reads as *no such
    organisation* to a caller that only holds the alias."""
    await client.post(
        "/admin/owners",
        headers=h(ADMIN),
        json={"id": "example-org", "name": "Example", "aliases": ["example"]},
    )
    r = await client.get("/owners/resolve", params={"alias": "example"}, headers=h(scope))
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "example-org"


@pytest.mark.asyncio
async def test_owner_resolve_is_not_a_participant_registry_read(client):
    """The control for the two tests above.

    A permission fix that quietly widens is the failure this one is avoiding:
    resolving an organisation the caller was configured with is not authority to
    enumerate who else is in the dataspace, nor to touch the DID surface.
    """
    for path in ("/admin/participants", "/admin/participants/check"):
        r = await client.get(path, headers=h(ORG_READ))
        assert r.status_code == 403, f"{path} answered {r.status_code}, not 403"

    r = await client.post(
        "/admin/dids",
        headers=h(ORG_READ),
        json={"did": "did:web:x.example.test", "did_type": "participant"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_unrelated_scope_cannot_resolve_an_owner(client):
    r = await client.get(
        "/owners/resolve", params={"alias": "example"}, headers=h("some.other.scope")
    )
    assert r.status_code == 403


# ── `GET /agreements/current` — the same reading, applied to the neighbour ────
#
# The connector's circle check. It carried `require_admin_or_read_scope` while the
# two routes beside it carry `require_agreements_read`, so a grant whose whole
# description is *"read service agreements and their acceptances"* could read the
# agreement list and not the one a participant currently holds.

@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [AGREEMENTS_READ, "identity-registry.read", ADMIN])
async def test_agreements_current_accepts_the_agreements_grant(client, scope):
    """404 (no such participant) proves the guard let the request through — a 403
    would not distinguish *refused* from *no agreement*, and this route answers 404
    for both of its own not-found cases by design."""
    r = await client.get(
        "/agreements/current",
        params={"participant_did": "did:web:nobody.example.test"},
        headers=h(scope),
    )
    assert r.status_code != 403, r.text


@pytest.mark.asyncio
async def test_agreements_current_refuses_an_unrelated_grant(client):
    r = await client.get(
        "/agreements/current",
        params={"participant_did": "did:web:nobody.example.test"},
        headers=h(ORG_READ),
    )
    assert r.status_code == 403
