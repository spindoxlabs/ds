"""Provider-side service: sync governance.yaml to EDC."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

# The exposure rule is upstream's and is **called, not reimplemented** — the
# catalogue gate and the dataspace gate are ANDed, so `expose: false` beside
# `dataspace.expose: true` cannot be honoured by a consumer that reaches the asset
# through the catalogue entry describing it. See `ADR-0013` and
# `libs/governance`'s `check_exposure_conflict`, which reports the same rule
# offline so a producer hears it from `validate` rather than from a failed
# transfer (https://github.com/spindoxlabs/ds/issues/20).
from celine.governance.exposure import exposure_conflict
from ds.governance.models import GovernanceRuleV2
from ds.governance.purposes import purpose_failure
from ds.governance.sharing import (
    DuplicateOfferError,
    SharingOfferCatalogue,
    load_sharing_offers,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..clients.edc_management import EdcManagementClient
from ..schemas.edc import SyncResult
from .consent_vocabulary import offer_user_visible_hash
from .governance import ConnectorGovernanceMapper, load_exposed_datasets
from .offer_drift import offers_with_drift
from .prov_bridge import ProvBridge

log = logging.getLogger(__name__)


def _offer_failure(
    rule: GovernanceRuleV2, catalogue: SharingOfferCatalogue
) -> str | None:
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
    return load_sharing_offers(
        path if path.exists() else None, overlay_name=overlay_name
    )


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

    Three rules, one gate:

    - **Purpose** — an empty or unresolvable ``dataspace.purpose[]`` would be
      published with *no purpose constraint at all* (`_purpose_iris` drops what it
      cannot resolve; `_build_permission` emits the constraint only for a
      non-empty list). Nothing would limit what a consumer may use it for, and
      the sync used to report success.
    - **Sharing offers** — an id that does not resolve means the dataset is not
      shared.
    - **Exposure** — ``expose: false`` with ``dataspace.expose: true`` is a
      contradiction, not a narrower grant.

    The first two say the same thing: a dataset missing a fact the platform
    enforces on is not published, rather than published without the enforcement.
    The third is the other shape — a dataset saying two things that cannot both
    hold — and it lands in the same gate because the outcome a producer needs is
    the same: told, in one pass, before anything ships.

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
                exposure_conflict(rule),
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
            result.errors.append(
                {"dataset": key, "error": f"Not published — it {reason}"}
            )

    return set(rejected)


def _local_name(key: str) -> str:
    """The last segment of a JSON-LD key, whatever prefix or IRI form it came back in.

    Same rule and the same reason as `dependencies._asset_owner`: the property is
    written as ``f"{prefix}:datasetKey"`` with the prefix from the active ODRL
    profile, EDC returns properties JSON-LD-compacted, and a deployment may
    change the prefix. A hardcoded key reads as *this asset is not ds's*, which
    for a reconcile is a silent refusal to withdraw anything — the failure mode
    this whole item exists to remove.
    """
    return key.rsplit("#", 1)[-1].rsplit("/", 1)[-1].rsplit(":", 1)[-1]


def _published_dataset_key(asset: dict) -> str:
    """The governance key an asset was published from.

    ``""`` when ds did not publish it — an EDC runtime may hold objects ds never
    wrote, and they are not ds's to withdraw.
    """
    for key, value in (asset.get("properties") or {}).items():
        if isinstance(key, str) and isinstance(value, str) and value.strip():
            if _local_name(key) == "datasetKey":
                return value.strip()
    return ""


def _selector_asset_ids(definition: dict) -> set[str]:
    """Every asset id a contract definition's ``assetsSelector`` names.

    The selector is a list of `Criterion`, and ds emits exactly one — ``id = <asset>``
    (`ConnectorGovernanceMapper.to_contract_definition`). Read defensively rather
    than by position: the list comes back from EDC, compacted, and a definition
    that selects several assets is legitimate even though ds does not write one.
    """
    selector = (
        definition.get("assetsSelector") or definition.get("assetsselector") or []
    )
    if isinstance(selector, dict):
        selector = [selector]
    ids: set[str] = set()
    for criterion in selector:
        if not isinstance(criterion, dict):
            continue
        for key, value in criterion.items():
            if isinstance(key, str) and _local_name(key) == "operandRight":
                if isinstance(value, str):
                    ids.add(value)
                elif isinstance(value, list):
                    ids.update(v for v in value if isinstance(v, str))
    return ids


async def _withdraw_stale(
    edc: EdcManagementClient,
    declared_keys: set[str],
    published_asset_ids: dict[str, str],
    result: SyncResult,
    prov: ProvBridge,
    acted_by: dict | None = None,
) -> None:
    """Remove what EDC still holds and this connector's governance no longer declares.

    **The sync owned creation and not withdrawal**, which is worse than it
    sounds: removing a dataset from `governance.yaml` left EDC holding its asset,
    both policies and its contract definition, *still offered over DSP* — and the
    next sync reported a publish count that had gone **up**, because the count is
    of what published rather than of what is on offer. Nothing distinguished it
    from a healthy run. Measured in a live deployment on 2026-09-18.

    Three bounds, and they are the decision rather than the implementation:

    * **Only assets ds published**, identified by the `datasetKey` property the
      mapper writes. An EDC runtime may legitimately hold objects ds did not
      create, and *governance does not declare it* is not evidence that ds did.
      An asset published by a ds old enough not to write that property is left
      alone; one sync under this version labels it, and only then can it be
      withdrawn. That is the safe direction, and it is a migration note rather
      than a gap.
    * **Only datasets governance no longer declares at all** — removed, or no
      longer `expose`d. A dataset that is declared but was *rejected* by
      `_reject_unpublishable`, or that failed mid-publish, keeps whatever it had:
      that gate deliberately leaves a previously published version standing
      rather than tearing it down over a bad edit, and a reconcile that removed
      it anyway would undo that decision by another route.
    * **Plus the asset a still-declared dataset has just been republished
      *away* from**, when its id changed in this run. Without it, renaming an
      `asset.id` — or upgrading past the derived-id default that this change
      replaces — leaves the old asset on offer for ever, which is the same defect
      under a different name.

    **The order is EDC's, not a preference**: the contract definition references
    both policies and the asset, so it goes first; a policy still referenced by a
    definition is refused. A 409 on the asset (it has agreements) is reported,
    not swallowed — a withdrawn dataset that is still under contract is precisely
    the state an operator has to be told about.

    **A successful withdrawal is recorded in provenance** (`CatalogueWithdrawn`,
    `ADR-0017`), and only for the `undeclared` case. A dataset republished under
    a new asset id is *still on offer*: recording its old asset as withdrawn
    would put "this dataset is no longer available" in the graph about a dataset
    that is. The event is emitted **after** EDC has accepted the delete, so the
    graph never claims a withdrawal EDC refused; emission itself is non-fatal
    (`ProvenanceClient.emit_event` logs and returns), because the dataset is
    already off offer and losing the record is better than failing the reconcile
    that achieved it.
    """
    try:
        assets = await edc.list_assets()
    except Exception as exc:  # noqa: BLE001 — a reconcile that cannot read is not a pass
        log.exception("Could not list EDC assets to reconcile")
        result.errors.append({"error": f"Could not reconcile what EDC holds: {exc}"})
        return

    stale: list[tuple[str, str, bool]] = []
    for asset in assets:
        asset_id = str(asset.get("@id") or asset.get("id") or "")
        key = _published_dataset_key(asset)
        if not asset_id or not key:
            continue
        undeclared = key not in declared_keys
        superseded = key in published_asset_ids and published_asset_ids[key] != asset_id
        if undeclared or superseded:
            stale.append((asset_id, key, undeclared))
    if not stale:
        return

    try:
        definitions = await edc.list_contract_definitions()
    except Exception as exc:  # noqa: BLE001
        log.exception("Could not list EDC contract definitions to reconcile")
        result.errors.append({"error": f"Could not reconcile what EDC holds: {exc}"})
        return

    for asset_id, key, undeclared in sorted(stale):
        try:
            policy_ids: set[str] = set()
            for definition in definitions:
                if asset_id not in _selector_asset_ids(definition):
                    continue
                for field in ("accessPolicyId", "contractPolicyId"):
                    value = definition.get(field)
                    if isinstance(value, str) and value:
                        policy_ids.add(value)
                definition_id = str(definition.get("@id") or definition.get("id") or "")
                if definition_id:
                    await edc.delete_contract_definition(definition_id)

            if undeclared:
                # The derived default ids too, so a graph whose contract
                # definition was already gone does not leave its policies behind
                # for ever. A delete of something absent is a 404, which the
                # client tolerates.
                #
                # **Only when the dataset is gone.** Policy and contract ids are
                # derived from the *key*, not from the asset id, so a dataset
                # that merely moved to a new asset id has just been republished
                # under these very ids — deleting them here would delete the live
                # policies of a dataset that is still on offer, and EDC would
                # refuse only because its new contract definition still
                # references them. Found by
                # `test_an_asset_id_that_moved_takes_the_old_asset_with_it`.
                slug = key.replace(".", "-")
                policy_ids.update({f"{slug}-policy", f"{slug}-access-policy"})
            for policy_id in sorted(policy_ids):
                await edc.delete_policy(policy_id)

            await edc.delete_asset(asset_id)
            # The **asset id**, not the key: it is what was removed, it is
            # unambiguous, and it is directly comparable with what
            # `GET /provider/assets` reads back. A rename removes an asset whose
            # key is still declared, so a list of keys would be a lie for that
            # case.
            result.withdrawn.append(asset_id)
            log.info("Withdrew dataset %s — asset %s removed from EDC", key, asset_id)
            if undeclared:
                await prov.catalogue_withdrawn(
                    data_product_id=asset_id,
                    reason="undeclared",
                    acted_by=acted_by,
                )
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to withdraw dataset %s (asset %s)", key, asset_id)
            why = (
                "governance no longer declares it"
                if undeclared
                else "it was republished under a different asset id"
            )
            result.errors.append(
                {
                    "dataset": key,
                    # The asset id as well as the key. They coincide wherever an
                    # id is unset or pinned to the key, and a caller reconciling
                    # this against `GET /provider/assets` must not depend on that
                    # coincidence.
                    "asset": asset_id,
                    "error": (
                        f"Not withdrawn — {why}, but asset {asset_id!r} could not "
                        f"be removed from EDC: {exc}"
                    ),
                }
            )


async def sync_governance(
    governance_yaml_path: str,
    edc: EdcManagementClient,
    mapper: ConnectorGovernanceMapper,
    prov: ProvBridge,
    overlay_name: str | None = None,
    session: AsyncSession | None = None,
    # Who published. Optional so `ir-cli` and tests can sync without one, and so
    # an unattributed publish is recorded as unattributed rather than guessed at.
    acted_by: dict | None = None,
) -> SyncResult:
    result = SyncResult()
    try:
        datasets = load_exposed_datasets(
            governance_yaml_path, overlay_name=overlay_name
        )
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
        result.errors.append(
            {"offer": offer_id, "error": f"Not published — it {failure}"}
        )

    # One authority for the offers this sync maps against — the same catalogue
    # the drift check and the recipient access policy both read.
    mapper.bind_offers(catalogue)

    rejected = _reject_unpublishable(datasets, mapper, catalogue, result, set(drifted))

    #: What each dataset was published *as* in this run, so the reconcile below
    #: can tell an id that moved from one that is simply gone.
    published_asset_ids: dict[str, str] = {}

    for key, rule in datasets.items():
        if key in rejected:
            continue
        try:
            asset_create = mapper.to_asset_create(key, rule)
            policy_create = mapper.to_policy_create(key, rule)
            # Two policies: the access half decides who is admitted (membership,
            # recipient), the contract half states the terms. They were one, so
            # every admission condition was published to every counterparty and
            # nothing could be hidden from one.
            access_policy_create = mapper.to_access_policy_create(key, rule)
            contract_create = mapper.to_contract_definition(
                key,
                rule,
                policy_id=policy_create.id,
                asset_id=asset_create.id,
                access_policy_id=access_policy_create.id,
            )

            # The contract definition references both policies, so it goes first
            # and comes back last: deleting a policy EDC still has a definition
            # for is refused.
            await edc.delete_contract_definition(contract_create.id)
            await edc.delete_policy(policy_create.id)
            if access_policy_create.id != policy_create.id:
                await edc.delete_policy(access_policy_create.id)

            try:
                await edc.delete_asset(asset_create.id)
                await edc.create_asset(asset_create)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 409:
                    # EDC refuses to delete an asset referenced by a contract
                    # agreement or an ongoing negotiation. This used to *keep*
                    # the old one and move on — so **an asset under agreement
                    # never received a property change again**, silently, and a
                    # governance edit to it published nothing at all.
                    #
                    # Measured on 2026-09-18 on a dev stack: three of four assets
                    # had agreements, and none of the three carried the
                    # `datasetKey` property the same sync had just written for
                    # all four — which also made them permanently invisible to
                    # the reconcile below.
                    #
                    # `PUT` is the call EDC provides for exactly this, and it is
                    # body-addressed, so it is also unaffected by the id-in-a-
                    # path-segment problem that started this plan.
                    log.info(
                        "Asset %s is under agreement — updating in place",
                        asset_create.id,
                    )
                    await edc.update_asset(asset_create)
                else:
                    raise

            await edc.create_policy(policy_create)
            if access_policy_create.id != policy_create.id:
                await edc.create_policy(access_policy_create)
            await edc.create_contract_definition(contract_create)

            await prov.catalogue_published(
                data_product_id=asset_create.id,
                title=rule.title,
                description=rule.description,
                event_id=f"sync:{asset_create.id}",
                acted_by=acted_by,
            )

            result.synced.append(key)
            published_asset_ids[key] = asset_create.id
            log.info("Synced dataset %s → asset %s", key, asset_create.id)
        except Exception as exc:
            log.exception("Failed to sync dataset %s", key)
            result.errors.append({"dataset": key, "error": str(exc)})

    # Counted from the datasets themselves, not from `len(result.errors)`.
    # `errors` also carries offer-level entries and, since the reconcile below,
    # withdrawal failures — none of which is a dataset that was skipped, and all
    # of which used to subtract from this number.
    failed = {e.get("dataset") for e in result.errors if e.get("dataset") in datasets}
    skipped_count = len(datasets) - len(result.synced) - len(failed)
    if skipped_count > 0:
        result.skipped.append(
            f"{skipped_count} datasets skipped (not exposed or secret)"
        )

    # **After** publishing, deliberately. Withdrawing first would take a renamed
    # dataset off offer before its replacement exists; withdrawing after closes
    # the window to nothing.
    await _withdraw_stale(
        edc, set(datasets), published_asset_ids, result, prov, acted_by
    )

    return result
