"""Provider-side service: sync governance.yaml to EDC."""
from __future__ import annotations

import logging

import httpx

from ..clients.edc_management import EdcManagementClient
from ..schemas.edc import SyncResult
from .governance import ConnectorGovernanceMapper, load_exposed_datasets
from .prov_bridge import ProvBridge

log = logging.getLogger(__name__)


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

    for key, rule in datasets.items():
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
