"""An offer must not change meaning under consent already recorded against it.

The failure this prevents is silent by nature: an operator edits the words, the
sync succeeds, and every stored consent for that id now attests to text nobody
agreed to. Nothing in the platform noticed before — including when offers lived
in a single file, which is why this is not a cost of distributing them.
"""
from __future__ import annotations

import pytest

from connector.services.offer_drift import drift_failure
from ds.governance.sharing import (
    CONSENT_BASIS,
    OfferRecipients,
    ProcessorCategory,
    SharingOffer,
)


def _offer(version: str = "1.0") -> SharingOffer:
    return SharingOffer(
        id="household-energy-flexibility",
        purpose="FlexibilityResearch",
        legal_basis=CONSENT_BASIS,
        recipients=OfferRecipients(
            controller="example-org",
            processors=ProcessorCategory(category="appointed-service-providers"),
        ),
        consent_text_version=version,
    )


def test_no_recorded_consent_is_never_drift():
    """A brand-new offer has nothing to contradict."""
    assert drift_failure(_offer(), "hash-a", None) is None
    assert drift_failure(_offer(), "hash-a", set()) is None


def test_unchanged_text_passes():
    recorded = {("1.0", "hash-a")}
    assert drift_failure(_offer(), "hash-a", recorded) is None


def test_changed_text_at_the_same_version_is_refused():
    """Same version, different words — an edit pretending nothing happened."""
    recorded = {("1.0", "hash-a")}
    failure = drift_failure(_offer("1.0"), "hash-b", recorded)
    assert failure is not None
    assert "consent_text_version" in failure


def test_changed_text_with_a_version_bump_passes():
    """A deliberate revision. Rows under the old version keep their meaning."""
    recorded = {("1.0", "hash-a")}
    assert drift_failure(_offer("2.0"), "hash-b", recorded) is None


def test_older_versions_coexisting_do_not_trip_the_check():
    """People re-consent at their own pace, so several versions are normal."""
    recorded = {("1.0", "hash-a"), ("2.0", "hash-b")}
    assert drift_failure(_offer("2.0"), "hash-b", recorded) is None


def test_a_revision_that_reuses_an_old_version_number_is_refused():
    recorded = {("1.0", "hash-a"), ("2.0", "hash-b")}
    failure = drift_failure(_offer("1.0"), "hash-c", recorded)
    assert failure is not None


def test_the_message_says_how_many_rows_disagree():
    recorded = {("1.0", "hash-a"), ("1.0", "hash-b")}
    failure = drift_failure(_offer("1.0"), "hash-c", recorded)
    assert "2 stored consent hash(es)" in failure


# ── The sync consequence ─────────────────────────────────────────────────────

def test_a_drifted_offer_blocks_the_datasets_that_declare_it():
    """Refusing the offer alone would not help: the dataset is what gets
    published, and republishing it leaves stored consent attesting to text
    nobody agreed to."""
    from connector.services.governance import ConnectorGovernanceMapper
    from connector.services.provider_service import _reject_unpublishable
    from connector.schemas.edc import SyncResult
    from ds.governance.models import (
        DataspacePolicy,
        DataspaceSpec,
        GovernanceRuleV2,
        load_odrl_profile,
    )
    from ds.governance.sharing import SharingOfferCatalogue

    offer = _offer()
    rule = GovernanceRuleV2(
        access_level="open",
        classification="green",
        dataspace=DataspaceSpec(expose=True, sharing_offers=[offer.id]),
        policy=DataspacePolicy(purpose=["FlexibilityResearch"]),
    )
    mapper = ConnectorGovernanceMapper(
        "provider", "https://provider.test", profile=load_odrl_profile()
    )
    result = SyncResult()

    rejected = _reject_unpublishable(
        {"datasets.silver.meters": rule},
        mapper,
        SharingOfferCatalogue(offers=[offer]),
        result,
        drifted_offer_ids={offer.id},
    )

    assert rejected == {"datasets.silver.meters"}
    assert "wording changed" in result.errors[0]["error"]


def test_an_unaffected_dataset_still_publishes_when_another_offer_drifted():
    """Drift is per offer — one bad edit must not empty the catalogue."""
    from connector.services.governance import ConnectorGovernanceMapper
    from connector.services.provider_service import _reject_unpublishable
    from connector.schemas.edc import SyncResult
    from ds.governance.models import (
        DataspacePolicy,
        DataspaceSpec,
        GovernanceRuleV2,
        load_odrl_profile,
    )
    from ds.governance.sharing import SharingOfferCatalogue

    offer = _offer()
    rule = GovernanceRuleV2(
        access_level="open",
        classification="green",
        dataspace=DataspaceSpec(expose=True, sharing_offers=[offer.id]),
        policy=DataspacePolicy(purpose=["FlexibilityResearch"]),
    )
    mapper = ConnectorGovernanceMapper(
        "provider", "https://provider.test", profile=load_odrl_profile()
    )
    result = SyncResult()

    rejected = _reject_unpublishable(
        {"datasets.silver.meters": rule},
        mapper,
        SharingOfferCatalogue(offers=[offer]),
        result,
        drifted_offer_ids={"some-other-offer"},
    )

    assert rejected == set()
    assert result.errors == []
