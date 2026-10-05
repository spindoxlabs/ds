"""Whose memberships a caller may change — and whose it may ask about.

`identity-registry.memberships.write` used to be checked alone: any holder could
make any DID a member of any organisation, and delete anybody's membership. The
connector's "the subject is a member of the organisation registering their
consent" check reads exactly these rows, so an unscoped write let one
organisation vouch for another's members.

The rule (`dependencies.authorize_membership_write`):

* `identity-registry.admin` — any organisation;
* an organisation's own client (`sub` = its DID) — since ADR-0026 its collector
  client, `svc-ds-collector-<alias>`, with a token minted for this registry —
  the owner carrying that DID, by any of its names, and nothing else, and only
  while that owner is verified;
* a plain service token — refused: it names no organisation.

And a person's `/memberships/check` holds in their own organisations only; a
service's (the connector's) is cross-organisation by design.
"""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest
from conftest import make_headers

ADMIN = make_headers("identity-registry.admin")
WRITE = "identity-registry.memberships.write"
READ = "identity-registry.membership.read"

REC = {
    "id": "example-rec",
    "type": "schema:Organization",
    "name": "Example REC",
    "did": "did:web:rec.example.org",
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
MEMBER = "did:web:users.example.org:ex-00001"


def _token(claims: dict) -> dict:
    now = int(time.time())
    token = pyjwt.encode(
        {"iat": now, "exp": now + 300, **claims}, "secret", algorithm="HS256"
    )
    return {"Authorization": f"Bearer {token}"}


IR = "svc-ds-identity-registry"


def org_client(
    alias: str,
    did: str,
    scope: str = WRITE,
    *,
    kind: str = "collector",
    aud: object = IR,
) -> dict:
    """A token from the organisation's client, shaped as Keycloak mints it.

    The collector client (`svc-ds-collector-<alias>`, ADR-0026) by default: it
    is the one holding `memberships.write`, and requesting the scope puts this
    registry in `aud`.
    """
    client_id = f"svc-ds-{kind}-{alias}"
    claims = {
        "scope": scope,
        "sub": did,
        "azp": client_id,
        "preferred_username": f"service-account-{client_id}",
    }
    if aud is not None:
        claims["aud"] = aud
    return _token(claims)


def person(organizations: dict[str, list[str]], roles: list[str] = ()) -> dict:
    return _token(
        {
            "sub": "00000000-0000-4000-a000-0000000000aa",
            "azp": "portal",
            "preferred_username": "someone",
            "email": "someone@example.org",
            "scope": "openid profile email",
            "realm_access": {"roles": list(roles)},
            "organization": {
                alias: {"groups": groups} for alias, groups in organizations.items()
            },
        }
    )


@pytest.fixture
async def seeded(client):
    for owner in (REC, DSO):
        r = await client.post("/admin/owners", json=owner, headers=ADMIN)
        assert r.status_code in (200, 201), r.text
    r = await client.post(
        "/admin/dids", json={"did": MEMBER, "did_type": "user"}, headers=ADMIN
    )
    assert r.status_code in (200, 201), r.text
    return client


async def _add(client, org: str, headers: dict):
    return await client.post(
        "/admin/memberships",
        json={"user_did": MEMBER, "organization_alias": org},
        headers=headers,
    )


async def _is_member(client, org: str) -> bool:
    r = await client.get(
        "/memberships/check",
        params={"user_did": MEMBER, "organization": org},
        headers=make_headers(READ),
    )
    assert r.status_code == 200, r.text
    return r.json()["member"]


# ── create ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("spelling", ["example-rec", "ex-rec"])
async def test_an_organisation_client_registers_a_member_of_its_own(seeded, spelling):
    r = await _add(seeded, spelling, org_client("example-rec", REC["did"]))
    assert r.status_code == 201, r.text
    assert r.json()["organization_alias"] == "example-rec"


@pytest.mark.asyncio
async def test_an_organisation_client_cannot_register_a_member_of_another(seeded):
    """The finding: one organisation vouching for another's members."""
    r = await _add(seeded, "example-dso", org_client("example-rec", REC["did"]))
    assert r.status_code == 403, r.text
    assert await _is_member(seeded, "example-dso") is False


@pytest.mark.asyncio
async def test_a_plain_service_token_cannot_register_a_membership(seeded):
    """It names no organisation, so there is nothing to bound it to."""
    r = await _add(seeded, "example-rec", make_headers(WRITE))
    assert r.status_code == 403, r.text
    assert await _is_member(seeded, "example-rec") is False


@pytest.mark.asyncio
async def test_an_organisation_client_whose_did_no_owner_carries_is_refused(seeded):
    r = await _add(
        seeded, "example-rec", org_client("example-rec", "did:web:other.example.org")
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_the_client_id_does_not_choose_the_organisation(seeded):
    """The organisation is the owner of the token's participant context; a client
    named after the target organisation with another's `sub` gains nothing."""
    r = await _add(seeded, "example-dso", org_client("example-dso", REC["did"]))
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_admin_still_registers_in_any_organisation(seeded):
    assert (await _add(seeded, "example-dso", ADMIN)).status_code == 201
    assert (await _add(seeded, "example-rec", ADMIN)).status_code == 201


@pytest.mark.asyncio
async def test_a_person_without_a_grant_in_the_organisation_is_refused(seeded):
    """No organisation bundle grants `memberships.write`; an organisation group
    naming it grants nothing, so the route guard already refuses."""
    r = await _add(seeded, "example-rec", person({"example-rec": [WRITE]}))
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_a_platform_admin_registers_in_any_organisation(seeded):
    r = await _add(seeded, "example-dso", person({}, roles=["platform-admin"]))
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_a_refused_create_reveals_nothing_about_the_did(seeded):
    """Authorised before the 404/409 checks: outside its organisation a caller
    gets 403 whether or not the DID or the row exists."""
    r = await seeded.post(
        "/admin/memberships",
        json={
            "user_did": "did:web:nobody.example.org",
            "organization_alias": "example-dso",
        },
        headers=org_client("example-rec", REC["did"]),
    )
    assert r.status_code == 403, r.text


# ── delete ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_organisation_client_removes_a_member_of_its_own(seeded):
    assert (await _add(seeded, "example-rec", ADMIN)).status_code == 201
    r = await seeded.delete(
        f"/admin/memberships/{MEMBER}/ex-rec",
        headers=org_client("example-rec", REC["did"]),
    )
    assert r.status_code == 204, r.text
    assert await _is_member(seeded, "example-rec") is False


@pytest.mark.asyncio
async def test_an_organisation_client_cannot_remove_a_member_of_another(seeded):
    assert (await _add(seeded, "example-dso", ADMIN)).status_code == 201
    r = await seeded.delete(
        f"/admin/memberships/{MEMBER}/example-dso",
        headers=org_client("example-rec", REC["did"]),
    )
    assert r.status_code == 403, r.text
    assert await _is_member(seeded, "example-dso") is True


@pytest.mark.asyncio
async def test_a_plain_service_token_cannot_remove_a_membership(seeded):
    assert (await _add(seeded, "example-rec", ADMIN)).status_code == 201
    r = await seeded.delete(
        f"/admin/memberships/{MEMBER}/example-rec", headers=make_headers(WRITE)
    )
    assert r.status_code == 403, r.text
    assert await _is_member(seeded, "example-rec") is True


@pytest.mark.asyncio
async def test_a_refused_delete_is_403_not_404(seeded):
    """A missing row outside the caller's organisation must not read differently
    from a present one."""
    r = await seeded.delete(
        f"/admin/memberships/{MEMBER}/example-dso",
        headers=org_client("example-rec", REC["did"]),
    )
    assert r.status_code == 403, r.text


# ── check ────────────────────────────────────────────────────────────────────


async def _check(client, org: str, headers: dict):
    return await client.get(
        "/memberships/check",
        params={"user_did": MEMBER, "organization": org},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_a_person_checks_membership_in_their_own_organisation(seeded):
    assert (await _add(seeded, "example-rec", ADMIN)).status_code == 201
    r = await _check(
        seeded, "ex-rec", person({"example-rec": ["ds-participant-admin"]})
    )
    assert r.status_code == 200, r.text
    assert r.json()["member"] is True


@pytest.mark.asyncio
async def test_a_person_cannot_probe_another_organisations_members(seeded):
    """`ds-participant-admin` in one organisation is not a membership oracle for
    every other."""
    assert (await _add(seeded, "example-dso", ADMIN)).status_code == 201
    r = await _check(
        seeded, "example-dso", person({"example-rec": ["ds-participant-admin"]})
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_an_organisation_client_checks_another_organisation(seeded):
    """The connector asks about a collector's or a recipient's members — never
    only its own. Bounding services here would break the consent path."""
    assert (await _add(seeded, "example-dso", ADMIN)).status_code == 201
    r = await _check(seeded, "example-dso", org_client("example-rec", REC["did"], READ))
    assert r.status_code == 200, r.text
    assert r.json()["member"] is True


@pytest.mark.asyncio
async def test_a_platform_admin_checks_any_organisation(seeded):
    r = await _check(seeded, "example-dso", person({}, roles=["platform-admin"]))
    assert r.status_code == 200, r.text
