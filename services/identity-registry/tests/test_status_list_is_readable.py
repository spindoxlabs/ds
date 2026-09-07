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

import json
from urllib.error import URLError

import pytest
from ds_auth import user_credentials
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


async def _serve(client, monkeypatch) -> dict[str, dict]:
    """Both registers, fetched from the route and handed to `ds_auth` verbatim.

    `Accept: application/json` is what the reader sends and what the route
    branches on — with anything else it serves a signed VC-JWT, which is the
    right default for EDC and not what this reader parses.
    """
    documents = {}
    for url, list_id in ((REVOCATION_LIST, "1"), (SUSPENSION_LIST, "2")):
        response = await client.get(
            f"/status/{list_id}", headers={"Accept": "application/json"}
        )
        assert response.status_code == 200, response.text
        documents[url] = response.json()

    class _Fetch:
        def __call__(self, request, timeout=None):
            url = request.full_url
            if url not in documents:
                raise URLError(f"{url} is unreachable")
            body = json.dumps(documents[url]).encode()

            class _Response:
                def read(self):
                    return body

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

            return _Response()

    monkeypatch.setattr(user_credentials, "urlopen", _Fetch())
    return documents


@pytest.mark.rule("P-27")
@pytest.mark.asyncio
async def test_a_live_credential_passes_against_the_published_registers(
    client, db_session, monkeypatch
):
    """The whole defect, in one assertion.

    This failed before the fix with 401 "User VC is not present in credential
    status list" — a message about an unknown credential, on a credential that
    was active, because the reader could not understand the document.
    """
    index = await allocate_suspendable_index(db_session)
    await db_session.commit()
    await _serve(client, monkeypatch)

    user_credentials._verify_credential_status(
        _credential(index), credential_status_url=REVOCATION_LIST
    )


@pytest.mark.rule("P-27")
@pytest.mark.asyncio
async def test_a_revoked_credential_is_refused_as_revoked(
    client, db_session, monkeypatch
):
    index = await allocate_suspendable_index(db_session)
    await revoke_status_list_index(db_session, index)
    await db_session.commit()
    await _serve(client, monkeypatch)

    with pytest.raises(HTTPException) as exc:
        user_credentials._verify_credential_status(
            _credential(index), credential_status_url=REVOCATION_LIST
        )
    assert exc.value.status_code == 401
    assert "revoked" in exc.value.detail


@pytest.mark.rule("P-27")
@pytest.mark.asyncio
async def test_a_suspended_credential_is_refused_as_suspended(
    client, db_session, monkeypatch
):
    """`P-27` gave every credential two registers so a verifier could tell
    *superseded* from *withdrawn*. Until this fix ours could see neither, and
    the bespoke lookup map had no way to express the difference at all."""
    index = await allocate_suspendable_index(db_session)
    await suspend_status_list_index(db_session, index)
    await db_session.commit()
    await _serve(client, monkeypatch)

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
    client, db_session, monkeypatch
):
    """The index is what makes a register per-credential, and it is allocated
    from a counter shared by both. A reader with the bit arithmetic wrong, or an
    allocator handing out the same index twice, both show up here."""
    suspended = await allocate_suspendable_index(db_session)
    bystander = await allocate_suspendable_index(db_session)
    assert suspended != bystander
    await suspend_status_list_index(db_session, suspended)
    await db_session.commit()
    await _serve(client, monkeypatch)

    user_credentials._verify_credential_status(
        _credential(bystander), credential_status_url=REVOCATION_LIST
    )


@pytest.mark.asyncio
async def test_the_registers_publish_the_purposes_the_credential_names(
    client, db_session, monkeypatch
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
    documents = await _serve(client, monkeypatch)

    assert (
        documents[REVOCATION_LIST]["credentialSubject"]["statusPurpose"] == "revocation"
    )
    assert (
        documents[SUSPENSION_LIST]["credentialSubject"]["statusPurpose"] == "suspension"
    )
