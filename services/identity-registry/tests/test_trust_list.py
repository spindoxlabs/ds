"""The dataspace's trust list — `DSSC-TRF-05`, `-07`, `-17`, `-19`, `-21`.

The document a stranger reads first. Everything else in the identity chain
answers *"is this credential valid"*; this answers the question underneath it —
*"is its issuer somebody this dataspace accredited, and for what"*.

Most of these assert things the specification says in as many words and that an
implementation would otherwise get subtly wrong: that revoked entries stay
listed, and that an entry with no scope is refused rather than treated as
trusted-for-everything.
"""

from __future__ import annotations

import pytest
from conftest import make_headers

from identity_registry.config import Settings
from identity_registry.services import trust_list

PROMOTE = make_headers(scope="identity-registry.organizations.promote")
WRITE = make_headers(scope="identity-registry.organizations.write")

ANCHOR = "did:web:trust-anchor.dataspaces.localhost"
CAB = "did:web:cab.example.test"


def settings() -> Settings:
    return Settings(_env_file=None, oidc_issuer_url=None)


async def seed_anchor(db_session):
    entry = await trust_list.ensure_own_anchor(db_session, settings())
    await db_session.commit()
    return entry


# ── Published, and readable by a stranger ─────────────────────────


@pytest.mark.rule("P-12a")
@pytest.mark.asyncio
async def test_the_list_is_public(client, db_session):
    """`P-13`'s reasoning, applied to trust rather than revocation.

    A counterparty decides whether to accept a credential **before** it has any
    relationship with this dataspace, so a list behind a token could not be read
    by the party that needs it most.
    """
    await seed_anchor(db_session)
    r = await client.get("/trust")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "DataspaceTrustList"
    assert [i["id"] for i in body["issuers"]] == [ANCHOR]


@pytest.mark.asyncio
async def test_the_list_says_what_it_conforms_to(client, db_session):
    """DSSC names no format, so the document names its own requirements.

    A reader from another dataspace gets enough to tell what they are holding
    without having read our rulebook first.
    """
    await seed_anchor(db_session)
    body = (await client.get("/trust")).json()
    assert set(body["conformsTo"]) >= {"DSSC-TRF-05", "DSSC-TRF-17"}
    assert body["dataspace"]


@pytest.mark.rule("P-12a")
@pytest.mark.asyncio
async def test_every_entry_names_where_its_key_resolves(client, db_session):
    """So a verifier checks a signature against the issuer's **DID document**.

    The same rule `P-8a` states for presentation queries: never against a key
    somebody handed you.
    """
    await seed_anchor(db_session)
    entry = (await client.get("/trust")).json()["issuers"][0]
    assert entry["didDocument"].endswith(f"/dids/{ANCHOR}/did.json")


@pytest.mark.rule("P-12a")
@pytest.mark.asyncio
async def test_the_anchor_lists_itself_after_bootstrap(db_session):
    """A dataspace that does not accredit its own anchor publishes an empty list.

    Every credential it has issued would then read as coming from an unlisted
    issuer — which is what `ir-cli bootstrap` seeding this prevents.
    """
    entry = await seed_anchor(db_session)
    assert entry.role == trust_list.TRUST_ANCHOR
    assert set(entry.scope_of_attestation) == set(trust_list.ANCHOR_SCOPE)

    again = await trust_list.ensure_own_anchor(db_session, settings())
    assert again.did == entry.did, "idempotent"


# ── `TRF-19`: a scope is required, and empty is not a wildcard ─────


@pytest.mark.rule("P-12b")
@pytest.mark.asyncio
async def test_an_entry_with_no_scope_is_refused(client, db_session):
    """The single most dangerous thing this list could allow by omission.

    `DSSC-TRF-19` accepts a trust anchor *in relation to a specific scope of
    attestation*. An empty scope defaulted to "everything" would make the most
    permissive possible entry the easiest one to create.
    """
    await seed_anchor(db_session)
    r = await client.post(
        "/admin/trust/issuers",
        json={
            "did": CAB,
            "name": "Conformity Assessment Body",
            "role": "trust-service-provider",
            "scope_of_attestation": [],
            "derives_authority_from": ANCHOR,
        },
        headers=PROMOTE,
    )
    assert r.status_code == 422


@pytest.mark.rule("P-12b")
@pytest.mark.asyncio
async def test_a_trust_service_provider_must_name_its_authority(client, db_session):
    """`DSSC-TRF-21` — a designated issuer *deriving authority from* an anchor."""
    await seed_anchor(db_session)
    r = await client.post(
        "/admin/trust/issuers",
        json={
            "did": CAB,
            "name": "Conformity Assessment Body",
            "role": "trust-service-provider",
            "scope_of_attestation": ["ComplianceCredential"],
        },
        headers=PROMOTE,
    )
    assert r.status_code == 422
    assert "authority" in r.text


