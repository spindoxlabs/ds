"""A holder does not present its own credential once the issuer retired it (D27).

The holder's copy stays ``active`` after the issuer suspends or revokes it — an
organisation reissue (`P-30`) suspends the predecessor the holder still keeps —
and EDC 0.18.0 rejects the whole presentation when one credential in it has a
set status bit. So the holder reads the issuer's registers and leaves such a
copy out; a register it cannot read leaves the copy out too (fail closed).
"""

from __future__ import annotations

import pytest
from test_dcp_auth import HOLDER, MEMBERSHIP_SCOPE
from test_presentation_scope import (
    _create_participant,
    _hold_credential,
    _presented,
    _query_as_verifier,
)

from identity_registry.config import Settings
from identity_registry.db.models import Credential
from identity_registry.dependencies import get_settings_dep
from identity_registry.services.presentation import (
    build_presentation_response,
    holder_status_reader,
)

ORG_SCOPE = "org.eclipse.dspace.dcp.vc.type:OrganizationCredential:read"
BOTH = {"MembershipCredential", "OrganizationCredential"}
OTHER = "did:web:other.dataspaces.localhost"


def _vp_credentials(response) -> list[str]:
    import base64
    import json

    vp_jwt = response["dcp:presentation"]["@value"][0]
    payload = json.loads(
        base64.urlsafe_b64decode(vp_jwt.split(".")[1] + "===").decode()
    )
    return payload["vp"]["verifiableCredential"]


def _reader(answers: dict[str, bool | None | Exception]):
    """A fake register: credential type → bit set, no register, or unreadable."""
    seen: list[str] = []

    async def read(credential: Credential) -> bool | None:
        seen.append(credential.credential_type)
        answer = answers.get(credential.credential_type)
        if isinstance(answer, Exception):
            raise answer
        return answer

    read.seen = seen  # type: ignore[attr-defined]
    return read


@pytest.fixture
async def holder_with_org_credential(db_session):
    await _create_participant(db_session, HOLDER)
    await _hold_credential(db_session, HOLDER, "MembershipCredential")
    await _hold_credential(db_session, HOLDER, "OrganizationCredential")


async def _build(db_session, read):
    return _vp_credentials(
        await build_presentation_response(
            db_session, HOLDER, granted_types=BOTH, status_reader=read
        )
    )


# ── The builder ──────────────────────────────────────────────────────────────


@pytest.mark.rule("P-31")
@pytest.mark.asyncio
async def test_a_retired_credential_is_left_out(db_session, holder_with_org_credential):
    """The suspended predecessor a reissue leaves with the holder (D25, D27)."""
    presented = await _build(
        db_session,
        _reader({"OrganizationCredential": True, "MembershipCredential": False}),
    )
    assert presented == ["jws-for-MembershipCredential"]


@pytest.mark.rule("P-31")
@pytest.mark.asyncio
async def test_an_unreadable_register_leaves_the_credential_out(
    db_session, holder_with_org_credential, caplog
):
    """Fail closed (D27): a smaller presentation, never a possibly retired one."""
    presented = await _build(
        db_session,
        _reader(
            {
                "OrganizationCredential": RuntimeError("register unreachable"),
                "MembershipCredential": False,
            }
        ),
    )
    assert presented == ["jws-for-MembershipCredential"]
    assert "could not be read" in caplog.text


@pytest.mark.asyncio
async def test_a_credential_naming_no_register_is_presented(
    db_session, holder_with_org_credential
):
    """Nothing published says it was retired; the row's own status still applies."""
    presented = await _build(db_session, _reader({}))
    assert sorted(presented) == [
        "jws-for-MembershipCredential",
        "jws-for-OrganizationCredential",
    ]


@pytest.mark.asyncio
async def test_without_a_reader_nothing_is_read(db_session, holder_with_org_credential):
    """A person's credentials are this registry's own rows: no register read."""
    presented = _vp_credentials(
        await build_presentation_response(db_session, HOLDER, granted_types=BOTH)
    )
    assert len(presented) == 2


# ── Both registers ───────────────────────────────────────────────────────────


@pytest.mark.rule("P-31")
@pytest.mark.parametrize(
    ("revocation", "suspension", "expected"),
    [
        (False, True, True),
        (True, False, True),
        (False, False, False),
        (None, False, False),
        (None, None, None),
    ],
)
@pytest.mark.asyncio
async def test_the_holder_reads_revocation_and_suspension(
    monkeypatch, revocation, suspension, expected
):
    from ds_auth import user_credentials

    bits = {"revocation": revocation, "suspension": suspension}
    purposes: list[str] = []

    def fake(vc, purpose, **kw):
        purposes.append(purpose)
        # Uncached (D38): never staler than the verifier presented to.
        assert kw["ttl_seconds"] == 0
        return bits[purpose]

    monkeypatch.setattr(user_credentials, "status_bit_set", fake)
    settings = Settings(
        role="participant",
        participant_did=HOLDER,
        trust_anchor_url="https://trust-anchor.internal",
        trust_anchor_domain="trust-anchor.example.org",
    )
    read = holder_status_reader(settings)
    credential = Credential(id="c-1", credential_type="OrganizationCredential")
    assert await read(credential) is expected
    assert purposes == ["revocation", "suspension"]


# ── The route: the participant's own credentials only ───────────────────────


@pytest.fixture
async def participant_holder(client, db_session, holder_with_org_credential):
    from conftest import TEST_DATABASE_URL
    from test_presentation_scope import VERIFIER

    await _create_participant(db_session, VERIFIER)
    settings = Settings(
        database_url=TEST_DATABASE_URL,
        oidc_issuer_url=None,
        role="participant",
        participant_did=HOLDER,
    )
    client._transport.app.dependency_overrides[get_settings_dep] = lambda: settings
    return settings


@pytest.mark.rule("P-31")
@pytest.mark.asyncio
async def test_the_participant_does_not_present_its_retired_credential(
    client, db_session, resolver, participant_holder, monkeypatch
):
    read = _reader({"OrganizationCredential": True})
    monkeypatch.setattr(
        "identity_registry.api.v1.credentials.holder_status_reader", lambda s: read
    )
    r = await _query_as_verifier(
        client,
        db_session,
        resolver,
        scope=ORG_SCOPE,
        granted=f"{MEMBERSHIP_SCOPE} {ORG_SCOPE}",
    )
    assert r.status_code == 200
    assert _presented(r) == []
    assert read.seen == ["OrganizationCredential"]


@pytest.mark.asyncio
async def test_another_holder_s_query_reads_no_register(
    client, db_session, resolver, holder_with_org_credential, monkeypatch
):
    """On an instance that is not this participant's, the filter does not run."""
    from conftest import TEST_DATABASE_URL
    from test_presentation_scope import VERIFIER

    await _create_participant(db_session, VERIFIER)
    client._transport.app.dependency_overrides[get_settings_dep] = lambda: Settings(
        database_url=TEST_DATABASE_URL,
        oidc_issuer_url=None,
        role="participant",
        participant_did=OTHER,
    )
    called: list[Settings] = []
    monkeypatch.setattr(
        "identity_registry.api.v1.credentials.holder_status_reader",
        lambda s: called.append(s) or _reader({}),
    )
    r = await _query_as_verifier(
        client, db_session, resolver, scope=ORG_SCOPE, granted=ORG_SCOPE
    )
    assert r.status_code == 200
    assert _presented(r) == ["jws-for-OrganizationCredential"]
    assert called == []
