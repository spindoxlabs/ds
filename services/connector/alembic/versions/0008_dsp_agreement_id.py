"""an agreement has two identifiers, and only one of them crosses

EDC 0.16 keeps a contract agreement under **two** ids, and this was found the
hard way — a data-plane request naming a perfectly valid agreement was refused
as `agreement_unknown`:

- ``ContractAgreement.getId()`` — this runtime's own entity id. The provider and
  the consumer generate their own, so for one negotiation they hold *different*
  values. Verified live: provider `1be47fa6…`, consumer `c6017794…`.
- ``ContractAgreement.getAgreementId()`` — the shared DSP id, identical on both
  sides (`dd1349d9…` for that same pair).

A counterparty can only name the shared one. `POST /internal/dataplane/authorize`
therefore resolves on either, and this column is what makes the shared id
findable.

Nullable and backfilled from nothing: rows written before this existed record
only the local id, and inventing a shared id for them would be a guess. They
resolve by local id as they always did.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contract_agreements", sa.Column("dsp_agreement_id", sa.Text(), nullable=True)
    )
    op.create_index(
        "ix_contract_agreements_dsp_agreement_id",
        "contract_agreements",
        ["dsp_agreement_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_contract_agreements_dsp_agreement_id", table_name="contract_agreements"
    )
    op.drop_column("contract_agreements", "dsp_agreement_id")
