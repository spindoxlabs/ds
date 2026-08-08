"""Block D — organisation onboarding tests.

Covers the credential builder, the full API lifecycle (register → verify →
agreement → issue-credential → promote), both gates (issue-before-agreement and
promote-before-credential fail closed), the agreement acceptance evidence, and
suspend (credential revoked + participant deactivated).
"""

from __future__ import annotations

import pytest
from conftest import make_headers, register_enrolled

from identity_registry.services.crypto import generate_key_pair
from identity_registry.services.vc import (
    build_organization_credential,
    sign_credential,
)

HEADERS = make_headers()
TA_DID = "did:web:trust-anchor.dataspaces.localhost"
ORG_DID = "did:web:acme.dataspaces.localhost"


# ── Credential builder ────────────────────────────────────────────


def test_build_organization_credential_shape():
    vc = build_organization_credential(
        issuer_did=TA_DID,
        subject_did=ORG_DID,
        legal_name="Acme Energy",
        registration_number="IT12345678901",
        registration_type="vatID",
        hq_country_code="IT-TN",
        legal_country_code="IT-TN",
        roles=["consumer"],
        allowed_scopes=["dataspaces.query"],
        credentials_context_url="https://x/ns",
        dataspace_uri="https://x/ds",
        status_list_credential_url="https://x/status/1",
        suspension_list_credential_url="https://x/status/2",
        status_list_index=7,
        parent_organizations=["did:web:parent"],
        dsp_address="https://acme/dsp",
    )
    assert vc["type"] == ["VerifiableCredential", "OrganizationCredential"]
    subj = vc["credentialSubject"]
    assert subj["legalName"] == "Acme Energy"
    assert subj["registrationType"] == "vatID"
    assert subj["headquartersAddress"] == {"countryCode": "IT-TN"}
    assert subj["legalAddress"] == {"countryCode": "IT-TN"}
    assert subj["parentOrganization"] == ["did:web:parent"]
    assert subj["dspAddress"] == "https://acme/dsp"
    assert {e["statusPurpose"] for e in vc["credentialStatus"]} == {
        "revocation",
        "suspension",
    }


def test_sign_organization_credential_roundtrip():
    vc = build_organization_credential(
        issuer_did=TA_DID,
        subject_did=ORG_DID,
        legal_name="Acme",
        registration_number="X",
        registration_type="leiCode",
        hq_country_code="IT-TN",
        legal_country_code="IT-TN",
        roles=["consumer"],
        allowed_scopes=["dataspaces.query"],
        credentials_context_url="https://x/ns",
        dataspace_uri="https://x/ds",
        status_list_credential_url="https://x/status/1",
        suspension_list_credential_url="https://x/status/2",
        status_list_index=1,
    )
    kp = generate_key_pair(TA_DID)
    signed = sign_credential(vc, kp.private_jwk, kp.kid)
    assert signed["proof"]["type"] == "JsonWebSignature2020"
    assert signed["proof"]["verificationMethod"] == kp.kid


# ── Helpers ───────────────────────────────────────────────────────


async def _bootstrap_ta(client):
    await client.post(
        "/admin/dids",
        json={"did": TA_DID, "did_type": "participant"},
        headers=HEADERS,
    )


async def _seed_agreement(db_session):
    # No import HTTP endpoint (CLI-only), so seed the Agreement row via the
    # db_session fixture, which is bound to the same engine as the test client.
    from identity_registry.services.agreements import import_agreements

    await import_agreements(
        db_session,
        [
            {
                "id": "dataspace-participation",
                "version": "1.0",
                "effective_from": None,
                "applies_to": ["consumer", "provider"],
                "capacity": "processor",
                "texts": {"en": {"path": "x.md", "sha256": "deadbeef"}},
            }
        ],
    )
    await db_session.commit()


