"""Sync refuses to publish a dataset whose purposes are unusable.

Before this gate, `_purpose_iris` dropped an unresolvable entry and
`_build_permission` emitted no constraint for an empty list, so a dataset with a
typo'd or missing purpose was published **with no purpose limitation** and the
sync reported success. These tests are the record that it now fails loudly, and
that it fails for every offending dataset in one pass rather than the first.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ds.governance.models import (
    DataspaceSpec,
    GovernanceRuleV2,
    load_odrl_profile,
)

from connector.services.governance import ConnectorGovernanceMapper
from connector.services.provider_service import sync_governance


def _mapper() -> ConnectorGovernanceMapper:
    # The bundled energy profile, matching what `POST /provider/sync` builds.
    # `GovernanceMapper` defaults to an *empty* `OdrlProfile` when none is passed
    # — deliberate platform neutrality, but it means a mapper built without one
    # resolves no purpose at all and this gate would reject everything.
    return ConnectorGovernanceMapper(
        "provider",
        "https://rec.dataspaces.localhost",
        profile=load_odrl_profile(),
    )


def _rule(
    purposes: list[str] | None,
    sharing_offers: list[str] | None = None,
    expose: bool | None = None,
) -> GovernanceRuleV2:
    return GovernanceRuleV2(
        access_level="open",
        classification="green",
        expose=expose,
        dataspace=DataspaceSpec(
            expose=True,
            sharing_offers=sharing_offers or [],
            purpose=purposes or [],
        ),
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


@pytest.mark.rule("C-10", "D-10")
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


@pytest.mark.rule("C-11", "D-7")
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


@pytest.mark.rule("C-9")
@pytest.mark.asyncio
async def test_every_offender_is_reported_in_one_pass(datasets):
    """A producer revising an ingest needs the whole list, not the first failure.

    Failing fast would turn one revision into three round trips, which is the
    opposite of blocking early to allow a fix.
    """
    datasets(
        {
            "datasets.gold.a": _rule(["energy-monitoring"]),
            "datasets.gold.b": _rule([]),
            "datasets.gold.c": _rule(["also-wrong"]),
        }
    )
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
    datasets(
        {
            "datasets.gold.bad": _rule(["nope"]),
            "datasets.gold.good": _rule(["EnergyForecasting"]),
        }
    )
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert result.synced == ["datasets.gold.good"]
    assert len(edc.created_assets) == 1
    assert [e["dataset"] for e in result.errors] == ["datasets.gold.bad"]


@pytest.mark.rule("M-7")
@pytest.mark.asyncio
async def test_absolute_iri_from_another_vocabulary_is_accepted(datasets):
    """A deployment may cite a purpose this profile does not carry."""
    datasets({"datasets.gold.ext": _rule(["https://example.org/purpose/Something"])})
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert result.synced == ["datasets.gold.ext"]
    assert result.errors == []


# ── Sharing offers (T25) ─────────────────────────────────────────────────────
#
# The sync reads offers from beside the governance file it was handed, so these
# resolve against `tests/fixtures/sharing-offers.yaml`.


@pytest.fixture
def fixture_governance() -> str:
    return str(Path(__file__).parent / "fixtures" / "governance.yaml")


@pytest.mark.rule("C-10")
@pytest.mark.asyncio
async def test_unresolvable_offer_id_is_not_published(datasets, fixture_governance):
    """ "No sharing offer" and "not shared" are the same statement.

    Publishing while skipping only the reference would advertise a consent gate
    that can never open — a consumer negotiates for data no grant can unlock.
    """
    datasets({"datasets.gold.dangling": _rule(["GridMonitoring"], ["no-such-offer"])})
    edc = _RecordingEdc()

    result = await sync_governance(fixture_governance, edc, _mapper(), _NullProv())

    assert edc.created_assets == []
    assert len(result.errors) == 1
    assert "no-such-offer" in result.errors[0]["error"]


@pytest.mark.rule("C-10")
@pytest.mark.asyncio
async def test_a_resolvable_offer_id_publishes(datasets, fixture_governance):
    datasets({"datasets.gold.ok": _rule(["FlexibilityResearch"], ["test-flexibility"])})
    edc = _RecordingEdc()

    result = await sync_governance(fixture_governance, edc, _mapper(), _NullProv())

    assert result.synced == ["datasets.gold.ok"]
    assert result.errors == []


@pytest.mark.asyncio
async def test_declaring_no_offer_is_not_an_error(datasets, fixture_governance):
    """A dataset that is not consent-gated has nothing to offer."""
    datasets({"datasets.gold.open": _rule(["GridMonitoring"], [])})
    edc = _RecordingEdc()

    result = await sync_governance(fixture_governance, edc, _mapper(), _NullProv())

    assert result.synced == ["datasets.gold.open"]
    assert result.errors == []


@pytest.mark.asyncio
async def test_both_problems_on_one_dataset_are_both_reported(
    datasets, fixture_governance
):
    """One revision, not two round trips."""
    datasets({"datasets.gold.both": _rule(["nope"], ["also-missing"])})
    edc = _RecordingEdc()

    result = await sync_governance(fixture_governance, edc, _mapper(), _NullProv())

    assert edc.created_assets == []
    joined = " ".join(e["error"] for e in result.errors)
    assert "nope" in joined
    assert "also-missing" in joined
    assert len(result.errors) == 2


# ── Exposure ─────────────────────────────────────────────────────────────────
#
# The third rule in the same gate, added with `ADR-0013` phase 3
# (https://github.com/spindoxlabs/ds/issues/20). The first two refuse a dataset
# **missing** a fact the platform enforces on; this one refuses a dataset stating
# two facts that cannot both hold.


@pytest.mark.asyncio
async def test_offered_but_unlisted_is_not_published(datasets):
    """`expose: false` with `dataspace.expose: true` must not reach EDC.

    The two gates are ANDed: a consumer reaches a dataspace asset through the
    catalogue entry describing it, so offering something unlisted cannot be
    honoured. Publishing anyway is what let a consumer negotiate and **conclude a
    contract** for data the plane was never going to serve — a failure that looked
    like an agreement until the transfer.

    The rule is `celine.governance.exposure.exposure_conflict`, called rather than
    copied.
    """
    datasets({"datasets.gold.unlisted": _rule(["GridMonitoring"], expose=False)})
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert edc.created_assets == [], "an unlisted dataset was offered to the dataspace"
    assert len(result.errors) == 1
    assert result.errors[0]["dataset"] == "datasets.gold.unlisted"
    assert "expose: true" in result.errors[0]["error"]
    assert result.synced == []


@pytest.mark.asyncio
async def test_listed_and_offered_still_publishes(datasets):
    datasets({"datasets.gold.ok": _rule(["GridMonitoring"], expose=True)})
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert len(edc.created_assets) == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_unstated_expose_still_publishes(datasets):
    """The unmigrated case, and the reason this was shippable ahead of the files.

    `expose` unstated means *not stated*, and the resolved catalogue gate falls back
    to `dataspace.expose`. Every governance file written against the old grammar —
    which is all of them; the corpus states `expose` nowhere — keeps behaving
    exactly as it did.
    """
    datasets({"datasets.gold.legacy": _rule(["GridMonitoring"], expose=None)})
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert len(edc.created_assets) == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_an_exposure_conflict_is_reported_beside_the_other_reasons(datasets):
    """One dataset, two independent faults, both named in one pass.

    The gate collects every reason before publishing anything; a dataset that is
    both unlisted and purposeless must not report only whichever check ran first.
    """
    datasets({"datasets.gold.both": _rule([], expose=False)})
    edc = _RecordingEdc()

    result = await _sync(edc)

    assert edc.created_assets == []
    messages = " ".join(e["error"] for e in result.errors)
    assert "declares no purpose" in messages
    assert "expose: true" in messages
    assert len(result.errors) == 2
