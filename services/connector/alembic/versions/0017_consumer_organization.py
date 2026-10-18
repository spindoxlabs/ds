"""an agreement records the organisation its consumer presented

Plan `an-undeclared-row-policy-denies`, phase 4.3. With `OrganizationCredential`
a DEFAULT DCP scope, EDC stores the consumer's verified credential on the
provider's agreement (`ContractAgreement.claims`), and `NegotiationEventPublisher`
forwards its `organizationId` and `organizationType`. They are kept here because
`/internal/dataplane/authorize` emits the consumer's organization from them, and
the agreement — not today's credential — is what the consumer presented when it
agreed. Whether that credential is still live is re-checked per request.

Nullable and not backfilled: an agreement made before this has no presented
organisation, and inventing one would be a guess. Such an agreement reads as
"organisation not established", which serves no organization-bound rows.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contract_agreements",
        sa.Column("consumer_organization_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "contract_agreements",
        sa.Column("consumer_organization_type", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contract_agreements", "consumer_organization_type")
    op.drop_column("contract_agreements", "consumer_organization_id")
