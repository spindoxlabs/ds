"""Verifying a user credential against the key its issuer **publishes**.

`DID-17`. The key used to come from a file the verifying service mounted, which
is the `P-8a` class — *never against a key this deployment happens to hold*. It
now comes from the issuer's DID document, resolved over did:web and cached.

The tests that matter most here are the ones about **what is checked before the
document is fetched**. The DID to resolve is named by an unverified claim inside
the token, so an implementation that resolves first and compares issuers
afterwards will cheerfully verify a stranger's signature against the stranger's
own key and then reject it — which passes every "bad issuer is refused" test
while being a live SSRF against any URL an attacker chooses.
"""

from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from ds_auth.did_web import DidResolutionError, DidWebResolver, did_web_url
from ds_auth.user_credentials import verify_user_vc_jwt

ANCHOR = "did:web:trust-anchor.dataspaces.localhost"
KID = f"{ANCHOR}#key-1"
SUBJECT = "did:web:rec.dataspaces.localhost:users:sub-001"
PARTICIPANT = "did:web:rec.dataspaces.localhost"
TRUST_LIST = "http://trust-anchor.dataspaces.localhost/trust"


def _b64(raw: bytes | str) -> str:
    if isinstance(raw, str):
        raw = raw.encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _int_b64(value: int) -> str:
    return _b64(value.to_bytes(32, "big"))


_UNSET = object()

TWO_REGISTERS = [
    {
        "id": "https://trust-anchor.example/status/1#3",
        "type": "StatusList2021Entry",
        "statusPurpose": "revocation",
        "statusListIndex": "3",
        "statusListCredential": "https://trust-anchor.example/status/1",
    },
    {
        "id": "https://trust-anchor.example/status/2#3",
        "type": "StatusList2021Entry",
        "statusPurpose": "suspension",
        "statusListIndex": "3",
        "statusListCredential": "https://trust-anchor.example/status/2",
    },
]

ONE_REGISTER = TWO_REGISTERS[0]


class Issuer:
    """A key, the document that publishes it, and the credentials it signs."""

    def __init__(self, did: str = ANCHOR, kid: str | None = None):
        self.did = did
        self.kid = kid or f"{did}#key-1"
        self.key = ec.generate_private_key(ec.SECP256R1())

    @property
    def jwk(self) -> dict:
        numbers = self.key.public_key().public_numbers()
        return {
            "kty": "EC",
            "crv": "P-256",
            "x": _int_b64(numbers.x),
            "y": _int_b64(numbers.y),
            "kid": self.kid,
            "use": "sig",
        }

    def document(self) -> dict:
        return {
            "@context": ["https://www.w3.org/ns/did/v1"],
            "id": self.did,
            "verificationMethod": [
                {
                    "id": self.kid,
                    "type": "JsonWebKey2020",
                    "controller": self.did,
                    "publicKeyJwk": self.jwk,
                }
            ],
            "assertionMethod": [self.kid],
        }

    def credential(
        self,
        *,
        subject: str = SUBJECT,
        role: str = "DataSubject",
        types: list[str] | None = None,
        linked: str | None = PARTICIPANT,
        kid: str | None = None,
        issuer: str | None = None,
        status: object = _UNSET,
    ) -> str:
        header = {"alg": "ES256", "typ": "JWT", "kid": kid or self.kid}
        vc = {
            "id": "urn:uuid:cred-1",
            "type": types or ["VerifiableCredential", "DataSubjectCredential"],
            "issuer": issuer or self.did,
            "credentialSubject": {
                "id": subject,
                "role": role,
                **({"linkedParticipant": linked} if linked else {}),
            },
        }
        # `_UNSET` rather than `None`: a credential with **no** `credentialStatus`
        # and one with an explicit null are different cases, and both are tested.
        if status is not _UNSET:
            vc["credentialStatus"] = status
        payload = {"iss": issuer or self.did, "sub": subject, "vc": vc}
        signing_input = f"{_b64(json.dumps(header))}.{_b64(json.dumps(payload))}"
        der = self.key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256()))
        from cryptography.hazmat.primitives.asymmetric.utils import (
            decode_dss_signature,
        )

        r, s = decode_dss_signature(der)
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return f"{signing_input}.{_b64(raw)}"


