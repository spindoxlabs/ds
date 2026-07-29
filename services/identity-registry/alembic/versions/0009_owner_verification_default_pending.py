"""Owner verification: default status 'pending', require evidence for 'verified'

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-29

An owner's `status` defaulted to 'verified' with `verified_by` null — a row that
read as verified while nothing verified it. That was harmless for a hand-seeded
dev owner and unsafe the moment a service account could reach a construction
path: it lands the owner in the consent circle for free, the safe direction for
the wrong reason. Flip the default to 'pending' and make "verified with no
evidence" unrepresentable with a CHECK constraint.

Any pre-existing default-verified row (verified, `verified_by` null) is backfilled
to a greppable sentinel rather than dropped to pending: dropping status would
silently change access decisions, whereas the sentinel keeps the row's meaning
and makes the previously-invisible defaulting auditable. At the time of writing
nothing is deployed outside dev, so this is expected to touch no rows — confirm
by grepping `verified_by = 'legacy:default-verified'` per environment.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CK = "ck_owner_verified_has_evidence"


def upgrade() -> None:
    # Backfill any invisible default-verified rows so the constraint can hold
    # without dropping a status something downstream may already rely on.
    op.execute(
        """
        UPDATE owners
           SET verified_by = 'legacy:default-verified',
               evidence_ref = COALESCE(evidence_ref, 'legacy:default-verified')
         WHERE status = 'verified' AND verified_by IS NULL
        """
    )
    op.alter_column("owners", "status", server_default="pending")
    op.create_check_constraint(
        _CK,
        "owners",
        "status <> 'verified' OR verified_by IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(_CK, "owners", type_="check")
    op.alter_column("owners", "status", server_default="verified")
