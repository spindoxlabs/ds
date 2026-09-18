"""`controller` on a consent row is the recipient

Plan `every-personal-dataset-asks-for-a-local-consent`, step 1. The column named
one of the three things `recipients.controller` meant, and the one it actually
held was the **recipient** — the DSP consumer, ODRL 2.2's `odrl:recipient`, the
DSSC data recipient. It is renamed to say so, with `controller_role` →
`recipient_role` beside it.

**A rename, not a re-key.** Every value is carried across unchanged, and `D-11`'s
consent key — (subject, purpose, recipient-role) — is the same tuple it was, so
no stored consent changes meaning and nobody is asked again. The offer hash is
unaffected for the same reason: `user_visible_facts` keeps the payload key
`controller`, because renaming a field renamed nothing a person read.

Downgrade renames back. Both directions are lossless.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-17
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("consent_requests") as batch:
        batch.alter_column("controller", new_column_name="recipient")
        batch.alter_column("controller_role", new_column_name="recipient_role")


def downgrade() -> None:
    with op.batch_alter_table("consent_requests") as batch:
        batch.alter_column("recipient", new_column_name="controller")
        batch.alter_column("recipient_role", new_column_name="controller_role")
