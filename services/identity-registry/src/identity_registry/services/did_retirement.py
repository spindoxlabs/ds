"""Retiring a DID when the identity behind it has been offboarded (R35).

A **retired** DID is a `dids` row with ``active = false`` and ``deactivated_at``
set. Nothing is deleted: consent records and provenance events keep pointing at
the identifier, so the row stays as evidence. What stops is **resolution**: the
document routes serve active rows only, so a retired DID answers 404, as an
unknown one does.

**Why stop serving rather than mark the document.** did:web has no deactivation
flag of its own. DID Resolution's ``deactivated: true`` is *resolution
metadata*, which a resolver reports and a did:web document cannot carry, and
EDC's ``WebDidResolver`` (0.18.0) reads only the HTTP status: anything but 200
fails resolution, a document marked deactivated would still resolve. EDC's
IdentityHub takes the same route: deactivating a participant context unpublishes
its DID document. So does this.

**Who retires what.** A person's DID is served by the organisation that holds
their credentials (the custodian), and an organisation's DID by its own
instance, not by the anchor that revoked them. The anchor reaches neither, and
DCP has no message for it, so each holder retires its own rows from what the
issuer publishes anyway: the revocation register. :func:`sweep` retires every
DID this instance serves whose credentials **all** carry a set revocation bit.
Suspension does not retire anything: it is reversible, and its bit already
stops every use. `ir-cli did sweep` runs it; `ir-cli did retire` retires one DID
by hand.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import Credential, Did

log = logging.getLogger(__name__)

#: Is this credential's revocation bit set? ``True``/``False``, ``None`` when the
#: credential names no revocation register. Raises when the register cannot be
#: read — never an answer the sweep could mistake for "not revoked".
RevocationReader = Callable[[Credential], Awaitable[bool | None]]


@dataclass
class SweepResult:
    examined: int = 0
    retired: list[str] = field(default_factory=list)
    unknown: int = 0

    @property
    def clean(self) -> bool:
        return self.unknown == 0


def retire(did_row: Did, now: datetime | None = None) -> bool:
    """Retire one DID. Idempotent: ``False`` when it already was."""
    if not did_row.active:
        return False
    did_row.active = False
    did_row.deactivated_at = now or datetime.now(UTC)
    return True


async def retire_did(db: AsyncSession, did: str) -> bool | None:
    """Retire *did*; ``None`` when this instance has no row for it."""
    row = await db.get(Did, did)
    if row is None:
        return None
    return retire(row)


async def anchor_reader(credential: Credential) -> bool | None:
    """On the issuer, its own record is the register's source."""
    if credential.status_list_index is None:
        return None
    return credential.status == "revoked"


def register_reader(settings: Settings) -> RevocationReader:
    """On a holder, the issuer's signed register, at the anchor's address."""
    from ds_auth.user_credentials import get_resolver, status_bit_set

    resolver = get_resolver(use_https=settings.did_web_use_https)

    async def read(credential: Credential) -> bool | None:
        return await asyncio.to_thread(
            status_bit_set,
            credential.credential_json or {},
            "revocation",
            register_origin=settings.issuer_base_url,
            issuer=settings.trust_anchor_did,
            resolver=resolver,
        )

    return read


def _sweepable(settings: Settings) -> Callable[[Did], bool]:
    """Persons always; on a participant, its own DID too; the anchor never itself."""

    def check(row: Did) -> bool:
        if row.did_type == "user":
            return True
        return settings.role == "participant" and row.did == settings.participant_did

    return check


async def sweep(
    db: AsyncSession,
    settings: Settings,
    read: RevocationReader,
    *,
    dry_run: bool = False,
) -> SweepResult:
    """Retire every served DID whose credentials are all revoked.

    A DID with no credential here, or with one that names no revocation
    register, is left alone: nothing published says it was offboarded. A
    register that cannot be read leaves the DID alone too, and is counted, so
    the caller can exit non-zero. Held copies whose bit is set are marked
    ``revoked`` so they are no longer offered.
    """
    result = SweepResult()
    sweepable = _sweepable(settings)
    rows = (await db.execute(select(Did).where(Did.active.is_(True)))).scalars()
    for row in [r for r in rows if sweepable(r)]:
        held = (
            (
                await db.execute(
                    select(Credential).where(Credential.subject_did == row.did)
                )
            )
            .scalars()
            .all()
        )
        if not held:
            continue
        result.examined += 1
        try:
            bits = [await read(c) for c in held]
        except Exception as exc:  # noqa: BLE001 — any failure is "unknown"
            result.unknown += 1
            log.warning("revocation register unreadable for a DID here: %s", exc)
            continue
        if not all(bit is True for bit in bits):
            continue
        result.retired.append(row.did)
        if dry_run:
            continue
        now = datetime.now(UTC)
        for credential in held:
            if credential.status != "revoked":
                credential.status = "revoked"
                credential.revoked_at = credential.revoked_at or now
        retire(row, now)
    if not dry_run:
        await db.commit()
    return result
