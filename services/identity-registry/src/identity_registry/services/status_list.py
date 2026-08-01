from __future__ import annotations

import base64
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Credential, StatusList
from .crypto import generate_credential_id

BITSTRING_SIZE = 16384  # 16KB = 131072 bits
BITSTRING_CAPACITY = BITSTRING_SIZE * 8


class StatusListFull(RuntimeError):
    """The register has no room for another credential.

    Raised *before* an index is consumed, so the counter and the register stay
    consistent and a retry after provisioning a second list is safe.
    """


def create_bitstring() -> bytes:
    return b"\x00" * BITSTRING_SIZE


def set_bit(bitstring: bytes, index: int) -> bytes:
    ba = bytearray(bitstring)
    byte_index = index // 8
    bit_offset = 7 - (index % 8)
    ba[byte_index] |= 1 << bit_offset
    return bytes(ba)


def get_bit(bitstring: bytes, index: int) -> bool:
    byte_index = index // 8
    bit_offset = 7 - (index % 8)
    return bool(bitstring[byte_index] & (1 << bit_offset))


def encode_bitstring(bitstring: bytes) -> str:
    compressed = zlib.compress(bitstring)
    return base64.b64encode(compressed).decode()


def decode_bitstring(encoded: str) -> bytes:
    compressed = base64.b64decode(encoded)
    return zlib.decompress(compressed)


# ── Allocation ────────────────────────────────────────────────────
#
# There is deliberately no `next_available_index(bitstring)` here any more.
# Scanning the register for the first unset bit is what produced both P0
# defects: leave the bit clear and it never moves, so every credential collides
# and revoking one revokes all of them; set it to make it move and the
# credential is published revoked from birth. The register answers "is this
# credential revoked"; it is not, and cannot be, the allocator.


async def get_or_create_status_list(
    db: AsyncSession, list_id: str = "1", *, lock: bool = False
) -> StatusList:
    """The status list row, created on first use.

    `lock=True` takes `SELECT … FOR UPDATE`, which is required for allocation
    and pointless for anything else. SQLite ignores the clause, so the test
    suite exercises the same code path without it.
    """
    stmt = select(StatusList).where(StatusList.id == list_id)
    if lock:
        stmt = stmt.with_for_update()
    sl = (await db.execute(stmt)).scalar_one_or_none()
    if sl is not None:
        return sl

    # Two workers can reach this line for the same list. The savepoint means
    # the loser of that race rolls back only its own failed INSERT — an outer
    # rollback here would discard the caller's half-built credential.
    try:
        async with db.begin_nested():
            sl = StatusList(
                id=list_id,
                purpose="revocation",
                bitstring=create_bitstring(),
                next_index=0,
            )
            db.add(sl)
            await db.flush()
    except IntegrityError:
        sl = (await db.execute(stmt)).scalar_one()
    return sl


async def allocate_status_list_index(db: AsyncSession, list_id: str = "1") -> int:
    """Reserve the next credential index on `list_id`.

    Taken from the counter under a row lock. The lock is not decorative:
    issuance runs on HTTP routes served by parallel workers, and two requests
    reading the same counter hand out the same index — a failure that stays
    silent until somebody revokes one of the two credentials and finds they
    have revoked both.

    Indices are never reused. A revoked credential keeps its index forever,
    because that index is what the register's bit refers to, and a deleted
    credential's index stays spent because its signed JSON may still be in a
    holder's wallet.

    `updated_at` is deliberately not touched: allocation does not change the
    published register, and bumping it would signal a revocation that did not
    happen.
    """
    sl = await get_or_create_status_list(db, list_id, lock=True)
    if sl.next_index >= BITSTRING_CAPACITY:
        raise StatusListFull(
            f"Status list {list_id!r} is full ({BITSTRING_CAPACITY} indices). "
            "Issue against a new status list."
        )
    index = sl.next_index
    sl.next_index = index + 1
    await db.flush()
    return index


async def revoke_status_list_index(
    db: AsyncSession, index: int, list_id: str = "1"
) -> StatusList:
    """Set the register's bit for `index` — the *only* thing that may set one.

    Idempotent, so re-revoking is not an error.
    """
    sl = await get_or_create_status_list(db, list_id, lock=True)
    sl.bitstring = set_bit(sl.bitstring, index)
    sl.updated_at = datetime.now(UTC)
    return sl


# ── Detecting damage the allocator fix cannot repair ──────────────


@dataclass
class DuplicateIndex:
    """One index held by more than one credential."""

    index: int
    credential_ids: list[str] = field(default_factory=list)
    subject_dids: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        subjects = ", ".join(sorted(set(self.subject_dids)))
        return (
            f"index {self.index}: {len(self.credential_ids)} credentials "
            f"held by {subjects}"
        )


async def find_duplicate_indices(db: AsyncSession) -> list[DuplicateIndex]:
    """Credentials sharing a StatusList index — the damage the old allocator
    left behind.

    This is a *report*, never a repair. The index is inside the signed
    credential JSON, so it cannot be corrected in place: changing it invalidates
    the signature. The only fix is re-issuance, which is an operational
    decision (in dev, re-run the identity bootstrap). Without this report,
    "you may need to re-issue" is unactionable — an operator cannot tell
    whether they are affected or how badly.
    """
    colliding = (
        select(Credential.status_list_index)
        .where(Credential.status_list_index.is_not(None))
        .group_by(Credential.status_list_index)
        .having(func.count() > 1)
    )
    rows = (
        (
            await db.execute(
                select(Credential)
                .where(Credential.status_list_index.in_(colliding))
                .order_by(Credential.status_list_index, Credential.id)
            )
        )
        .scalars()
        .all()
    )

    grouped: dict[int, DuplicateIndex] = {}
    for cred in rows:
        entry = grouped.setdefault(
            cred.status_list_index, DuplicateIndex(index=cred.status_list_index)
        )
        entry.credential_ids.append(cred.id)
        entry.subject_dids.append(cred.subject_did)
    return [grouped[i] for i in sorted(grouped)]


def build_status_list_credential(
    *,
    list_id: str,
    issuer_did: str,
    encoded_list: str,
    purpose: str = "revocation",
) -> dict[str, Any]:
    return {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://w3id.org/vc/status-list/2021/v1",
        ],
        "id": generate_credential_id(),
        "type": ["VerifiableCredential", "StatusList2021Credential"],
        "issuer": issuer_did,
        "credentialSubject": {
            "id": f"urn:status-list:{list_id}",
            "type": "StatusList2021",
            "statusPurpose": purpose,
            "encodedList": encoded_list,
        },
    }
