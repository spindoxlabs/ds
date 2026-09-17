"""`GET /participants/resolve` — one participant, by DID or DSP address.

The question a consumer connector asks before it dials a counterparty (rulebook
`C-19`, `DSSC-PUB-27`): *is the party at this address a registered participant,
which DID is it, and in which role?* It used to answer that by reading
`GET /admin/participants` — every participant, with its allowed scopes and
registration time — on a route under `/admin`, which an organisation's own client
then had to reach.

This is the narrow form, beside the admin listing the way `/owners/resolve` sits
beside `/admin/owners` and `/memberships/check` beside `/admin/memberships`:

- one participant per call, named by exactly one of `did` or `dsp_address`;
- **active** participants only — a suspended one is not a counterparty;
- the answer is `did`, `dsp_address` and `roles`. Not `allowed_scopes`, not the
  registration time, not the STS secret, not the credentials;
- an unknown, inactive or ambiguous key is a `404` with one message, so the
  route does not tell a suspended participant from one that never existed.

Guarded by `identity-registry.read` (or `.admin`), which the connector's
organisation client already holds. No new permission.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Participant
from ...dependencies import get_db, require_admin_or_read_scope
from ...schemas.responses import ParticipantResolveResponse

router = APIRouter(tags=["participants"])

_NOT_FOUND = "No active participant matches"


@router.get("/participants/resolve", response_model=ParticipantResolveResponse)
async def resolve_participant(
    did: str | None = Query(None),
    dsp_address: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_admin_or_read_scope),
) -> ParticipantResolveResponse:
    if bool(did) == bool(dsp_address):
        raise HTTPException(
            status_code=422, detail="Name exactly one of `did` or `dsp_address`"
        )
    stmt = select(Participant).where(Participant.active.is_(True))
    if did:
        stmt = stmt.where(Participant.did == did)
    else:
        stmt = stmt.where(Participant.dsp_address == dsp_address)
    rows = (await db.execute(stmt)).scalars().all()
    # Two active participants on one DSP address is a registry defect, and
    # picking one would hand a connector a counterparty identity by row order.
    if len(rows) != 1:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    participant = rows[0]
    return ParticipantResolveResponse(
        did=participant.did,
        dsp_address=participant.dsp_address,
        roles=list(participant.roles or []),
    )
