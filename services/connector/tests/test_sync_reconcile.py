"""`POST /provider/sync` withdraws what governance no longer declares.

**The defect.** The sync created and updated; it never removed. A dataset taken
out of `governance.yaml` kept its EDC asset, both its policies and its contract
definition, and went on being offered over DSP — while the next sync reported a
publish count that had gone *up*, because the count is of what published rather
than of what is on offer. Nothing in the output distinguished it from a healthy
run. Measured in a live deployment on 2026-09-18
(`the-dso-connector-holds-the-release-consent`, finding 1 of the governance pass).

**Why these tests can fail.** The stand-in for EDC holds state (`fake_edc.py`).
The previous one recorded only the assets it was asked to create, so "withdrew
nothing" and "withdrew correctly" produced identical output and a test for this
could not have failed. Run `test_a_removed_dataset_is_withdrawn_from_edc` against
the sync as it was and it fails on `edc.assets`, which is the point.
"""

from __future__ import annotations

import pytest
from ds.governance.models import (
    DataspaceAsset,
    DataspaceSpec,
    GovernanceRuleV2,
    load_odrl_profile,
)

from connector.services.governance import ConnectorGovernanceMapper
from connector.services.provider_service import sync_governance

from .fake_edc import FakeEdc, NullProv

PROFILE_PREFIX = load_odrl_profile().prefix


def _mapper() -> ConnectorGovernanceMapper:
    return ConnectorGovernanceMapper(
        "provider",
        "https://rec.dataspaces.localhost",
        profile=load_odrl_profile(),
    )


def _rule(purposes: list[str] | None = None, asset_id: str | None = None):
    return GovernanceRuleV2(
        access_level="open",
        classification="green",
        dataspace=DataspaceSpec(
            expose=True,
            purpose=purposes or ["GridMonitoring"],
            asset=DataspaceAsset(id=asset_id) if asset_id else DataspaceAsset(),
        ),
    )


@pytest.fixture
def datasets(monkeypatch):
    def _install(mapping: dict[str, GovernanceRuleV2]):
        monkeypatch.setattr(
            "connector.services.provider_service.load_exposed_datasets",
            lambda *_args, **_kwargs: mapping,
        )

    return _install


async def _sync(edc, prov: NullProv | None = None):
    return await sync_governance("unused.yaml", edc, _mapper(), prov or NullProv())


@pytest.mark.asyncio
async def test_a_removed_dataset_is_withdrawn_from_edc(datasets):
    """The defect itself: governance drops a dataset, EDC must stop offering it."""
    edc = FakeEdc()
    edc.seed_published(
        "datasets.gold.gone",
        "datasets.gold.gone",
        prefix=PROFILE_PREFIX,
        policy_ids=("datasets-gold-gone-access-policy", "datasets-gold-gone-policy"),
        contract_id="datasets-gold-gone-contract",
    )
    datasets({"datasets.gold.kept": _rule()})

    result = await _sync(edc)

    assert result.synced == ["datasets.gold.kept"]
    assert result.withdrawn == ["datasets.gold.gone"]
    assert "datasets.gold.gone" not in edc.assets
    assert "datasets-gold-gone-contract" not in edc.contract_definitions
    assert edc.policies == {
        k: v for k, v in edc.policies.items() if k.startswith("datasets-gold-kept")
    }
    assert not result.errors


@pytest.mark.asyncio
async def test_the_withdrawal_order_is_the_only_one_edc_accepts(datasets):
    """Contract definition, then policies, then the asset.

    Not a style preference: the fake refuses to delete a policy a definition
    still references, exactly as EDC does. Reversing the order fails this test
    with a 409 in `errors`, which is what a real EDC would have answered.
    """
    edc = FakeEdc()
    edc.seed_published(
        "datasets.gold.gone",
        "datasets.gold.gone",
        prefix=PROFILE_PREFIX,
        policy_ids=("datasets-gold-gone-access-policy", "datasets-gold-gone-policy"),
        contract_id="datasets-gold-gone-contract",
    )
    datasets({})

    result = await _sync(edc)

    assert not result.errors
    order = [
        name
        for name, target in edc.calls
        if target.startswith("datasets.gold.gone")
        or target.startswith("datasets-gold-gone")
    ]
    assert order.index("delete_contract_definition") < order.index("delete_policy")
    assert order.index("delete_policy") < order.index("delete_asset")


