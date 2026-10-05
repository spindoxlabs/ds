from __future__ import annotations

import base64
import gzip
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Credential, StatusList

BITSTRING_SIZE = 16384  # 16KB = 131072 bits
BITSTRING_CAPACITY = BITSTRING_SIZE * 8

# ── Two registers, and the difference between them ────────────────
#
# A **revocation** bit is terminal: set once, never cleared, because the
# credential it refers to is finished. A **suspension** bit is a *state* — set
# while the holder is suspended, cleared when they are reinstated. That is the
# whole difference between suspension and deactivation, and Bitstring Status
# List (like StatusList2021 before it) carries it in `statusPurpose`.
#
# A verifier enforces it. EDC's `BitstringStatusListRevocationService` (and
# `StatusList2021RevocationService`, for entries issued before R3) refuses an
# entry whose `statusPurpose` does not match the fetched list's (v0.18.0), and
# `RevocationServiceRegistryImpl` checks **every** `credentialStatus` entry a
# credential carries, failing with the purpose it found set
# (`"Credential status is '%s', status at index %d is '1'"`). So a credential
# naming both registers is rejected while either bit is set, and the rejection
# says which — suspended, or revoked.
#
# The index space is **mirrored, not allocated twice**: a credential's one index
# means the same credential on both registers. Two counters would drift the
# moment one register was written to more than the other, and a drifted index is
# a bit that suspends somebody else.
REVOCATION_LIST_ID = "1"
SUSPENSION_LIST_ID = "2"

LIST_PURPOSE = {
    REVOCATION_LIST_ID: "revocation",
    SUSPENSION_LIST_ID: "suspension",
}


class StatusListPurposeMismatch(RuntimeError):
    """An operation that only one register permits was asked of the other.

    Clearing a revocation bit is the one this exists for: it would make a
    finished credential valid again, and it is exactly the mistake a reinstate
    path makes when it is handed the wrong list id.
    """


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


def clear_bit(bitstring: bytes, index: int) -> bytes:
    ba = bytearray(bitstring)
    byte_index = index // 8
    bit_offset = 7 - (index % 8)
    ba[byte_index] &= ~(1 << bit_offset) & 0xFF
    return bytes(ba)


def get_bit(bitstring: bytes, index: int) -> bool:
    byte_index = index // 8
    bit_offset = 7 - (index % 8)
    return bool(bitstring[byte_index] & (1 << bit_offset))


def encode_bitstring(bitstring: bytes) -> str:
    """Multibase base64url (`u` header, no padding) of the GZIP-compressed list.

    That is the Bitstring Status List encoding (W3C `vc-bitstring-status-list`
    §"Bitstring Encoding"), and it is what EDC's IssuerService publishes
    (`BitString.Writer.writeMultibase`). EDC's `BitString.Parser` reads it by the
    `u` header, and reads a header-less list as plain base64 — so every verifier
    that read the StatusList2021 form reads this one.

    **GZIP, never zlib.** This once emitted a raw zlib stream: same DEFLATE
    payload, different two-byte header, so no conformant verifier could
    decompress it and every revocation check failed — closed, and silently,
    because a status list that cannot be read is indistinguishable from a
    credential that is revoked. Nothing caught it because `decode_bitstring`
    used zlib too and every test round-tripped perfectly.
    """
    compressed = gzip.compress(bitstring, mtime=0)
    return "u" + base64.urlsafe_b64encode(compressed).decode().rstrip("=")


def decode_bitstring(encoded: str) -> bytes:
    """Read every encoding this registry has ever published.

    - `u…` — multibase base64url, the Bitstring Status List form (current).
    - plain base64 of a GZIP stream — the StatusList2021 form (before R3).
    - plain base64 of a zlib stream — before the GZIP fix.

    The older forms stay readable because issued credentials and exported
    snapshots already reference them. A GZIP stream always base64-encodes to
    `H4sI…`, so the `u` header cannot be mistaken for a legacy list.
    """
    if encoded.startswith("u"):
        body = encoded[1:]
        compressed = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    else:
        compressed = base64.b64decode(encoded)
    try:
        return gzip.decompress(compressed)
    except (OSError, EOFError):
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
    db: AsyncSession, list_id: str = REVOCATION_LIST_ID, *, lock: bool = False
) -> StatusList:
    """The status list row, created on first use with the purpose its id means.

    `lock=True` takes `SELECT … FOR UPDATE`, which is required for allocation
    and pointless for anything else. SQLite ignores the clause, so the test
    suite exercises the same code path without it.

    A row whose stored purpose disagrees with `LIST_PURPOSE` is refused rather
    than used. `/status/{list_id}` publishes `statusPurpose` from this column, so
    a wrong value is not a local inconsistency: it is a register every verifier
    reads under the wrong meaning, and EDC rejects credentials pointing at it.
    """
    purpose = LIST_PURPOSE.get(list_id, "revocation")
    stmt = select(StatusList).where(StatusList.id == list_id)
    if lock:
        stmt = stmt.with_for_update()
    sl = (await db.execute(stmt)).scalar_one_or_none()
    if sl is not None:
        if sl.purpose != purpose:
            raise StatusListPurposeMismatch(
                f"Status list {list_id!r} is published as {sl.purpose!r}, but this "
                f"deployment uses it as {purpose!r}."
            )
        return sl

    # Two workers can reach this line for the same list. The savepoint means
    # the loser of that race rolls back only its own failed INSERT — an outer
    # rollback here would discard the caller's half-built credential.
    try:
        async with db.begin_nested():
            sl = StatusList(
                id=list_id,
                purpose=purpose,
                bitstring=create_bitstring(),
                next_index=0,
            )
            db.add(sl)
            await db.flush()
    except IntegrityError:
        sl = (await db.execute(stmt)).scalar_one()
    return sl


