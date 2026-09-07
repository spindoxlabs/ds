import pytest
from conftest import make_admin_headers, register_enrolled

from identity_registry.services.crypto import generate_key_pair
from identity_registry.services.did import build_did_document


@pytest.mark.rule("P-6")
def test_participant_did_document():
    kp = generate_key_pair("did:web:rec.dataspaces.localhost")
    doc = build_did_document(
        did="did:web:rec.dataspaces.localhost",
        public_jwk=kp.public_jwk,
        did_type="participant",
        service_endpoints=[
            {
                "type": "DSPEndpoint",
                "serviceEndpoint": "https://rec.dataspaces.localhost/protocol",
            },
            {
                "type": "CredentialService",
                "serviceEndpoint": "https://vc-wallet-rec.dataspaces.localhost/api/v1",
            },
        ],
    )
    assert doc["id"] == "did:web:rec.dataspaces.localhost"
    assert doc["@context"][0] == "https://www.w3.org/ns/did/v1"
    assert len(doc["verificationMethod"]) == 1
    vm = doc["verificationMethod"][0]
    assert vm["type"] == "JsonWebKey2020"
    assert vm["controller"] == "did:web:rec.dataspaces.localhost"
    assert "d" not in vm["publicKeyJwk"]
    assert "authentication" in doc
    assert "assertionMethod" in doc
    assert len(doc["service"]) == 2


@pytest.mark.rule("P-6")
def test_trust_anchor_did_document():
    kp = generate_key_pair("did:web:trust-anchor.dataspaces.localhost")
    doc = build_did_document(
        did="did:web:trust-anchor.dataspaces.localhost",
        public_jwk=kp.public_jwk,
        did_type="trust-anchor",
    )
    assert "authentication" not in doc
    assert "assertionMethod" in doc
    assert "service" not in doc


@pytest.mark.rule("D-22")
@pytest.mark.rule("P-6")
def test_user_did_document_no_auth():
    kp = generate_key_pair("did:web:rec.dataspaces.localhost:users:email-abc123")
    doc = build_did_document(
        did="did:web:rec.dataspaces.localhost:users:email-abc123",
        public_jwk=kp.public_jwk,
        did_type="user",
    )
    assert "authentication" not in doc


# ── Resolution over the did:web mapping ─────────────────────────────────────
#
# `GET /.well-known/did.json` is how every counterparty and every EDC actually
# reaches a DID document. It was served only by Caddy's and the Ingress's
# rewrite to `/dids/{did}/did.json`, so the service itself could not answer the
# request the did:web method defines.

HEADERS = make_admin_headers()


async def _add_participant(db_session, did: str) -> None:
    """Register a participant the way one now comes to exist.

    Was `POST /admin/participants`, which created the DID and its keypair as a
    side effect. It no longer does (`D-51`): the anchor records a key the
    organisation proved control of. These tests are about DID **resolution**, so
    what they need is a registered DID with a published public key.
    """
    await register_enrolled(db_session, did, roles=["provider"], scopes=[])


