"""Delete the private keys held for natural persons

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-03

`D-49`: a natural person is a data rights holder, not a credential holder. They
present nothing and sign nothing — their `DataSubjectCredential` is signed by the
trust anchor and verified against the *anchor's* key
(`ds_auth.user_credentials.verify_user_vc_jwt`), and no caller has ever reached
`/sts` or a presentation query with a user DID.

So the keypair issuance generated for every onboarded person was **written and
never read**: custody with no purpose, which is an impersonation surface with no
upside. Issuance no longer creates one; this removes the ones already there.

The `dids` row stays. The DID must still **resolve** — it is the identifier
consent records, provenance events and `credentialSubject.id` all point at
(`personal-data.md` `D-22`) — and its document simply asserts no verification
method.

**Deletes rather than nulls the private half.** A `keys` row carrying only a
public key means "this key exists and belongs to that holder", which is true of
an enrolled participant and false of a subject who has no key at all. Leaving one
would state something untrue in the direction that matters: it would imply a
person controls a key they were never given.

No data migration risk: nothing reads these values, and there is no production
deployment.
"""
import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # Unlink first: `dids.key_id` is a foreign key onto the rows being removed.
    bind.execute(
        sa.text(
            "UPDATE dids SET key_id = NULL WHERE did_type = 'user' "
            "AND key_id IS NOT NULL"
        )
    )
    result = bind.execute(
        sa.text(
            "DELETE FROM keys WHERE owner_did IN "
            "(SELECT did FROM dids WHERE did_type = 'user')"
        )
    )
    if result.rowcount:
        print(f"  removed {result.rowcount} data-subject key(s) — D-49")


def downgrade() -> None:
    # There is nothing to restore: the keys were generated, never used, and are
    # gone. Re-creating them would mean minting new key material for people who
    # were never given any — inventing custody rather than restoring it.
    pass
