"""Drop organization_memberships.role — the column nothing ever read

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-06

`a-role-change-is-a-reissue`. The column was written by
`POST /admin/memberships` and `ir-cli membership add|import`, and **read by
nothing** — `GET /memberships/check` answers `member: true|false`, and no
policy, constraint function or report has ever consulted it. A column no code
reads is documentation, which is why the missing `PATCH /admin/memberships`
never hurt anybody: nothing downstream could tell whether the value was current.

Where the role lives now: a `communityRole` claim on the person's
`DataSubjectCredential`, changed by reissue
(`services/role_transition.py`). That makes it *checkable* — a sharing offer can
say `admitted_by: [{credential_claim: {claim: communityRole, value: prosumer}}]`
and the connector evaluates it — and it makes it *current*, because a superseded
credential is suspended and the register says so.

**Two places holding the same fact, one of them unreadable and stale, is the
state that makes people leave columns behind for years.** So it goes.

No data is lost that anything could have used. Deployments that want the
community's own record of what was declared at join time have it in whatever
produced the import file; ds is not that record.
"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text("SELECT count(*) FROM organization_memberships WHERE role IS NOT NULL")
    ).scalar_one()
    if populated:
        # Printed, not silently dropped. The value was never read, but a
        # migration that removes populated rows without saying how many is one
        # nobody can audit afterwards.
        print(
            f"  dropping organization_memberships.role — {populated} row(s) carried a value"
        )
    op.drop_column("organization_memberships", "role")


def downgrade() -> None:
    # Restores the column, not its contents: the values are gone and nothing
    # read them. A nullable column is exactly the state a fresh deployment of
    # the previous schema would be in.
    op.add_column(
        "organization_memberships",
        sa.Column("role", sa.String(length=32), nullable=True),
    )
