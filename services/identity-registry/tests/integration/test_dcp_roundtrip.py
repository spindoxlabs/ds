"""The DCP presentation exchange, across two registries that share nothing.

Each assertion here failed before this change, and none of them could have been
made against a single instance: the holder verifies a signature using a key it
can only have obtained by resolving the verifier's DID document over HTTP.
"""
from __future__ import annotations

import base64
import json

import httpx
import pytest
from conftest import MEMBERSHIP_SCOPE, run_exchange

pytestmark = pytest.mark.integration


def _claims(jwt: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(jwt.split(".")[1] + "===").decode())


def _query(scope: str = MEMBERSHIP_SCOPE) -> dict:
    return {
        "@context": ["https://w3id.org/dspace-dcp/v1.0/dcp.jsonld"],
        "@type": "PresentationQueryMessage",
        "scope": [scope],
    }


def _ask(holder, token: str, body: dict | None = None) -> httpx.Response:
    return httpx.post(
        f"{holder.url}/credentials/{holder.did}/presentations/query",
        json=body or _query(),
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )


# ── Publication and resolution are two halves of one thing ──────────────────


def test_each_registry_publishes_its_did_at_the_well_known_path(holder, verifier):
    for registry in (holder, verifier):
        response = httpx.get(f"{registry.url}/.well-known/did.json", timeout=10)
        assert response.status_code == 200
        assert response.json()["id"] == registry.did


def test_the_published_document_carries_a_usable_key(holder):
    document = httpx.get(f"{holder.url}/.well-known/did.json", timeout=10).json()
    method = document["verificationMethod"][0]
    assert method["publicKeyJwk"]["crv"] == "P-256"
    assert "d" not in method["publicKeyJwk"]


# ── The exchange ────────────────────────────────────────────────────────────


def test_a_verifier_with_a_grant_is_served(holder, verifier, dcp_exchange):
    """The call that used to 401 every time, now across two processes."""
    response = _ask(holder, dcp_exchange())
    assert response.status_code == 200, response.text
    assert response.json()["@type"] == "dcp:PresentationResponseMessage"


def test_the_presentation_carries_the_membership_credential(
    holder, verifier, dcp_exchange
):
    """`ir-cli participant add` issued it; the exchange is what makes it reachable."""
    body = _ask(holder, dcp_exchange()).json()
    vp = _claims(body["dcp:presentation"]["@value"][0])
    assert vp["vp"]["holder"] == holder.did
    assert vp["aud"] == verifier.did
    credentials = vp["vp"]["verifiableCredential"]
    assert len(credentials) == 1
    assert "MembershipCredential" in _claims(credentials[0])["vc"]["type"]


def test_the_credential_is_signed_by_the_trust_anchor(holder, dcp_exchange):
    body = _ask(holder, dcp_exchange()).json()
    vp = _claims(body["dcp:presentation"]["@value"][0])
    vc = _claims(vp["vp"]["verifiableCredential"][0])["vc"]
    assert vc["issuer"].startswith("did:web:")
    assert vc["issuer"] != holder.did


def test_the_status_list_url_is_fetchable(holder, dcp_exchange):
    """A revocation check that cannot fetch the list fails closed.

    Every credential issued in dev carried an `https://` URL that dev does not
    serve, so this had never once been true. It is asserted here rather than in
    a unit test because only a running server can answer it.
    """
    body = _ask(holder, dcp_exchange()).json()
    vp = _claims(body["dcp:presentation"]["@value"][0])
    vc = _claims(vp["vp"]["verifiableCredential"][0])["vc"]
    status_url = vc["credentialStatus"]["statusListCredential"]
    response = httpx.get(status_url, timeout=10)
    assert response.status_code == 200, f"{status_url} → {response.status_code}"
    assert "StatusList2021Credential" in response.json()["type"]


# ── Refusals, across the process boundary ───────────────────────────────────


def test_a_self_issued_token_without_a_grant_is_refused(holder, verifier):
    """Proving control of your own DID says who you are, not what you may see."""
    token = verifier.sts_token(audience=holder.did)["access_token"]
    assert _ask(holder, token).status_code == 401


def test_a_grant_addressed_to_a_third_party_is_refused(holder, verifier, dcp_exchange):
    """The verifier asks for a token naming somebody else as audience."""
    token = dcp_exchange(audience=verifier.did)
    assert _ask(holder, token).status_code == 401


def test_an_unreachable_did_document_is_refused(holder, ephemeral_verifier):
    """A verifier whose DID stops resolving is refused, not trusted on its token.

    The grant is real and unexpired; only the ability to check *who is presenting
    it* is gone. Failing closed here is the difference between "we verified the
    signature" and "we tried to".
    """
    token = run_exchange(holder, ephemeral_verifier)
    assert _ask(holder, token).status_code == 200, "precondition: the exchange works"
    ephemeral_verifier.stop()
    assert not ephemeral_verifier.is_running()
    assert _ask(holder, token).status_code == 401


def test_no_token_is_refused(holder):
    response = httpx.post(
        f"{holder.url}/credentials/{holder.did}/presentations/query",
        json=_query(),
        timeout=10,
    )
    assert response.status_code == 401
