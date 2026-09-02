"""Organisation onboarding operations, shared by the API and the CLI.

Block D §5. The gates (§5.6) are enforced *here*, not in documentation, so the
portal (which calls the HTTP API) and ``ir-cli org`` (which calls the DB
directly) behave identically — the CLI is the reference implementation and both
funnel through these functions.

No PII is stored or emitted: agreement acceptance is proved by ``text_sha256``,
never the prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import (
    Agreement,
    AgreementAcceptance,
    Credential,
    Did,
    Key,
    OrganizationApplication,
    Owner,
    Participant,
)
from .crypto import (
    decrypt_private_jwk,
    generate_credential_id,
    require_private_jwk,
)
from .status_list import (
    SUSPENSION_LIST_ID,
    allocate_suspendable_index,
    revoke_status_list_index,
    suspend_status_list_index,
    unsuspend_status_list_index,
)
from .vc import build_organization_credential, sign_credential


class OrgOnboardingError(Exception):
    """A gate or precondition failed. ``status_code`` maps to the HTTP status
    the API layer should return; the CLI renders ``message`` and exits."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── Status-list + trust-anchor helpers ────────────────────────────


async def get_trust_anchor_key(db: AsyncSession, settings: Settings) -> Key:
    ta_did = f"did:web:{settings.trust_anchor_domain}"
    result = await db.execute(
        select(Key).where(Key.owner_did == ta_did, Key.active.is_(True))
    )
    key = result.scalar_one_or_none()
    if not key:
        raise OrgOnboardingError(
            "Trust anchor not bootstrapped. Run: ir-cli bootstrap", status_code=500
        )
    return key


# ── Owner resolution ──────────────────────────────────────────────


async def resolve_owner(db: AsyncSession, alias: str) -> Owner | None:
    result = await db.execute(select(Owner).where(Owner.id == alias))
    owner = result.scalar_one_or_none()
    if owner:
        return owner
    result = await db.execute(select(Owner))
    for o in result.scalars().all():
        if alias in (o.aliases or []):
            return o
    return None


# ── Application intake (upsert by alias) ──────────────────────────

#: What an ``OrganizationCredential`` asserts about the organisation. Changing
#: one of these after verification is a re-verification, not an edit — the
#: issued credential says the old value. Everything else on an application
#: (roles, dsp_address, notes) is operational and may change freely.
LEGAL_IDENTITY_FIELDS = (
    "legal_name",
    "registration_number",
    "registration_type",
    "hq_country_code",
    "legal_country_code",
    "parent_organizations",
    "sub_organizations",
    "did",
)

_APPLICATION_FIELDS = LEGAL_IDENTITY_FIELDS + ("roles", "dsp_address", "notes")


async def resolve_application(
    db: AsyncSession, alias: str
) -> OrganizationApplication | None:
    result = await db.execute(
        select(OrganizationApplication)
        .where(OrganizationApplication.alias == alias)
        .order_by(OrganizationApplication.created_at.desc())
    )
    return result.scalars().first()


async def upsert_application(
    db: AsyncSession, alias: str, fields: dict, defaults: dict | None = None
) -> tuple[OrganizationApplication, bool]:
    """Create or update the application for ``alias``. Returns (row, created).

    An alias identifies an organisation, so a second registration of the same
    one is the same application — inserting another row instead gave whichever
    query ran first a different answer about a single organisation's state.
    Both the HTTP intake and ``ir-cli org register``/``import`` come through
    here, so the two cannot disagree about what a re-registration means.

    ``fields`` is what the caller declared; verification state
    (``status``/``verified_*``/``evidence_ref``) is never written here — a
    re-registration must not silently re-open or re-assert a completed check.
    ``defaults`` is applied **only on create**, so a caller that sends a partial
    body still gets a complete new row without those same omissions reading as
    "clear this" on an update.
    """
    app = await resolve_application(db, alias)
    created = app is None
    if app is None:
        app = OrganizationApplication(
            alias=alias, legal_name=fields.get("legal_name") or alias
        )
        db.add(app)
        for name in _APPLICATION_FIELDS:
            if defaults and name in defaults:
                setattr(app, name, defaults[name])
    elif app.status == "verified":
        changed = [
            name
            for name in LEGAL_IDENTITY_FIELDS
            if name in fields and getattr(app, name) != fields[name]
        ]
        if changed:
            raise OrgOnboardingError(
                f"Application {alias!r} is already verified; "
                f"{', '.join(sorted(changed))} cannot be changed without "
                "re-verification (the issued credential asserts the old value)",
                status_code=409,
            )

    for name in _APPLICATION_FIELDS:
        if name in fields:
            setattr(app, name, fields[name])
    app.updated_at = datetime.now(UTC)
    await db.flush()
    return app, created


# ── Promotion: application → Owner ────────────────────────────────


