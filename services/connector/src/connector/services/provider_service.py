"""Provider-side service: sync governance.yaml to EDC."""
from __future__ import annotations

import logging

import httpx

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ds.governance.models import GovernanceRuleV2
from ds.governance.purposes import purpose_failure
from ds.governance.sharing import (
    DuplicateOfferError,
    SharingOfferCatalogue,
    load_sharing_offers,
)

from ..clients.edc_management import EdcManagementClient
from ..schemas.edc import SyncResult
from .consent_vocabulary import offer_user_visible_hash
from .governance import ConnectorGovernanceMapper, load_exposed_datasets
from .offer_drift import offers_with_drift
from .prov_bridge import ProvBridge

log = logging.getLogger(__name__)


def _offer_failure(rule: GovernanceRuleV2, catalogue: SharingOfferCatalogue) -> str | None:
    """Why this dataset's declared sharing offers are unusable, or ``None``.

    An id that does not resolve means the dataset is **not shared**: "no sharing
    offer" and "not shared" are the same statement. Publishing it while skipping
    only the *reference* would drop its consent gate — the data plane still fails
    closed, but the catalogue would advertise something that can never return a
    row, and a consumer would negotiate for data no grant can ever unlock.

    Declaring none is fine. A dataset that is not consent-gated has nothing to
    offer, and saying so is not an error.
    """
    unresolved = [
        offer_id
        for offer_id in rule.dataspace.sharing_offers
        if catalogue.get(offer_id) is None
    ]
    if not unresolved:
        return None
    listed = ", ".join(repr(entry) for entry in unresolved)
    known = ", ".join(sorted(o.id for o in catalogue.offers)) or "(none are declared)"
    return (
        f"declares sharing offer {listed}, which does not resolve — a dataset "
        f"whose consent gate cannot open is not shared. Known offers: {known}"
    )


def _sibling_offers(
    governance_yaml_path: str, overlay_name: str | None
) -> SharingOfferCatalogue:
    """The offers declared beside the governance file being synced.

    A missing file yields an empty catalogue, which is valid: a deployment with
    no offers simply has nothing to ask. Datasets that declare an offer id will
    then fail to resolve it, which is the right outcome — they named something
    that is not there.
    """
    path = Path(governance_yaml_path).parent / "sharing-offers.yaml"
    return load_sharing_offers(path if path.exists() else None, overlay_name=overlay_name)


async def _drifted_offers(
    session: AsyncSession | None, catalogue: SharingOfferCatalogue
) -> dict[str, str]:
    """Offers whose user-visible text changed under recorded consent.

    Without a session the check cannot run — there is nothing to compare against
    — so it is skipped rather than assumed clean. That happens only where sync is
    driven without a database (tests, and a CLI dry run); every real ingest path
    passes one.
    """
    if session is None:
        return {}
    return await offers_with_drift(session, catalogue, offer_user_visible_hash)


def _reject_unpublishable(
    datasets: dict[str, GovernanceRuleV2],
    mapper: ConnectorGovernanceMapper,
    catalogue: SharingOfferCatalogue,
    result: SyncResult,
    drifted_offer_ids: set[str] | None = None,
) -> set[str]:
    """Datasets that must not be published, with every reason reported at once.

    Two rules, one gate:

    - **Purpose** — an empty or unresolvable ``policy.purpose[]`` would be
      published with *no purpose constraint at all* (`_purpose_iris` drops what it
      cannot resolve; `_build_permission` emits the constraint only for a
      non-empty list). Nothing would limit what a consumer may use it for, and
      the sync used to report success.
    - **Sharing offers** — an id that does not resolve means the dataset is not
      shared.

    Both say the same thing: a dataset missing a fact the platform enforces on is
    not published, rather than published without the enforcement.

    **Every failure is collected before anything is published**, mirroring
    `ProductionGuard`, which logs all violations and only then refuses. Ingest is
    where a producer finds out, and they need the whole list in one pass — failing
    on the first turns one revision into several round trips. A dataset with both
    problems reports both.

    A rejected dataset is *skipped*, not deleted from EDC. If it was published
    before while valid, that version stays live rather than being torn down over a
    bad edit: the previously published constraint is the safer of the two states
    to leave standing.
    """
    drifted = drifted_offer_ids or set()
    rejected: dict[str, list[str]] = {}
    for key, rule in datasets.items():
        stale = sorted(set(rule.dataspace.sharing_offers) & drifted)
        reasons = [
            reason
            for reason in (
                purpose_failure(rule, mapper.profile),
                _offer_failure(rule, catalogue),
                (
                    "declares sharing offer "
                    + ", ".join(repr(o) for o in stale)
                    + ", whose wording changed under consent already recorded "
                    "against it"
                    if stale
                    else None
                ),
            )
            if reason
        ]
        if reasons:
            rejected[key] = reasons

    for key, reasons in rejected.items():
        for reason in reasons:
            log.error("Refusing to publish %s — it %s", key, reason)
            result.errors.append({"dataset": key, "error": f"Not published — it {reason}"})

    return set(rejected)


