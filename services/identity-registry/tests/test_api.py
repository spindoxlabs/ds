import pytest
from conftest import CUSTODIAN_DID, make_headers, register_did

HEADERS = make_headers()
READ_HEADERS = make_headers(scope="identity-registry.read")
TEST_DID = "did:web:rec.dataspaces.localhost"
#: This instance's own — the one DID a trust anchor may still create for itself.
OWN_DID = "did:web:trust-anchor.dataspaces.localhost"


async def seed_did(db_session, did: str = TEST_DID):
    """Register *did* the way it now comes to exist: by enrolment.

    `POST /admin/dids` created a participant DID **and its private key**, and
    `POST /admin/participants` did the same as a side effect. Neither does now
    (`D-51`) — the anchor records a key the organisation proved control of, and
    holds only the public half. Every test below that merely *needs* a
    participant to exist goes through here; the ones that test the routes
    themselves assert the refusal.
    """
    return await register_did(db_session, did)


@pytest.mark.asyncio
async def test_create_did_for_this_instances_own_identity(client):
    """The anchor may still create **its own** DID — it holds that key.

    The line `D-51` draws is "somebody else's identity", not "a participant
    DID": the anchor's own is a participant DID too, and `ir-cli bootstrap` has
    to be able to create it.
    """
    r = await client.post(
        "/admin/dids",
        json={"did": OWN_DID, "did_type": "participant"},
        headers=HEADERS,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["did"] == OWN_DID
    assert data["key"]["kid"].startswith(OWN_DID)


@pytest.mark.asyncio
async def test_creating_another_partys_participant_did_is_refused(client):
    """Otherwise the guard on `POST /admin/participants` is theatre.

    Mint a participant DID here, register it there, and the anchor is back to
    holding an identity it invented.
    """
    r = await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )
    assert r.status_code == 422
    assert "enrolment" in r.text