async def upsert_owner_from_application(
    db: AsyncSession,
    app: OrganizationApplication,
    *,
    verified_by: str | None = None,
) -> Owner:
    """Promote a verified application's legal identity into an ``Owner`` row.

    Idempotent: re-running updates the existing owner. Sets ``status=verified``.
    """
    now = datetime.now(UTC)
    result = await db.execute(select(Owner).where(Owner.id == app.alias))
    owner = result.scalar_one_or_none()

    if owner is None:
        owner = Owner(id=app.alias, type="schema:Organization", name=app.legal_name)
        db.add(owner)
    elif owner.status in ("suspended", "revoked"):
        # Promotion writes `status = "verified"` unconditionally a few lines
        # down. Reached with a suspended owner it silently undid the suspension
        # *and nothing else* — no bit cleared, no participant reactivated —
        # leaving a verified organisation whose credential the register still
        # reports as held. Lifting a suspension is `reinstate_owner`, and it is
        # not something a re-applied seed does by accident.
        raise OrgOnboardingError(
            f"Owner {app.alias!r} is {owner.status!r} and cannot be re-verified "
            "in passing. "
            + (
                "Use `org reinstate` to lift the suspension."
                if owner.status == "suspended"
                else "Revocation is terminal."
            )
        )

    owner.name = app.legal_name
    if app.did:
        owner.did = app.did
    owner.registration_number = app.registration_number
    owner.registration_type = app.registration_type
    owner.hq_country_code = app.hq_country_code
    owner.legal_country_code = app.legal_country_code
    owner.parent_organizations = app.parent_organizations
    owner.sub_organizations = app.sub_organizations
    # `verified_at` is *when the check happened*, not when this ran. Re-running
    # the promotion (a re-applied seed, a pod restart) must not move it forward,
    # or the evidence trail drifts away from the verification it records.
    if owner.status != "verified" or owner.verified_at is None:
        owner.verified_at = now
    owner.status = "verified"
    owner.verified_by = verified_by or app.verified_by
    owner.evidence_ref = app.evidence_ref
    owner.updated_at = now
    await db.flush()
    return owner


# ── Agreement acceptance ──────────────────────────────────────────


async def record_agreement_acceptance(
    db: AsyncSession,
    owner: Owner,
    agreement: Agreement,
    *,
    locale: str,
    accepted_by: str | None = None,
) -> AgreementAcceptance:
    """Record an org's acceptance of an agreement version and stamp the owner's
    current agreement + capacity (§2.5). Idempotent per (owner, agreement, version)."""
    texts = agreement.texts or {}
    if locale not in texts:
        raise OrgOnboardingError(
            f"Agreement {agreement.id}@{agreement.version} has no text for locale "
            f"{locale!r}. Available: {sorted(texts)}",
            status_code=422,
        )
    text_sha256 = texts[locale].get("sha256", "")
    now = datetime.now(UTC)

    result = await db.execute(
        select(AgreementAcceptance).where(
            and_(
                AgreementAcceptance.owner_alias == owner.id,
                AgreementAcceptance.agreement_id == agreement.id,
                AgreementAcceptance.agreement_version == agreement.version,
            )
        )
    )
    acceptance = result.scalar_one_or_none()
    already_current = (
        acceptance is not None
        and owner.agreement_id == agreement.id
        and owner.agreement_version == agreement.version
        and owner.agreement_accepted_at is not None
    )
    if acceptance is None:
        acceptance = AgreementAcceptance(
            owner_alias=owner.id,
            agreement_id=agreement.id,
            agreement_version=agreement.version,
            capacity=agreement.capacity,
            locale=locale,
            text_sha256=text_sha256,
            accepted_by=accepted_by,
        )
        db.add(acceptance)

    owner.agreement_id = agreement.id
    owner.agreement_version = agreement.version
    # Same reason as `verified_at` above: re-recording an acceptance the owner
    # already carries must not restamp *when* they accepted it.
    if not already_current:
        owner.agreement_accepted_at = now
    owner.agreement_capacity = agreement.capacity
    owner.updated_at = now
    await db.flush()
    return acceptance


# ── Credential issuance (gated) ───────────────────────────────────


