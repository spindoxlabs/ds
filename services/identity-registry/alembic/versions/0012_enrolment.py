"""Enrolment: a participant registers its own key, the anchor stops holding it

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-03

Three changes, one idea (`DID-09`): a participant's identity is something it
**proves**, not something the trust anchor **hands over**.

* `keys.private_jwk` becomes nullable. A trust anchor records the *public* key of
  every participant it has enrolled — it needs one to verify signatures and to
  bind an issued credential — and holds the private half of none of them. A row
  with `private_jwk IS NULL` is a key this instance knows about and cannot use,
  which is the correct relationship between an issuer and a holder. That column
  being NULL for every non-local DID is what `DID-12` asserts.

* `enrolment_tokens` carries the out-of-band authorization DCP's Credential
  Issuance Protocol deliberately leaves undefined, in the form the spec names:
  the `pre-authorized_code` claim of a Self-Issued ID token. Same primitive as
  `onboarding_invites`, one step later in the lifecycle, and for the same reason
  — the party presenting it has no credentials yet.

* `credential_requests` holds CIP request state, because the protocol is
  asynchronous: acknowledge on receipt, decide later, deliver by writing to the
  client's Credential Service. `GET /issuer/requests/{issuerPid}` has to read it
  from somewhere.

**No data migration.** Nothing is deployed to production, and widening a column
to nullable is compatible with every existing row. The downgrade cannot restore
NOT NULL honestly once a public-only key exists, so it refuses rather than
deleting the rows that would block it — losing a participant's registered public
key to a downgrade would mean nobody can verify that participant again.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

JSON_TYPE = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.alter_column(
        "keys",
        "private_jwk",
        existing_type=JSON_TYPE,
        nullable=True,
    )

    op.create_table(
        "enrolment_tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("owner_alias", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_did", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_enrolment_tokens_code_hash",
        "enrolment_tokens",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        "ix_enrolment_tokens_owner_alias", "enrolment_tokens", ["owner_alias"]
    )

    op.create_table(
        "credential_requests",
        sa.Column("issuer_pid", sa.String(), primary_key=True),
        sa.Column("holder_pid", sa.Text(), nullable=False),
        sa.Column("holder_did", sa.Text(), nullable=False),
        sa.Column("owner_alias", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="RECEIVED"
        ),
        sa.Column("requested", JSON_TYPE, nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_credential_requests_holder_did", "credential_requests", ["holder_did"]
    )


def downgrade() -> None:
    op.drop_index("ix_credential_requests_holder_did", "credential_requests")
    op.drop_table("credential_requests")
    op.drop_index("ix_enrolment_tokens_owner_alias", "enrolment_tokens")
    op.drop_index("ix_enrolment_tokens_code_hash", "enrolment_tokens")
    op.drop_table("enrolment_tokens")

    # Restoring NOT NULL would need every enrolled participant's private key,
    # which this registry deliberately does not have. Deleting those rows to make
    # the constraint satisfiable would delete the public keys their signatures
    # are verified against — a downgrade that silently un-trusts every
    # participant. Refuse instead, and say what to do.
    bind = op.get_bind()
    public_only = bind.execute(
        sa.text("SELECT count(*) FROM keys WHERE private_jwk IS NULL")
    ).scalar_one()
    if public_only:
        raise RuntimeError(
            f"{public_only} key(s) hold only a public JWK — participants that "
            "enrolled with their own keys. Downgrading past 0012 would require "
            "deleting them, which removes the keys their signatures are verified "
            "against. Migrate those participants back to anchor-held keys first, "
            "or drop the database."
        )
    op.alter_column(
        "keys",
        "private_jwk",
        existing_type=JSON_TYPE,
        nullable=False,
    )
