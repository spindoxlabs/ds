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


# ── derive is deprecated: the registry no longer derives subject ids ────────
#
# `derive=true` used to answer an unmapped person with `email-` and an HMAC of
# their email. The generator is removed: an id derived from an address ties a
# DID to something that changes, and every caller now mints its own opaque id.
# The parameter stays so callers sending `derive=false` keep working; `true`
# is refused exactly where the generator used to answer.


@pytest.mark.asyncio
async def test_derive_true_without_a_mapping_is_refused_with_guidance(client):
    r = await client.get(
        "/users/resolve?email=new@example.test&derive=true",
        headers=_headers(),
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "no longer supported" in detail
    assert "POST /admin/credentials/data-subject" in detail
    assert "email-" not in r.text, "nothing derived is handed out"


@pytest.mark.asyncio
async def test_without_a_mapping_and_without_derive_it_is_a_404(client):
    """No mapping is not an error: it is how a first-time caller learns to mint."""
    for query in (
        "email=unknown@example.test",
        "email=unknown@example.test&derive=false",
    ):
        r = await client.get(f"/users/resolve?{query}", headers=_headers())
        assert r.status_code == 404, query


@pytest.mark.asyncio
async def test_derive_true_with_a_mapping_answers_the_mapping(client, db_session):
    """The parameter changes nothing for a person the registry knows."""
    await _seed_user(db_session)

    r = await client.get(
        f"/users/resolve?email={EMAIL}&derive=true",
        headers=_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["did"] == USER_DID
    assert body["subject_id"] == SUBJECT_ID


def test_derive_is_marked_deprecated_in_the_contract(client):
    schema = client._transport.app.openapi()
    params = schema["paths"]["/users/resolve"]["get"]["parameters"]
    [derive] = [p for p in params if p["name"] == "derive"]
    assert derive.get("deprecated") is True


# ── DIDs issued by the removed generator keep working ───────────────────────

LEGACY_SUBJECT_ID = "email-9f2c1ab4d7e60351cc2f8b19"


@pytest.mark.rule("D-22b")
@pytest.mark.asyncio
async def test_an_email_derived_did_issued_before_the_removal_still_resolves(
    client, anchor_identity
):
    """Issued, mapped, then found by every rung, and its DID document served.

    The id is stored, never re-derived, so the removal cannot reach it: what
    the registry holds is a DID like any other."""
    admin = make_headers()
    r = await client.post(
        "/admin/credentials/data-subject",
        json={"subject_id": LEGACY_SUBJECT_ID, "linked_participant_did": CUSTODIAN},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    legacy_did = r.json()["subjectDid"]
    assert legacy_did == f"{CUSTODIAN}:users:{LEGACY_SUBJECT_ID}"

    r = await client.post(
        "/admin/keycloak/sync",
        json={
            "did": legacy_did,
            "keycloak_realm": "dataspaces",
            "keycloak_user_id": "legacy-user-id",
            "email": "legacy@example.test",
            "username": "legacy-user",
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text

    for query in (
        "realm=dataspaces&user_id=legacy-user-id",
        "username=legacy-user",
        "email=legacy@example.test",
        "email=legacy@example.test&derive=true",
    ):
        r = await client.get(f"/users/resolve?{query}", headers=_headers())
        assert r.status_code == 200, (query, r.text)
        body = r.json()
        assert body["did"] == legacy_did, query
        assert body["subject_id"] == LEGACY_SUBJECT_ID, query
        assert [c["role"] for c in body["credentials"]], query

    r = await client.get(f"/dids/{legacy_did}/did.json")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == legacy_did


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