async def issue_organization_credential(
    db: AsyncSession,
    settings: Settings,
    owner: Owner,
    *,
    roles: list[str],
    allowed_scopes: list[str],
    dsp_address: str | None = None,
    ttl_days: int | None = None,
) -> Credential:
    """Issue an OrganizationCredential for a verified owner.

    Gate (§5.6): ``status == verified`` AND a current agreement version accepted.
    Ensures the owner's ``did:web`` exists as a DID+key so it resolves.
    """
    if owner.status != "verified":
        raise OrgOnboardingError(
            f"Owner {owner.id!r} is {owner.status!r}; must be 'verified' to issue a "
            "credential."
        )
    if not owner.agreement_id:
        raise OrgOnboardingError(
            f"Owner {owner.id!r} has not accepted a current agreement version."
        )
    if not owner.did:
        raise OrgOnboardingError(
            f"Owner {owner.id!r} has no DID; set one before issuing a credential.",
            status_code=422,
        )

    ta_key = await get_trust_anchor_key(db, settings)
    ta_did = f"did:web:{settings.trust_anchor_domain}"
    status_list_url = settings.status_list_url()
    ttl = min(
        ttl_days or settings.default_credential_ttl_days,
        settings.max_credential_ttl_days,
    )

    # **The organisation must have enrolled** (`D-51`).
    #
    # This used to generate the organisation's keypair here — the anchor
    # inventing an identity and keeping the private half — which is the whole of
    # the `§3.1` custody deviation.
    #
    # Issuance never needed that key. The credential is signed with the
    # **anchor's** key and merely *names* `subject_did`; the generation existed
    # only so `did:web` would resolve, which is now the participant's own job. So
    # what is required is that the DID is **registered**, which is what enrolment
    # does — by verifying a signature from a key the organisation generated
    # itself and the anchor has never seen.
    did_result = await db.execute(select(Did).where(Did.did == owner.did))
    if not did_result.scalar_one_or_none():
        raise OrgOnboardingError(
            f"Owner {owner.id!r} has not enrolled: {owner.did} is not registered "
            "here, so there is no proven key to bind a credential to. Issue an "
            f"enrolment code (`ir-cli org enrolment-token --alias {owner.id}`) "
            "and let the organisation present its own key.",
            status_code=409,
        )

    sl_index = await allocate_suspendable_index(db)
    cred_id = generate_credential_id()

    vc = build_organization_credential(
        issuer_did=ta_did,
        subject_did=owner.did,
        legal_name=owner.name,
        registration_number=owner.registration_number,
        registration_type=owner.registration_type,
        hq_country_code=owner.hq_country_code,
        legal_country_code=owner.legal_country_code,
        roles=roles,
        allowed_scopes=allowed_scopes,
        credentials_context_url=settings.credentials_context_url,
        dataspace_uri=settings.dataspace_uri,
        status_list_credential_url=status_list_url,
        suspension_list_credential_url=settings.status_list_url(SUSPENSION_LIST_ID),
        status_list_index=sl_index,
        parent_organizations=owner.parent_organizations,
        sub_organizations=owner.sub_organizations,
        dsp_address=dsp_address,
        credential_id=cred_id,
        ttl_days=ttl,
    )
    ta_raw_jwk = decrypt_private_jwk(
        require_private_jwk(
            ta_key.private_jwk,
            kid=ta_key.kid,
            purpose="sign the trust anchor's onboarding credential",
        ),
        settings.encryption_key,
    )
    signed_vc = sign_credential(vc, ta_raw_jwk, ta_key.kid)

    cred = Credential(
        id=cred_id,
        credential_type="OrganizationCredential",
        issuer_did=ta_did,
        subject_did=owner.did,
        credential_json=signed_vc,
        status_list_index=sl_index,
        expires_at=datetime.now(UTC) + timedelta(days=ttl),
    )
    db.add(cred)
    await db.flush()
    return cred


async def _active_org_credential(db: AsyncSession, owner: Owner) -> Credential | None:
    if not owner.did:
        return None
    result = await db.execute(
        select(Credential).where(
            and_(
                Credential.subject_did == owner.did,
                Credential.credential_type == "OrganizationCredential",
                Credential.status == "active",
            )
        )
    )
    return result.scalars().first()


# ── Promotion to participant (gated) ──────────────────────────────


async def promote_owner_to_participant(
    db: AsyncSession,
    settings: Settings,
    owner: Owner,
    *,
    dsp_address: str,
    roles: list[str],
    allowed_scopes: list[str],
) -> Participant:
    """Register the org as a DSP participant.

    Gate (§5.6): a valid, unrevoked ``OrganizationCredential`` must exist.
    Idempotent: updates the participant if it already exists.

    **No STS secret** (`D-51`). This used to mint one — defaulting to
    ``insecure-dev-secret`` — which meant the anchor decided how a participant
    authenticates *to its own STS*, a service the anchor does not run. The
    participant sets its own at bootstrap; the anchor's copy of the row carries
    none, and that is what makes it unable to act as that participant.
    """
    cred = await _active_org_credential(db, owner)
    if cred is None:
        raise OrgOnboardingError(
            f"Owner {owner.id!r} has no active OrganizationCredential; issue one "
            "before promoting to a participant."
        )
    if not owner.did:
        raise OrgOnboardingError(f"Owner {owner.id!r} has no DID.", status_code=422)

    result = await db.execute(select(Participant).where(Participant.did == owner.did))
    participant = result.scalar_one_or_none()
    if participant is None:
        participant = Participant(
            did=owner.did,
            dsp_address=dsp_address,
            roles=roles,
            allowed_scopes=allowed_scopes,
            sts_client_secret=None,
        )
        db.add(participant)
    else:
        participant.dsp_address = dsp_address
        participant.roles = roles
        participant.allowed_scopes = allowed_scopes
        participant.active = True
        participant.deactivated_at = None
    await db.flush()
    return participant


# ── Suspend / reinstate / revoke ──────────────────────────────────
#
# `participation.md` §5 asks for **suspension as a state distinct from
# deactivation**, and the distinction is not a label. Suspension says *does not
# qualify right now*; revocation says *finished*. Two things have to be true for
# that to mean anything:
#
# 1. **A verifier must be able to tell them apart.** It can: a participant
#    credential names both registers, and EDC reports the purpose of whichever
#    bit it found set (see `status_list.py`). Both answers stop a negotiation —
#    a suspended participant must not transact — but they are different answers,
#    and only one of them can be taken back.
# 2. **There must be a way out.** `reinstate_owner` is that way, and it is the
#    half whose absence made suspension a slower revocation. It clears the
#    suspension bits on the credentials that are already issued: no re-issuance,
#    no new indices, the same signed credential valid again.
#
# Revocation is terminal and stays terminal. Nothing here clears a revocation
# bit, and `revoke_owner` refuses nothing — it is reachable from `verified` and
# from `suspended` alike, because escalating a suspension is the normal ending.

