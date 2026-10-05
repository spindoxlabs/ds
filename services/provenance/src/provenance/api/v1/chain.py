"""`GET /prov/chain/verify` — recompute the event record's hash chain (`L-17`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...dependencies import get_db, require_read_scope
from ...services import chain

router = APIRouter()


@router.get("/chain/verify", dependencies=[Depends(require_read_scope)])
async def verify_chain(db: AsyncSession = Depends(get_db)):
    """Recompute every hash from the first record.

    `ok` is false when any record was changed, removed or reordered, or is not
    chained yet; `firstFailure` names where. `head` is the newest hash: recorded
    somewhere else, it is what shows that no record was removed from the end.
    Reads the whole record, so it is an operator's check, not a page's.
    """
    return (await chain.verify(db)).as_dict()
