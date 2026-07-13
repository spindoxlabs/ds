"""Initial schema — keys, dids, credentials, participants, keycloak_mappings, status_lists

Revision ID: 0001
Revises:
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "keys",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_did", sa.Text(), nullable=False, index=True),
        sa.Column("algorithm", sa.String(16), nullable=False, server_default="ES256"),
        sa.Column("private_jwk", postgresql.JSONB(), nullable=False),
        sa.Column("public_jwk", postgresql.JSONB(), nullable=False),
        sa.Column("kid", sa.String(), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "dids",
        sa.Column("did", sa.Text(), primary_key=True),
        sa.Column("did_type", sa.String(16), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("service_endpoints", postgresql.JSONB(), nullable=True),
        sa.Column("key_id", sa.String(), sa.ForeignKey("keys.id"), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "credentials",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("credential_type", sa.String(64), nullable=False),
        sa.Column("issuer_did", sa.Text(), nullable=False),
        sa.Column(
            "subject_did", sa.Text(), sa.ForeignKey("dids.did"), nullable=False
        ),
        sa.Column("credential_json", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("status_list_index", sa.Integer(), nullable=True),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "participants",
        sa.Column(
            "did", sa.Text(), sa.ForeignKey("dids.did"), primary_key=True
        ),
        sa.Column("dsp_address", sa.Text(), nullable=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "allowed_scopes",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "keycloak_mappings",
        sa.Column(
            "did", sa.Text(), sa.ForeignKey("dids.did"), primary_key=True
        ),
        sa.Column("keycloak_realm", sa.Text(), nullable=False),
        sa.Column("keycloak_user_id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "status_lists",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "purpose", sa.String(32), nullable=False, server_default="revocation"
        ),
        sa.Column("bitstring", sa.LargeBinary(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("status_lists")
    op.drop_table("keycloak_mappings")
    op.drop_table("participants")
    op.drop_table("credentials")
    op.drop_table("dids")
    op.drop_table("keys")
