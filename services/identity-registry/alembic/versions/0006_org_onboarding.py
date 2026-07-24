"""Organisation onboarding: Owner Gaia-X columns, applications, agreements

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb():
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    # ── Owner: Gaia-X-shaped legal identity + verification lifecycle ──
    op.add_column("owners", sa.Column("registration_number", sa.Text(), nullable=True))
    op.add_column("owners", sa.Column("registration_type", sa.String(16), nullable=True))
    op.add_column("owners", sa.Column("hq_country_code", sa.String(8), nullable=True))
    op.add_column("owners", sa.Column("legal_country_code", sa.String(8), nullable=True))
    op.add_column("owners", sa.Column("parent_organizations", _jsonb(), nullable=True))
    op.add_column("owners", sa.Column("sub_organizations", _jsonb(), nullable=True))
    op.add_column(
        "owners",
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="verified"
        ),
    )
    op.add_column("owners", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("owners", sa.Column("verified_by", sa.Text(), nullable=True))
    op.add_column("owners", sa.Column("evidence_ref", sa.Text(), nullable=True))
    op.add_column("owners", sa.Column("agreement_id", sa.Text(), nullable=True))
    op.add_column("owners", sa.Column("agreement_version", sa.String(32), nullable=True))
    op.add_column(
        "owners", sa.Column("agreement_accepted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("owners", sa.Column("agreement_capacity", sa.String(32), nullable=True))

    # ── Organisation applications (pre-verification) ──────────────────
    op.create_table(
        "organization_applications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("alias", sa.String(), nullable=False),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("registration_number", sa.Text(), nullable=True),
        sa.Column("registration_type", sa.String(16), nullable=True),
        sa.Column("hq_country_code", sa.String(8), nullable=True),
        sa.Column("legal_country_code", sa.String(8), nullable=True),
        sa.Column("parent_organizations", _jsonb(), nullable=True),
        sa.Column("sub_organizations", _jsonb(), nullable=True),
        sa.Column("roles", _jsonb(), nullable=False, server_default="[]"),
        sa.Column("did", sa.Text(), nullable=True),
        sa.Column("dsp_address", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("evidence_ref", sa.Text(), nullable=True),
        sa.Column("verified_by", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_organization_applications_alias",
        "organization_applications",
        ["alias"],
    )

    # ── Agreement definitions ─────────────────────────────────────────
    op.create_table(
        "agreements",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("applies_to", _jsonb(), nullable=False, server_default="[]"),
        sa.Column("capacity", sa.String(32), nullable=False),
        sa.Column("texts", _jsonb(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", "version"),
    )

    # ── Agreement acceptances ─────────────────────────────────────────
    op.create_table(
        "agreement_acceptances",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_alias", sa.String(), nullable=False),
        sa.Column("agreement_id", sa.String(), nullable=False),
        sa.Column("agreement_version", sa.String(32), nullable=False),
        sa.Column("capacity", sa.String(32), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("accepted_by", sa.Text(), nullable=True),
        sa.Column(
            "accepted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_alias",
            "agreement_id",
            "agreement_version",
            name="uq_agreement_acceptance",
        ),
    )
    op.create_index(
        "ix_agreement_acceptances_owner_alias",
        "agreement_acceptances",
        ["owner_alias"],
    )


def downgrade() -> None:
    op.drop_index("ix_agreement_acceptances_owner_alias", table_name="agreement_acceptances")
    op.drop_table("agreement_acceptances")
    op.drop_table("agreements")
    op.drop_index("ix_organization_applications_alias", table_name="organization_applications")
    op.drop_table("organization_applications")
    for col in (
        "agreement_capacity",
        "agreement_accepted_at",
        "agreement_version",
        "agreement_id",
        "evidence_ref",
        "verified_by",
        "verified_at",
        "status",
        "sub_organizations",
        "parent_organizations",
        "legal_country_code",
        "hq_country_code",
        "registration_type",
        "registration_number",
    ):
        op.drop_column("owners", col)
