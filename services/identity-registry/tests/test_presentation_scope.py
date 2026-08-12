"""What a presentation may contain — bounded by the grant, then by the request.

The edge e2e cannot see. A live run asks for one credential type and gets it, so
an over-broad answer looks identical to a correct one: the EDC takes what it
asked for and ignores the rest. The bound only becomes visible when a
participant holds credentials it was *not* asked for and *not* granted — which is
what these tests set up.

Before the fix neither bound existed. The query's scope was never read and no
grant existed, so the empty presentation definition EDC sends returned every
active credential the participant held.
"""
from __future__ import annotations

import base64
import json

import pytest
from conftest import make_admin_headers, register_holder
from test_dcp_auth import (
    HOLDER,
    MEMBERSHIP_SCOPE,
    VERIFIER,
    _publish,
    _si_token,
)

from identity_registry.db.models import Credential, Did
from identity_registry.services.presentation import (
    ScopeInvalid,
    credential_types_for,
    parse_credential_scope,
)
from identity_registry.services.token import create_access_token

HEADERS = make_admin_headers()

SUBJECT_SCOPE = "org.eclipse.dspace.dcp.vc.type:DataSubjectCredential:read"


async def _create_participant(db_session, did: str) -> None:
    """A participant **on its own instance** — it holds the private key.

    Was `POST /admin/participants`, which now refuses to create a DID: the anchor
    does not invent a participant's identity (`D-51`). These tests are the
    holder's side — they sign SI tokens and presentations — so the row they need
    is the one `ir-cli participant init` writes locally, not the public-only one
    the anchor records.
    """
    await register_holder(db_session, did)


async def _hold_credential(db_session, subject_did: str, credential_type: str) -> None:
    """Put a credential of *credential_type* in *subject_did*'s store."""
    db_session.add(
        Credential(
            id=f"urn:uuid:{credential_type}-{subject_did}",
            credential_type=credential_type,
            issuer_did="did:web:trust-anchor.dataspaces.localhost",
            subject_did=subject_did,
            credential_json={
                "type": ["VerifiableCredential", credential_type],
                "credentialSubject": {"id": subject_did},
                "proof": {"jws": f"jws-for-{credential_type}"},
            },
            status="active",
        )
    )
    await db_session.commit()


def _presented(response) -> list[str]:
    """The credentials carried by the VP in a PresentationResponseMessage."""
    vp_jwt = response.json()["dcp:presentation"]["@value"][0]
    payload = json.loads(
        base64.urlsafe_b64decode(vp_jwt.split(".")[1] + "===").decode()
    )
    return payload["vp"]["verifiableCredential"]


async def _query_as_verifier(client, db_session, resolver, *, scope, granted):
    grant = await create_access_token(
        db_session, HOLDER, verifier_did=VERIFIER, scope=granted
    )
    await _publish(resolver, db_session, VERIFIER)
    token = await _si_token(db_session, VERIFIER, audience=HOLDER, access_token=grant)
    return await client.post(
        f"/credentials/{HOLDER}/presentations/query",
        json={"@type": "PresentationQueryMessage", "scope": [scope]},
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.fixture
async def holder_with_two_credentials(client, db_session):
    await _create_participant(db_session, HOLDER)
    await _create_participant(db_session, VERIFIER)
    # `dids` already carries the participant rows; the credential FK points there.
    assert (await db_session.get(Did, HOLDER)) is not None
    await _hold_credential(db_session, HOLDER, "MembershipCredential")
    await _hold_credential(db_session, HOLDER, "DataSubjectCredential")


@pytest.mark.asyncio
async def test_only_the_requested_type_is_presented(
    client, db_session, resolver, holder_with_two_credentials
):
    r = await _query_as_verifier(
        client,
        db_session,
        resolver,
        scope=MEMBERSHIP_SCOPE,
        granted=f"{MEMBERSHIP_SCOPE} {SUBJECT_SCOPE}",
    )
    assert r.status_code == 200
    assert _presented(r) == ["jws-for-MembershipCredential"]


@pytest.mark.asyncio
async def test_a_type_outside_the_grant_is_not_presented(
    client, db_session, resolver, holder_with_two_credentials
):
    """The DCP rule: fewer presentations, **not** an error.

    A verifier granted membership only, asking for data-subject credentials, gets
    a valid empty presentation. Refusing with 4xx here would tell the verifier
    which credentials exist, which is the disclosure the grant is meant to bound.
    """
    r = await _query_as_verifier(
        client, db_session, resolver, scope=SUBJECT_SCOPE, granted=MEMBERSHIP_SCOPE
    )
    assert r.status_code == 200
    assert _presented(r) == []


@pytest.mark.asyncio
async def test_the_grant_bounds_an_unrestricted_request(
    client, db_session, resolver, holder_with_two_credentials
):
    """Asking for everything you were granted does not mean everything held."""
    r = await _query_as_verifier(
        client, db_session, resolver, scope=MEMBERSHIP_SCOPE, granted=MEMBERSHIP_SCOPE
    )
    assert _presented(r) == ["jws-for-MembershipCredential"]


@pytest.mark.rule("P-16", "P-14")
@pytest.mark.asyncio
async def test_a_revoked_credential_is_never_presented(
    client, db_session, resolver, holder_with_two_credentials
):
    cred = await db_session.get(
        Credential, f"urn:uuid:MembershipCredential-{HOLDER}"
    )
    cred.status = "revoked"
    await db_session.commit()
    r = await _query_as_verifier(
        client, db_session, resolver, scope=MEMBERSHIP_SCOPE, granted=MEMBERSHIP_SCOPE
    )
    assert _presented(r) == []


# ── Scope parsing, against upstream's rules ─────────────────────────────────


def test_scope_names_a_credential_type():
    assert parse_credential_scope(MEMBERSHIP_SCOPE) == "MembershipCredential"


def test_context_qualified_discriminator():
    scope = (
        "org.eclipse.dspace.dcp.vc.type:"
        "https://example.org/ctx#MembershipCredential:read"
    )
    assert parse_credential_scope(scope) == "MembershipCredential"


@pytest.mark.parametrize("operation", ["read", "all", "*"])
def test_allowed_operations(operation):
    scope = f"org.eclipse.dspace.dcp.vc.type:MembershipCredential:{operation}"
    assert parse_credential_scope(scope) == "MembershipCredential"


@pytest.mark.parametrize(
    "scope",
    [
        "MembershipCredential",
        "org.eclipse.dspace.dcp.vc.type:MembershipCredential",
        "org.eclipse.dspace.dcp.vc.type:MembershipCredential:write",
        # The spelling `ds-e2e` used to send. No other credential service would
        # have answered it, so accepting it here would have hidden the mismatch.
        "org.eclipse.edc.vc.type:MembershipCredential:read",
    ],
)
def test_rejected_scopes(scope):
    with pytest.raises(ScopeInvalid):
        parse_credential_scope(scope)


def test_unparseable_scopes_are_dropped_not_fatal():
    """A scope this service does not understand narrows the answer, not breaks it."""
    assert credential_types_for(["nonsense", MEMBERSHIP_SCOPE]) == {
        "MembershipCredential"
    }