async def allocate_status_list_index(
    db: AsyncSession, list_id: str = REVOCATION_LIST_ID
) -> int:
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


async def allocate_suspendable_index(db: AsyncSession) -> int:
    """One index, usable on both registers.

    Allocated from the revocation counter — the only counter — and the
    suspension register is *created here* rather than on first suspension. A
    credential is issued naming `/status/2`; if that route 404s because nobody
    has suspended anyone yet, a verifier that fails closed rejects a perfectly
    valid credential. The register a credential points at has to exist from the
    moment the credential does.
    """
    index = await allocate_status_list_index(db, REVOCATION_LIST_ID)
    await get_or_create_status_list(db, SUSPENSION_LIST_ID)
    return index


async def revoke_status_list_index(
    db: AsyncSession, index: int, list_id: str = REVOCATION_LIST_ID
) -> StatusList:
    """Set the revocation register's bit for `index` — terminal, and never undone.

    Idempotent, so re-revoking is not an error.
    """
    sl = await get_or_create_status_list(db, list_id, lock=True)
    if sl.purpose != "revocation":
        raise StatusListPurposeMismatch(
            f"Status list {list_id!r} is a {sl.purpose!r} register; revocation "
            "belongs on the revocation register."
        )
    sl.bitstring = set_bit(sl.bitstring, index)
    sl.updated_at = datetime.now(UTC)
    return sl


async def suspend_status_list_index(db: AsyncSession, index: int) -> StatusList:
    """Set the *suspension* register's bit for `index`.

    Idempotent. The list id is not a parameter: a suspension written to the
    revocation register is a revocation, and the difference between the two is
    the entire point of this pair.
    """
    sl = await get_or_create_status_list(db, SUSPENSION_LIST_ID, lock=True)
    sl.bitstring = set_bit(sl.bitstring, index)
    sl.updated_at = datetime.now(UTC)
    return sl


async def unsuspend_status_list_index(db: AsyncSession, index: int) -> StatusList:
    """Clear the *suspension* register's bit for `index` — the only bit that
    may ever be cleared.

    Idempotent. Nothing here can reach the revocation register, by construction:
    revoking is final, and a "clear" that could touch it would make a finished
    credential valid again.
    """
    sl = await get_or_create_status_list(db, SUSPENSION_LIST_ID, lock=True)
    sl.bitstring = clear_bit(sl.bitstring, index)
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
        # The column is nullable — a credential that was never allocated an index
        # has none — but SQL `IN` cannot match NULL, so the `.in_(colliding)`
        # filter above has already excluded those rows. Bound and asserted rather
        # than ignored, so the invariant is stated where it is relied on.
        index = cred.status_list_index
        assert index is not None, "IN (...) cannot match a NULL index"
        entry = grouped.setdefault(index, DuplicateIndex(index=index))
        entry.credential_ids.append(cred.id)
        entry.subject_dids.append(cred.subject_did)
    return [grouped[i] for i in sorted(grouped)]


def build_status_list_credential(
    *,
    list_url: str,
    issuer_did: str,
    encoded_list: str,
    purpose: str = "revocation",
    valid_from: datetime | None = None,
) -> dict[str, Any]:
    """The register as a `BitstringStatusListCredential` (R3).

    DCP v1.0 issuance says revocation MUST use Bitstring Status List
    (`credential.issuance.protocol.md:359`), and EDC's IssuerService publishes
    exactly this shape at v0.18.0: a **VC 1.1** credential (`issuanceDate`),
    signed as a VC-JWT with a `vc` claim (`BitstringStatusListManager`, still
    `VC1_0_JWT` with a "todo: VC2_0_JOSE"). A VCDM 2.0 envelope would not be
    readable by EDC's verifier at the pin, which takes the list from `vc`.

    **The `id` is the list's own URL, stable per list.** It used to be a fresh
    `urn:uuid` on every build, so the same register was a different credential
    on every fetch — nothing could cache it, pin it, or say which list a
    revocation was published in. The URL is what `statusListCredential` in every
    holder credential names, so the two now agree (the spec's own examples do
    the same).

    `valid_from` is when this version of the register took effect (the row's
    `updated_at`), so it is stable too until a bit changes. `ttl` is left out:
    DCP's profile note says to ignore it in favour of validity dates.
    """
    issued = (valid_from or datetime.now(UTC)).replace(microsecond=0)
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=UTC)
    return {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "id": list_url,
        "type": ["VerifiableCredential", "BitstringStatusListCredential"],
        "issuer": issuer_did,
        "issuanceDate": issued.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "credentialSubject": {
            "id": f"{list_url}#list",
            "type": "BitstringStatusList",
            "statusPurpose": purpose,
            "encodedList": encoded_list,
        },
    }
