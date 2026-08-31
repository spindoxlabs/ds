"""Every CIP message this service emits, against the protocol's own schemas.

`DID-14`. The messages were built in CIP's shape from the start, which is what
made this conformance work rather than a rewrite — but *shaped like* is not
*conformant to*, and reading the prose is not reading the schema. Two defects
here were found by doing the latter:

- `issuerPid` / `holderPid` carried **DIDs**, where the schema defines them as
  the *request ids* on each side. It read plausibly and made correlation
  impossible: a holder with two requests in flight could not tell which one a
  delivery answered.
- `credentialsSupported` omitted `credentialSchema`, which the specification
  requires on **every** entry ("Every `CredentialObject` in the
  `credentialsSupported` array MUST contain all OPTIONAL properties").

## Why the expectations are vendored

The schemas live in the DCP repository, not this one. A test that read them from
a sibling checkout would pass or fail depending on whether the developer happens
to have cloned it — so the required-property sets below are a **copy**, with the
file each came from named.

A copy drifts, so it is pinned: when the DCP checkout *is* present,
`test_the_vendored_expectations_match_upstream` reads the real schemas and fails
on any divergence. A developer with the clone gets drift detection; everyone
else still gets the conformance check. Same idiom as
`provisioning.CONNECTOR_SCOPES`, and for the same reason.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# The enrolment module owns the client-side helpers: a stranger with a key, the
# code an operator issued it, and the request body it sends. The fixtures those
# need — `anchor_identity`, `credential_store` — are `conftest`'s, and are named
# by each test that needs one rather than being on by default, because two of
# the tests below turn on whether the anchor is bootstrapped or not.
from test_enrolment import Client, issue_code, make_owner, request_body

from identity_registry.api.v1.issuer import CREDENTIALS_SUPPORTED

#: Where the DCP specification's schemas live, if this machine has them.
DCP_SCHEMAS = (
    Path(os.path.expanduser("~"))
    / "git/github.com/eclipse-edc/decentralized-claims-protocol"
    / "artifacts/src/main/resources/issuance"
)

#: Copied from `credential-request-message-schema.json`.
CREDENTIAL_REQUEST_MESSAGE_REQUIRED = {"@context", "holderPid", "credentials", "type"}
CREDENTIAL_REQUEST_CREDENTIALS_REQUIRED = {"id"}

#: Copied from `credential-message-schema.json`.
CREDENTIAL_MESSAGE_REQUIRED = {"@context", "type", "issuerPid", "status"}
CREDENTIAL_CONTAINER_REQUIRED = {"payload", "credentialType", "format"}

#: Copied from `credential-object-schema.json` — plus the specification's
#: additional rule that entries in `credentialsSupported` carry every optional
#: property, which the schema itself does not express.
CREDENTIAL_OBJECT_REQUIRED = {"id", "type"}
CREDENTIAL_OBJECT_ALL = {
    "id",
    "type",
    "credentialType",
    "credentialSchema",
    "offerReason",
    "bindingMethods",
    "profile",
    "issuancePolicy",
}

#: `CredentialStatus` — from `credential-status-schema.json` / the spec table.
CREDENTIAL_STATUS_REQUIRED = {"@context", "type", "issuerPid", "holderPid", "status"}
CREDENTIAL_STATUS_VALUES = {"RECEIVED", "REJECTED", "ISSUED"}


def _definition(name: str, key: str) -> tuple[dict, dict]:
    """A named definition out of a DCP schema, with the file it came from.

    The schemas are **not** flat objects: the document root is
    `allOf: [$ref → #/definitions/X]`, and some definitions are themselves an
    `allOf` composing a sibling definition with a few extra properties
    (`CredentialStatus` = `CredentialStatusClass` + `@context`).

    Reading `required` off the wrong level returns an empty set and every
    comparison against it passes vacuously — which is exactly the failure mode
    this file exists to catch, so the composition is resolved rather than
    assumed away.
    """
    doc = json.loads((DCP_SCHEMAS / name).read_text())
    return doc["definitions"][key], doc


def _required(schema: dict, doc: dict) -> set[str]:
    """Every required property, following `allOf` and local `$ref`s.

    Only `#/definitions/…` refs are followed. A ref pointing outside the file
    (`@context` resolves to the common context schema) contributes nothing but
    is also never where a required property hides — the `required` keyword sits
    beside the ref, not behind it.
    """
    out = set(schema.get("required") or [])
    for member in schema.get("allOf") or []:
        ref = member.get("$ref", "")
        if ref.startswith("#/definitions/"):
            member = doc["definitions"][ref.rsplit("/", 1)[1]]
        out |= _required(member, doc)
    assert out, "read the wrong level: an empty required set passes vacuously"
    return out


needs_dcp = pytest.mark.skipif(
    not DCP_SCHEMAS.is_dir(),
    reason="the DCP specification checkout is not on this machine",
)


# ── The vendored copy, pinned to upstream ─────────────────────────


@needs_dcp
def test_the_vendored_expectations_match_upstream():
    """The copy above against the schemas it was copied from.

    Skipped where the DCP checkout is absent — which is most machines, and why
    the expectations are vendored at all. Where it *is* present this is what
    stops the copy going quietly stale.
    """
    assert (
        _required(
            *_definition(
                "credential-request-message-schema.json", "CredentialRequestMessage"
            )
        )
        == CREDENTIAL_REQUEST_MESSAGE_REQUIRED
    )

    assert (
        _required(*_definition("credential-message-schema.json", "CredentialMessage"))
        == CREDENTIAL_MESSAGE_REQUIRED
    )
    assert (
        _required(*_definition("credential-message-schema.json", "CredentialContainer"))
        == CREDENTIAL_CONTAINER_REQUIRED
    )

    obj, doc = _definition("credential-object-schema.json", "CredentialObject")
    assert _required(obj, doc) == CREDENTIAL_OBJECT_REQUIRED
    assert set(obj["properties"]) == CREDENTIAL_OBJECT_ALL

    assert (
        _required(*_definition("credential-status-schema.json", "CredentialStatus"))
        == CREDENTIAL_STATUS_REQUIRED
    )


# ── What this service publishes ───────────────────────────────────


def test_every_credential_object_carries_all_optional_properties():
    """*"Every CredentialObject in `credentialsSupported` MUST contain all
    OPTIONAL properties"* — the rule `credentialSchema` was violating."""
    for obj in CREDENTIALS_SUPPORTED:
        assert set(obj) == CREDENTIAL_OBJECT_ALL, obj["id"]