class FakeResolver(DidWebResolver):
    """A resolver that serves documents from a dict and counts its fetches.

    Subclasses the real one so the cache, the `id` check and the trust-list
    logic under test are the production ones — only the HTTP call is replaced.
    """

    def __init__(self, documents: dict[str, dict], listing: dict | None = None):
        super().__init__(use_https=False, ttl_seconds=60.0)
        self.documents = documents
        self.listing = listing
        self.fetches: list[str] = []

    def _fetch(self, did: str) -> dict:
        self.fetches.append(did)
        if did not in self.documents:
            raise DidResolutionError(f"{did} is unreachable")
        return self.documents[did]

    def _trust_list(self, url: str) -> dict:
        self.fetches.append(url)
        if self.listing is None:
            raise DidResolutionError(f"trust list at {url} is unavailable")
        return self.listing


def active_listing(did: str = ANCHOR, scope: list[str] | None = None) -> dict:
    return {
        "type": "DataspaceTrustList",
        "issuers": [
            {
                "id": did,
                "role": "trust-anchor",
                "status": "active",
                "scopeOfAttestation": scope
                if scope is not None
                else ["DataSubjectCredential"],
            }
        ],
    }


@pytest.fixture
def anchor() -> Issuer:
    return Issuer()


@pytest.fixture
def resolver(anchor: Issuer) -> FakeResolver:
    return FakeResolver({anchor.did: anchor.document()}, active_listing())


def verify(token, resolver, **kwargs):
    return verify_user_vc_jwt(
        token,
        kwargs.pop("subject", SUBJECT),
        kwargs.pop("issuer_did", ANCHOR),
        kwargs.pop("roles", {"DataSubject"}),
        resolver=resolver,
        **kwargs,
    )


# ── the key comes from the document ───────────────────────────────


@pytest.mark.rule("P-8c")
def test_a_credential_verifies_against_the_published_key(anchor, resolver):
    credential = verify(anchor.credential(), resolver)
    assert credential.did == SUBJECT
    assert credential.issuer == ANCHOR
    assert resolver.fetches == [ANCHOR]


@pytest.mark.rule("P-8c", "P-11")
def test_a_signature_from_another_key_is_refused(anchor, resolver):
    impostor = Issuer()  # same DID, different key — a stolen or stale key
    with pytest.raises(HTTPException) as exc:
        verify(impostor.credential(), resolver)
    assert exc.value.status_code == 401


def test_the_kid_selects_the_key(anchor, resolver):
    """A `kid` naming a method the document does not publish is a refusal.

    Not a fallback to "the only key there is": a document with one key today
    may have two tomorrow, and a verifier that ignores `kid` would then verify
    against whichever was serialised first.
    """
    with pytest.raises(HTTPException) as exc:
        verify(anchor.credential(kid=f"{ANCHOR}#key-9"), resolver)
    assert exc.value.status_code == 503
    assert "kid" in exc.value.detail


@pytest.mark.rule("P-8c")
def test_an_unreachable_issuer_fails_closed(anchor):
    empty = FakeResolver({}, active_listing())
    with pytest.raises(HTTPException) as exc:
        verify(anchor.credential(), empty)
    assert exc.value.status_code == 503


# ── what happens before the document is fetched ───────────────────


@pytest.mark.rule("P-8c")
def test_an_untrusted_issuer_is_refused_without_resolving_anything(resolver):
    """The check that keeps this from being a request-forgery primitive.

    `iss` is attacker-controlled and names the URL to fetch. Refusing it only
    *after* resolution would mean any token could make this service issue an
    outbound request to a host of the attacker's choosing — and would still pass
    a test that merely asserts the credential is rejected.
    """
    stranger = Issuer(did="did:web:evil.example.test")
    resolver.documents[stranger.did] = stranger.document()

    with pytest.raises(HTTPException) as exc:
        verify(stranger.credential(), resolver)
    assert exc.value.status_code == 403
    assert resolver.fetches == [], "the stranger's DID must never be fetched"