@pytest.mark.asyncio
async def test_create_did_duplicate(client):
    for _ in range(2):
        r = await client.post(
            "/admin/dids",
            json={"did": OWN_DID, "did_type": "participant"},
            headers=HEADERS,
        )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_get_did(client, db_session):
    await seed_did(db_session)
    r = await client.get(f"/admin/dids/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["did"] == TEST_DID


@pytest.mark.asyncio
async def test_delete_did(client, db_session):
    await seed_did(db_session)
    r = await client.delete(f"/admin/dids/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 204

    r = await client.get(f"/admin/dids/{TEST_DID}", headers=HEADERS)
    assert r.json()["active"] is False


@pytest.mark.asyncio
async def test_resolve_did_document(client, db_session):
    await seed_did(db_session)
    r = await client.get(f"/dids/{TEST_DID}/did.json")
    assert r.status_code == 200
    doc = r.json()
    assert doc["id"] == TEST_DID
    assert len(doc["verificationMethod"]) == 1


@pytest.mark.asyncio
async def test_create_participant(client, db_session):
    await seed_did(db_session)
    r = await client.post(
        "/admin/participants",
        json={
            "did": TEST_DID,
            "dsp_address": "http://edc-rec:19194/protocol",
            "roles": ["provider"],
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["did"] == TEST_DID
    assert data["roles"] == ["provider"]
    assert data["allowed_scopes"] == ["dataspaces.query"]


@pytest.mark.asyncio
async def test_create_participant_dual_role(client, db_session):
    await seed_did(db_session)
    r = await client.post(
        "/admin/participants",
        json={
            "did": TEST_DID,
            "roles": ["provider", "consumer"],
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    assert r.status_code == 201
    data = r.json()
    assert set(data["roles"]) == {"provider", "consumer"}


@pytest.mark.asyncio
async def test_create_participant_invalid_role(client, db_session):
    await seed_did(db_session)
    r = await client.post(
        "/admin/participants",
        json={
            "did": TEST_DID,
            "roles": ["invalid"],
        },
        headers=HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_registering_a_participant_records_a_keyless_did(client, db_session):
    """It used to create the DID **and its keypair**, and that was the defect.

    Registering a participant silently made the anchor the holder of that
    participant's private key. It now records a DID with **no key at all** —
    the honest state for a party this registry has never been shown a key for
    and is not vouching for.

    `P-6` survives: a keyless DID resolves nowhere, because the anchor does not
    publish somebody else's document. When the party enrols, its public key
    lands here with proof of control behind it.
    """
    from sqlalchemy import select

    from identity_registry.db.models import Did, Key

    r = await client.post(
        "/admin/participants",
        json={"did": TEST_DID, "roles": ["provider"]},
        headers=HEADERS,
    )
    assert r.status_code == 201

    did_row = (
        await db_session.execute(select(Did).where(Did.did == TEST_DID))
    ).scalar_one()
    assert did_row.key_id is None
    assert (
        await db_session.execute(select(Key).where(Key.owner_did == TEST_DID))
    ).scalar_one_or_none() is None

    # And nothing resolves for it — the anchor publishes no document it cannot
    # back with a key.
    doc = await client.get(f"/dids/{TEST_DID}/did.json")
    assert doc.status_code == 404


@pytest.mark.rule("P-12")
@pytest.mark.asyncio
async def test_list_participants(client, db_session):
    await seed_did(db_session)
    await client.post(
        "/admin/participants",
        json={"did": TEST_DID, "roles": ["provider"]},
        headers=HEADERS,
    )
    r = await client.get("/admin/participants", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_get_participant_detail(client, db_session):
    await seed_did(db_session)
    await client.post(
        "/admin/participants",
        json={"did": TEST_DID, "roles": ["provider"]},
        headers=HEADERS,
    )
    r = await client.get(f"/admin/participants/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["did"] == TEST_DID
    assert "credentials" in r.json()


@pytest.mark.asyncio
async def test_update_participant(client, db_session):
    await seed_did(db_session)
    await client.post(
        "/admin/participants",
        json={"did": TEST_DID, "roles": ["consumer"]},
        headers=HEADERS,
    )
    r = await client.patch(
        f"/admin/participants/{TEST_DID}",
        json={"roles": ["provider"], "allowed_scopes": ["dataspaces.admin"]},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["roles"] == ["provider"]
    assert r.json()["allowed_scopes"] == ["dataspaces.admin"]


@pytest.mark.asyncio
async def test_delete_participant(client, db_session):
    await seed_did(db_session)
    await client.post(
        "/admin/participants",
        json={"did": TEST_DID, "roles": ["consumer"]},
        headers=HEADERS,
    )
    r = await client.delete(f"/admin/participants/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 204


@pytest.mark.rule("P-12")
@pytest.mark.asyncio
async def test_list_participants_read_scope_active_only(client, db_session):
    await seed_did(db_session)
    """GET /admin/participants with read scope returns only active participants."""
    await client.post(
        "/admin/participants",
        json={
            "did": TEST_DID,
            "dsp_address": "http://edc-rec:19194/protocol",
            "roles": ["provider"],
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    inactive_did = "did:web:old.dataspaces.localhost"
    await client.post(
        "/admin/participants",
        json={"did": inactive_did, "roles": ["consumer"]},
        headers=HEADERS,
    )
    await client.patch(
        f"/admin/participants/{inactive_did}",
        json={"active": False},
        headers=HEADERS,
    )

    r = await client.get("/admin/participants", headers=READ_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["did"] == TEST_DID
    assert data[0]["dsp_address"] == "http://edc-rec:19194/protocol"
    assert data[0]["allowed_scopes"] == ["dataspaces.query"]
    assert "private" not in str(data).lower()
    assert "key" not in str(data).lower()


@pytest.mark.asyncio
async def test_list_participants_empty(client):
    """GET /admin/participants returns empty list when no participants."""
    r = await client.get("/admin/participants", headers=READ_HEADERS)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_participant_check_allowed(client, db_session):
    await seed_did(db_session)
    await client.post(
        "/admin/participants",
        json={
            "did": TEST_DID,
            "roles": ["provider"],
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    r = await client.get(
        f"/admin/participants/check?did={TEST_DID}&scope=dataspaces.query",
        headers=READ_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["allowed"] is True


@pytest.mark.asyncio
async def test_participant_check_denied(client, db_session):
    await seed_did(db_session)
    await client.post(
        "/admin/participants",
        json={
            "did": TEST_DID,
            "roles": ["provider"],
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    r = await client.get(
        f"/admin/participants/check?did={TEST_DID}&scope=dataspaces.admin",
        headers=READ_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["allowed"] is False


@pytest.mark.rule("P-3")
@pytest.mark.asyncio
async def test_issue_membership_credential(client, db_session):
    # Bootstrap trust anchor first
    await client.post(
        "/admin/dids",
        json={
            "did": "did:web:trust-anchor.dataspaces.localhost",
            "did_type": "participant",
        },
        headers=HEADERS,
    )
    # Create subject DID
    await seed_did(db_session)

    r = await client.post(
        "/admin/credentials/membership",
        json={
            "subject_did": TEST_DID,
            "role": "provider",
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["credentialId"].startswith("urn:uuid:")
    assert data["subjectDid"] == TEST_DID


@pytest.mark.asyncio
async def test_issue_data_subject_credential(client):
    await client.post(
        "/admin/dids",
        json={
            "did": "did:web:trust-anchor.dataspaces.localhost",
            "did_type": "participant",
        },
        headers=HEADERS,
    )

    r = await client.post(
        "/admin/credentials/data-subject",
        json={
            "subject_id": "email-abc123",
            "linked_participant_did": CUSTODIAN_DID,
        },
        headers=HEADERS,
    )
    assert r.status_code == 201
    data = r.json()
    # **The person lives in their custodian's namespace**, not the anchor's
    # (`D-50`). The old shape said every person in the dataspace belonged to the
    # trust anchor, which is not the relationship anybody has with them.
    assert data["subjectDid"] == f"{CUSTODIAN_DID}:users:email-abc123"
    assert data["custodianDid"] == CUSTODIAN_DID
    assert data["credentialId"].startswith("urn:uuid:")


@pytest.mark.asyncio
async def test_data_subject_creates_user_did(client):
    await client.post(
        "/admin/dids",
        json={
            "did": "did:web:trust-anchor.dataspaces.localhost",
            "did_type": "participant",
        },
        headers=HEADERS,
    )
    r = await client.post(
        "/admin/credentials/data-subject",
        json={"subject_id": "email-xyz", "linked_participant_did": CUSTODIAN_DID},
        headers=HEADERS,
    )
    subject_did = r.json()["subjectDid"]

    r = await client.get(f"/dids/{subject_did}/did.json")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_get_credential(client, db_session):
    await client.post(
        "/admin/dids",
        json={
            "did": "did:web:trust-anchor.dataspaces.localhost",
            "did_type": "participant",
        },
        headers=HEADERS,
    )
    await seed_did(db_session)
    issue = await client.post(
        "/admin/credentials/membership",
        json={"subject_did": TEST_DID, "role": "provider"},
        headers=HEADERS,
    )
    cred_id = issue.json()["credentialId"]

    r = await client.get(f"/admin/credentials/{cred_id}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["type"] == ["VerifiableCredential", "MembershipCredential"]


@pytest.mark.asyncio
async def test_list_credentials(client, db_session):
    await client.post(
        "/admin/dids",
        json={
            "did": "did:web:trust-anchor.dataspaces.localhost",
            "did_type": "participant",
        },
        headers=HEADERS,
    )
    await seed_did(db_session)
    await client.post(
        "/admin/credentials/membership",
        json={"subject_did": TEST_DID, "role": "provider"},
        headers=HEADERS,
    )

    r = await client.get(f"/admin/credentials?subject_did={TEST_DID}", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.rule("P-16")
@pytest.mark.asyncio
async def test_revoke_credential(client, db_session):
    await client.post(
        "/admin/dids",
        json={
            "did": "did:web:trust-anchor.dataspaces.localhost",
            "did_type": "participant",
        },
        headers=HEADERS,
    )
    await seed_did(db_session)
    issue = await client.post(
        "/admin/credentials/membership",
        json={"subject_did": TEST_DID, "role": "provider"},
        headers=HEADERS,
    )
    cred_id = issue.json()["credentialId"]

    r = await client.delete(f"/admin/credentials/{cred_id}", headers=HEADERS)
    assert r.status_code == 204

    r = await client.get(f"/admin/credentials?subject_did={TEST_DID}", headers=HEADERS)
    assert r.json()[0]["status"] == "revoked"


@pytest.mark.asyncio
async def test_keycloak_sync(client, db_session):
    await seed_did(db_session)

    r = await client.post(
        "/admin/keycloak/sync",
        json={
            "did": TEST_DID,
            "keycloak_realm": "dataspaces",
            "keycloak_user_id": "user-123",
            "email": "user@example.com",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "synced"

    r = await client.get(f"/admin/keycloak/mapping/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["keycloak_user_id"] == "user-123"


@pytest.mark.asyncio
async def test_keycloak_sync_writes_nothing_to_keycloak(
    client, monkeypatch, tmp_path, db_session
):
    """The endpoint records a mapping and touches Keycloak **not at all**.

    It used to also push a `dataspace_did` user attribute, which no protocol
    mapper emitted, no service read, and no portal page looked up — while being
    the only thing here that needed *write* access to a realm ds may not own.

    Asserted the hard way: `keycloak_admin_url` **is** configured, so a
    reintroduced push would run, and any HTTP client construction fails the test.
    Asserting on the response body alone would pass even if the call came back.
    """
    import httpx
    from conftest import TEST_DATABASE_URL

    from identity_registry.config import Settings
    from identity_registry.dependencies import get_settings_dep

    settings_with_kc = Settings(
        database_url=TEST_DATABASE_URL,
        oidc_issuer_url=None,
        KEYCLOAK_ADMIN_URL="http://keycloak.invalid",
    )
    assert settings_with_kc.keycloak_admin_url == "http://keycloak.invalid"
    client._transport.app.dependency_overrides[get_settings_dep] = lambda: (
        settings_with_kc
    )

    class NoOutboundHttp:
        def __init__(self, *a, **k):
            raise AssertionError(
                "POST /admin/keycloak/sync made an outbound HTTP call — the "
                "dataspace_did attribute push must stay removed"
            )

    monkeypatch.setattr(httpx, "AsyncClient", NoOutboundHttp)

    await seed_did(db_session)
    r = await client.post(
        "/admin/keycloak/sync",
        json={
            "did": TEST_DID,
            "keycloak_realm": "dataspaces",
            "keycloak_user_id": "u1",
        },
        headers=HEADERS,
    )

    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "synced", "did": TEST_DID}
    # The removed fields must not come back: onboarding reads them defensively,
    # so a resurrected `keycloak_attribute_synced: False` would start logging
    # warnings about an attribute that no longer exists.
    assert "keycloak_attribute_synced" not in body
    assert "warning" not in body

    m = await client.get(f"/admin/keycloak/mapping/{TEST_DID}", headers=HEADERS)
    assert m.status_code == 200
    assert m.json()["keycloak_user_id"] == "u1"


@pytest.mark.asyncio
async def test_keycloak_mapping_by_subject_id(client, db_session):
    await seed_did(db_session)
    await client.post(
        "/admin/keycloak/sync",
        json={
            "did": TEST_DID,
            "keycloak_realm": "dataspaces",
            "keycloak_user_id": "user-123",
        },
        headers=HEADERS,
    )

    r = await client.get(
        f"/admin/keycloak/mapping?subject_id={TEST_DID}", headers=HEADERS
    )
    assert r.status_code == 200
    assert r.json()["did"] == TEST_DID


@pytest.mark.asyncio
async def test_key_rotation(client, db_session):
    await seed_did(db_session)

    r = await client.post(f"/admin/keys/rotate/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["old_kid"].endswith("#key-1")
    assert data["new_kid"].endswith("#key-2")

    r = await client.get(f"/dids/{TEST_DID}/did.json")
    doc = r.json()
    assert doc["verificationMethod"][0]["publicKeyJwk"]["kid"] == data["new_kid"]