#: What suspension and revocation act on. **Both** types, not just the
#: organisation's: an org whose `OrganizationCredential` is revoked while its
#: `MembershipCredential` stays active still satisfies the membership constraint
#: at a counterparty's connector, so revoking one and not the other suspends
#: nobody. Both are issued to the same subject DID (`promote_owner_to_
#: participant` uses `owner.did` as the participant DID), so both are reachable
#: from the owner.
PARTICIPANT_CREDENTIAL_TYPES = ("OrganizationCredential", "MembershipCredential")


def suspension_index(credential_json: dict) -> int | None:
    """The credential's index on the *suspension* register, or `None` if it
    names no such register.

    `None` is not a detail to route around. A credential issued before this
    registry published a suspension register carries one `credentialStatus`
    entry, for revocation — suspending its holder would set a bit no verifier
    fetches, and report a suspension that does not hold anywhere it counts.
    """
    status = credential_json.get("credentialStatus")
    entries = status if isinstance(status, list) else [status]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("statusPurpose") == "suspension":
            raw = entry.get("statusListIndex")
            # `None` checked rather than caught. `int(None)` does raise
            # `TypeError`, so the behaviour was already right — but relying on
            # the exception meant the absent case and a malformed one ("abc", a
            # dict) were indistinguishable to a reader, and mypy could not see
            # that absence was handled at all. The except still covers malformed.
            if raw is None:
                return None
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
    return None


async def _participant_credentials(
    db: AsyncSession, owner: Owner, statuses: tuple[str, ...]
) -> list[Credential]:
    if not owner.did:
        return []
    result = await db.execute(
        select(Credential).where(
            and_(
                Credential.subject_did == owner.did,
                Credential.credential_type.in_(PARTICIPANT_CREDENTIAL_TYPES),
                Credential.status.in_(statuses),
            )
        )
    )
    return list(result.scalars().all())


async def _participant_for(db: AsyncSession, owner: Owner) -> Participant | None:
    if not owner.did:
        return None
    result = await db.execute(select(Participant).where(Participant.did == owner.did))
    return result.scalar_one_or_none()


async def suspend_owner(db: AsyncSession, owner: Owner) -> None:
    """Suspend: set the suspension bits AND deactivate the participant (one tx).

    Deactivating the participant is not what makes this suspension — it is what
    stops the registry itself issuing tokens for a party that does not currently
    qualify. What makes it suspension is that `reinstate_owner` undoes all of
    it, and that the bit a verifier reads says `suspension`.
    """
    if owner.status == "revoked":
        raise OrgOnboardingError(
            f"Owner {owner.id!r} is revoked; revocation is terminal and cannot be "
            "reduced to a suspension."
        )

    # `status_list_index is None` means this registry did not issue it — a
    # holder's own stored copy (`issuance._store_holder_credentials`) carries no
    # index, because the register belongs to the issuer. Its `credentialStatus`
    # names the *issuer's* index, so acting on it here would set a bit on this
    # registry's register at a number that means somebody else entirely.
    creds = [
        c
        for c in await _participant_credentials(db, owner, ("active",))
        if c.status_list_index is not None
    ]
    unsuspendable = [c for c in creds if suspension_index(c.credential_json) is None]
    if unsuspendable:
        raise OrgOnboardingError(
            f"Owner {owner.id!r} holds {len(unsuspendable)} credential(s) issued "
            "before this registry published a suspension register, so no verifier "
            "would see them suspended: "
            + ", ".join(sorted(c.id for c in unsuspendable))
            + ". Re-issue them to make the organisation suspendable, or use "
            "`revoke` if the intent is terminal."
        )

    now = datetime.now(UTC)
    for cred in creds:
        index = suspension_index(cred.credential_json)
        if index is not None:
            await suspend_status_list_index(db, index)
        cred.status = "suspended"

    owner.status = "suspended"
    owner.updated_at = now
    participant = await _participant_for(db, owner)
    if participant:
        participant.active = False
        participant.deactivated_at = now
    await db.flush()


