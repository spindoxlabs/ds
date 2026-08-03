"""Key custody — what this instance can sign as, checked rather than asserted.

`D-47` and `D-51` make one claim: **an instance holds the private key of its own
DID and of nothing else.** Everything else in this pass is machinery for making
that true; this is the thing that says whether it *is*.

## Why it is a sweep and not a test

A test asserts what someone remembered to write down. This reads the rows that
exist, in the process that serves them, at startup — so it fails on a key nobody
meant to create: a migration that back-filled, a restored dump from before the
split, a `POST` that mints again because someone re-added a convenience. That is
the `T-4` shape, and it is the fourth instance of it here after
`test_settings_are_read.py`, `PolicyRegistrationTest` and `roles.audit`.

## It reads SQL, deliberately

`keys.private_jwk IS NULL` — not `key.private_jwk is None` through the ORM.
Until migration `0014` the two disagreed: SQLAlchemy wrote Python `None` as the
JSON value `'null'`, so `IS NULL` was **False for every enrolled participant**
while the ORM said `None`. SQLite deserialises `'null'` back to `None`, so the
unit suite agreed with the code and Postgres did not — 445 tests passing against
a claim that was false in the only database that runs.

An invariant checked through the layer that got it wrong is not an invariant.

## Natural persons are a **named** exception, not a silent one

The anchor still generates and holds a keypair for every data subject
(`admin.py`'s data-subject issuance). That is `D-49`/`DID-11`'s subject and it is
deferred, not overlooked — so those keys are reported every start, by DID, as a
declared deviation. The moment `DID-11` lands they disappear and this reports
nothing; if they *grow*, that is visible.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HeldKey:
    """A DID this instance holds a usable private key for."""

    did: str
    did_type: str
    kid: str


@dataclass(frozen=True, slots=True)
class CustodyReport:
    own: list[HeldKey]
    #: Natural persons — the declared `D-49` deviation.
    subjects: list[HeldKey]
    #: **Nobody else's key should be here.** Anything in this list is a
    #: participant whose identity this instance could speak as.
    foreign: list[HeldKey]

    @property
    def ok(self) -> bool:
        return not self.foreign

    def summary(self) -> str:
        return (
            f"own={len(self.own)} subjects={len(self.subjects)} "
            f"foreign={len(self.foreign)}"
        )


async def audit_custody(db: AsyncSession, settings: Settings) -> CustodyReport:
    """Every private key this instance can actually sign with, classified.

    ``active`` is not part of the question. A rotated-out key still decrypts and
    still signs; "we stopped using it" is not "we cannot use it".
    """
    rows = (
        await db.execute(
            text(
                "SELECT k.owner_did, COALESCE(d.did_type, 'unknown') AS did_type, "
                "k.kid FROM keys k "
                "LEFT JOIN dids d ON d.did = k.owner_did "
                "WHERE k.private_jwk IS NOT NULL "
                "ORDER BY k.owner_did"
            )
        )
    ).all()

    own: list[HeldKey] = []
    subjects: list[HeldKey] = []
    foreign: list[HeldKey] = []
    for owner_did, did_type, kid in rows:
        held = HeldKey(did=owner_did, did_type=did_type, kid=kid)
        if settings.is_own_did(owner_did):
            own.append(held)
        elif did_type == "user":
            subjects.append(held)
        else:
            foreign.append(held)

    return CustodyReport(own=own, subjects=subjects, foreign=foreign)


def describe(report: CustodyReport, settings: Settings) -> list[str]:
    """Operator-facing lines. Empty when there is nothing worth saying."""
    lines: list[str] = []
    if report.subjects:
        lines.append(
            f"{len(report.subjects)} data-subject key(s) held — the declared "
            "D-49 deviation (a natural person has no wallet yet; DID-11 removes "
            "these): " + ", ".join(k.did for k in report.subjects)
        )
    for key in report.foreign:
        lines.append(
            f"PRIVATE KEY HELD FOR {key.did} ({key.did_type}) — this instance "
            f"can sign as that participant. kid={key.kid}"
        )
    return lines


#: What an operator does about a foreign key. Stated once, used by the guard and
#: by the CLI, because the two must not give different advice.
REMEDIATION = (
    "Delete the key row and have that participant enrol again — it generates "
    "its own key and this registry records only the public half "
    "(`ir-cli org enrolment-token --alias <owner>`, then `ir-cli participant "
    "init --code <code>` on their instance). A private key here means this "
    "instance can speak as them, which is the deviation D-47 and D-51 exist to "
    "end."
)
