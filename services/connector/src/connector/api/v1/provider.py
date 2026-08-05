"""Provider management routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import ContractAgreementORM
from ds_auth import Principal

from ...services.prov_bridge import acting_principal
from ...dependencies import (
    get_db,
    get_provider_edc,
    get_settings_dep,
    require_provider_read,
    require_provider_write,
    require_provider_write_own,
)
from ...services.authorization_service import get_authorized_datasets

router = APIRouter(prefix="/provider", tags=["provider"])


class SyncRequest(BaseModel):
    governance_yaml_path: str | None = None


@router.post("/sync")
async def sync(
    req: SyncRequest | None = None,
    settings: Settings = Depends(get_settings_dep),
    edc=Depends(get_provider_edc),
    # The verified caller, carried through so the published offers can name who
    # published them. `require_permission` yields a Principal; the old `_claims:
    # dict` annotation was wrong about that and nothing used it.
    principal: Principal = Depends(require_provider_write),
    # Recorded consent is what makes the offer-drift check possible: the rows
    # carry the hash and version they were written with, so the sync can tell an
    # edit from a revision.
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    from ds.governance.models import load_odrl_profile

    from ...services.governance import ConnectorGovernanceMapper, load_exposed_datasets
    from ...services.provider_service import sync_governance

    yaml_path = (req.governance_yaml_path if req else None) or settings.governance_yaml_path
    profile = load_odrl_profile(settings.odrl_profile_path)

    owner_did_resolver = None
    owners_registry = getattr(request.app.state, "owners_registry", None) if request else None
    if owners_registry is not None:
        datasets = load_exposed_datasets(yaml_path, overlay_name=settings.governance_overlay_name)
        owner_aliases = {
            o.name
            for rule in datasets.values()
            for o in rule.ownership
        }
        resolved: dict[str, str | None] = {}
        for alias in owner_aliases:
            resolved[alias] = await owners_registry.canonical_uri(alias)
        owner_did_resolver = resolved.get

    mapper = ConnectorGovernanceMapper(
        settings.participant_id,
        settings.participant_base_url,
        profile=profile,
        owner_did_resolver=owner_did_resolver,
        participant_did=settings.participant_did,
    )
    prov = request.app.state.prov
    result = await sync_governance(
        yaml_path,
        edc,
        mapper,
        prov,
        overlay_name=settings.governance_overlay_name,
        session=db,
        acted_by=acting_principal(principal),
    )

    # A sync re-reads governance and the offer files; the consent vocabulary is
    # cached for the process lifetime, so without this it keeps serving the view
    # it had at startup. That is not merely stale output: `resolve_offer` and
    # `known_dataset_keys` gate consent *writes*, so a freshly contributed offer
    # would be accepted by this sync and then rejected as unknown by
    # `POST /consent/my/shares`, and `/ns/sharing-offers` would advertise a
    # consent_text_version nobody is publishing any more.
    #
    # Dropped even when the sync reported errors: the files on disk changed
    # either way, and the caches are rebuilt lazily on next read.
    from ...services import consent_vocabulary as vocab

    vocab.reset_caches()
    return result


@router.get("/authorizations")
async def get_authorizations(
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_provider_read),
):
    """Return consented subject IDs per dataset.

    Read-only query endpoint — external consumers (DSO, compliance tools)
    poll it on their own schedule.
    """
    datasets = await get_authorized_datasets(db)
    return {"datasets": datasets}


# A commented-out `GET /governance/matrix` lived here, and the only caller of
# `load_governance_policy_matrix` was inside the comment — so the function was
# reachable from nothing and the route was declared to nobody. Both are gone.
#
# The one thing worth keeping from it is the reason it was never enabled: the
# matrix projected **access levels, classification, consent rules and row-filter
# columns** — the whole enforcement structure, including the columns a row filter
# keys on. That is an admin disclosure, not a public one, and `require_provider_read`
# is not enough for it.
#
# `ds.governance.build_policy_matrix` is **gone too** (2026-08-05). With the route
# deleted it had no caller anywhere, in this repository or in any sibling
# checkout, and it had silently drifted out of agreement with the mapper it
# describes: two of the four operand names it sorted constraints by were terms
# the mapper has never emitted. Rebuild it from `GovernanceMapper`'s output if
# the route ever comes back — and derive the operands from the profile rather
# than re-listing them, which is the mistake that made the old one wrong.


@router.get("/assets")
async def list_assets(edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    return await edc.list_assets()


@router.get("/assets/{asset_id:path}")
async def get_asset(asset_id: str, edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    try:
        return await edc.get_asset(asset_id)
    except Exception:
        raise HTTPException(404, f"Asset {asset_id!r} not found")


@router.delete("/assets/{asset_id:path}", status_code=204)
async def delete_asset(
    asset_id: str,
    edc=Depends(get_provider_edc),
    # Owner-scoped: `connector.provider.write` says what may be done, not
    # whose data it may be done to. See `_own_owner_only`.
    _c: dict = Depends(require_provider_write_own),
):
    await edc.delete_asset(asset_id)


@router.get("/policies")
async def list_policies(edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    return await edc.list_policies()


@router.delete("/policies/{policy_id}", status_code=204)
async def delete_policy(
    policy_id: str,
    edc=Depends(get_provider_edc),
    # Owner-scoped through governance: EDC labels no owner on a policy, but its id
    # is derived from the dataset key. See `_target_owner`.
    _c: dict = Depends(require_provider_write_own),
):
    await edc.delete_policy(policy_id)


@router.get("/contracts")
async def list_contracts(edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    return await edc.list_contract_definitions()


@router.delete("/contracts/{contract_id}", status_code=204)
async def delete_contract(
    contract_id: str,
    edc=Depends(get_provider_edc),
    _c: dict = Depends(require_provider_write_own),
):
    await edc.delete_contract_definition(contract_id)


@router.get("/agreements")
async def list_agreements(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _c: dict = Depends(require_provider_read),
) -> list[dict]:
    """The contract agreements this participant granted, as a provider.

    Deliberately gated on ``provider.read`` rather than ``history.read``: a
    producer looking at the contracts over their *own* datasets is reading
    provider data, and requiring the history grant would lock a read-only
    producer out of it. The same rows are visible through ``/history/agreements``
    to a caller holding that broader grant, which spans every party's activity.
    """
    q = select(ContractAgreementORM).where(
        ContractAgreementORM.provider_id == settings.participant_did
    )
    if active_only:
        q = q.where(ContractAgreementORM.terminated_at.is_(None))
    result = await db.execute(q.order_by(ContractAgreementORM.agreed_at.desc()))
    return [
        {
            "agreement_id": a.agreement_id,
            "asset_id": a.asset_id,
            "consumer_id": a.consumer_id,
            "provider_id": a.provider_id,
            "agreed_at": a.agreed_at.isoformat() if a.agreed_at else None,
            "terminated_at": a.terminated_at.isoformat() if a.terminated_at else None,
            "termination_reason": a.termination_reason,
        }
        for a in result.scalars()
    ]


@router.get("/transfers")
async def list_transfers(edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    return await edc.list_transfers()


@router.get("/transfers/{transfer_id}")
async def get_transfer(transfer_id: str, edc=Depends(get_provider_edc), _c: dict = Depends(require_provider_read)):
    return await edc.get_transfer(transfer_id)
