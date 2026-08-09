"""Enrolment — the handshake that replaces the anchor minting somebody's identity.

The client here is a *stranger with a key*: an organisation that generated its own
keypair, published its own DID document, and holds an out-of-band code. Nothing
about it is in this registry until it enrols, which is the whole point — the
previous design had the anchor generate the key and so had nothing to verify.

Shapes are DCP's, not ours: `credential.issuance.protocol.md` §Credential Request
API, and `base.protocol.md` §Validating Self-Issued ID Tokens for the check. The
`pre-authorized_code` claim is the spec's own name for the authorization carrier.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from conftest import ANCHOR_DID, REAL_ASYNC_CLIENT, make_admin_headers
from sqlalchemy import select

from identity_registry.db.models import (
    CredentialRequest,
    EnrolmentToken,
    Key,
    Owner,
    Participant,
)
from identity_registry.services import issuance
from identity_registry.services.crypto import (
    create_jws,
    generate_key_pair,
    load_private_key,
)
from identity_registry.services.did import build_did_document

HEADERS = make_admin_headers()

ANCHOR = ANCHOR_DID
REC_DID = "did:web:rec.dataspaces.localhost"
DSP = "http://172.17.0.1:19194/protocol/2025-1"
CS = f"http://rec.dataspaces.localhost/credentials/{REC_DID}"


class Client:
    """An organisation's own instance: a keypair it generated and never shared."""

    def __init__(self, did: str = REC_DID):
        self.did = did
        self.kp = generate_key_pair(did)
        self.private_key = load_private_key(self.kp.private_jwk)

    def document(self, *, dsp: str | None = DSP, cs: str | None = CS) -> dict:
        endpoints = []
        if dsp:
            endpoints.append({"type": "DSPEndpoint", "serviceEndpoint": dsp})
        if cs:
            endpoints.append({"type": "CredentialService", "serviceEndpoint": cs})
        return build_did_document(
            self.did, self.kp.public_jwk, service_endpoints=endpoints or None
        )

    def si_token(
        self,
        *,
        code: str | None,
        audience: str = ANCHOR,
        iss: str | None = None,
        sub: str | None = None,
        ttl: int = 300,
    ) -> str:
        now = int(time.time())
        claims: dict = {
            "iss": iss or self.did,
            "sub": sub or self.did,
            "aud": [audience],
            "iat": now,
            "exp": now + ttl,
        }
        if code is not None:
            claims["pre-authorized_code"] = code
        return create_jws(
            {"alg": "ES256", "kid": self.kp.kid}, claims, self.private_key
        )


def request_body(*, credentials=("MembershipCredential",), holder_pid="req-1") -> dict:
    return {
        "@context": ["https://w3id.org/dspace-dcp/v1.0/dcp.jsonld"],
        "type": "CredentialRequestMessage",
        "holderPid": holder_pid,
        "credentials": [{"id": c} for c in credentials],
    }


@pytest_asyncio.fixture(autouse=True)
async def _issuance_environment(anchor_identity, credential_store):
    """Both `conftest` fixtures, on for every test in this module.

    Every enrolment here issues and delivers, so a signing anchor and a
    reachable holder store are the baseline rather than something each test
    opts into. Tests that need to *break* one of them override it locally —
    `test_a_delivery_failure_is_reported` does exactly that.
    """
    return anchor_identity


async def make_owner(db_session, alias="rec", *, status="verified") -> Owner:
    owner = Owner(
        id=alias,
        type="schema:Organization",
        name="Riverside Energy Community",
        status=status,
        verified_by="ops@example.test" if status == "verified" else None,
        verified_at=datetime.now(UTC) if status == "verified" else None,
    )
    db_session.add(owner)
    await db_session.commit()
    return owner


async def issue_code(client, alias="rec") -> str:
    r = await client.post(
        "/admin/onboarding/enrolments",
        json={"owner_alias": alias},
        headers=HEADERS,
    )
    assert r.status_code == 201, r.text
    return r.json()["code"]


# ── The happy path ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enrolment_registers_the_did_the_key_and_the_endpoints(
    client, db_session, resolver
):
    await make_owner(db_session)
    code = await issue_code(client)

    org = Client()
    resolver.documents[org.did] = org.document()

    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    assert r.status_code == 201, r.text

    body = r.json()
    assert body["type"] == "CredentialStatus"
    # Issued in the same call: the enrolment code *is* the operator's approval,
    # so there is no second judgement for CIP's asynchronous leg to wait on.
    assert body["status"] == "ISSUED"
    assert body["holderPid"] == "req-1"
    assert r.headers["Location"] == f"/issuer/requests/{body['issuerPid']}"

    participant = (
        await db_session.execute(select(Participant).where(Participant.did == org.did))
    ).scalar_one()
    assert participant.dsp_address == DSP
    # The anchor does not decide how a participant authenticates to its own STS.
    assert participant.sts_client_secret is None


