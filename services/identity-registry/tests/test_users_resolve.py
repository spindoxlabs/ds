"""GET /users/resolve — every credential a user can present, not just the newest.

One human legitimately holds more than one role: the same person can be a data
subject about their own consumption *and* a consumer user acting for an
organisation. Returning only the most recently issued credential made those
mutually exclusive for every caller, and left a caller presenting whichever VC
happened to be newest rather than the one the operation requires.

The singular `role`/`vc_jws` fields stay because `libs/ds-e2e` and the portal
read them; they must keep meaning "the newest presentable credential".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_headers

from identity_registry.db.models import Credential, Did, KeycloakMapping
from identity_registry.services.did import subject_did_for

EMAIL = "dual@example.test"
CUSTODIAN = "did:web:rec.dataspaces.localhost"
SUBJECT_ID = "dual-user"
USER_DID = f"{CUSTODIAN}:users:{SUBJECT_ID}"


def _headers() -> dict:
    return make_headers(scope="identity-registry.resolve")


async def _seed_user(db_session) -> None:
    db_session.add(Did(did=USER_DID, did_type="user", active=True))
    db_session.add(
        KeycloakMapping(
            did=USER_DID,
            keycloak_realm="dataspaces",
            keycloak_user_id="dual-user-id",
            email=EMAIL,
            subject_id=USER_DID,
        )
    )
    await db_session.commit()


async def _seed_credential(
    db_session,
    *,
    cred_id: str,
    role: str,
    jws: str,
    issued_at: datetime,
    expires_at: datetime | None = None,
    status: str = "active",
) -> None:
    db_session.add(
        Credential(
            id=cred_id,
            credential_type=role,
            issuer_did="did:web:trust-anchor.dataspaces.localhost",
            subject_did=USER_DID,
            credential_json={
                "credentialSubject": {"id": USER_DID, "role": role},
                "proof": {"jws": jws},
            },
            status=status,
            issued_at=issued_at,
            expires_at=expires_at,
        )
    )
    await db_session.commit()


def _now() -> datetime:
    return datetime.now(UTC)


async def _resolve(client) -> dict:
    r = await client.get(f"/users/resolve?email={EMAIL}", headers=_headers())
    assert r.status_code == 200
    return r.json()


@pytest.mark.asyncio
async def test_returns_every_active_credential(client, db_session):
    """The whole point: two roles, both visible."""
    await _seed_user(db_session)
    await _seed_credential(
        db_session,
        cred_id="c-subject",
        role="DataSubject",
        jws="jws-subject",
        issued_at=_now() - timedelta(days=2),
    )
    await _seed_credential(
        db_session,
        cred_id="c-consumer",
        role="ConsumerUser",
        jws="jws-consumer",
        issued_at=_now() - timedelta(days=1),
    )

    body = await _resolve(client)
    assert set(body["roles"]) == {"DataSubject", "ConsumerUser"}
    by_role = {c["role"]: c["vc_jws"] for c in body["credentials"]}
    assert by_role == {"DataSubject": "jws-subject", "ConsumerUser": "jws-consumer"}


@pytest.mark.asyncio
async def test_singular_fields_stay_on_the_newest_credential(client, db_session):
    """`ds-e2e` and older callers read `vc_jws` — it must not shift meaning."""
    await _seed_user(db_session)
    await _seed_credential(
        db_session,
        cred_id="c-old",
        role="DataSubject",
        jws="jws-old",
        issued_at=_now() - timedelta(days=5),
    )
    await _seed_credential(
        db_session,
        cred_id="c-new",
        role="ConsumerUser",
        jws="jws-new",
        issued_at=_now() - timedelta(hours=1),
    )

    body = await _resolve(client)
    assert body["role"] == "ConsumerUser"
    assert body["vc_jws"] == "jws-new"
    # …and the newest is first in the list, so a caller with no role preference
    # gets the same answer from either field.
    assert body["credentials"][0]["vc_jws"] == "jws-new"


@pytest.mark.asyncio
async def test_expired_credentials_are_not_offered(client, db_session):
    """An expired VC is rejected by the verifier, so offering it only produces a
    failure the caller cannot explain. `status == "active"` does not imply
    unexpired."""
    await _seed_user(db_session)
    await _seed_credential(
        db_session,
        cred_id="c-expired",
        role="ConsumerUser",
        jws="jws-expired",
        issued_at=_now() - timedelta(days=1),
        expires_at=_now() - timedelta(minutes=1),
    )
    await _seed_credential(
        db_session,
        cred_id="c-valid",
        role="DataSubject",
        jws="jws-valid",
        issued_at=_now() - timedelta(days=3),
        expires_at=_now() + timedelta(days=30),
    )

    body = await _resolve(client)
    assert body["roles"] == ["DataSubject"]
    assert body["vc_jws"] == "jws-valid"


@pytest.mark.asyncio
async def test_revoked_credentials_are_not_offered(client, db_session):
    await _seed_user(db_session)
    await _seed_credential(
        db_session,
        cred_id="c-revoked",
        role="ConsumerUser",
        jws="jws-revoked",
        issued_at=_now(),
        status="revoked",
    )

    body = await _resolve(client)
    assert body["roles"] == []
    assert body["credentials"] == []
    assert body["vc_jws"] is None


@pytest.mark.asyncio
async def test_user_with_no_credential_still_resolves_its_did(client, db_session):
    """Admin and provider users have a mapping but no VC. They must still resolve
    — the portal needs the DID, and a 404 here would break login."""
    await _seed_user(db_session)

    body = await _resolve(client)
    assert body["did"] == USER_DID
    assert body["subject_id"] == SUBJECT_ID
    assert body["roles"] == []
    assert body["role"] is None


# ── derive=true ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_derive_returns_subject_id_without_mapping(client):
    """No mapping → derive a subject_id from the email, no 404."""
    r = await client.get(
        "/users/resolve?email=new@example.test&derive=true",
        headers=_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["did"] is None
    assert body["subject_id"].startswith("email-")
    assert body["roles"] == []
    assert body["credentials"] == []


@pytest.mark.asyncio
async def test_derive_is_deterministic(client):
    r1 = await client.get(
        "/users/resolve?email=new@example.test&derive=true",
        headers=_headers(),
    )
    r2 = await client.get(
        "/users/resolve?email=New@Example.TEST&derive=true",
        headers=_headers(),
    )
    assert r1.json()["subject_id"] == r2.json()["subject_id"]


@pytest.mark.asyncio
async def test_derive_false_still_404s(client):
    """Backwards compat: without derive, unknown email is a 404."""
    r = await client.get(
        "/users/resolve?email=unknown@example.test",
        headers=_headers(),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_derive_prefers_existing_mapping(client, db_session):
    """When a mapping exists, derive=true returns the existing identity, not a
    fresh derivation."""
    await _seed_user(db_session)

    r = await client.get(
        f"/users/resolve?email={EMAIL}&derive=true",
        headers=_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["did"] == USER_DID
    assert body["subject_id"] == SUBJECT_ID


# ── One field, one kind of value ─────────────────────────────────
#
# `subject_id` used to carry the **DID** whenever a Keycloak mapping existed —
# both write paths store the DID in that column — and a short derived id when
# there was none. So which kind of value a caller got depended on state it could
# not see, and the round trip the docstring documents (resolve, then issue with
# `subject_id`) minted a second identity for a person who already had one. The
# stored column still holds the DID, because it is the lookup key of
# `GET /admin/keycloak/mapping?subject_id=…`; the *response* is derived (ds#31).


@pytest.mark.asyncio
async def test_subject_id_is_the_id_within_the_did_not_the_did(client, db_session):
    await _seed_user(db_session)

    body = await _resolve(client)
    assert body["subject_id"] == SUBJECT_ID
    assert body["subject_id"] != body["did"], (
        "the two fields exist because they carry different things"
    )
    assert body["did"] == subject_did_for(CUSTODIAN, body["subject_id"]), (
        "what resolve returns must rebuild the DID it returned beside it"
    )


@pytest.mark.asyncio
async def test_the_documented_round_trip_does_not_mint_a_second_identity(
    client, db_session
):
    """The issue's reproduce, as an assertion.

    An onboarding application resolves a user, reads `subject_id`, and passes it
    back as the subject id for issuance. That produced

        did:web:rec…:users:did:web:rec…:users:dual-user

    — well-formed enough to be stored, resolved and published, and invisible to
    `_existing_subject_did` because `subject_id_of` splits on the last
    `:users:`. One person, two DIDs, two consent states.
    """
    await _seed_user(db_session)

    body = await _resolve(client)
    assert subject_did_for(CUSTODIAN, body["subject_id"]) == USER_DID


@pytest.mark.asyncio
async def test_the_stored_mapping_still_keys_on_the_did(client, db_session):
    """The response changed; the column did not.

    `GET /admin/keycloak/mapping?subject_id=…` is looked up by the stored value
    and its callers pass a DID. Deriving at the point of reading is what lets
    the API say one thing without a migration this defect does not need.
    """
    await _seed_user(db_session)

    r = await client.get(
        f"/admin/keycloak/mapping?subject_id={USER_DID}",
        headers=make_headers(),
    )
    assert r.status_code == 200
    assert r.json()["did"] == USER_DID


@pytest.mark.asyncio
async def test_a_derived_subject_id_is_usable_where_a_resolved_one_is(client):
    """Both branches return something `subject_did_for` accepts. That is the
    property the field name promised all along."""
    r = await client.get(
        "/users/resolve?email=new@example.test&derive=true", headers=_headers()
    )
    assert r.status_code == 200
    derived = r.json()["subject_id"]
    assert r.json().get("did") is None
    assert subject_did_for(CUSTODIAN, derived) == f"{CUSTODIAN}:users:{derived}"
