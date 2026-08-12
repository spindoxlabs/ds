"""did:web resolution and verification-key selection.

Pure rules, and the ones a live run can never exercise: on the stack every DID
resolves and every document is well formed, so the *refusals* — the whole point
of resolving rather than trusting — never happen. Each case below is a sentence
from the DCP specification, §Validating Self-Issued ID Tokens, or from the
did:web method.
"""
from __future__ import annotations

import httpx
import pytest

from identity_registry.services.did_resolver import (
    DidResolutionError,
    DidResolver,
    did_web_url,
    normalize_did_web,
    verification_key,
)

# ── did:web → URL ───────────────────────────────────────────────────────────


def test_bare_host_resolves_to_well_known():
    assert (
        did_web_url("did:web:example.com")
        == "https://example.com/.well-known/did.json"
    )


def test_path_segments_become_a_path():
    assert (
        did_web_url("did:web:example.com:users:alice")
        == "https://example.com/users/alice/did.json"
    )


def test_percent_encoded_port_is_decoded():
    assert (
        did_web_url("did:web:example.com%3A3000")
        == "https://example.com:3000/.well-known/did.json"
    )


def test_http_is_opt_in():
    """Dev serves did:web over plain HTTP through Caddy; production never does."""
    assert did_web_url("did:web:x.localhost", use_https=False).startswith("http://")


@pytest.mark.parametrize("did", ["did:key:z6Mk", "did:web:", "not-a-did"])
def test_unsupported_identifiers_are_refused(did):
    with pytest.raises(DidResolutionError):
        did_web_url(did)


# ── Key selection out of a document ─────────────────────────────────────────


def _document(*methods, invocation=None):
    doc = {"id": "did:web:example.com", "verificationMethod": list(methods)}
    if invocation is not None:
        doc["capabilityInvocation"] = invocation
    return doc


def _method(kid, jwk=None):
    return {
        "id": kid,
        "type": "JsonWebKey2020",
        "publicKeyJwk": {"kty": "EC", "crv": "P-256", "x": "a", "y": "b"}
        if jwk is None
        else jwk,
    }


@pytest.mark.rule("P-8a")
def test_kid_selects_the_matching_method():
    doc = _document(
        _method("did:web:example.com#key-1"),
        _method("did:web:example.com#key-2"),
    )
    assert verification_key(doc, "did:web:example.com#key-2") == doc[
        "verificationMethod"
    ][1]["publicKeyJwk"]


@pytest.mark.rule("P-8a")
def test_unmatched_kid_is_a_refusal_not_a_fallback():
    """The single most important rule here.

    Falling back to "the only key in the document" when the kid does not match
    is how a rotated or revoked key keeps working.
    """
    doc = _document(_method("did:web:example.com#key-1"))
    with pytest.raises(DidResolutionError):
        verification_key(doc, "did:web:example.com#key-9")


def test_no_kid_uses_a_lone_capability_invocation_method():
    doc = _document(
        _method("did:web:example.com#key-1"),
        invocation=["did:web:example.com#key-1"],
    )
    assert verification_key(doc, None)["crv"] == "P-256"


def test_no_kid_with_several_candidates_is_refused():
    doc = _document(
        _method("did:web:example.com#key-1"),
        _method("did:web:example.com#key-2"),
        invocation=["did:web:example.com#key-1", "did:web:example.com#key-2"],
    )
    with pytest.raises(DidResolutionError):
        verification_key(doc, None)


def test_no_kid_and_no_capability_invocation_is_refused():
    with pytest.raises(DidResolutionError):
        verification_key(_document(_method("did:web:example.com#key-1")), None)


@pytest.mark.rule("P-8a")
def test_method_without_a_jwk_is_refused():
    doc = _document(
        {"id": "did:web:example.com#key-1", "type": "Ed25519VerificationKey2018"}
    )
    with pytest.raises(DidResolutionError):
        verification_key(doc, "did:web:example.com#key-1")


@pytest.mark.rule("P-8a")
def test_document_without_verification_methods_is_refused():
    with pytest.raises(DidResolutionError):
        verification_key({"id": "did:web:example.com"}, None)


# ── Fetching ────────────────────────────────────────────────────────────────


class _StubTransport(httpx.AsyncBaseTransport):
    def __init__(self, handler):
        self._handler = handler

    async def handle_async_request(self, request):
        return self._handler(request)


@pytest.fixture
def stub_http(monkeypatch):
    """Answer any outbound httpx.AsyncClient GET with a canned response."""

    def install(handler):
        original = httpx.AsyncClient.__init__

        def patched(self, *args, **kwargs):
            kwargs["transport"] = _StubTransport(handler)
            original(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)

    return install


@pytest.mark.rule("P-8a")
@pytest.mark.asyncio
async def test_document_answering_for_another_did_is_refused(stub_http):
    """A host serving several DIDs must not let one answer for another."""
    stub_http(
        lambda request: httpx.Response(
            200, json={"id": "did:web:someone-else.example.com"}
        )
    )
    with pytest.raises(DidResolutionError):
        await DidResolver().resolve("did:web:example.com")


@pytest.mark.asyncio
async def test_non_200_is_refused(stub_http):
    stub_http(lambda request: httpx.Response(404, text="nope"))
    with pytest.raises(DidResolutionError):
        await DidResolver().resolve("did:web:example.com")


@pytest.mark.asyncio
async def test_non_json_is_refused(stub_http):
    stub_http(lambda request: httpx.Response(200, text="<html>hi</html>"))
    with pytest.raises(DidResolutionError):
        await DidResolver().resolve("did:web:example.com")


@pytest.mark.rule("P-8a")
@pytest.mark.asyncio
async def test_transport_failure_is_refused_not_raised_raw(stub_http):
    def boom(request):
        raise httpx.ConnectError("no route to host")

    stub_http(boom)
    with pytest.raises(DidResolutionError):
        await DidResolver().resolve("did:web:example.com")


@pytest.mark.asyncio
async def test_a_well_formed_document_is_returned(stub_http):
    document = {"id": "did:web:example.com", "verificationMethod": []}
    stub_http(lambda request: httpx.Response(200, json=document))
    assert await DidResolver().resolve("did:web:example.com") == document


# ── The spelling a URL path leaves behind ───────────────────────────────────


def test_a_decoded_port_is_restored():
    """`did:web:host%3A8080` arrives from a URL path as `did:web:host:8080`.

    Found by the integration harness, which is the first thing in this
    repository to run a registry anywhere but a default port: every lookup and
    every `client_id` comparison is string equality against the stored, encoded
    form, so the decoded spelling matched nothing and the STS answered 401.
    """
    assert (
        normalize_did_web("did:web:127.0.0.1:8080") == "did:web:127.0.0.1%3A8080"
    )


def test_a_path_segment_is_not_mistaken_for_a_port():
    did = "did:web:users.example.org:alice"
    assert normalize_did_web(did) == did


def test_an_already_encoded_did_is_unchanged():
    did = "did:web:127.0.0.1%3A8080"
    assert normalize_did_web(did) == did


def test_a_port_and_a_path_together():
    assert (
        normalize_did_web("did:web:127.0.0.1:8080:trust-anchor")
        == "did:web:127.0.0.1%3A8080:trust-anchor"
    )


def test_a_non_web_did_is_left_alone():
    assert normalize_did_web("did:key:z6Mk") == "did:key:z6Mk"