@pytest.mark.asyncio
async def test_the_anchor_stores_the_public_key_and_no_private_key(
    client, db_session, resolver
):
    """The row this whole change exists to produce."""
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    assert r.status_code == 201

    key = (
        await db_session.execute(select(Key).where(Key.owner_did == org.did))
    ).scalar_one()
    assert key.private_jwk is None
    assert key.public_jwk["kid"] == org.kp.kid
    assert "d" not in key.public_jwk


@pytest.mark.asyncio
async def test_the_owner_is_bound_to_the_did_that_enrolled(
    client, db_session, resolver
):
    owner = await make_owner(db_session)
    assert owner.did is None
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )

    await db_session.refresh(owner)
    assert owner.did == org.did


@pytest.mark.asyncio
async def test_the_code_is_spent_and_records_which_did_used_it(
    client, db_session, resolver
):
    """The audit trail from a verification an operator made to the key that speaks."""
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )

    token = (await db_session.execute(select(EnrolmentToken))).scalar_one()
    assert token.redeemed_at is not None
    assert token.redeemed_did == org.did


@pytest.mark.asyncio
async def test_endpoints_come_from_the_did_document_not_the_request(
    client, db_session, resolver
):
    """A client cannot claim an endpoint its published document does not carry."""
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document(dsp="http://declared.example/protocol")

    body = request_body()
    body["dspAddress"] = "http://claimed.example/protocol"  # ignored
    await client.post(
        "/issuer/credentials",
        json=body,
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )

    participant = (
        await db_session.execute(select(Participant).where(Participant.did == org.did))
    ).scalar_one()
    assert participant.dsp_address == "http://declared.example/protocol"


# ── Neither factor is sufficient alone ────────────────────────────


