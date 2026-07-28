"""Sync refuses to publish a dataset whose purposes are unusable.

Before this gate, `_purpose_iris` dropped an unresolvable entry and
`_build_permission` emitted no constraint for an empty list, so a dataset with a
typo'd or missing purpose was published **with no purpose limitation** and the
sync reported success. These tests are the record that it now fails loudly, and
that it fails for every offending dataset in one pass rather than the first.
"""
from __future__ import annotations

import pytest

from connector.services.governance import ConnectorGovernanceMapper
from connector.services.provider_service import sync_governance
from ds.governance.models import (
    DataspacePolicy,
    DataspaceSpec,
    GovernanceRuleV2,
    load_odrl_profile,
)


def _mapper() -> ConnectorGovernanceMapper:
    # The bundled energy profile, matching what `POST /provider/sync` builds.
    # `GovernanceMapper` defaults to an *empty* `OdrlProfile` when none is passed
    # — deliberate platform neutrality, but it means a mapper built without one
    # resolves no purpose at all and this gate would reject everything.
    return ConnectorGovernanceMapper(
        "provider",
        "https://provider.dataspaces.localhost",
        profile=load_odrl_profile(),
    )


def _rule(purposes: list[str] | None) -> GovernanceRuleV2:
    return GovernanceRuleV2(
        access_level="open",
        classification="green",
        dataspace=DataspaceSpec(expose=True),
        policy=DataspacePolicy(purpose=purposes or []),
    )


class _RecordingEdc:
    """Records what reached EDC. Anything published is a real publication."""

    def __init__(self) -> None:
        self.created_assets: list[str] = []

    async def delete_contract_definition(self, _id): ...
    async def delete_policy(self, _id): ...
    async def delete_asset(self, _id): ...
    async def create_policy(self, _payload): ...
    async def create_contract_definition(self, _payload): ...

    async def create_asset(self, payload):
        self.created_assets.append(payload.id)


class _NullProv:
    async def catalogue_published(self, **_kwargs): ...


@pytest.fixture
def datasets(monkeypatch):
    """Patch the loader so these tests exercise the gate, not YAML parsing."""

    def _install(mapping: dict[str, GovernanceRuleV2]):
        monkeypatch.setattr(
            "connector.services.provider_service.load_exposed_datasets",
            lambda *_args, **_kwargs: mapping,
        )

    return _install


async def _sync(edc) -> object:
    return await sync_governance("unused.yaml", edc, _mapper(), _NullProv())


@pytest.mark.asyncio
async def test_unresolvable_purpose_is_not_published(datasets):
    datasets({"datasets.gold.typo": _rule(["energy-monitoring"])})
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert edc.created_assets == [], "a dataset with no usable purpose reached EDC"
    assert len(result.errors) == 1
    assert result.errors[0]["dataset"] == "datasets.gold.typo"
    assert "energy-monitoring" in result.errors[0]["error"]
    assert result.synced == []


@pytest.mark.asyncio
async def test_empty_purpose_is_not_published(datasets):
    """The silent case: no entries to iterate, so every earlier check passed."""
    datasets({"datasets.gold.bare": _rule([])})
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert edc.created_assets == []
    assert len(result.errors) == 1
    assert "declares no purpose" in result.errors[0]["error"]


@pytest.mark.asyncio
async def test_a_valid_dataset_still_publishes(datasets):
    datasets({"datasets.gold.ok": _rule(["GridMonitoring"])})
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert len(edc.created_assets) == 1
    assert result.synced == ["datasets.gold.ok"]
    assert result.errors == []


@pytest.mark.asyncio
async def test_every_offender_is_reported_in_one_pass(datasets):
    """A producer revising an ingest needs the whole list, not the first failure.

    Failing fast would turn one revision into three round trips, which is the
    opposite of blocking early to allow a fix.
    """
    datasets({
        "datasets.gold.a": _rule(["energy-monitoring"]),
        "datasets.gold.b": _rule([]),
        "datasets.gold.c": _rule(["also-wrong"]),
    })
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert edc.created_assets == []
    assert {e["dataset"] for e in result.errors} == {
        "datasets.gold.a",
        "datasets.gold.b",
        "datasets.gold.c",
    }


@pytest.mark.asyncio
async def test_one_bad_dataset_does_not_block_the_good_ones(datasets):
    """Rejection is per dataset — a bad edit must not empty the catalogue."""
    datasets({
        "datasets.gold.bad": _rule(["nope"]),
        "datasets.gold.good": _rule(["EnergyForecasting"]),
    })
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert result.synced == ["datasets.gold.good"]
    assert len(edc.created_assets) == 1
    assert [e["dataset"] for e in result.errors] == ["datasets.gold.bad"]


@pytest.mark.asyncio
async def test_absolute_iri_from_another_vocabulary_is_accepted(datasets):
    """A deployment may cite a purpose this profile does not carry."""
    datasets({"datasets.gold.ext": _rule(["https://example.org/purpose/Something"])})
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert result.synced == ["datasets.gold.ext"]
    assert result.errors == []
