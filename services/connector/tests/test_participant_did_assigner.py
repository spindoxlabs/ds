"""`CONNECTOR_PARTICIPANT_DID` reaches the ODRL assigner.

`GovernanceMapper` accepts `participant_did` and falls back to
``did:web:{participant_id}.dataspaces.localhost`` when it is not given.
`ConnectorGovernanceMapper` neither accepted nor forwarded it, so the setting
was read by `Settings`, carried through compose and Helm, and then dropped one
constructor short of the only thing that uses it.

The assigner is not cosmetic: it is the identity a consumer resolves and
verifies the offer against. Under any deployment domain other than the dev one,
every published policy named a DID that resolves to nothing.
"""
from __future__ import annotations

import pytest
from ds.governance.models import DataspaceSpec, GovernanceRuleV2
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.services.governance import ConnectorGovernanceMapper

from . import make_headers

DEPLOYED_DID = "did:web:provider.energy.example.test"


def _rule() -> GovernanceRuleV2:
    return GovernanceRuleV2(
        title="Test Dataset",
        access_level="internal",
        classification="green",
        dataspace=DataspaceSpec(expose=True),
    )


def test_the_mapper_forwards_participant_did_to_the_assigner():
    mapper = ConnectorGovernanceMapper(
        "provider",
        "https://provider.energy.example.test",
        participant_did=DEPLOYED_DID,
    )

    policy = mapper.to_policy_create("datasets.gold.test", _rule())

    assert policy.policy["odrl:assigner"] == {"@id": DEPLOYED_DID}


def test_the_dev_fallback_still_applies_when_no_did_is_configured():
    """Unchanged behaviour, pinned: omitting the DID is not the same as a bug."""
    mapper = ConnectorGovernanceMapper("provider", "https://rec.dataspaces.localhost")

    policy = mapper.to_policy_create("datasets.gold.test", _rule())

    assert policy.policy["odrl:assigner"] == {
        "@id": "did:web:rec.dataspaces.localhost"
    }


@pytest.mark.asyncio
async def test_sync_builds_the_mapper_with_the_configured_did(engine, monkeypatch):
    """The route is where the setting was being dropped, so assert on the route.

    A mapper that accepts `participant_did` and a caller that never passes it
    leaves the defect exactly where it was.

    The DID here is deliberately *not* the dev default: with
    ``did:web:rec.dataspaces.localhost`` configured, the fallback produces
    the same string and the assertion proves nothing.
    """
    from connector.config import Settings
    from connector.dependencies import get_db, get_provider_edc, get_settings_dep
    from connector.main import create_app
    from connector.schemas.edc import SyncResult

    seen: list[str] = []

    async def _fake_sync(_yaml_path, _edc, mapper, *_args, **_kwargs):
        seen.append(mapper._mapper.participant_did)
        return SyncResult()

    monkeypatch.setattr(
        "connector.services.provider_service.sync_governance", _fake_sync
    )

    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_provider_edc] = lambda: object()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        role="provider", participant_id="provider", participant_did=DEPLOYED_DID
    )
    app.state.prov = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/provider/sync",
            json={},
            headers=make_headers(scope="connector.provider.write"),
        )

    assert resp.status_code == 200
    assert seen == [DEPLOYED_DID]