async def reinstate_owner(db: AsyncSession, owner: Owner) -> None:
    """The inverse of `suspend_owner`, and the reason suspension is a state.

    Clears the suspension bits on the credentials the organisation already
    holds. No re-issuance: the credential in its wallet is signed, unexpired and
    unchanged, and it was never revoked — only held. Re-minting one here would
    burn a fresh index and leave the holder carrying a credential the register
    no longer covers.
    """
    if owner.status == "revoked":
        raise OrgOnboardingError(
            f"Owner {owner.id!r} is revoked. Revocation is terminal: re-admitting "
            "this organisation is a new verification and a new credential, not a "
            "reinstatement."
        )
    if owner.status != "suspended":
        raise OrgOnboardingError(
            f"Owner {owner.id!r} is {owner.status!r}, not 'suspended'; there is "
            "nothing to reinstate."
        )
    if not owner.verified_by:
        # `ck_owner_verified_has_evidence` would refuse the write anyway. Saying
        # so here is the difference between a message and an IntegrityError.
        raise OrgOnboardingError(
            f"Owner {owner.id!r} has no recorded verification evidence, so it "
            "cannot return to 'verified'.",
            status_code=422,
        )

    now = datetime.now(UTC)
    for cred in await _participant_credentials(db, owner, ("suspended",)):
        if cred.status_list_index is None:
            continue  # not ours to lift; see `suspend_owner`
        index = suspension_index(cred.credential_json)
        if index is not None:
            await unsuspend_status_list_index(db, index)
        cred.status = "active"

    owner.status = "verified"
    owner.updated_at = now
    participant = await _participant_for(db, owner)
    if participant:
        participant.active = True
        participant.deactivated_at = None
    await db.flush()


async def revoke_owner(db: AsyncSession, owner: Owner) -> None:
    """Revoke: terminal, and reachable from `verified` or `suspended` alike.

    This no longer runs `suspend_owner` first. Doing so was what made the two
    indistinguishable — one function, one set of effects, one label written over
    the top. A revocation bit is set here and by nothing else, and no path in
    this module clears one.

    A suspension bit already set is left set. It is still true, the credential
    is finished either way, and leaving it means `unsuspend_status_list_index`
    has exactly one caller.
    """
    now = datetime.now(UTC)
    for cred in await _participant_credentials(db, owner, ("active", "suspended")):
        if cred.status_list_index is not None:
            await revoke_status_list_index(db, cred.status_list_index)
        cred.status = "revoked"
        cred.revoked_at = now

    owner.status = "revoked"
    owner.updated_at = now
    participant = await _participant_for(db, owner)
    if participant:
        participant.active = False
        participant.deactivated_at = now
    await db.flush()


# ── Seeding an organisation end to end (T26) ──────────────────────
#
# The five lifecycle calls above are individually idempotent, but reaching a
# promoted organisation still meant an operator running them in order, by hand,
# once per organisation. `apply_owner_entry` composes them from one declarative
# entry so a fresh environment can reach a promoted organisation with no human
# in a browser, and a re-run is a no-op.
#
# The entry is an `owners.yaml` owner extended with an optional `dataspace:`
# block. An entry without that block is not ours — it is there for the other
# consumers of that file — and is reported as skipped, never guessed at.


DEFAULT_ROLES = ["consumer"]
DEFAULT_SCOPES = ["dataspaces.query"]

#: Owner columns an `owners.yaml` entry owns directly. `upsert_owner_from_
#: application` writes the legal identity; these carry the presentation and
#: lookup keys, so `org apply` alone leaves the same owner row `owner import`
#: would — governance `ownership[].name` resolves by alias, so dropping them
#: would publish datasets nobody can resolve an owner for.
_ENTRY_OWNER_FIELDS = ("type", "url")


@dataclass(slots=True)
class RunEvidence:
    """Verification evidence supplied once per invocation, not per entry.

    A deployment's `owners.yaml` is celine-domain and carries no ds `dataspace:`
    block; the evidence for the organisations in it is *this file at this
    revision*, which is a fact about the run and not about any one entry. That is
    the same claim `seed/owners.dev.yaml` already records for itself
    (`verified_by: dev-seed, evidence_ref: owners.dev.yaml`), so the DB CHECK that
    a verified owner carries its evidence is satisfied without weakening it.

    A per-entry `dataspace:` block still wins wherever one exists.
    """

    verified_by: str
    evidence_ref: str | None = None


@dataclass(slots=True)
class Selection:
    """Which entries an `org apply` run will attempt, and why the rest are out."""

    entries: list[dict] = field(default_factory=list)
    #: Reasons a selector refused, one per line, all of them — the caller reports
    #: every one and then exits non-zero rather than stopping at the first.
    errors: list[str] = field(default_factory=list)
    #: Why the entries this selector did *not* pick are out. One string, because
    #: each selector has one reason: governance did not name them, or they carry
    #: no DID. Reported per entry so a skip says what the selector decided rather
    #: than what the entry happens to lack.
    skipped_reason: str = "no dataspace: block"

    @property
    def ok(self) -> bool:
        return not self.errors


