"""Provider-side service: sync governance.yaml to EDC."""
from __future__ import annotations

import logging

import httpx

from ds.governance.models import GovernanceRuleV2
from ds.governance.purposes import purpose_failure

from ..clients.edc_management import EdcManagementClient
from ..schemas.edc import SyncResult
from .governance import ConnectorGovernanceMapper, load_exposed_datasets
from .prov_bridge import ProvBridge

log = logging.getLogger(__name__)


def _reject_unusable_purposes(
    datasets: dict[str, GovernanceRuleV2],
    mapper: ConnectorGovernanceMapper,
    result: SyncResult,
) -> set[str]:
    """Datasets that must not be published, with every reason reported at once.

    A dataset whose ``policy.purpose[]`` is empty or unresolvable would be
    published with **no purpose constraint at all** — `_purpose_iris` drops what
    it cannot resolve and `_build_permission` emits the constraint only for a
    non-empty list. Nothing then limits what a consumer may use it for, and
    nothing says so: the sync used to report success. This is the same statement
    the unknown-offer rule makes — a dataset with no usable stated reason for
    processing has no stated reason, so it is not published.

    **Every failure is collected before anything is published**, mirroring
    `ProductionGuard`, which logs all violations and only then refuses. Ingest is
    where a producer finds out, and they need the whole list in one pass —
    failing on the first turns one revision into several round trips.

    A rejected dataset is *skipped*, not deleted from EDC. If it was published
    before with a valid purpose, that version stays live rather than being torn
    down over a bad edit: the previously published constraint is the safer of the
    two states to leave standing.
    """
    rejected: dict[str, str] = {}
    for key, rule in datasets.items():
        failure = purpose_failure(rule, mapper.profile)
        if failure:
            rejected[key] = failure

    for key, failure in rejected.items():
        log.error("Refusing to publish %s — it %s", key, failure)
        result.errors.append({"dataset": key, "error": f"Not published — it {failure}"})

    return set(rejected)


async def sync_governance(
    governance_yaml_path: str,
    edc: EdcManagementClient,
    mapper: ConnectorGovernanceMapper,
    prov: ProvBridge,
    overlay_name: str | None = None,
) -> SyncResult:
    result = SyncResult()
    try:
        datasets = load_exposed_datasets(governance_yaml_path, overlay_name=overlay_name)
    except Exception as exc:
        result.errors.append({"error": f"Failed to load governance.yaml: {exc}"})
        return result

    rejected = _reject_unusable_purposes(datasets, mapper, result)

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
