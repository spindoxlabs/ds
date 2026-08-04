"""Conformity assessment — is a *participant* still what the rulebook requires?

`DSSC-TRF-02`, `-03`, `-04`. The blueprint asks that the rulebook support
**automated conformity assessment** and that a compliance verification service
check participants and services against it. Until now this did not exist:
`task compliance:validate` checks a **governance file** against the ODRL profile,
which is a different question about a different artefact, and the similar name
was doing real harm.

## What conformity is, and what it is not

Onboarding decides whether a party *may* join. Conformity asks whether one still
*qualifies* — and the two answers drift apart on their own, without anybody
acting: a credential expires, an agreement version is superseded, a DID document
stops resolving because a host moved. **Nothing in this file changes state.** It
reads what is already recorded and reports; suspension is a decision, and a
decision an automated check makes for you is a decision nobody made.

## Why the criteria are a file

The rules on `participation.md` are prose. A check needs them as data, and the
data has to be a *deployment's* to state — which credential types, which
agreement, whether a DSP endpoint is required — because a dataspace that admits
observers on different terms than providers is a normal dataspace, not a broken
one. `seed/conformity.dev.yaml` is this repository's dev fixture, and it is a
fixture rather than a baseline for the same reason a producer's `governance.yaml`
is.

## Everything unprovable is non-conformant

A participant whose owner cannot be resolved, whose credential has no expiry this
registry recorded, whose DID document does not resolve — each is reported as a
failure with the reason, never skipped. A conformity check that silently drops
the rules it cannot evaluate reports conformity it did not establish, which is
the one output worse than "unknown".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import AgreementAcceptance, Credential, Owner, Participant

log = logging.getLogger(__name__)

#: Where the dev fixture lives when nothing else is configured.
DEFAULT_CRITERIA_PATH = "seed/conformity.dev.yaml"

CONFORMANT = "conformant"
NON_CONFORMANT = "non-conformant"


class ConformityError(Exception):
    """The criteria could not be read. Never *a participant failing* — that is a
    finding, not an error, and the difference matters to the exit code."""


@dataclass(frozen=True, slots=True)
class Criteria:
    """The rulebook, as data.

    `applies_to` narrows a rule set to participants holding a role, so a
    dataspace can require a resolvable DSP endpoint of a provider and not of a
    consumer — which is the normal case, not an exception.
    """

    name: str
    required_credentials: tuple[str, ...] = ()
    required_agreement: str | None = None
    required_agreement_version: str | None = None
    require_dsp_address: bool = False
    require_verified_owner: bool = True
    applies_to: tuple[str, ...] = ()

    def covers(self, roles: list[str]) -> bool:
        return not self.applies_to or any(r in self.applies_to for r in roles)


@dataclass(slots=True)
class Finding:
    rule: str
    ok: bool
    detail: str


@dataclass(slots=True)
class Assessment:
    did: str
    roles: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def status(self) -> str:
        return CONFORMANT if all(f.ok for f in self.findings) else NON_CONFORMANT

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if not f.ok]


def load_criteria(path: str | Path) -> list[Criteria]:
    """Read the criteria file, or say precisely why it could not be read."""
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text()) or {}
    except FileNotFoundError as exc:
        raise ConformityError(
            f"no conformity criteria at {p}. A deployment states its own; "
            f"{DEFAULT_CRITERIA_PATH} is this repository's dev fixture."
        ) from exc
    except yaml.YAMLError as exc:
        raise ConformityError(f"{p} is not valid YAML: {exc}") from exc

    entries = raw.get("criteria")
    if not isinstance(entries, list) or not entries:
        raise ConformityError(
            f"{p} declares no `criteria`. An empty rule set would report every "
            "participant conformant, which is the answer nobody asked for."
        )

    out: list[Criteria] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("name"):
            raise ConformityError(f"{p}: every criterion needs a `name`")
        out.append(
            Criteria(
                name=str(entry["name"]),
                required_credentials=tuple(entry.get("required_credentials") or ()),
                required_agreement=entry.get("required_agreement"),
                required_agreement_version=entry.get("required_agreement_version"),
                require_dsp_address=bool(entry.get("require_dsp_address", False)),
                require_verified_owner=bool(entry.get("require_verified_owner", True)),
                applies_to=tuple(entry.get("applies_to") or ()),
            )
        )
    return out


def _expired(expires_at: datetime | None, now: datetime) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


async def _owner_for(db: AsyncSession, did: str) -> Owner | None:
    return (
        await db.execute(select(Owner).where(Owner.did == did))
    ).scalar_one_or_none()


async def assess(
    db: AsyncSession,
    settings: Settings,
    participant: Participant,
    criteria: list[Criteria],
) -> Assessment:
    """One participant against every criterion that covers it."""
    now = datetime.now(UTC)
    roles = list(participant.roles or [])
    report = Assessment(did=participant.did, roles=roles)

    applicable = [c for c in criteria if c.covers(roles)]
    if not applicable:
        # Not silence: a participant no rule covers has been admitted on terms
        # nobody wrote down, and that is a finding about the *criteria*.
        report.findings.append(
            Finding(
                "criteria",
                False,
                f"no criterion covers roles {roles or ['(none)']} — this "
                "participant is held to no stated standard",
            )
        )
        return report

    if not participant.active:
        report.findings.append(
            Finding("active", False, "the participant is deactivated")
        )

    owner = await _owner_for(db, participant.did)
    credentials = (
        await db.execute(
            select(Credential).where(
                Credential.subject_did == participant.did,
                Credential.status == "active",
            )
        )
    ).scalars().all()
    held = {
        c.credential_type
        for c in credentials
        if not _expired(c.expires_at, now)
    }

    for c in applicable:
        for want in c.required_credentials:
            if want in held:
                report.findings.append(
                    Finding(f"credential:{want}", True, "held, active and unexpired")
                )
                continue
            expired_one = any(
                cr.credential_type == want and _expired(cr.expires_at, now)
                for cr in credentials
            )
            report.findings.append(
                Finding(
                    f"credential:{want}",
                    False,
                    "expired" if expired_one else "not held",
                )
            )

        if c.require_verified_owner:
            if owner is None:
                report.findings.append(
                    Finding(
                        "owner",
                        False,
                        "no organisation resolves to this DID — the participant "
                        "speaks for nobody the registry knows",
                    )
                )
            elif owner.status != "verified":
                report.findings.append(
                    Finding("owner", False, f"organisation status is {owner.status!r}")
                )
            else:
                report.findings.append(
                    Finding("owner", True, f"{owner.id} is verified")
                )

        if c.required_agreement:
            if owner is None:
                report.findings.append(
                    Finding(
                        f"agreement:{c.required_agreement}",
                        False,
                        "no organisation to have accepted it",
                    )
                )
            else:
                accepted = (
                    await db.execute(
                        select(AgreementAcceptance).where(
                            AgreementAcceptance.owner_alias == owner.id,
                            AgreementAcceptance.agreement_id == c.required_agreement,
                        )
                    )
                ).scalars().all()
                versions = {a.agreement_version for a in accepted}
                want_version = c.required_agreement_version
                if not versions:
                    report.findings.append(
                        Finding(
                            f"agreement:{c.required_agreement}",
                            False,
                            "never accepted",
                        )
                    )
                elif want_version and want_version not in versions:
                    # **A superseded acceptance is a finding, not a pass.** This
                    # is the drift the whole check exists for: nobody did
                    # anything wrong, and the participant is no longer covered by
                    # the version in force.
                    report.findings.append(
                        Finding(
                            f"agreement:{c.required_agreement}",
                            False,
                            f"accepted {sorted(versions)}, required {want_version}",
                        )
                    )
                else:
                    report.findings.append(
                        Finding(
                            f"agreement:{c.required_agreement}",
                            True,
                            f"accepted at {sorted(versions)[-1]}",
                        )
                    )

        if c.require_dsp_address:
            if participant.dsp_address:
                report.findings.append(
                    Finding("dsp", True, participant.dsp_address)
                )
            else:
                report.findings.append(
                    Finding(
                        "dsp",
                        False,
                        "publishes no DSP address — a provider nothing can "
                        "negotiate with is not participating",
                    )
                )

    return report


async def assess_all(
    db: AsyncSession, settings: Settings, criteria: list[Criteria]
) -> list[Assessment]:
    """Every registered participant, **including deactivated ones**.

    A deactivated participant is exactly the one an auditor asks about, and
    filtering it out here would make the report answer a narrower question than
    its name.
    """
    rows = (
        await db.execute(select(Participant).order_by(Participant.did))
    ).scalars().all()
    return [await assess(db, settings, p, criteria) for p in rows]


def render(assessments: list[Assessment], settings: Settings) -> dict[str, Any]:
    """The published report.

    Self-describing for the same reason the trust list is: DSSC names no format,
    so a reader gets the requirement ids it answers and the dataspace it is
    about.
    """
    return {
        "type": "ConformityReport",
        "dataspace": settings.dataspace_uri,
        "conformsTo": ["DSSC-TRF-02", "DSSC-TRF-03", "DSSC-TRF-04"],
        "assessedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "participants": len(assessments),
            "conformant": sum(1 for a in assessments if a.status == CONFORMANT),
            "nonConformant": sum(
                1 for a in assessments if a.status == NON_CONFORMANT
            ),
        },
        "participants": [
            {
                "did": a.did,
                "roles": a.roles,
                "status": a.status,
                "findings": [
                    {"rule": f.rule, "ok": f.ok, "detail": f.detail}
                    for f in a.findings
                ],
            }
            for a in assessments
        ],
    }