def select_entries(
    entries: list[dict],
    *,
    governance_paths: list[Path] | None = None,
) -> Selection:
    """Choose the owners.yaml entries to onboard.

    Two selectors, and **both preserve the property the `dataspace:` skip
    provides**: they pick out the organisations that operate in the dataspace and
    leave the rest of the file — attribution metadata for open data, upstream
    sources with no connector — alone.

    - **Given governance files**, the set is derived: every owner alias named by an
      exposed dataset, resolved through the registry's existing id/alias swap. An
      organisation is onboarded because it owns data published here, so the set
      cannot drift from the governance that produced it.
    - **Given none**, every entry carrying a `did`. A DID is what
      `GET /owners/resolve` exists to answer with, and an entry without one cannot
      be the recipient of anything.

    An alias that resolves to no entry, and an entry carrying no `did`, are both
    **errors** rather than quiet omissions: a governance file naming an owner the
    deployment does not declare is a broken deployment, and reporting it as a skip
    is how it reaches production. Every one is collected so a fourteen-owner file
    is fixed in one pass.
    """
    # `ds-governance` ships no `py.typed`, so mypy skips it. Silenced here rather
    # than adding the marker: that would make every other consumer start type-
    # checking against it in the same change, which is a bigger move than this.
    from ds.governance import (  # type: ignore[import-untyped]
        OwnerEntry,
        OwnersRegistry,
        exposed_owner_aliases,
    )

    if not governance_paths:
        return Selection(
            entries=[e for e in entries if e.get("did")],
            skipped_reason="carries no did",
        )

    selection = Selection(skipped_reason="governance does not name it")
    known: list[OwnerEntry] = []
    for entry in entries:
        if not entry.get("id"):
            selection.errors.append("owners.yaml entry with no id")
            continue
        known.append(OwnerEntry(**entry))
    registry = OwnersRegistry(known)

    chosen: dict[str, dict] = {}
    by_id = {e["id"]: e for e in entries if e.get("id")}
    for path in governance_paths:
        for alias in exposed_owner_aliases(path):
            owner = registry.by_id(alias)
            if owner is None:
                selection.errors.append(
                    f"{path}: governance names owner '{alias}', which is neither an "
                    f"id nor an alias in the owners file"
                )
                continue
            if not owner.did:
                selection.errors.append(
                    f"{path}: governance names owner '{alias}' ({owner.id}), which "
                    f"carries no did — an owner with no DID cannot be resolved by "
                    f"the services that need it"
                )
                continue
            chosen.setdefault(owner.id, by_id[owner.id])

    if not chosen and not selection.errors:
        selection.errors.append(
            "no exposed dataset in "
            + ", ".join(str(p) for p in governance_paths)
            + " names an owner — nothing would be onboarded, which is not the "
            "same answer as 'no organisations needed'"
        )
    selection.entries = list(chosen.values())
    return selection


@dataclass(slots=True)
class ApplyStep:
    """What one lifecycle stage did for one entry."""

    step: str  # application | verification | agreement | credential | participant
    action: str  # created | updated | unchanged | issued | promoted | skipped
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.step:<13} {self.action:<9} {self.detail}".rstrip()


@dataclass(slots=True)
class ApplyOutcome:
    """The per-entry report. ``error`` set means the chain stopped there."""

    alias: str
    steps: list[ApplyStep] = field(default_factory=list)
    error: str | None = None
    #: False when the entry declares no ``dataspace:`` block — not a failure.
    applied: bool = True

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def changed(self) -> bool:
        return any(s.action not in ("unchanged", "skipped") for s in self.steps)


def _require(block: dict, key: str, alias: str) -> object:
    value = block.get(key)
    if value in (None, "", [], {}):
        raise OrgOnboardingError(
            f"{alias}: dataspace.{key} is required", status_code=422
        )
    return value


async def _current_org_credential(db: AsyncSession, owner: Owner) -> Credential | None:
    """An active OrganizationCredential that has not expired.

    ``_active_org_credential`` (the promote gate) only reads ``status``. Here the
    expiry matters: re-issuing on every run would mint a credential and burn a
    StatusList index per pod restart, while never re-issuing would let a seeded
    organisation quietly age out.
    """
    cred = await _active_org_credential(db, owner)
    if cred is None:
        return None
    expires_at = cred.expires_at
    if expires_at is not None:
        # SQLite hands back naive datetimes where Postgres hands back aware
        # ones. Assume UTC — everything written here is.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            return None
    return cred


async def apply_owner_entry(
    db: AsyncSession,
    settings: Settings,
    entry: dict,
    evidence: RunEvidence | None = None,
    skip_reason: str | None = None,
) -> ApplyOutcome:
    """Walk register → verify → agreement → issue-credential → promote for one entry.

    Idempotent throughout: a second run advances nothing and duplicates nothing.
    Raises nothing — a gate or a malformed entry lands in ``ApplyOutcome.error``
    so the caller can report every entry in one pass rather than stopping at the
    first, the same shape as the connector's sync gate and ``ProductionGuard``.
    """
    alias = entry.get("id") or entry.get("alias") or "<unnamed>"
    outcome = ApplyOutcome(alias=alias)

    block = entry.get("dataspace")
    per_run_evidence = False
    if not block:
        # Without run evidence this is the old behaviour exactly: the entry is not
        # ours and is left alone. With it, the entry is onboarded as far as the
        # evidence honestly supports — application and verification, no agreement,
        # no credential, no promotion, because a run flag cannot assert those.
        if evidence is None:
            outcome.applied = False
            # **Whose reason this is.** Without run evidence a `dataspace:` block is
            # the only way in, so its absence *is* the reason and the default holds.
            # With run evidence the entry was reachable and the selector still left
            # it out — `skip_reason` is that selector's answer, and reporting the
            # block instead names a fact that had nothing to do with the decision.
            outcome.steps.append(
                ApplyStep("entry", "skipped", skip_reason or "no dataspace: block")
            )
            return outcome
        block = {
            "verified_by": evidence.verified_by,
            "evidence_ref": evidence.evidence_ref,
        }
        per_run_evidence = True
    if not isinstance(block, dict):
        outcome.error = f"{alias}: dataspace must be a mapping"
        return outcome

    try:
        await _apply_steps(
            db,
            settings,
            entry,
            block,
            alias,
            outcome,
            per_run_evidence=per_run_evidence,
        )
    except OrgOnboardingError as exc:
        outcome.error = f"{alias}: {exc.message}"
    return outcome