@pytest.mark.rule("P-12b")
@pytest.mark.asyncio
async def test_a_provider_derives_authority_and_says_so(client, db_session):
    await seed_anchor(db_session)
    r = await client.post(
        "/admin/trust/issuers",
        json={
            "did": CAB,
            "name": "Conformity Assessment Body",
            "role": "trust-service-provider",
            "scope_of_attestation": ["ComplianceCredential"],
            "derives_authority_from": ANCHOR,
        },
        headers=PROMOTE,
    )
    assert r.status_code == 201

    entry = next(
        i for i in (await client.get("/trust")).json()["issuers"] if i["id"] == CAB
    )
    assert entry["derivesAuthorityFrom"] == ANCHOR
    assert entry["scopeOfAttestation"] == ["ComplianceCredential"]


# ── `TRF-05`: revoked entries stay listed ─────────────────────────


@pytest.mark.rule("P-12a", "P-12c")
@pytest.mark.asyncio
async def test_a_revoked_issuer_stays_in_the_list(client, db_session):
    """The requirement says *including revoked ones*, and the reason matters.

    A list that forgets what it used to trust cannot answer whether a credential
    already in circulation was legitimate when it was issued. Deleting the row
    would silently re-open every past credential from that issuer.
    """
    await seed_anchor(db_session)
    await client.post(
        "/admin/trust/issuers",
        json={
            "did": CAB,
            "name": "Conformity Assessment Body",
            "role": "trust-service-provider",
            "scope_of_attestation": ["ComplianceCredential"],
            "derives_authority_from": ANCHOR,
        },
        headers=PROMOTE,
    )

    r = await client.delete(
        f"/admin/trust/issuers/{CAB}?reason=accreditation+withdrawn",
        headers=PROMOTE,
    )
    assert r.status_code == 200

    issuers = {i["id"]: i for i in (await client.get("/trust")).json()["issuers"]}
    assert CAB in issuers, "a revoked issuer must still be listed"
    assert issuers[CAB]["status"] == "revoked"
    assert issuers[CAB]["revocationReason"] == "accreditation withdrawn"
    assert issuers[CAB]["revokedAt"]


@pytest.mark.rule("P-12c")
@pytest.mark.asyncio
async def test_revocation_requires_a_reason(client, db_session):
    """*"Removed, no reason given"* answers nothing for a verifier holding
    credentials from that issuer."""
    await seed_anchor(db_session)
    r = await client.delete(f"/admin/trust/issuers/{ANCHOR}", headers=PROMOTE)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_revoking_twice_is_idempotent(client, db_session):
    await seed_anchor(db_session)
    first = await client.delete(
        f"/admin/trust/issuers/{ANCHOR}?reason=compromised", headers=PROMOTE
    )
    second = await client.delete(
        f"/admin/trust/issuers/{ANCHOR}?reason=compromised+again", headers=PROMOTE
    )
    assert first.status_code == second.status_code == 200
    # The first reason stands: a second call must not rewrite the record of why.
    assert second.json()["reason"] == "compromised"


# ── Authorisation ─────────────────────────────────────────────────


@pytest.mark.rule("P-12a")
@pytest.mark.asyncio
async def test_accrediting_needs_promote_not_write(client, db_session):
    """Saying "this dataspace stands behind that entity" is at least as
    consequential as admitting a counterparty."""
    await seed_anchor(db_session)
    r = await client.post(
        "/admin/trust/issuers",
        json={
            "did": CAB,
            "name": "CAB",
            "role": "trust-service-provider",
            "scope_of_attestation": ["ComplianceCredential"],
            "derives_authority_from": ANCHOR,
        },
        headers=WRITE,
    )
    assert r.status_code == 403


@pytest.mark.rule("P-12c")
@pytest.mark.asyncio
async def test_an_unknown_issuer_cannot_be_revoked(client, db_session):
    await seed_anchor(db_session)
    r = await client.delete(
        "/admin/trust/issuers/did:web:nobody.example.test?reason=never+accredited",
        headers=PROMOTE,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_a_participant_instance_does_not_publish_a_trust_list(monkeypatch):
    """The list is a **governance** statement, so only the anchor makes it.

    A participant publishing one would be a party asserting who the dataspace
    accredits, which is not theirs to say.
    """
    from fastapi.testclient import TestClient

    from identity_registry.config import get_settings
    from identity_registry.main import create_app

    monkeypatch.setenv("IDENTITY_REGISTRY_ROLE", "participant")
    monkeypatch.setenv("IDENTITY_REGISTRY_PARTICIPANT_DID", "did:web:rec.example.test")
    get_settings.cache_clear()
    try:
        paths = set(TestClient(create_app()).get("/openapi.json").json()["paths"])
        assert "/trust" not in paths
    finally:
        get_settings.cache_clear()
