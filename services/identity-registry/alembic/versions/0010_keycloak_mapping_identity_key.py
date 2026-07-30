"""One Keycloak user maps to one DID — make it structural

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-30

`keycloak_mappings` was keyed on `did` alone, so nothing stopped two DIDs from
claiming the same Keycloak user. That is not a hypothetical: `GET /users/resolve`
derived a subject id whenever an **email** lookup missed, and an email is the one
identifier an IdP lets people change. So an ordinary email change produced a second
DID for the same human — with its own keypair, its own credentials and an empty
consent state — while the data plane resolved *both* DIDs to the same username. A
revocation against one left the other still disclosing.

The API now refuses the rebind (`POST /admin/keycloak/sync` answers 409) and
resolves by the cascade `id > username > email`. This constraint is what makes the
rule structural rather than a check somebody can forget to call.

**Duplicates are reported, not deleted.** A duplicate row here means two DIDs are
already in circulation for one person, and which of them holds the live consent is
not something a migration can decide — deleting either would silently drop consent
records or credentials. The upgrade fails with both DIDs named so an operator can
merge them deliberately. There is no merge operation by design: provenance is
append-only and consent rows key on a DID, so preventing the split is the whole
strategy.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "uq_keycloak_mappings_realm_user"


def upgrade() -> None:
    conn = op.get_bind()
    duplicates = conn.execute(
        sa.text(
            """
            SELECT keycloak_realm, keycloak_user_id, string_agg(did, ', ') AS dids
            FROM keycloak_mappings
            GROUP BY keycloak_realm, keycloak_user_id
            HAVING count(*) > 1
            """
        )
    ).fetchall()
    if duplicates:
        detail = "; ".join(
            f"{r.keycloak_realm}/{r.keycloak_user_id} -> {r.dids}" for r in duplicates
        )
        raise RuntimeError(
            "keycloak_mappings holds more than one DID for the same Keycloak user, "
            "so the uniqueness constraint cannot be applied. Each of these is one "
            "human with two dataspace identities whose consent states have "
            "diverged; an operator must decide which DID survives before this "
            f"migration can run. Duplicates: {detail}"
        )

    op.create_unique_constraint(
        _CONSTRAINT, "keycloak_mappings", ["keycloak_realm", "keycloak_user_id"]
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "keycloak_mappings", type_="unique")