@pytest.mark.asyncio
async def test_an_asset_ds_did_not_publish_is_left_alone(datasets):
    """*Governance does not declare it* is not evidence that ds created it.

    An EDC runtime may hold objects ds never wrote. The reconcile identifies its
    own work by the `datasetKey` property the mapper writes, and nothing else.
    """
    edc = FakeEdc()
    edc.seed_foreign_asset("somebody-elses-asset")
    datasets({"datasets.gold.kept": _rule()})

    result = await _sync(edc)

    assert "somebody-elses-asset" in edc.assets
    assert result.withdrawn == []


@pytest.mark.asyncio
async def test_a_rejected_dataset_keeps_what_it_had(datasets):
    """A bad edit must not tear down a previously valid publication.

    `_reject_unpublishable` deliberately leaves the published version standing
    rather than deleting it over an unusable purpose. A reconcile that removed it
    anyway would undo that decision by another route — the dataset is still
    *declared*, it is merely not publishable today.
    """
    edc = FakeEdc()
    edc.seed_published(
        "datasets.gold.typo", "datasets.gold.typo", prefix=PROFILE_PREFIX
    )
    datasets({"datasets.gold.typo": _rule(["not-a-purpose"])})

    result = await _sync(edc)

    assert result.withdrawn == []
    assert "datasets.gold.typo" in edc.assets
    assert any(e.get("dataset") == "datasets.gold.typo" for e in result.errors)


@pytest.mark.asyncio
async def test_an_asset_id_that_moved_takes_the_old_asset_with_it(datasets):
    """A still-declared dataset republished under a new id leaves no orphan.

    This is also the upgrade path off the old derived id: the first sync after
    the change republishes under the dataset key and removes what the derived
    form left behind.
    """
    edc = FakeEdc()
    edc.seed_published(
        "https://old/datasets/gold/moved",
        "datasets.gold.moved",
        prefix=PROFILE_PREFIX,
    )
    datasets({"datasets.gold.moved": _rule(asset_id="datasets.gold.moved")})

    result = await _sync(edc)

    assert result.synced == ["datasets.gold.moved"]
    assert result.withdrawn == ["https://old/datasets/gold/moved"]
    assert "https://old/datasets/gold/moved" not in edc.assets
    assert "datasets.gold.moved" in edc.assets


# ── The withdrawal is recorded, not only performed ───────────────────────────
#
# `ADR-0017` shipped the reconcile and recorded, in its own consequences, that a
# withdrawal emitted **no provenance event** — so the graph's last word on a
# dataset taken off offer was that it had been published. That is the gap these
# three close.


@pytest.mark.rule("L-1", "L-15")
@pytest.mark.asyncio
async def test_a_withdrawn_dataset_is_recorded_in_provenance(datasets):
    """The event names the **asset id**, which is what the publication named.

    Not the governance key: `CataloguePublished` carries `asset_create.id`, and
    the two events have to invalidate and generate one entity node.
    """
    edc = FakeEdc()
    edc.seed_published(
        "datasets.gold.gone",
        "datasets.gold.gone",
        prefix=PROFILE_PREFIX,
        policy_ids=("datasets-gold-gone-access-policy", "datasets-gold-gone-policy"),
        contract_id="datasets-gold-gone-contract",
    )
    datasets({"datasets.gold.kept": _rule()})
    prov = NullProv()

    result = await _sync(edc, prov)

    assert result.withdrawn == ["datasets.gold.gone"]
    [event] = prov.emitted("CatalogueWithdrawn")
    assert event["data_product_id"] == "datasets.gold.gone"
    assert event["reason"] == "undeclared"


@pytest.mark.asyncio
async def test_a_republished_dataset_is_not_recorded_as_withdrawn(datasets):
    """A new asset id is a move, not a withdrawal — the dataset is still on offer.

    The reconcile deletes the old asset either way (that is what
    `test_an_asset_id_that_moved_takes_the_old_asset_with_it` pins), but saying
    so in provenance would put "no longer available" in the graph about a
    dataset that is available, under a new id, from the same run.
    """
    edc = FakeEdc()
    edc.seed_published(
        "https://old/datasets/gold/moved",
        "datasets.gold.moved",
        prefix=PROFILE_PREFIX,
    )
    datasets({"datasets.gold.moved": _rule(asset_id="datasets.gold.moved")})
    prov = NullProv()

    result = await _sync(edc, prov)

    assert result.withdrawn == ["https://old/datasets/gold/moved"]
    assert prov.emitted("CatalogueWithdrawn") == []
    assert len(prov.emitted("CataloguePublished")) == 1


