"""who took the decision is a column, not an inference

``D-15c`` — a withdrawal may only be lifted by the authority that made it — needs
to know which authority wrote a row. Nothing on the row said so. The nearest
thing was ``legal_basis["source"]``, required and non-empty on
``POST /consent/admin/shares`` and ``None`` on the subject's own path, which is
an evidence field pressed into service as an access-control discriminator — and
the bare-dataset path stores no ``legal_basis`` at all, so for those rows it had
no answer to give (issue #34).

``decided_by`` is ``NOT NULL`` with a server default of ``subject``, and that
default is the whole migration for existing rows.

**Backfilling from ``legal_basis["source"]`` would be the wrong direction to be
wrong in.** It would mark historical service-provisioned rows ``service``, which
is more accurate — and it would mean a withdrawal this deployment cannot classify
is treated as a service's, so the next provisioning call lifts it silently, which
is the defect this column exists to close. Defaulting everything to ``subject``
over-protects a service's own past withdrawals: the cost is a ``409`` and an
explicit, evidenced override, paid by a service, and the benefit is that no
person's withdrawal is lifted by a row written before anyone was recording who
decided.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "consent_requests",
        sa.Column(
            "decided_by",
            sa.Text(),
            nullable=False,
            server_default="subject",
        ),
    )


def downgrade() -> None:
    op.drop_column("consent_requests", "decided_by")