async def sync_governance(
    governance_yaml_path: str,
    edc: EdcManagementClient,
    mapper: ConnectorGovernanceMapper,
    prov: ProvBridge,
    overlay_name: str | None = None,
    session: AsyncSession | None = None,
) -> SyncResult:
    result = SyncResult()
    try:
        datasets = load_exposed_datasets(governance_yaml_path, overlay_name=overlay_name)
    except Exception as exc:
        result.errors.append({"error": f"Failed to load governance.yaml: {exc}"})
        return result

    # Offers are read from beside the file being synced, not from the connector's
    # configured path: `POST /provider/sync` may be pointed at another governance
    # file, and validating it against a different deployment's offers would either
    # pass a dangling reference or reject a sound one.
    #
    # A duplicate id across contributing files raises here. It is fatal to the
    # whole sync rather than to one dataset: until it is resolved, nobody can say
    # which offer any dataset referencing that id actually means.
    try:
        catalogue = _sibling_offers(governance_yaml_path, overlay_name)
    except DuplicateOfferError as exc:
        result.errors.append({"error": str(exc)})
        return result

    # Offers whose wording drifted under recorded consent are refused, and so is
    # every dataset declaring them — republishing would leave stored consent
    # attesting to text nobody agreed to.
    drifted = await _drifted_offers(session, catalogue)
    for offer_id, failure in drifted.items():
        result.errors.append({"offer": offer_id, "error": f"Not published — it {failure}"})

    rejected = _reject_unpublishable(datasets, mapper, catalogue, result, set(drifted))

    for key, rule in datasets.items():
        if key in rejected:
            continue
        try:
            asset_create = mapper.to_asset_create(key, rule)
            policy_create = mapper.to_policy_create(key, rule)
            contract_create = mapper.to_contract_definition(
                key, rule, policy_id=policy_create.id, asset_id=asset_create.id
            )

            await edc.delete_contract_definition(contract_create.id)
            await edc.delete_policy(policy_create.id)

            try:
                await edc.delete_asset(asset_create.id)
                await edc.create_asset(asset_create)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 409:
                    log.debug("Asset %s already exists (has agreements) — keeping", asset_create.id)
                else:
                    raise

            await edc.create_policy(policy_create)
            await edc.create_contract_definition(contract_create)

            await prov.catalogue_published(
                data_product_id=asset_create.id,
                title=rule.title,
                description=rule.description,
                event_id=f"sync:{asset_create.id}",
            )

            result.synced.append(key)
            log.info("Synced dataset %s → asset %s", key, asset_create.id)
        except Exception as exc:
            log.exception("Failed to sync dataset %s", key)
            result.errors.append({"dataset": key, "error": str(exc)})

    skipped_count = len(datasets) - len(result.synced) - len(result.errors)
    if skipped_count > 0:
        result.skipped.append(f"{skipped_count} datasets skipped (not exposed or secret)")

    return result
