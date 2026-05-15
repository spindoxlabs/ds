"""initial provenance schema

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "prov_nodes",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("iri", sa.Text(), nullable=False),
        sa.Column("node_type", sa.String(length=16), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("energy_type", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_meta", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("iri"),
    )
    op.create_table(
        "prov_relations",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.String(), sa.ForeignKey("prov_nodes.id"), nullable=False),
        sa.Column("object_id", sa.String(), sa.ForeignKey("prov_nodes.id"), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("extra", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("relation_type", "subject_id", "object_id"),
    )
    op.create_table(
        "domain_events",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("prov_node_id", sa.String(), sa.ForeignKey("prov_nodes.id"), nullable=True),
        sa.Column("agreement_id", sa.Text(), nullable=True),
        sa.Column("data_product_id", sa.Text(), nullable=True),
        sa.Column("provider_did", sa.Text(), nullable=True),
        sa.Column("consumer_did", sa.Text(), nullable=True),
        sa.Column("processed", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("event_id"),
    )
    op.create_table(
        "access_log",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("consumer_id", sa.Text(), nullable=False),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("agreement_id", sa.Text(), nullable=True),
        sa.Column("transfer_id", sa.Text(), nullable=True),
        sa.Column("query_params", json_type, nullable=True),
        sa.Column("subject_ids", json_type, nullable=True),
        sa.Column("rows_returned", sa.Integer(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("provider_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("access_log")
    op.drop_table("domain_events")
    op.drop_table("prov_relations")
    op.drop_table("prov_nodes")
