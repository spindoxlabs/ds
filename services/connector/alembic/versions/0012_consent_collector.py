"""a collector registers consent at the holder

Plan `a-collector-registers-consent-at-the-holder`. Three changes to
``consent_requests``:

- ``collector`` — the organisation (DID) whose token registered the decision;
- ``subject_keys`` — the subject's typed data keys at this holder, sent with the
  registration and matched by the data plane;
- ``decided_by`` gains ``collector``, and the column's value space is now a
  constraint rather than a convention: ``subject``, ``service``, ``operator``,
  ``collector``. Every row written before carries one of the first three — the
  application refused anything else — so the constraint validates as it lands.

Downgrade maps ``collector`` to ``service``: the previous code lets any non-subject
authority lift a non-subject withdrawal, which is what a collector's own
withdrawal was closest to. A relayed member decision is already ``subject``.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

DECIDERS = ("subject", "service", "operator", "collector")


def upgrade() -> None:
    with op.batch_alter_table("consent_requests") as batch:
        batch.add_column(sa.Column("collector", sa.Text(), nullable=True))
        batch.add_column(sa.Column("subject_keys", sa.JSON(), nullable=True))
        batch.create_check_constraint(
            "ck_consent_decided_by",
            "decided_by IN ({})".format(", ".join(f"'{d}'" for d in DECIDERS)),
        )


def downgrade() -> None:
    op.execute(
        "UPDATE consent_requests SET decided_by = 'service' "
        "WHERE decided_by = 'collector'"
    )
    with op.batch_alter_table("consent_requests") as batch:
        batch.drop_constraint("ck_consent_decided_by", type_="check")
        batch.drop_column("subject_keys")
        batch.drop_column("collector")