@pytest.mark.rule("P-22")
@pytest.mark.asyncio
async def test_issuer_metadata_is_conformant(client):
    body = (await client.get("/issuer/metadata")).json()
    assert {"@context", "type", "issuer"} <= set(body)
    assert body["type"] == "IssuerMetadata"
    for obj in body["credentialsSupported"]:
        assert set(obj) == CREDENTIAL_OBJECT_ALL


# ── What this service sends and accepts ───────────────────────────


@pytest.mark.rule("P-21")
@pytest.mark.asyncio
async def test_the_acknowledgement_is_a_conformant_credential_status(
    client, db_session, resolver, anchor_identity, credential_store
):
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()

    body = (
        await client.post(
            "/issuer/credentials",
            json=request_body(),
            headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
        )
    ).json()

    assert CREDENTIAL_STATUS_REQUIRED <= set(body)
    assert body["type"] == "CredentialStatus"
    assert body["status"] in CREDENTIAL_STATUS_VALUES


@pytest.mark.rule("P-21")
@pytest.mark.asyncio
async def test_the_delivered_message_is_a_conformant_credential_message(
    client, db_session, resolver, anchor_identity, credential_store
):
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()
    await client.post(
        "/issuer/credentials",
        json=request_body(),
        headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
    )

    message = credential_store[0]["body"]
    assert CREDENTIAL_MESSAGE_REQUIRED <= set(message)
    assert message["type"] == "CredentialMessage"
    assert message["status"] in CREDENTIAL_STATUS_VALUES
    for container in message["credentials"]:
        assert CREDENTIAL_CONTAINER_REQUIRED <= set(container)
        assert container["format"] in {"jwt", "json-ld"}