@pytest.mark.asyncio
async def test_a_withdrawal_edc_refused_is_not_recorded(datasets):
    """The graph must not claim a withdrawal that did not happen.

    EDC answers 409 for an asset with agreements. The event is emitted after the
    delete is accepted, so a refusal leaves an error in the result and nothing
    in provenance — the dataset really is still on offer.
    """
    edc = FakeEdc()
    edc.seed_published(
        "datasets.gold.stuck", "datasets.gold.stuck", prefix=PROFILE_PREFIX
    )
    edc.pinned_assets.add("datasets.gold.stuck")
    datasets({})
    prov = NullProv()

    result = await _sync(edc, prov)

    assert result.errors
    assert prov.emitted("CatalogueWithdrawn") == []


@pytest.mark.asyncio
async def test_an_asset_edc_refuses_to_delete_is_reported(datasets):
    """A withdrawn dataset still under agreement is exactly what must be said aloud.

    EDC answers 409 for an asset with contract agreements. Swallowing it would
    leave the dataset on offer *and* the run reporting success — the original
    defect, reproduced one level down.
    """
    edc = FakeEdc()
    edc.seed_published(
        "datasets.gold.gone", "datasets.gold.gone", prefix=PROFILE_PREFIX
    )
    edc.pinned_assets.add("datasets.gold.gone")
    datasets({})

    result = await _sync(edc)

    assert result.withdrawn == []
    assert len(result.errors) == 1
    message = result.errors[0]["error"]
    assert "Not withdrawn" in message
    assert "datasets.gold.gone" in message
    assert "409" in message


@pytest.mark.asyncio
async def test_a_reconcile_that_cannot_read_edc_says_so(datasets):
    """Unable to check is not the same as nothing to do (`ENV-09`).

    A silent return would report a clean sync while EDC's state is unknown.
    """

    class _Blind(FakeEdc):
        async def list_assets(self):
            raise RuntimeError("management API unreachable")

    edc = _Blind()
    datasets({"datasets.gold.kept": _rule()})

    result = await _sync(edc)

    assert result.synced == ["datasets.gold.kept"]
    assert any("Could not reconcile" in e["error"] for e in result.errors)


@pytest.mark.asyncio
async def test_an_asset_under_agreement_is_updated_in_place(datasets):
    """EDC refuses to delete it, so the sync updates it rather than keeping it.

    **This one was found live, not by reading.** On a dev stack, three of four
    assets carried contract agreements; EDC answered 409 to `delete_asset`, the
    sync logged "keeping" and moved on — and none of the three ever received the
    `datasetKey` property the same run had just written for the fourth. Two
    consequences, and the second is worse than the first:

    * a governance edit to an asset under agreement published **nothing**,
      silently, for as long as the agreement stood;
    * an unlabelled asset is invisible to the reconcile, so the dataset that most
      needs withdrawing — one somebody is actually using — could never be
      withdrawn.

    `PUT …/assets` is what EDC provides for this, and it is body-addressed.
    """
    edc = FakeEdc()
    edc.seed_published(
        "datasets.gold.pinned", "stale-key-from-an-older-version", prefix=PROFILE_PREFIX
    )
    edc.pinned_assets.add("datasets.gold.pinned")
    datasets({"datasets.gold.pinned": _rule(asset_id="datasets.gold.pinned")})

    result = await _sync(edc)

    assert result.synced == ["datasets.gold.pinned"]
    assert not result.errors
    assert ("update_asset", "datasets.gold.pinned") in edc.calls
    # The point of updating: the asset now carries this run's properties, so the
    # next reconcile can see it.
    assert (
        edc.assets["datasets.gold.pinned"]["properties"][f"{PROFILE_PREFIX}:datasetKey"]
        == "datasets.gold.pinned"
    )
