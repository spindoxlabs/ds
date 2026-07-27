"""an access request records the intent it was made with

The row already recorded *what* was asked for — asset, offer, assigner, and the
three EDC identifiers. It recorded nothing about *why*, and the offer's policy
cannot supply that: a multi-purpose dataset is published as one ``odrl:purpose``
constraint with ``odrl:isAnyOf`` over every permitted purpose, so the agreement
says "any of these three" and says so forever.

Nor can the gap be closed at the protocol layer. EDC resolves the contract
policy from the offer id against the provider's own contract definition and
discards the policy body the consumer sent
(``ContractNegotiationProtocolServiceImpl.notifyRequested``), so a consumer
cannot narrow what it is agreeing to. The declaration is therefore recorded
here, consumer-side, as what it actually is: a statement of intent, checked
against the offer so it can never claim more than the offer permits.

All four columns are nullable. Declaring is optional, and a request that
declared nothing must read as undeclared — backfilling it with the offer's
purpose set would put a statement in the record that nobody made.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "consumer_access_requests", sa.Column("declared_purpose", sa.JSON(), nullable=True)
    )
    op.add_column(
        "consumer_access_requests",
        sa.Column("declared_from", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "consumer_access_requests",
        sa.Column("declared_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "consumer_access_requests", sa.Column("justification_ref", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("consumer_access_requests", "justification_ref")
    op.drop_column("consumer_access_requests", "declared_until")
    op.drop_column("consumer_access_requests", "declared_from")
    op.drop_column("consumer_access_requests", "declared_purpose")