def test_a_credential_naming_the_anchor_but_signed_by_a_stranger_is_refused(
    anchor, resolver
):
    """`iss` says the anchor, the signature is somebody else's key."""
    stranger = Issuer(did="did:web:evil.example.test", kid=KID)
    token = stranger.credential(issuer=ANCHOR, kid=KID)
    with pytest.raises(HTTPException) as exc:
        verify(token, resolver)
    assert exc.value.status_code == 401


# ── authority, not authorship: the trust list ─────────────────────


@pytest.mark.rule("P-8c")
def test_a_revoked_issuer_is_refused(anchor, resolver):
    """The event the trust list exists to publish.

    A withdrawn accreditation changes nothing about the issuer's key: it still
    signs perfectly valid credentials. Only the list says it should no longer be
    believed, which is why revoked entries stay listed rather than disappearing.
    """
    resolver.listing = {
        "issuers": [
            {"id": ANCHOR, "status": "revoked", "revocationReason": "key compromise"}
        ]
    }
    with pytest.raises(HTTPException) as exc:
        verify(anchor.credential(), resolver, trust_list_url=TRUST_LIST)
    assert exc.value.status_code == 503
    assert "key compromise" in exc.value.detail


@pytest.mark.rule("P-8c")
def test_an_unlisted_issuer_is_refused(anchor, resolver):
    resolver.listing = {"issuers": []}
    with pytest.raises(HTTPException) as exc:
        verify(anchor.credential(), resolver, trust_list_url=TRUST_LIST)
    assert exc.value.status_code == 503
    assert "not on the dataspace trust list" in exc.value.detail


def test_a_credential_outside_the_scope_of_attestation_is_refused(anchor, resolver):
    """`DSSC-TRF-19` — accredited *in relation to a specific scope*."""
    resolver.listing = active_listing(scope=["MembershipCredential"])
    with pytest.raises(HTTPException) as exc:
        verify(anchor.credential(), resolver, trust_list_url=TRUST_LIST)
    assert exc.value.status_code == 503
    assert "DataSubjectCredential" in exc.value.detail


def test_an_unreachable_trust_list_fails_closed(anchor, resolver):
    """Not consulting the list is not the same as the list saying yes."""
    resolver.listing = None
    with pytest.raises(HTTPException) as exc:
        verify(anchor.credential(), resolver, trust_list_url=TRUST_LIST)
    assert exc.value.status_code == 503


def test_the_list_is_not_consulted_when_no_url_is_configured(anchor, resolver):
    resolver.listing = None
    assert verify(anchor.credential(), resolver).issuer == ANCHOR


# ── caching ───────────────────────────────────────────────────────


def test_the_document_is_fetched_once_across_requests(anchor, resolver):
    """This runs on every request carrying a credential, so it is cached."""
    for _ in range(3):
        verify(anchor.credential(), resolver)
    assert resolver.fetches == [ANCHOR]


def test_invalidating_forces_a_refetch(anchor, resolver):
    """Key rotation without waiting out the TTL."""
    verify(anchor.credential(), resolver)
    resolver.invalidate(ANCHOR)
    verify(anchor.credential(), resolver)
    assert resolver.fetches == [ANCHOR, ANCHOR]


def test_a_rotated_key_is_picked_up_after_invalidation(anchor, resolver):
    verify(anchor.credential(), resolver)

    rotated = Issuer()
    resolver.documents[ANCHOR] = rotated.document()
    # Still cached: the old key verifies, the new one does not. This is the
    # rotation window the TTL bounds, stated rather than discovered.
    with pytest.raises(HTTPException):
        verify(rotated.credential(), resolver)

    resolver.invalidate()
    assert verify(rotated.credential(), resolver).issuer == ANCHOR


# ── configuration ─────────────────────────────────────────────────


@pytest.mark.rule("P-11")
def test_no_issuer_and_no_insecure_flag_is_a_503(anchor, resolver):
    with pytest.raises(HTTPException) as exc:
        verify(anchor.credential(), resolver, issuer_did=None)
    assert exc.value.status_code == 503


