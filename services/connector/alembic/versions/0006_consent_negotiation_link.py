"""consent rows link to the negotiation they are blocking

An ask raised by the EDC pending guard exists *because* a contract negotiation
is parked waiting for it, so the row has to name that negotiation — otherwise
nothing can resume the negotiation when the subject answers, and no operator
view can say which request a person's decision is holding up.

Two identifiers, because the two sides of a DSP negotiation use different ones:

- ``negotiation_id`` — this connector's own id. Clearing ``pending`` is a
  control-plane-local operation, so only this id can drive the resume.
- ``correlation_id`` — the counterparty's id for the same negotiation. It is the
  only handle the consumer holds, so it is the key ``GET /consent/pending``
  answers on. Keeping it separate is what lets a participant ask about its own
  negotiation without ever learning a provider-side identifier.

Both are indexed and nullable: every row written by a subject through
``/consent/my/*`` or provisioned at onboarding has no negotiation behind it.

``negotiation_closed_at`` records that the negotiation is over. It is what lets
the TTL sweep terminate: "this negotiation has no pending and no granted asks"
is a property of the consent rows that, once true, stays true forever — so
without a marker the sweep would re-terminate the same dead negotiation on every
pass, and a single failed termination could never be told apart from a
never-attempted one.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("consent_requests", sa.Column("negotiation_id", sa.Text(), nullable=True))
    op.add_column("consent_requests", sa.Column("correlation_id", sa.Text(), nullable=True))
    op.add_column(
        "consent_requests",
        sa.Column("negotiation_closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_consent_requests_negotiation_id", "consent_requests", ["negotiation_id"]
    )
    op.create_index(
        "ix_consent_requests_correlation_id", "consent_requests", ["correlation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_consent_requests_correlation_id", table_name="consent_requests")
    op.drop_index("ix_consent_requests_negotiation_id", table_name="consent_requests")
    op.drop_column("consent_requests", "negotiation_closed_at")
    op.drop_column("consent_requests", "correlation_id")
    op.drop_column("consent_requests", "negotiation_id")
