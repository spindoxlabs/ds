"""Consent collectors — the admin relation and the connector's narrow check.

Plan `a-collector-registers-consent-at-the-holder`. The relation "organisation X
is an accepted consent collector for holder Y" lives here; the holder's connector
reads it before it accepts a consent registration from X's organisation token.

- `POST /admin/consent-collectors`, `POST /admin/consent-collectors/revoke`,
  `GET /admin/consent-collectors` — the anchor operator's surface, on
  `identity-registry.collectors.write` (or `.admin`).
- `GET /consent-collectors/check` — one pair at a time, on
  `identity-registry.read`, which a connector's organisation client holds. The
  same split as `/admin/memberships` and `/memberships/check`: a connector asking
  about one caller never needs the whole list.

A write tells the connectors to drop their cached answers
(`registry_notify.invalidate_participant_caches`, the hint the participant
registry already sends); the TTL bounds staleness when the hint is lost.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import ConsentCollector
from ...dependencies import (
    get_db,
    get_settings_dep,
    require_admin_or_read_scope,
    require_collectors_write,
)
from ...schemas.requests import ConsentCollectorRequest, RevokeConsentCollectorRequest
from ...schemas.responses import (
    ConsentCollectorCheckResponse,
    ConsentCollectorResponse,
)
from ...services import consent_collectors as collectors
from ...services.registry_notify import invalidate_participant_caches

router = APIRouter(tags=["consent-collectors"])


def _to_response(row: ConsentCollector) -> ConsentCollectorResponse:
    return ConsentCollectorResponse(
        holder_did=row.holder_did,
        collector_did=row.collector_did,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        revoked_at=row.revoked_at,
        revocation_reason=row.revocation_reason,
    )


@router.post(
    "/admin/consent-collectors",
    status_code=201,
    response_model=ConsentCollectorResponse,
)
async def add_consent_collector(
    data: ConsentCollectorRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    principal=Depends(require_collectors_write),
):
    """Accept an organisation as a consent collector for a holder. Idempotent."""
    try:
        row = await collectors.add(
            db,
            holder_did=data.holder_did,
            collector_did=data.collector_did,
            added_by=getattr(principal, "subject", None),
        )
    except collectors.CollectorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    await db.commit()
    await db.refresh(row)
    await invalidate_participant_caches(settings)
    return _to_response(row)


@router.post(
    "/admin/consent-collectors/revoke",
    response_model=ConsentCollectorResponse,
)
async def revoke_consent_collector(
    data: RevokeConsentCollectorRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _principal=Depends(require_collectors_write),
):
    """Withdraw the acceptance. The row stays, marked revoked, with the reason.

    Consents the collector already registered are not touched: they are the
    members' decisions, and withdrawing them is theirs (or the collector's, while
    it still may). What stops is the collector's ability to write more.
    """
    try:
        row = await collectors.revoke(
            db,
            holder_did=data.holder_did,
            collector_did=data.collector_did,
            reason=data.reason,
        )
    except collectors.CollectorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    await db.commit()
    await db.refresh(row)
    await invalidate_participant_caches(settings)
    return _to_response(row)


@router.get(
    "/admin/consent-collectors",
    response_model=list[ConsentCollectorResponse],
)
async def list_consent_collectors(
    holder_did: str | None = Query(default=None),
    include_revoked: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    _principal=Depends(require_collectors_write),
):
    rows = await collectors.list_relations(
        db, holder_did=holder_did, include_revoked=include_revoked
    )
    return [_to_response(row) for row in rows]


@router.get(
    "/consent-collectors/check",
    response_model=ConsentCollectorCheckResponse,
)
async def check_consent_collector(
    holder_did: str = Query(..., min_length=1),
    collector_did: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_or_read_scope),
):
    """May *collector_did* register consent at *holder_did*, and for whose members?"""
    answer = await collectors.check(db, holder_did, collector_did)
    return ConsentCollectorCheckResponse(
        holder_did=answer.holder_did,
        collector_did=answer.collector_did,
        accepted=answer.accepted,
        collector_owner=answer.collector_owner,
        reason=answer.reason,
    )