def test_insecure_dev_skips_verification(anchor, resolver):
    """One switch, one meaning.

    It used to be implied by *the absence of a mounted key*, so a deployment
    that forgot the mount and left the flag at its permissive default accepted
    unverified credentials while looking configured.
    """
    impostor = Issuer()
    credential = verify(impostor.credential(), resolver, insecure_dev=True)
    assert credential.did == SUBJECT
    assert resolver.fetches == []


@pytest.mark.rule("P-8c")
def test_a_document_served_for_the_wrong_did_is_refused(anchor):
    """A host that answers with somebody else's document resolves nothing."""

    class WrongDocument(FakeResolver):
        def _fetch(self, did: str) -> dict:
            self.fetches.append(did)
            return {"id": "did:web:somebody.else", "verificationMethod": []}

    with pytest.raises(HTTPException) as exc:
        verify(anchor.credential(), WrongDocument({}, active_listing()))
    assert exc.value.status_code == 503


# ── did:web URL mapping ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("did", "url"),
    [
        ("did:web:example.com", "https://example.com/.well-known/did.json"),
        ("did:web:example.com:a:b", "https://example.com/a/b/did.json"),
        ("did:web:example.com%3A3000", "https://example.com:3000/.well-known/did.json"),
    ],
)
def test_did_web_urls(did, url):
    assert did_web_url(did) == url


@pytest.mark.rule("P-8c")
def test_did_web_over_http_is_explicit():
    assert did_web_url("did:web:x.test", use_https=False).startswith("http://")


@pytest.mark.rule("P-8c")
def test_only_did_web_is_supported():
    with pytest.raises(DidResolutionError):
        did_web_url("did:key:z6Mk")


# ── credentialStatus: one entry or several ────────────────────────
#
# Every credential the identity-registry issues now names **two** registers —
# revocation and suspension, on the index they share — because a superseded
# credential has to be retirable without being revoked. That makes
# `credentialStatus` a JSON *array*, and this check used to require an object.
# The failure was a 401 reading "User VC has no credentialStatus" on a
# credential that had two.


def _status_list(tmp_path, status: str = "active"):
    path = tmp_path / "credential-status.json"
    path.write_text(
        json.dumps({"credentials": {"urn:uuid:cred-1": {"status": status}}})
    )
    return str(path)


@pytest.mark.rule("P-27")
def test_a_credential_naming_both_registers_is_accepted(anchor, resolver, tmp_path):
    credential = verify(
        anchor.credential(status=TWO_REGISTERS),
        resolver,
        credential_status_path=_status_list(tmp_path),
    )
    assert credential.did == SUBJECT


@pytest.mark.rule("P-27")
def test_a_credential_naming_one_register_is_still_accepted(anchor, resolver, tmp_path):
    """The shape issued before this change, and by any other issuer. Dropping
    it would refuse every credential already in a wallet."""
    credential = verify(
        anchor.credential(status=ONE_REGISTER),
        resolver,
        credential_status_path=_status_list(tmp_path),
    )
    assert credential.did == SUBJECT


@pytest.mark.parametrize("status", [_UNSET, None, [], "not-an-object", [None]])
def test_a_credential_with_no_usable_status_entry_is_refused(
    anchor, resolver, tmp_path, status
):
    """An empty array is *not* a status entry, and neither is a list of nulls —
    which is the case a naive `isinstance(status, list)` would let through."""
    with pytest.raises(HTTPException) as exc:
        verify(
            anchor.credential(status=status),
            resolver,
            credential_status_path=_status_list(tmp_path),
        )
    assert exc.value.status_code == 401
    assert "credentialStatus" in exc.value.detail


def test_a_suspended_credential_is_refused_whatever_its_shape(
    anchor, resolver, tmp_path
):
    """Suspension is what the second register exists for, and this is the check
    that reads it — by credential id, not by bit."""
    with pytest.raises(HTTPException) as exc:
        verify(
            anchor.credential(status=TWO_REGISTERS),
            resolver,
            credential_status_path=_status_list(tmp_path, "suspended"),
        )
    assert exc.value.status_code == 401
    assert "not active" in exc.value.detail