@pytest.mark.asyncio
async def test_well_known_resolves_the_host_did(client, db_session):
    await _add_participant(db_session, "did:web:rec.dataspaces.localhost")
    r = await client.get(
        "/.well-known/did.json",
        headers={"Host": "rec.dataspaces.localhost"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == "did:web:rec.dataspaces.localhost"


@pytest.mark.asyncio
async def test_well_known_percent_encodes_a_port(client, db_session):
    """did:web:127.0.0.1%3A8080 ← host 127.0.0.1:8080. Without this a
    non-standard port cannot be resolved at all, which is what an integration
    test — and any deployment not on :443 — needs."""
    await _add_participant(db_session, "did:web:127.0.0.1%3A8080")
    r = await client.get("/.well-known/did.json", headers={"Host": "127.0.0.1:8080"})
    assert r.status_code == 200
    assert r.json()["id"] == "did:web:127.0.0.1%3A8080"


@pytest.mark.rule("P-6")
@pytest.mark.asyncio
async def test_well_known_is_404_for_an_unknown_host(client):
    r = await client.get(
        "/.well-known/did.json", headers={"Host": "stranger.dataspaces.localhost"}
    )
    assert r.status_code == 404


@pytest.mark.rule("D-22")
@pytest.mark.asyncio
async def test_the_did_path_route_does_not_shadow_dids(client, db_session):
    """`/{did_path}/did.json` is a catch-all and is registered last.

    A catch-all declared before its siblings is how `/dids/{did}/did.json` would
    start answering 404 for a DID it holds — the shape that once made
    `POST /catalog/search` look like a missing dataset in the connector.
    """
    did = "did:web:rec.dataspaces.localhost"
    await _add_participant(db_session, did)
    r = await client.get(f"/dids/{did}/did.json")
    assert r.status_code == 200
    assert r.json()["id"] == did


@pytest.mark.rule("D-22", "D-22a")
@pytest.mark.rule("P-6")
@pytest.mark.asyncio
async def test_path_form_resolves_a_user_did(client, db_session):
    """`did:web:<participant>:users:<id>` → `/users/<id>/did.json`, served here.

    The path form is what makes a person's DID resolvable by **the organisation
    that holds their credentials** rather than by a proxy rewrite the chart turns
    on. Since `DID-11` step 2 that is the whole mechanism: the person is named in
    their custodian's namespace, and their custodian's instance answers — no
    `users.<domain>` host and no rule of its own (`personal-data.md` `D-22a`).
    """
    from identity_registry.db.models import Did

    did = "did:web:rec.dataspaces.localhost:users:alice"
    # No key, and that is the honest document for somebody who signs nothing.
    db_session.add(Did(did=did, did_type="user", key_id=None, active=True))
    await db_session.commit()

    r = await client.get(
        "/users/alice/did.json", headers={"Host": "rec.dataspaces.localhost"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == did
    assert "verificationMethod" not in body


# ── The subject id is validated, because the DID is concatenation ─
#
# `subject_did_for` validated its custodian and not its subject id, so a caller
# that fed a DID back in produced a nested one — well-formed enough to be
# stored, resolved and published, and unrecognisable to `subject_id_of`, which
# splits on the last `:users:`. That is one person becoming two, silently
# (ds#31).


@pytest.mark.parametrize(
    "subject_id",
    [
        "did:web:rec.dataspaces.localhost:users:member-001",
        "did:web:rec.dataspaces.localhost",
        "users:alice",
        "a:b",
    ],
)
def test_a_qualified_subject_id_is_refused(subject_id):
    from identity_registry.services.did import SubjectNamespaceError, subject_did_for

    with pytest.raises(SubjectNamespaceError) as exc:
        subject_did_for("did:web:rec.dataspaces.localhost", subject_id)
    assert "subject_id" in str(exc.value)


@pytest.mark.parametrize("subject_id", ["", "   ", "\t"])
def test_an_empty_subject_id_is_refused(subject_id):
    """`did:web:rec…:users:` resolves to the custodian's users collection rather
    than to anybody, and is a DID row nothing can look up."""
    from identity_registry.services.did import SubjectNamespaceError, subject_did_for

    with pytest.raises(SubjectNamespaceError):
        subject_did_for("did:web:rec.dataspaces.localhost", subject_id)


@pytest.mark.parametrize(
    "subject_id", ["alice", "member-001", "email-9f2c1ab4d7e60351cc2f8b19"]
)
def test_an_unqualified_subject_id_round_trips(subject_id):
    """Including the shape `derive_email_subject_id` returns, which is the value
    `/users/resolve` hands a caller for first-time issuance."""
    from identity_registry.services.did import subject_did_for, subject_id_of

    did = subject_did_for("did:web:rec.dataspaces.localhost", subject_id)
    assert subject_id_of(did) == subject_id


@pytest.mark.asyncio
async def test_issuing_with_a_did_as_subject_id_is_422(client, anchor_identity):
    """The refusal a caller actually meets: 422 naming the problem, at the point
    the mistake is made, rather than 201 and a second identity."""
    from conftest import make_headers

    r = await client.post(
        "/admin/credentials/data-subject",
        json={
            "subject_id": "did:web:rec.dataspaces.localhost:users:member-001",
            "role": "DataSubject",
            "linked_participant_did": "did:web:rec.dataspaces.localhost",
        },
        headers=make_headers(),
    )
    assert r.status_code == 422
    assert "subject_id" in r.json()["detail"]
