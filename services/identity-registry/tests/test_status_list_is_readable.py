"""The register this service publishes, read by the verifier that consumes it.

Both ends of this were ours and neither had ever met the other. The provisioning
bundle hands a new participant `trust.credential_status_url = {ir}/status/1`;
that endpoint serves a **StatusList2021 credential**; and `ds_auth` read its
source as a bespoke `{"credentials": {<id>: {"status": …}}}` lookup map that no
issuer anywhere emits. So a deployment that wired the value it was handed 401'd
every user credential it was ever shown, on every route behind a user VC
(ds#32).

Nothing caught it because `ds_auth`'s only fixture wrote the bespoke shape by
hand: the reader and its test agreed with each other and with nothing else.
`libs/ds-auth` now builds the real document, but it still *builds* it — so this
is the test that closes the loop, because the document here comes out of the
route and the index comes out of the allocator.

**It is a seam test, so it belongs to both sides.** If `/status/{id}` changes
shape, or `_suspendable_credential_status` changes which URL it names, or
`ds_auth` changes how it reads a register, this is what fails.
"""

from __future__ import annotations

import base64
import functools
import json
from urllib.error import URLError

import pytest
from ds_auth import user_credentials
from ds_auth.did_web import DidResolutionError, DidWebResolver
from fastapi import HTTPException

from identity_registry.services.status_list import (
    allocate_suspendable_index,
    get_or_create_status_list,
    revoke_status_list_index,
    suspend_status_list_index,
)
from identity_registry.services.vc import build_data_subject_credential

ANCHOR_DID = "did:web:trust-anchor.dataspaces.localhost"
PARTICIPANT = "did:web:rec.dataspaces.localhost"
SUBJECT = f"{PARTICIPANT}:users:alice"

#: What the bundle hands a participant, and what the credential names. One
#: source in production — `Settings.public_base_url` builds both.
REVOCATION_LIST = "http://test/status/1"
SUSPENSION_LIST = "http://test/status/2"


def _credential(index: int) -> dict:
    return build_data_subject_credential(
        issuer_did=ANCHOR_DID,
        subject_did=SUBJECT,
        role="DataSubject",
        linked_participant_did=PARTICIPANT,
        credentials_context_url="http://test/contexts/credentials.jsonld",
        dataspace_uri="urn:dataspace:test",
        status_list_credential_url=REVOCATION_LIST,
        suspension_list_credential_url=SUSPENSION_LIST,
        status_list_index=index,
    )


class _AnchorResolver(DidWebResolver):
    """Serves the anchor's DID document as the registry itself publishes it."""

    def __init__(self, document: dict):
        super().__init__(use_https=False)
        self.document = document

    def _fetch(self, did: str) -> dict:
        if did != self.document.get("id"):
            raise DidResolutionError(f"{did} is unreachable")
        return self.document


@pytest.fixture(autouse=True)
def _no_cached_register():
    user_credentials.reset_status_cache()
    yield
    user_credentials.reset_status_cache()


