"""a member's own offer-scoped decision is re-keyed to the wildcard

``POST /consent/my/shares`` with an ``offer_id`` used to key the row on
``settings.consumer_participant_did`` — the party this connector negotiates
against when it *consumes*, which is a transfer fact and has nothing to do with
who a member discloses to. Every reader evaluates ``{consumer_id, "*"}`` and asks
about the offer's *controller*, so those rows were in neither set: a consent that
was genuinely recorded reported an audience of zero, and an export built on it
wrote a correctly-headed file with no rows (issue #33).

The route now writes ``consumer_id = "*"``, as ``POST /consent/admin/shares`` has
always done for the same offer. **This migration exists because the code change
alone would open a hole it did not have**: a member who granted before it and
withdraws after would write a wildcard revocation, and ``resolve_decision`` gives
an older *specific* grant precedence over the standing wildcard (D-15) — so the
withdrawal would be ignored for exactly the party the deployment negotiates with.

The filter is exact, not heuristic. ``set_subject_data_sharing`` is the only
writer of those two messages, and it writes them whenever no caller supplies one
— which no caller does: ``DataSharingSetRequest`` has no ``message`` field and
all three call sites pass none. Rows from ``POST /consent/request`` are genuine
per-party asks; they carry the requester's message or none, never these literals.

It also re-keys a per-party decision made with an explicit ``consumer_id``, since
nothing on the row distinguishes one. The only writer that sends one is
``libs/ds-e2e``, whose rows are dev fixtures rewritten on the next run.

``downgrade`` does not put them back. The old key is not recoverable from the row,
and inventing ``consumer_participant_did`` here would re-key rows that never held
it — the wrong direction to be wrong in, since it would make a standing decision
answer for one party only.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# The defaults `set_subject_data_sharing` writes when the caller supplies no
# message, which is always. Spelled out rather than imported: a migration
# describes the rows as they were written, and changing the literal in the
# service must not silently change which rows this statement selected.
_SUBJECT_DECISION_MESSAGES = (
    "Data owner enabled sharing.",
    "Data owner disabled sharing.",
)


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE consent_requests SET consumer_id = '*' "
            "WHERE offer_id IS NOT NULL "
            "AND consumer_id <> '*' "
            "AND message IN (:enabled, :disabled)"
        ).bindparams(
            enabled=_SUBJECT_DECISION_MESSAGES[0],
            disabled=_SUBJECT_DECISION_MESSAGES[1],
        )
    )


def downgrade() -> None:
    """Nothing to undo — see the module docstring."""