async def _register(client, alias="acme-energy"):
    r = await client.post(
        "/admin/organizations/applications",
        json={
            "alias": alias,
            "legal_name": "Acme Energy",
            "registration_number": "IT12345678901",
            "registration_type": "vatID",
            "hq_country_code": "IT-TN",
            "legal_country_code": "IT-TN",
            "roles": ["consumer"],
            "did": ORG_DID,
            "dsp_address": "https://acme/dsp",
        },
        headers=HEADERS,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── Application lifecycle ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_application_create_and_list(client):
    app = await _register(client)
    assert app["status"] == "pending"
    assert app["registration_type"] == "vatID"

    r = await client.get(
        "/admin/organizations/applications?status=pending", headers=HEADERS
    )
    assert r.status_code == 200
    assert any(a["id"] == app["id"] for a in r.json())


@pytest.mark.asyncio
async def test_application_invalid_registration_type(client):
    r = await client.post(
        "/admin/organizations/applications",
        json={"alias": "bad-org", "legal_name": "Bad", "registration_type": "bogus"},
        headers=HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_verify_requires_verified_by(client):
    app = await _register(client)
    r = await client.patch(
        f"/admin/organizations/applications/{app['id']}",
        json={"status": "verified"},
        headers=HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_verify_promotes_owner(client):
    app = await _register(client)
    r = await client.patch(
        f"/admin/organizations/applications/{app['id']}",
        json={"status": "verified", "verified_by": "op1"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "verified"

    owner = await client.get(
        "/owners/resolve?alias=acme-energy", headers=HEADERS
    )
    assert owner.status_code == 200
    body = owner.json()
    assert body["status"] == "verified"
    assert body["registration_number"] == "IT12345678901"
    assert body["did"] == ORG_DID


# ── Gates ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_issue_credential_gate_needs_agreement(client):
    await _bootstrap_ta(client)
    app = await _register(client)
    await client.patch(
        f"/admin/organizations/applications/{app['id']}",
        json={"status": "verified", "verified_by": "op1"},
        headers=HEADERS,
    )
    # No agreement accepted yet → must fail closed.
    r = await client.post(
        "/admin/credentials/organization",
        json={"alias": "acme-energy", "roles": ["consumer"]},
        headers=HEADERS,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_promote_gate_needs_credential(client, db_session):
    await _bootstrap_ta(client)
    await _seed_agreement(db_session)
    app = await _register(client)
    await client.patch(
        f"/admin/organizations/applications/{app['id']}",
        json={"status": "verified", "verified_by": "op1"},
        headers=HEADERS,
    )
    await client.post(
        "/admin/owners/acme-energy/agreement",
        json={"agreement_id": "dataspace-participation", "version": "1.0"},
        headers=HEADERS,
    )
    # Credential not yet issued → promote must fail closed.
    r = await client.post(
        "/admin/owners/acme-energy/promote",
        json={"dsp_address": "https://acme/dsp", "roles": ["consumer"]},
        headers=HEADERS,
    )
    assert r.status_code == 409


# ── Agreement acceptance ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_agreement_acceptance_records_hash(client, db_session):
    await _seed_agreement(db_session)
    app = await _register(client)
    await client.patch(
        f"/admin/organizations/applications/{app['id']}",
        json={"status": "verified", "verified_by": "op1"},
        headers=HEADERS,
    )
    r = await client.post(
        "/admin/owners/acme-energy/agreement",
        json={
            "agreement_id": "dataspace-participation",
            "version": "1.0",
            "locale": "en",
            "accepted_by": "contact1",
        },
        headers=HEADERS,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["text_sha256"] == "deadbeef"
    assert body["capacity"] == "processor"

    owner = (await client.get("/owners/resolve?alias=acme-energy", headers=HEADERS)).json()
    assert owner["agreement_id"] == "dataspace-participation"
    assert owner["agreement_capacity"] == "processor"


@pytest.mark.asyncio
async def test_agreement_acceptance_unknown_locale(client, db_session):
    await _seed_agreement(db_session)
    app = await _register(client)
    await client.patch(
        f"/admin/organizations/applications/{app['id']}",
        json={"status": "verified", "verified_by": "op1"},
        headers=HEADERS,
    )
    r = await client.post(
        "/admin/owners/acme-energy/agreement",
        json={"agreement_id": "dataspace-participation", "version": "1.0", "locale": "de"},
        headers=HEADERS,
    )
    assert r.status_code == 422


# ── Full happy path + suspend ─────────────────────────────────────


@pytest.mark.asyncio
async def test_full_lifecycle_and_suspend(client, db_session):
    await _bootstrap_ta(client)
    await _seed_agreement(db_session)
    app = await _register(client)
    await client.patch(
        f"/admin/organizations/applications/{app['id']}",
        json={"status": "verified", "verified_by": "op1"},
        headers=HEADERS,
    )
    await client.post(
        "/admin/owners/acme-energy/agreement",
        json={"agreement_id": "dataspace-participation", "version": "1.0"},
        headers=HEADERS,
    )

    # Enrolment sits between the agreement and issuance (`D-51`).
    await register_enrolled(db_session, ORG_DID, roles=["consumer"])

    cred = await client.post(
        "/admin/credentials/organization",
        json={"alias": "acme-energy", "roles": ["consumer"], "dsp_address": "https://acme/dsp"},
        headers=HEADERS,
    )
    assert cred.status_code == 201, cred.text

    promote = await client.post(
        "/admin/owners/acme-energy/promote",
        json={"dsp_address": "https://acme/dsp", "roles": ["consumer"]},
        headers=HEADERS,
    )
    assert promote.status_code == 201, promote.text
    assert promote.json()["did"] == ORG_DID
    assert promote.json()["active"] is True

    # Participant is authorised for its scope.
    from urllib.parse import quote

    check = await client.get(
        f"/admin/participants/check?did={quote(ORG_DID, safe='')}&scope=dataspaces.query",
        headers=HEADERS,
    )
    assert check.json()["allowed"] is True

    # Suspend → credential held + participant deactivated in one step.
    suspend = await client.patch(
        "/admin/owners/acme-energy", json={"status": "suspended"}, headers=HEADERS
    )
    assert suspend.status_code == 200
    assert suspend.json()["status"] == "suspended"

    async def _org_creds():
        creds = (
            await client.get(
                f"/admin/credentials?subject_did={quote(ORG_DID, safe='')}",
                headers=HEADERS,
            )
        ).json()
        return [c for c in creds if c["credential_type"] == "OrganizationCredential"]

    held = await _org_creds()
    assert held and all(c["status"] == "suspended" for c in held)
    # Not `revoked`, and the difference is the whole of `DSSC-TRF-04`: a revoked
    # credential is finished, and this one is coming back three lines from here.
    assert all(c["status"] != "revoked" for c in held)

    check2 = await client.get(
        f"/admin/participants/check?did={quote(ORG_DID, safe='')}&scope=dataspaces.query",
        headers=HEADERS,
    )
    assert check2.json()["allowed"] is False

    # Reinstate → the same credentials, valid again. No re-issuance: a
    # suspension that could only be lifted by minting a new credential is a
    # revocation with a friendlier name.
    reinstated = await client.patch(
        "/admin/owners/acme-energy", json={"status": "verified"}, headers=HEADERS
    )
    assert reinstated.status_code == 200, reinstated.text
    assert reinstated.json()["status"] == "verified"

    back = await _org_creds()
    assert {c["id"] for c in back} == {c["id"] for c in held}, (
        "reinstatement minted a new credential instead of lifting the hold"
    )
    assert all(c["status"] == "active" for c in back)

    check3 = await client.get(
        f"/admin/participants/check?did={quote(ORG_DID, safe='')}&scope=dataspaces.query",
        headers=HEADERS,
    )
    assert check3.json()["allowed"] is True


# ── T27 — the intake is an upsert on alias ────────────────────────


@pytest.mark.asyncio
async def test_reregistering_an_alias_upserts_instead_of_duplicating(client):
    """An alias identifies one organisation, so a second POST is the same
    application. Inserting another row left several live applications for one
    organisation, and whichever query ran first answered differently about its
    state."""
    first = await _register(client)

    r = await client.post(
        "/admin/organizations/applications",
        json={
            "alias": "acme-energy",
            "legal_name": "Acme Energy",
            "registration_number": "IT12345678901",
            "registration_type": "vatID",
            "roles": ["consumer", "provider"],
            "did": ORG_DID,
            "dsp_address": "https://acme/dsp2",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text          # 201 creates, 200 updates
    assert r.json()["id"] == first["id"]
    assert r.json()["dsp_address"] == "https://acme/dsp2"

    listed = await client.get(
        "/admin/organizations/applications?alias=acme-energy", headers=HEADERS
    )
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_reregistering_preserves_verification_state(client):
    """A re-registration must not re-open a completed check."""
    app = await _register(client)
    await client.patch(
        f"/admin/organizations/applications/{app['id']}",
        json={"status": "verified", "verified_by": "op1"},
        headers=HEADERS,
    )

    r = await client.post(
        "/admin/organizations/applications",
        json={
            "alias": "acme-energy",
            "legal_name": "Acme Energy",
            "registration_number": "IT12345678901",
            "registration_type": "vatID",
            "roles": ["consumer"],
            "did": ORG_DID,
            "dsp_address": "https://acme/dsp-moved",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "verified"
    assert body["verified_by"] == "op1"
    assert body["dsp_address"] == "https://acme/dsp-moved"
    # The body omitted the country codes; a call patches what it names, so they
    # survive rather than being cleared — and the verified-lock above therefore
    # fires on a real edit, not on an omission.
    assert body["hq_country_code"] == "IT-TN"
    assert body["legal_country_code"] == "IT-TN"


@pytest.mark.asyncio
async def test_editing_a_verified_legal_identity_is_refused(client):
    """The issued credential asserts the old value, so this is a
    re-verification, not an edit."""
    app = await _register(client)
    await client.patch(
        f"/admin/organizations/applications/{app['id']}",
        json={"status": "verified", "verified_by": "op1"},
        headers=HEADERS,
    )

    r = await client.post(
        "/admin/organizations/applications",
        json={
            "alias": "acme-energy",
            "legal_name": "Acme Energy Renamed",
            "registration_number": "IT99999999999",
            "roles": ["consumer"],
            "did": ORG_DID,
        },
        headers=HEADERS,
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "legal_name" in detail and "registration_number" in detail