async def _serve(client, monkeypatch, anchor_identity) -> dict[str, dict]:
    """Both registers, fetched from the route and handed to `ds_auth` verbatim.

    **The signed form**, with the exact `Accept` the reader sends
    (`application/vc+jwt`): the reader verifies the register's signature against
    the key the anchor's DID document publishes and refuses the unsigned JSON
    branch (R3). So both the register and the DID document come out of this
    registry's own routes — nothing here is built by hand.

    Returns the register credentials, decoded, for the purpose assertions.
    """
    bodies: dict[str, str] = {}
    documents: dict[str, dict] = {}
    for url, list_id in ((REVOCATION_LIST, "1"), (SUSPENSION_LIST, "2")):
        response = await client.get(
            f"/status/{list_id}", headers={"Accept": "application/vc+jwt"}
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/vc+jwt")
        bodies[url] = response.text
        payload = response.text.split(".")[1]
        documents[url] = json.loads(base64.urlsafe_b64decode(payload + "==="))["vc"]

    did_document = await client.get(f"/dids/{ANCHOR_DID}/did.json")
    assert did_document.status_code == 200, did_document.text
    resolver = _AnchorResolver(did_document.json())

    class _Fetch:
        def __call__(self, request, timeout=None):
            url = request.full_url
            assert request.get_header("Accept") == "application/vc+jwt"
            if url not in bodies:
                raise URLError(f"{url} is unreachable")
            body = bodies[url].encode()

            class _Response:
                def read(self):
                    return body

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

            return _Response()

    monkeypatch.setattr(user_credentials, "urlopen", _Fetch())
    monkeypatch.setattr(
        user_credentials,
        "_verify_credential_status",
        functools.partial(
            _VERIFY, issuer=ANCHOR_DID, verify_signature=True, resolver=resolver
        ),
    )
    return documents


_VERIFY = user_credentials._verify_credential_status


@pytest.mark.rule("P-27")
@pytest.mark.asyncio
async def test_a_live_credential_passes_against_the_published_registers(
    client, db_session, monkeypatch, anchor_identity
):
    """The whole defect, in one assertion.

    This failed before the fix with 401 "User VC is not present in credential
    status list" — a message about an unknown credential, on a credential that
    was active, because the reader could not understand the document.
    """
    index = await allocate_suspendable_index(db_session)
    await db_session.commit()
    await _serve(client, monkeypatch, anchor_identity)

    user_credentials._verify_credential_status(
        _credential(index), credential_status_url=REVOCATION_LIST
    )


@pytest.mark.rule("P-27")
@pytest.mark.asyncio
async def test_a_revoked_credential_is_refused_as_revoked(
    client, db_session, monkeypatch, anchor_identity
):
    index = await allocate_suspendable_index(db_session)
    await revoke_status_list_index(db_session, index)
    await db_session.commit()
    await _serve(client, monkeypatch, anchor_identity)

    with pytest.raises(HTTPException) as exc:
        user_credentials._verify_credential_status(
            _credential(index), credential_status_url=REVOCATION_LIST
        )
    assert exc.value.status_code == 401
    assert "revoked" in exc.value.detail


@pytest.mark.rule("P-27")
@pytest.mark.asyncio
async def test_a_suspended_credential_is_refused_as_suspended(
    client, db_session, monkeypatch, anchor_identity
):
    """`P-27` gave every credential two registers so a verifier could tell
    *superseded* from *withdrawn*. Until this fix ours could see neither, and
    the bespoke lookup map had no way to express the difference at all."""
    index = await allocate_suspendable_index(db_session)
    await suspend_status_list_index(db_session, index)
    await db_session.commit()
    await _serve(client, monkeypatch, anchor_identity)

    with pytest.raises(HTTPException) as exc:
        user_credentials._verify_credential_status(
            _credential(index), credential_status_url=REVOCATION_LIST
        )
    assert exc.value.status_code == 401
    assert "suspended" in exc.value.detail
    assert "revoked" not in exc.value.detail


@pytest.mark.rule("P-27")
@pytest.mark.asyncio
async def test_suspending_one_credential_does_not_refuse_its_neighbour(
    client, db_session, monkeypatch, anchor_identity
):
    """The index is what makes a register per-credential, and it is allocated
    from a counter shared by both. A reader with the bit arithmetic wrong, or an
    allocator handing out the same index twice, both show up here."""
    suspended = await allocate_suspendable_index(db_session)
    bystander = await allocate_suspendable_index(db_session)
    assert suspended != bystander
    await suspend_status_list_index(db_session, suspended)
    await db_session.commit()
    await _serve(client, monkeypatch, anchor_identity)

    user_credentials._verify_credential_status(
        _credential(bystander), credential_status_url=REVOCATION_LIST
    )


@pytest.mark.asyncio
async def test_the_registers_publish_the_purposes_the_credential_names(
    client, db_session, monkeypatch, anchor_identity
):
    """A revocation entry pointing at a list published as suspension is refused
    by EDC and now by us. This asserts the two ends actually agree — that
    `/status/1` is the revocation register and `/status/2` the suspension one,
    which is the pairing `_suspendable_credential_status` writes into every
    credential.
    """
    await get_or_create_status_list(db_session, "1")
    await get_or_create_status_list(db_session, "2")
    await db_session.commit()
    documents = await _serve(client, monkeypatch, anchor_identity)

    assert (
        documents[REVOCATION_LIST]["credentialSubject"]["statusPurpose"] == "revocation"
    )
    assert (
        documents[SUSPENSION_LIST]["credentialSubject"]["statusPurpose"] == "suspension"
    )


@pytest.mark.rule("P-8b")
@pytest.mark.asyncio
async def test_the_unsigned_json_branch_is_not_a_register_the_reader_accepts(
    client, db_session, monkeypatch, anchor_identity
):
    """R3: `/status/{id}` still answers `Accept: application/json` with the bare
    credential, for anyone who asks for it — and the verifier refuses that body,
    because a register nobody signed is one anyone on the path can rewrite."""
    index = await allocate_suspendable_index(db_session)
    await db_session.commit()
    await _serve(client, monkeypatch, anchor_identity)
    unsigned = await client.get("/status/1", headers={"Accept": "application/json"})
    assert unsigned.status_code == 200

    class _Fetch:
        def __call__(self, request, timeout=None):
            body = unsigned.content

            class _Response:
                def read(self):
                    return body

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

            return _Response()

    monkeypatch.setattr(user_credentials, "urlopen", _Fetch())
    with pytest.raises(HTTPException) as exc:
        user_credentials._verify_credential_status(
            _credential(index), credential_status_url=REVOCATION_LIST
        )
    assert exc.value.status_code == 503