async def _apply_steps(
    db: AsyncSession,
    settings: Settings,
    entry: dict,
    block: dict,
    alias: str,
    outcome: ApplyOutcome,
    *,
    per_run_evidence: bool = False,
) -> None:
    legal_name = block.get("legal_name") or entry.get("name") or alias
    did = block.get("did") or entry.get("did")
    dsp_address = block.get("dsp_address")
    roles = list(block.get("roles") or DEFAULT_ROLES)
    scopes = list(block.get("scopes") or DEFAULT_SCOPES)
    accepted = block.get("accepted")

    # 'verified' must carry its evidence — the same invariant as the DB CHECK and
    # `ir-cli owner import`. A seed that promotes an owner without saying who
    # verified it is exactly the free-verification state T30 closed.
    verified_by = _require(block, "verified_by", alias)
    evidence_ref = block.get("evidence_ref")

    # The same vocabulary the admin API enforces. `dataspace.roles` is the
    # *participant* role, not the Keycloak `organization.role` beside it in the
    # same entry — a seed that mixes them would register a participant the API
    # would have refused, and only the seeded environments would carry it.
    from ..schemas.requests import VALID_REGISTRATION_TYPES, VALID_ROLES

    invalid_roles = set(roles) - VALID_ROLES
    if invalid_roles:
        raise OrgOnboardingError(
            f"dataspace.roles {sorted(invalid_roles)} invalid; must be one of "
            f"{sorted(VALID_ROLES)} (Keycloak roles belong under organization.role)",
            status_code=422,
        )
    registration_type = block.get("registration_type")
    if registration_type is not None and registration_type not in (
        VALID_REGISTRATION_TYPES
    ):
        raise OrgOnboardingError(
            f"dataspace.registration_type {registration_type!r} invalid; must be "
            f"one of {sorted(VALID_REGISTRATION_TYPES)}",
            status_code=422,
        )

    # Refuse a half-declared chain up front rather than promoting an owner and
    # failing at the gate three steps later, leaving state nobody asked for.
    if dsp_address and not did:
        raise OrgOnboardingError(
            "dataspace.dsp_address needs a did to promote against", status_code=422
        )
    if dsp_address and not accepted:
        raise OrgOnboardingError(
            "dataspace.dsp_address requires dataspace.accepted — a participant "
            "cannot be promoted without an accepted agreement",
            status_code=422,
        )

    # ── 1. application ────────────────────────────────────────────
    app_defaults: dict | None = None
    if per_run_evidence:
        # **Only what the file actually says.** A deployment's owners.yaml carries
        # no registration number, no country codes and no participant role, and a
        # synthesised block reports them as ``None`` — which `upsert_application`
        # would write as *"clear this"*, blanking the legal identity of an
        # organisation registered properly. It refuses outright once the
        # application is verified (`409`, the credential asserts the old values),
        # so this path could not even run against an organisation ds already knows.
        #
        # Omitting a key leaves the stored value alone, and `defaults` applies on
        # create only, so a first run still writes a complete row. `did` stays in
        # `fields` because it is the one fact this file is authoritative about; a
        # DID that has changed still meets the verified-application guard, which is
        # right — re-minting is not decided here.
        fields = {"did": did}
        app_defaults = {"legal_name": legal_name, "roles": roles}
    else:
        fields = {
            "legal_name": legal_name,
            "registration_number": block.get("registration_number"),
            "registration_type": registration_type,
            "hq_country_code": block.get("hq_country_code"),
            "legal_country_code": block.get("legal_country_code"),
            "parent_organizations": block.get("parent_organizations"),
            "sub_organizations": block.get("sub_organizations"),
            "roles": roles,
            "did": did,
            "dsp_address": dsp_address,
        }
    before = await resolve_application(db, alias)
    unchanged = before is not None and all(
        getattr(before, name) == value for name, value in fields.items()
    )
    # Same intake as the HTTP route and `org register`, so a seed cannot edit a
    # verified organisation's legal identity behind its issued credential.
    app_row, created_app = await upsert_application(
        db, alias, fields, defaults=app_defaults
    )
    if created_app:
        action = "created"
    else:
        action = "unchanged" if unchanged else "updated"
    outcome.steps.append(ApplyStep("application", action, alias))

    # ── 2. verification → Owner ───────────────────────────────────
    existing = await db.execute(select(Owner).where(Owner.id == alias))
    owner_before = existing.scalar_one_or_none()
    was_verified = owner_before is not None and owner_before.status == "verified"

    # Per-run evidence must never overwrite a claim the entry itself made. The
    # flags say "this deployment's owner registry at this revision", which is true
    # and generic; an owner ds verified properly carries a DPA reference or a
    # registration extract, and rewriting that to the generic string would
    # silently downgrade the evidence behind an issued credential. Free
    # verification is the state T30 closed, and this is the same hole from the
    # other side. A per-entry `dataspace:` block is not per-run and still wins.
    retained_evidence = (
        per_run_evidence
        and app_row.verified_by is not None
        and app_row.verified_by != str(verified_by)
    )
    if retained_evidence:
        verified_by = app_row.verified_by
        evidence_ref = None

    if app_row.status != "verified":
        app_row.status = "verified"
        app_row.verified_at = datetime.now(UTC)
    if not retained_evidence:
        app_row.verified_by = str(verified_by)
        if evidence_ref is not None:
            app_row.evidence_ref = evidence_ref
    await db.flush()

    owner = await upsert_owner_from_application(
        db, app_row, verified_by=str(verified_by)
    )

    # The owner's presentation and lookup keys come from the entry itself, so
    # `org apply` leaves the row `owner import` would have.
    for name in _ENTRY_OWNER_FIELDS:
        value = entry.get(name)
        if value is not None:
            setattr(owner, name, value)
    if entry.get("aliases") is not None:
        owner.aliases = list(entry["aliases"])
    if entry.get("organization") is not None:
        owner.organization_config = entry["organization"]
    await db.flush()

    if retained_evidence:
        verification = "unchanged"
        detail = f"kept existing evidence: verified by {verified_by}"
    elif was_verified:
        verification = "unchanged"
        detail = f"verified by {verified_by}"
    else:
        verification = "advanced" if owner_before else "created"
        detail = f"verified by {verified_by}"
    outcome.steps.append(ApplyStep("verification", verification, detail))

    # ── 3. agreement acceptance ───────────────────────────────────
    if not accepted:
        outcome.steps.append(
            ApplyStep("agreement", "skipped", "no dataspace.accepted declared")
        )
    else:
        agreement_id = _require(accepted, "agreement", alias)
        version = str(_require(accepted, "version", alias))
        locale = accepted.get("locale", "en")
        ag_result = await db.execute(
            select(Agreement).where(
                and_(Agreement.id == agreement_id, Agreement.version == version)
            )
        )
        agreement = ag_result.scalar_one_or_none()
        if agreement is None:
            raise OrgOnboardingError(
                f"agreement {agreement_id}@{version} is not imported "
                "(ir-cli agreement import)",
                status_code=422,
            )
        already = (
            owner.agreement_id == agreement.id
            and owner.agreement_version == agreement.version
        )
        await record_agreement_acceptance(
            db,
            owner,
            agreement,
            locale=locale,
            accepted_by=accepted.get("accepted_by"),
        )
        outcome.steps.append(
            ApplyStep(
                "agreement",
                "unchanged" if already else "accepted",
                f"{agreement.id}@{agreement.version} capacity={agreement.capacity}",
            )
        )

    # ── 4. organisation credential ────────────────────────────────
    if not owner.agreement_id:
        outcome.steps.append(
            ApplyStep("credential", "skipped", "no accepted agreement to issue against")
        )
    else:
        cred = await _current_org_credential(db, owner)
        if cred is not None:
            outcome.steps.append(
                ApplyStep("credential", "unchanged", f"{cred.id} valid")
            )
        else:
            try:
                cred = await issue_organization_credential(
                    db,
                    settings,
                    owner,
                    roles=roles,
                    allowed_scopes=scopes,
                    dsp_address=dsp_address,
                    ttl_days=block.get("credential_ttl_days"),
                )
            except OrgOnboardingError as exc:
                # Not enrolled yet is the **normal** state for a seeded
                # organisation, not a failure: the operator has done everything
                # they can do alone, and the rest is the organisation's. Report
                # it as a skip with the reason and carry on, or a seed of ten
                # organisations would exit non-zero because none of them has
                # stood up a registry yet.
                if exc.status_code != 409:
                    raise
                outcome.steps.append(
                    ApplyStep("credential", "skipped", "awaiting enrolment")
                )
                outcome.steps.append(
                    ApplyStep("participant", "skipped", "awaiting enrolment")
                )
                return
            outcome.steps.append(ApplyStep("credential", "issued", cred.id))

    # ── 5. participant promotion ──────────────────────────────────
    if not dsp_address:
        outcome.steps.append(
            ApplyStep("participant", "skipped", "no dataspace.dsp_address declared")
        )
        return

    existing_participant = await db.execute(
        select(Participant).where(Participant.did == owner.did)
    )
    was_participant = existing_participant.scalar_one_or_none() is not None
    participant = await promote_owner_to_participant(
        db,
        settings,
        owner,
        dsp_address=dsp_address,
        roles=roles,
        allowed_scopes=scopes,
    )
    outcome.steps.append(
        ApplyStep(
            "participant",
            "unchanged" if was_participant else "promoted",
            f"{participant.did} dsp={participant.dsp_address}",
        )
    )
