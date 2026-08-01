"""Allocate credential indices from a counter, not from the revocation register

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-01

`status_lists.bitstring` is a **revocation** register: bit *n* set means
credential *n* is revoked. It was also being read as the *allocator* for new
credentials, via `next_available_index()` → the first unset bit. Those two
readings cannot both be true, and the codebase held both at once:

* four issuance sites read the first unset bit and did **not** set it, so the
  bit never moved and every credential they issued took the *same* index —
  revoking any one of them revoked all the others;
* two issuance sites read it and **did** set it, which advanced the allocator
  correctly and published the credential revoked from birth.

That mixture is also why the defect looked intermittent: the two bit-setting
paths advance the register, so the four colliding sites do not all return 0 —
they return the first index no onboarding path has claimed. A fresh database
and a seeded one produce different numbers.

`next_index` is the allocator. The bitstring goes back to meaning one thing.

**The backfill starts above every index ever handed out**, which is not the
same as above every index still stored. A credential row can be deleted while
its signed JSON — naming its index — is still in a holder's wallet, and the
register may still carry its revocation bit. So the starting point is the
greater of `max(credentials.status_list_index) + 1` and one past the highest
set bit. Reusing an index would silently bind a live credential to a stranger's
revocation.

**Existing damage is reported, not repaired, and does not block the upgrade.**
Unlike 0010, this migration cannot fix what it finds: `status_list_index` is
embedded in the *signed* credential JSON, so correcting a collision in place
invalidates the signature. Colliding credentials can only be re-issued. Failing
the upgrade would also be the wrong response — it would strand the deployment
on the code that causes the collisions. The duplicates are printed instead,
with their subjects, so an operator can plan the re-issuance. In dev the answer
is to re-run the identity bootstrap.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _highest_set_bit(bitstring: bytes | None) -> int:
    """One past the highest revoked index, or 0. Scans backwards because the
    register is 16KB and almost entirely zero."""
    if not bitstring:
        return 0
    for byte_index in range(len(bitstring) - 1, -1, -1):
        byte = bitstring[byte_index]
        if byte:
            for bit_offset in range(8):
                if byte & (1 << bit_offset):
                    return byte_index * 8 + (7 - bit_offset) + 1
    return 0


def upgrade() -> None:
    op.add_column(
        "status_lists",
        sa.Column(
            "next_index", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )

    conn = op.get_bind()

    duplicates = conn.execute(
        sa.text(
            """
            SELECT status_list_index, count(*) AS n,
                   string_agg(subject_did, ', ') AS subjects
            FROM credentials
            WHERE status_list_index IS NOT NULL
            GROUP BY status_list_index
            HAVING count(*) > 1
            ORDER BY status_list_index
            """
        )
    ).fetchall()
    if duplicates:
        affected = sum(r.n for r in duplicates)
        noun = "index" if len(duplicates) == 1 else "indices"
        print(
            f"\n  WARNING: {affected} credentials share {len(duplicates)} "
            f"StatusList {noun}.\n"
            "  Revoking any one of a colliding group revokes the whole group. "
            "The index is inside\n"
            "  the signed credential, so this cannot be corrected in place — "
            "the affected\n"
            "  credentials must be RE-ISSUED. In dev, re-run the identity "
            "bootstrap.\n"
        )
        for r in duplicates:
            print(f"    index {r.status_list_index}: {r.n} credentials — {r.subjects}")
        print()

    for row in conn.execute(sa.text("SELECT id, bitstring FROM status_lists")):
        highest_issued = (
            conn.execute(
                sa.text(
                    "SELECT max(status_list_index) FROM credentials "
                    "WHERE status_list_index IS NOT NULL"
                )
            ).scalar()
            or -1
        ) + 1
        start = max(highest_issued, _highest_set_bit(row.bitstring))
        conn.execute(
            sa.text("UPDATE status_lists SET next_index = :n WHERE id = :id"),
            {"n": start, "id": row.id},
        )


def downgrade() -> None:
    op.drop_column("status_lists", "next_index")