@pytest.mark.asyncio
async def test_a_valid_code_without_a_matching_signature_enrols_nothing(
    client, db_session, resolver
):
    """The code says which organisation; the signature says which key.

    Here the token is signed by a key whose DID document publishes a *different*
    key — a leaked code in the hands of someone who cannot prove control.
    """
    await make_owner(db_session)
    code = await issue_code(client)

    org = Client()
    impostor = Client()
    # The document published for org.did carries org's key, not the impostor's.
    resolver.documents[org.did] = org.document()

    forged = impostor.si_token(code=code, iss=org.did, sub=org.did)
    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert r.status_code == 401
    assert (await db_session.execute(select(Participant))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_a_valid_signature_without_a_code_enrols_nothing(
    client, db_session, resolver
):
    await make_owner(db_session)
    org = Client()
    resolver.documents[org.did] = org.document()

    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=None)}"},
    )
    assert r.status_code == 401
    assert (await db_session.execute(select(Participant))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_an_unknown_code_and_a_spent_code_answer_identically(
    client, db_session, resolver
):
    """No oracle. Distinguishing the two tells an attacker which codes exist."""
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    first = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    assert first.status_code == 201

    spent = await client.post(
        "/issuer/credentials",
        json=request_body(holder_pid="req-2"),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    unknown = await client.post(
        "/issuer/credentials",
        json=request_body(holder_pid="req-3"),
        headers={"Authorization": f"Bearer {org.si_token(code='never-issued')}"},
    )
    assert spent.status_code == unknown.status_code == 401
    assert spent.json() == unknown.json()


@pytest.mark.asyncio
async def test_an_expired_code_is_refused(client, db_session, resolver):
    await make_owner(db_session)
    code = await issue_code(client)
    token = (await db_session.execute(select(EnrolmentToken))).scalar_one()
    token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    org = Client()
    resolver.documents[org.did] = org.document()
    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_an_unresolvable_did_is_refused(client, db_session, resolver):
    """No local shortcut: the key comes from did:web or the request fails."""
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()  # never published

    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_a_token_addressed_to_someone_else_is_refused(
    client, db_session, resolver
):
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={
            "Authorization": (
                f"Bearer {org.si_token(code=code, audience='did:web:elsewhere')}"
            )
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_iss_must_equal_sub(client, db_session, resolver):
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={
            "Authorization": f"Bearer {org.si_token(code=code, sub='did:web:other')}"
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_an_expired_token_is_refused(client, db_session, resolver):
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code, ttl=-3600)}"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_a_missing_bearer_is_refused(client, db_session):
    r = await client.post("/issuer/credentials", json=request_body())
    assert r.status_code == 401


# ── Rebinding, retries and idempotence ────────────────────────────


@pytest.mark.asyncio
async def test_re_enrolling_the_same_did_is_idempotent(client, db_session, resolver):
    """A retry after a network failure must not need an operator."""
    await make_owner(db_session)
    org = Client()
    resolver.documents[org.did] = org.document()

    for pid in ("req-1", "req-2"):
        code = await issue_code(client)
        r = await client.post(
            "/issuer/credentials",
            json=request_body(holder_pid=pid),
            headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
        )
        assert r.status_code == 201, r.text

    keys = (
        await db_session.execute(select(Key).where(Key.owner_did == org.did))
    ).scalars().all()
    assert len(keys) == 1
    participants = (await db_session.execute(select(Participant))).scalars().all()
    assert len(participants) == 1


@pytest.mark.asyncio
async def test_a_second_did_cannot_take_over_an_enrolled_owner(
    client, db_session, resolver
):
    """Re-pointing an organisation's identity is not a keyholder's decision."""
    await make_owner(db_session)
    first = Client()
    resolver.documents[first.did] = first.document()
    code = await issue_code(client)
    assert (
        await client.post(
            "/issuer/credentials",
            json=request_body(),
            headers={"Authorization": f"Bearer {first.si_token(code=code)}"},
        )
    ).status_code == 201

    second = Client("did:web:usurper.dataspaces.localhost")
    resolver.documents[second.did] = second.document()
    code2 = await issue_code(client)
    r = await client.post(
        "/issuer/credentials",
        json=request_body(holder_pid="req-2"),
        headers={"Authorization": f"Bearer {second.si_token(code=code2)}"},
    )
    assert r.status_code == 409

    owner = (await db_session.execute(select(Owner))).scalar_one()
    assert owner.did == first.did


@pytest.mark.asyncio
async def test_a_locally_held_did_cannot_be_enrolled(client, db_session, resolver):
    """A DID this registry generated is not re-bindable by presenting a key.

    Otherwise the trust anchor's own DID could be taken over by anyone holding an
    enrolment code, which is the worst version of the defect this replaces.
    """
    await make_owner(db_session)
    org = Client()
    local = generate_key_pair(org.did)
    db_session.add(
        Key(owner_did=org.did, kid=local.kid, private_jwk={"fake": "encrypted"},
            public_jwk=local.public_jwk)
    )
    from identity_registry.db.models import Did as DidRow

    db_session.add(DidRow(did=org.did, did_type="participant"))
    await db_session.commit()

    resolver.documents[org.did] = org.document()
    code = await issue_code(client)
    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    assert r.status_code == 409


# ── Governance gates ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_unverified_owner_gets_no_enrolment_token(client, db_session):
    await make_owner(db_session, status="pending")
    r = await client.post(
        "/admin/onboarding/enrolments",
        json={"owner_alias": "rec"},
        headers=HEADERS,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_an_unknown_owner_gets_no_enrolment_token(client):
    r = await client.post(
        "/admin/onboarding/enrolments",
        json={"owner_alias": "nobody"},
        headers=HEADERS,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_issuing_an_enrolment_token_needs_a_scope(client, db_session):
    await make_owner(db_session)
    r = await client.post(
        "/admin/onboarding/enrolments", json={"owner_alias": "rec"}
    )
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_the_code_is_never_readable_back(client, db_session):
    await make_owner(db_session)
    code = await issue_code(client)

    listing = await client.get("/admin/onboarding/enrolments", headers=HEADERS)
    assert listing.status_code == 200
    assert code not in listing.text
    assert listing.json()[0]["owner_alias"] == "rec"


# ── The request message and the status endpoint ───────────────────


@pytest.mark.asyncio
async def test_an_unsupported_credential_id_is_a_400(client, db_session, resolver):
    """Naming what is unsupported is safe: `credentialsSupported` is public."""
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    r = await client.post(
        "/issuer/credentials",
        json=request_body(credentials=("DriversLicence",)),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    assert r.status_code == 400
    assert "DriversLicence" in r.text


@pytest.mark.asyncio
async def test_a_wrong_message_type_is_a_400(client, db_session, resolver):
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    body = request_body()
    body["type"] = "SomethingElse"
    r = await client.post(
        "/issuer/credentials",
        json=body,
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_issuer_metadata_is_public_and_names_the_anchor(client):
    r = await client.get("/issuer/metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "IssuerMetadata"
    assert body["issuer"].startswith("did:web:")
    ids = {obj["id"] for obj in body["credentialsSupported"]}
    assert ids == {"MembershipCredential", "OrganizationCredential"}
    # A natural person is not a holder and does not enrol (`D-49`).
    assert "DataSubjectCredential" not in ids


@pytest.mark.asyncio
async def test_credentials_supported_carries_every_optional_property(client):
    """CIP: *"Every CredentialObject in credentialsSupported MUST contain all
    OPTIONAL properties defined in CredentialObject"*."""
    body = (await client.get("/issuer/metadata")).json()
    # **Every** optional property, which is what the spec requires of entries in
    # `credentialsSupported` — `credentialSchema` was the one missing, and a set
    # that omitted it asserted conformance without checking it.
    required = {
        "id",
        "type",
        "credentialType",
        "credentialSchema",
        "bindingMethods",
        "profile",
        "issuancePolicy",
        "offerReason",
    }
    for obj in body["credentialsSupported"]:
        assert required <= set(obj)


@pytest.mark.asyncio
async def test_the_requesting_client_can_read_its_own_request_status(
    client, db_session, resolver
):
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    created = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    pid = created.json()["issuerPid"]

    r = await client.get(
        f"/issuer/requests/{pid}",
        headers={"Authorization": f"Bearer {org.si_token(code=None)}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ISSUED"
    assert r.json()["holderPid"] == "req-1"


@pytest.mark.asyncio
async def test_another_client_cannot_read_a_request_status(
    client, db_session, resolver
):
    """*"only the client that made the request MAY access a particular status"*."""
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()
    created = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    pid = created.json()["issuerPid"]

    stranger = Client("did:web:stranger.dataspaces.localhost")
    resolver.documents[stranger.did] = stranger.document()
    r = await client.get(
        f"/issuer/requests/{pid}",
        headers={"Authorization": f"Bearer {stranger.si_token(code=None)}"},
    )
    # Identical to an unknown request: distinguishing them enumerates holders.
    assert r.status_code == 404

    missing = await client.get(
        "/issuer/requests/does-not-exist",
        headers={"Authorization": f"Bearer {stranger.si_token(code=None)}"},
    )
    assert missing.status_code == r.status_code
    assert missing.json() == r.json()


@pytest.mark.asyncio
async def test_the_request_is_recorded(client, db_session, resolver):
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()
    await client.post(
        "/issuer/credentials",
        json=request_body(
            credentials=("MembershipCredential", "OrganizationCredential")
        ),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )

    request = (await db_session.execute(select(CredentialRequest))).scalar_one()
    assert request.holder_did == org.did
    assert request.owner_alias == "rec"
    assert set(request.requested) == {"MembershipCredential", "OrganizationCredential"}
    assert request.status == "ISSUED"
    # The organisation credential is gated on an accepted agreement (§5.6) and
    # this owner has none, so it is withheld **and said so** rather than silently
    # missing.
    assert "OrganizationCredential" in (request.detail or "")


# ── Issuance and delivery (CIP steps 7-8) ─────────────────────────


@pytest.mark.asyncio
async def test_enrolment_issues_and_delivers_a_membership_credential(
    client, db_session, resolver, credential_store
):
    """The leg without which a decentralized participant holds nothing.

    A presentation query is answered from the *holder's* store, so a participant
    that enrolled and was issued to only at the anchor answers every query with
    an empty presentation — correct-looking, and granting nothing.
    """
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    assert r.status_code == 201

    assert len(credential_store) == 1
    delivery = credential_store[0]
    # CIP §Storage API: POST {credentialService}/credentials
    assert delivery["url"] == f"{CS}/credentials"
    body = delivery["body"]
    assert body["type"] == "CredentialMessage"
    assert body["status"] == "ISSUED"
    payloads = {c["credentialType"] for c in body["credentials"]}
    assert payloads == {"MembershipCredential"}
    vc = body["credentials"][0]["payload"]
    assert vc["credentialSubject"]["id"] == org.did
    assert vc["proof"]["jws"]


@pytest.mark.asyncio
async def test_the_anchor_keeps_its_own_issuance_record(
    client, db_session, resolver, credential_store
):
    """Not a duplicate of the holder's copy — a different fact.

    The issuer knows *what it attested*, which is what `/credentials/check` reads
    and what revocation acts on; the holder holds *what it can present*.
    """
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()
    await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )

    from identity_registry.db.models import Credential

    rows = (
        await db_session.execute(
            select(Credential).where(Credential.subject_did == org.did)
        )
    ).scalars().all()
    assert [row.credential_type for row in rows] == ["MembershipCredential"]
    assert rows[0].status_list_index is not None


@pytest.mark.asyncio
async def test_delivery_correlates_with_the_request(
    client, db_session, resolver, credential_store
):
    """The same proof-of-control mechanism, running the other way.

    The holder verifies this token against the *anchor's* DID document, so the
    push is not "whoever can reach the endpoint".
    """
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()
    await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )

    # The delivery correlates with the request that asked for it: `issuerPid`
    # and `holderPid` are **request ids**, not DIDs. `holderPid` is echoed from
    # the client's own request, which is how a holder with two requests in
    # flight tells which one was just answered.
    body = credential_store[0]["body"]
    request = (await db_session.execute(select(CredentialRequest))).scalar_one()
    assert body["issuerPid"] == request.issuer_pid
    assert body["holderPid"] == request.holder_pid == "req-1"
    assert body["issuerPid"] != ANCHOR, "a DID here would make correlation impossible"


@pytest.mark.asyncio
async def test_a_delivery_failure_is_reported_not_swallowed(
    client, db_session, resolver, monkeypatch
):
    """A credential issued and not delivered is a partial state, and says so."""
    def _raise(request):
        raise httpx.ConnectError("no credential service there")

    transport = httpx.MockTransport(_raise)
    monkeypatch.setattr(
        issuance.httpx,
        "AsyncClient",
        lambda **kw: REAL_ASYNC_CLIENT(
            transport=transport, **{k: v for k, v in kw.items() if k != "transport"}
        ),
    )

    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()
    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    assert r.status_code == 201
    assert r.json()["status"] == "REJECTED"

    request = (await db_session.execute(select(CredentialRequest))).scalar_one()
    assert "could not deliver" in (request.detail or "")


@pytest.mark.asyncio
async def test_a_participant_publishing_no_credential_service_is_reported(
    client, db_session, resolver, credential_store
):
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document(cs=None)

    r = await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )
    assert r.json()["status"] == "REJECTED"
    assert credential_store == []
    request = (await db_session.execute(select(CredentialRequest))).scalar_one()
    assert "CredentialService" in (request.detail or "")


@pytest.mark.asyncio
async def test_re_enrolment_redelivers_and_does_not_re_mint(
    client, db_session, resolver, credential_store
):
    """A retry after a failed push must not burn a second StatusList index."""
    await make_owner(db_session)
    org = Client()
    resolver.documents[org.did] = org.document()

    for pid in ("req-1", "req-2"):
        code = await issue_code(client)
        await client.post(
            "/issuer/credentials",
            json=request_body(holder_pid=pid),
            headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
        )

    from identity_registry.db.models import Credential

    rows = (
        await db_session.execute(
            select(Credential).where(Credential.subject_did == org.did)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert len(credential_store) == 2  # delivered twice, minted once


# ── The role vocabulary is one vocabulary (GOV-21) ─────────────────────────────


@pytest.mark.asyncio
async def test_an_enrolment_token_cannot_admit_a_role_the_api_would_reject(
    client, db_session
):
    """One field, one vocabulary, whichever door you come through.

    ``POST``/``PATCH /admin/participants`` have always rejected anything outside
    ``{provider, consumer}``, and the enrolment token — which is what a
    participant's ``roles`` are written from — validated nothing. So
    ``ir-cli org enrolment-token --roles operations`` produced a participant the
    API itself forbids, and the dev bootstrap is the caller that uses that door.

    Found by a governance check: an offer named ``controller_role: operations``,
    and closing it meant deciding that a controller function is not a participant
    role. That decision is only enforceable if both doors agree.
    """
    await make_owner(db_session)
    r = await client.post(
        "/admin/onboarding/enrolments",
        json={"owner_alias": "rec", "roles": ["operations"]},
        headers=HEADERS,
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_the_service_layer_refuses_it_too_not_only_the_request_model(
    db_session,
):
    """Asserted at the service, because the CLI does not go through the API.

    `ir-cli org enrolment-token` calls `create_enrolment_token` directly, so a
    check that lives only in `CreateEnrolmentTokenRequest` leaves the one caller
    that mattered unguarded — which is exactly the state this fixes.
    """
    from identity_registry.services import enrolment as enrol_service

    await make_owner(db_session, alias="rec-service")
    with pytest.raises(enrol_service.EnrolmentError) as exc:
        await enrol_service.create_enrolment_token(
            db_session, "rec-service", roles=["operations"]
        )
    assert "operations" in exc.value.message


@pytest.mark.asyncio
async def test_the_dsp_roles_are_still_accepted(db_session):
    """The guard must not have closed the door it exists to keep open."""
    from identity_registry.services import enrolment as enrol_service

    await make_owner(db_session, alias="rec-ok")
    issued = await enrol_service.create_enrolment_token(
        db_session, "rec-ok", roles=["provider", "consumer"]
    )
    assert issued.code