@pytest.mark.asyncio
async def test_the_pids_are_request_ids_not_dids(
    client, db_session, resolver, anchor_identity, credential_store
):
    """The defect this file exists because of.

    `issuerPid` and `holderPid` are *"a string corresponding to the issuance id"*
    on each side. DIDs there are the right *type* and the wrong *value*, so
    nothing would fail — the correlation would simply never work.
    """
    await make_owner(db_session)
    code = await issue_code(client)
    org = Client()
    resolver.documents[org.did] = org.document()
    ack = (
        await client.post(
            "/issuer/credentials",
            json=request_body(holder_pid="holder-side-id"),
            headers={"Authorization": f"Bearer {org.si_token(code=code)}"},
        )
    ).json()

    # Echoed verbatim: it is the client's id for its own request.
    assert ack["holderPid"] == "holder-side-id"
    assert ack["issuerPid"] != ack["holderPid"]
    assert not ack["issuerPid"].startswith("did:")

    delivered = credential_store[0]["body"]
    assert delivered["holderPid"] == "holder-side-id"
    assert delivered["issuerPid"] == ack["issuerPid"]


# ── Discovery ─────────────────────────────────────────────────────


@pytest.mark.rule("P-22")
@pytest.mark.asyncio
async def test_the_anchor_publishes_an_issuer_service_entry(client, db_session):
    """CIP discovery: the Issuer Service is a `service` entry of type
    `IssuerService`, whose `serviceEndpoint` is the base every credential
    request goes to.

    Without it a client has to be *told* where to enrol out of band — which
    works, and is exactly the side-channel a resolvable identifier exists to
    remove.

    Goes through `anchor_bootstrap.ensure_identity` — what `ir-cli bootstrap`
    calls — rather than hand-writing the row, because a test that builds the
    document it then reads asserts nothing about the code that builds it in
    production.
    """
    from identity_registry.config import get_settings
    from identity_registry.services import anchor_bootstrap

    settings = get_settings()
    identity = await anchor_bootstrap.ensure_identity(db_session, settings)
    await db_session.commit()

    doc = (await client.get(f"/dids/{identity.did}/did.json")).json()
    entry = next(
        s for s in doc["service"] if s["type"] == anchor_bootstrap.ISSUER_SERVICE_TYPE
    )
    assert entry["serviceEndpoint"] == f"{settings.public_base_url}/issuer"
    # The *base*: a client appends CIP's own paths to it. Publishing
    # `/issuer/credentials` would hardcode one of the two endpoints under it.
    assert not entry["serviceEndpoint"].endswith("/credentials")


@pytest.mark.rule("P-4", "P-22")
@pytest.mark.asyncio
async def test_bootstrapping_again_republishes_the_service_entry(
    client, db_session, anchor_identity
):
    """The reason this moved out of the CLI.

    Bootstrap used to return early on "a DID already exists", so a registry
    bootstrapped *before* the `IssuerService` entry was introduced would never
    publish one however many times it was re-run — the fix would have been a
    manual `UPDATE`. The autouse anchor fixture is exactly that registry: a key
    and a document with no service entries.
    """
    from identity_registry.config import get_settings
    from identity_registry.services import anchor_bootstrap

    settings = get_settings()
    anchor = f"did:web:{settings.trust_anchor_domain}"
    before = (await client.get(f"/dids/{anchor}/did.json")).json()
    assert not before.get("service"), "the fixture's anchor publishes nothing"

    identity = await anchor_bootstrap.ensure_identity(db_session, settings)
    await db_session.commit()
    assert identity.created is False, "the key was reused, not rotated"

    after = (await client.get(f"/dids/{identity.did}/did.json")).json()
    assert [s["type"] for s in after["service"]] == [
        anchor_bootstrap.ISSUER_SERVICE_TYPE
    ]
    # A rotated key would silently invalidate every credential bound to the old
    # one, on nothing more than a second bootstrap.
    assert after["verificationMethod"][0]["id"] == before["verificationMethod"][0]["id"]
