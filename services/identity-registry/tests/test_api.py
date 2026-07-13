import pytest

from conftest import make_admin_headers

HEADERS = make_admin_headers()
TEST_DID = "did:web:rec.dataspaces.localhost"


@pytest.mark.asyncio
async def test_create_did(client):
    r = await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["did"] == TEST_DID
    assert data["did_type"] == "participant"
    assert data["active"] is True
    assert data["key"]["kid"].startswith(TEST_DID)
    assert data["did_document"]["id"] == TEST_DID


@pytest.mark.asyncio
async def test_create_did_duplicate(client):
    await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )
    r = await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_get_did(client):
    await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )
    r = await client.get(f"/admin/dids/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["did"] == TEST_DID


@pytest.mark.asyncio
async def test_delete_did(client):
    await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )
    r = await client.delete(f"/admin/dids/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 204

    r = await client.get(f"/admin/dids/{TEST_DID}", headers=HEADERS)
    assert r.json()["active"] is False


@pytest.mark.asyncio
async def test_resolve_did_document(client):
    await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )
    r = await client.get(f"/dids/{TEST_DID}/did.json")
    assert r.status_code == 200
    doc = r.json()
    assert doc["id"] == TEST_DID
    assert len(doc["verificationMethod"]) == 1


@pytest.mark.asyncio
async def test_create_participant(client):
    r = await client.post(
        "/admin/participants",
        json={
            "did": TEST_DID,
            "dsp_address": "http://edc-rec:19194/protocol",
            "role": "provider",
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["did"] == TEST_DID
    assert data["role"] == "provider"
    assert data["allowed_scopes"] == ["dataspaces.query"]


@pytest.mark.asyncio
async def test_create_participant_creates_did(client):
    r = await client.post(
        "/admin/participants",
        json={
            "did": TEST_DID,
            "role": "provider",
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    assert r.status_code == 201

    r = await client.get(f"/dids/{TEST_DID}/did.json")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_list_participants(client):
    await client.post(
        "/admin/participants",
        json={"did": TEST_DID, "role": "provider"},
        headers=HEADERS,
    )
    r = await client.get("/admin/participants", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_get_participant_detail(client):
    await client.post(
        "/admin/participants",
        json={"did": TEST_DID, "role": "provider"},
        headers=HEADERS,
    )
    r = await client.get(f"/admin/participants/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["did"] == TEST_DID
    assert "credentials" in r.json()


@pytest.mark.asyncio
async def test_update_participant(client):
    await client.post(
        "/admin/participants",
        json={"did": TEST_DID, "role": "consumer"},
        headers=HEADERS,
    )
    r = await client.patch(
        f"/admin/participants/{TEST_DID}",
        json={"role": "provider", "allowed_scopes": ["dataspaces.admin"]},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["role"] == "provider"
    assert r.json()["allowed_scopes"] == ["dataspaces.admin"]


@pytest.mark.asyncio
async def test_delete_participant(client):
    await client.post(
        "/admin/participants",
        json={"did": TEST_DID, "role": "consumer"},
        headers=HEADERS,
    )
    r = await client.delete(f"/admin/participants/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_list_active_participants_internal(client):
    """GET /participants (internal, no auth) returns only active participants."""
    await client.post(
        "/admin/participants",
        json={
            "did": TEST_DID,
            "dsp_address": "http://edc-rec:19194/protocol",
            "role": "provider",
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    inactive_did = "did:web:old.dataspaces.localhost"
    await client.post(
        "/admin/participants",
        json={"did": inactive_did, "role": "consumer"},
        headers=HEADERS,
    )
    await client.patch(
        f"/admin/participants/{inactive_did}",
        json={"active": False},
        headers=HEADERS,
    )

    r = await client.get("/participants")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["did"] == TEST_DID
    assert data[0]["dsp_address"] == "http://edc-rec:19194/protocol"
    assert data[0]["allowed_scopes"] == ["dataspaces.query"]
    assert "private" not in str(data).lower()
    assert "key" not in str(data).lower()


@pytest.mark.asyncio
async def test_list_active_participants_empty(client):
    """GET /participants returns empty list when no participants."""
    r = await client.get("/participants")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_participant_check_allowed(client):
    await client.post(
        "/admin/participants",
        json={
            "did": TEST_DID,
            "role": "provider",
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    r = await client.get(f"/participants/{TEST_DID}/check?scope=dataspaces.query")
    assert r.status_code == 200
    assert r.json()["allowed"] is True


@pytest.mark.asyncio
async def test_participant_check_denied(client):
    await client.post(
        "/admin/participants",
        json={
            "did": TEST_DID,
            "role": "provider",
            "allowed_scopes": ["dataspaces.query"],
        },
        headers=HEADERS,
    )
    r = await client.get(f"/participants/{TEST_DID}/check?scope=dataspaces.admin")
    assert r.status_code == 200
    assert r.json()["allowed"] is False


@pytest.mark.asyncio
async def test_issue_membership_credential(client):
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
    await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )

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
        json={"subject_id": "email-abc123"},
        headers=HEADERS,
    )
    assert r.status_code == 201
    data = r.json()
    assert "users.dataspaces.localhost" in data["subjectDid"]
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
        json={"subject_id": "email-xyz"},
        headers=HEADERS,
    )
    subject_did = r.json()["subjectDid"]

    r = await client.get(f"/dids/{subject_did}/did.json")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_get_credential(client):
    await client.post(
        "/admin/dids",
        json={
            "did": "did:web:trust-anchor.dataspaces.localhost",
            "did_type": "participant",
        },
        headers=HEADERS,
    )
    await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )
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
async def test_list_credentials(client):
    await client.post(
        "/admin/dids",
        json={
            "did": "did:web:trust-anchor.dataspaces.localhost",
            "did_type": "participant",
        },
        headers=HEADERS,
    )
    await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )
    await client.post(
        "/admin/credentials/membership",
        json={"subject_did": TEST_DID, "role": "provider"},
        headers=HEADERS,
    )

    r = await client.get(f"/admin/credentials?subject_did={TEST_DID}", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_revoke_credential(client):
    await client.post(
        "/admin/dids",
        json={
            "did": "did:web:trust-anchor.dataspaces.localhost",
            "did_type": "participant",
        },
        headers=HEADERS,
    )
    await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )
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
async def test_keycloak_sync(client):
    await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )

    r = await client.post(
        "/admin/keycloak/sync",
        json={
            "did": TEST_DID,
            "keycloak_realm": "celine",
            "keycloak_user_id": "user-123",
            "email": "user@example.com",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "synced"

    r = await client.get(f"/keycloak/mapping/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["keycloak_user_id"] == "user-123"


@pytest.mark.asyncio
async def test_keycloak_mapping_by_subject_id(client):
    await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )
    await client.post(
        "/admin/keycloak/sync",
        json={
            "did": TEST_DID,
            "keycloak_realm": "celine",
            "keycloak_user_id": "user-123",
        },
        headers=HEADERS,
    )

    r = await client.get(f"/keycloak/mapping?subject_id={TEST_DID}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["did"] == TEST_DID


@pytest.mark.asyncio
async def test_key_rotation(client):
    await client.post(
        "/admin/dids",
        json={"did": TEST_DID, "did_type": "participant"},
        headers=HEADERS,
    )

    r = await client.post(f"/admin/keys/rotate/{TEST_DID}", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["old_kid"].endswith("#key-1")
    assert data["new_kid"].endswith("#key-2")

    r = await client.get(f"/dids/{TEST_DID}/did.json")
    doc = r.json()
    assert doc["verificationMethod"][0]["publicKeyJwk"]["kid"] == data["new_kid"]
