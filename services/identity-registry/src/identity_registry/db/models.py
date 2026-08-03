from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .engine import Base

# `none_as_null=True` is **not optional**, and it was found the only way it could
# be: on Postgres, live.
#
# Without it SQLAlchemy stores Python `None` in a JSON column as the JSON value
# `'null'`, not as SQL `NULL`. So `keys.private_jwk IS NULL` — the test for "this
# instance holds only the public half", which `get_participant_key` fails closed
# on and `DID-12` asserts — was **False for every public-only key**. The guard
# never fired, and what reached `decrypt_private_jwk` was a JSON null.
#
# SQLite deserialises `'null'` back to Python `None`, so the unit suite agreed
# with the code and Postgres did not: 445 tests passed against a claim that was
# false in the only database that runs. That is why the sweep in `DID-12` reads
# the column in SQL rather than through the ORM.
JsonType = JSONB(none_as_null=True).with_variant(JSON(none_as_null=True), "sqlite")


class Key(Base):
    __tablename__ = "keys"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    owner_did: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    algorithm: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ES256"
    )
    #: **Nullable, and that is the decentralization** (`DID-09`). A trust anchor
    #: records the *public* key of every participant it has enrolled — it needs
    #: one to verify their signatures and to bind an issued credential — and must
    #: hold the private half of none of them. A row with `private_jwk IS NULL` is
    #: a key this instance knows about but cannot use, which is the correct
    #: relationship between an issuer and a holder.
    #:
    #: `DID-12` is the invariant that asserts the anchor holds no other kind.
    private_jwk: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    public_jwk: Mapped[dict] = mapped_column(JsonType, nullable=False)
    kid: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Did(Base):
    __tablename__ = "dids"

    did: Mapped[str] = mapped_column(Text, primary_key=True)
    did_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # 'participant' | 'user'
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_endpoints: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    key_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("keys.id"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    key: Mapped[Key | None] = relationship("Key", lazy="joined")
    credentials: Mapped[list[Credential]] = relationship(
        "Credential",
        foreign_keys="Credential.subject_did",
        back_populates="subject",
        lazy="selectin",
    )


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    credential_type: Mapped[str] = mapped_column(String(64), nullable=False)
    issuer_did: Mapped[str] = mapped_column(Text, nullable=False)
    subject_did: Mapped[str] = mapped_column(
        Text, ForeignKey("dids.did"), nullable=False
    )
    credential_json: Mapped[dict] = mapped_column(JsonType, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )
    status_list_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    subject: Mapped[Did] = relationship(
        "Did", back_populates="credentials", lazy="joined"
    )


class Participant(Base):
    __tablename__ = "participants"

    did: Mapped[str] = mapped_column(
        Text, ForeignKey("dids.did"), primary_key=True
    )
    dsp_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    roles: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    allowed_scopes: Mapped[list] = mapped_column(
        JsonType, nullable=False, default=list
    )
    sts_client_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    did_record: Mapped[Did] = relationship("Did", lazy="joined")


class KeycloakMapping(Base):
    __tablename__ = "keycloak_mappings"
    __table_args__ = (
        # One Keycloak user, one DID. Without this a second identity for the same
        # human is representable — and it was reachable, because resolution used to
        # derive a new subject id whenever an *email* lookup missed, and the email
        # is the identifier an IdP lets people change. The data plane resolves both
        # DIDs to the same username, so a revocation against one leaves the other
        # disclosing. See migration 0010.
        UniqueConstraint(
            "keycloak_realm", "keycloak_user_id", name="uq_keycloak_mappings_realm_user"
        ),
    )

    did: Mapped[str] = mapped_column(
        Text, ForeignKey("dids.did"), primary_key=True
    )
    keycloak_realm: Mapped[str] = mapped_column(Text, nullable=False)
    keycloak_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    # Keycloak's `preferred_username`. Downstream systems that key on the person
    # rather than on a DID use this: the REC registry resolves a member with
    # `Member.user_id == user.get_username()`, so a dataspace decision about
    # "which subjects consented" can only reach it through this value.
    #
    # Nullable, and `email` is the fallback: many realms (ours included) set
    # username = email, and mappings written before this column existed have
    # only the email. Never guess beyond that — a wrong username silently
    # resolves to another person's assets.
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Owner(Base):
    __tablename__ = "owners"
    __table_args__ = (
        # 'verified' is a claim that must carry its evidence. A row that reads
        # verified while `verified_by` is null asserts a check nobody made — the
        # exact state that let an operator- or service-seeded owner default into
        # the consent circle for free. Make it unrepresentable.
        CheckConstraint(
            "status <> 'verified' OR verified_by IS NOT NULL",
            name="ck_owner_verified_has_evidence",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="schema:Organization"
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    did: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    organization_config: Mapped[dict | None] = mapped_column(
        JsonType, nullable=True
    )
    # ── Gaia-X-shaped legal identity (Block D) ────────────────────────
    # Shape-compatible with gx:LegalParticipant; not full GXDCH compliance.
    registration_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # local | EUID | EORI | vatID | leiCode
    hq_country_code: Mapped[str | None] = mapped_column(
        String(8), nullable=True
    )  # ISO 3166-2
    legal_country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    parent_organizations: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    sub_organizations: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    # ── Verification lifecycle ────────────────────────────────────────
    # Owners default to 'pending'. 'verified' is written only *because*
    # something verified them — every construction path that sets it also sets
    # `verified_by`/`evidence_ref`, and `ck_owner_verified_has_evidence` above
    # holds that invariant. Owners move pending → verified → suspended | revoked.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ── Current accepted service agreement + declared capacity (§2.5) ──
    agreement_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    agreement_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agreement_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    agreement_capacity: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # processor | joint_controller | independent_controller
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OrganizationApplication(Base):
    """Pre-verification organisation registration data (Block D §5.5).

    Holds an applicant's declared legal identity before it is promoted into an
    ``Owner`` row on verification. All trust state (the ``status`` transition to
    ``verified``) lives here and in the ``Owner`` it promotes into — never in the
    portal or CLI, which only call the IR.
    """

    __tablename__ = "organization_applications"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    alias: Mapped[str] = mapped_column(String, nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    registration_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    hq_country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    legal_country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    parent_organizations: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    sub_organizations: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    roles: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    did: Mapped[str | None] = mapped_column(Text, nullable=True)
    dsp_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )  # pending | verified | rejected
    evidence_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OnboardingInvite(Base):
    """A single-use code that lets a stranger file an organisation application.

    An applicant has no identity yet — that is the point of applying — so the
    intake route cannot be authenticated the normal way. A fully public write on
    the service that holds every private key is a spam and enumeration surface,
    so the operator issues a code out of band and the code is what gates the write.

    The code is stored hashed: a leaked database should not yield usable invites,
    and nothing needs to read it back (it is shown once, when issued).
    """

    __tablename__ = "onboarding_invites"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # Free-text note for the operator: who this was sent to, and why.
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when consumed. Single-use: a redeemed invite is spent, not deleted, so
    # an operator can still see which application it produced.
    redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    application_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class Agreement(Base):
    """Service-agreement definition, YAML-seeded and IR-hosted (Block D §5.4).

    Shaped so it can later become a ``gx:GaiaXTermsAndConditions`` credential.
    The ``capacity`` field is the consent boundary (§2.5): it decides whether a
    party accepting this agreement is covered-and-disclosed or needs its own
    consent.
    """

    __tablename__ = "agreements"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    effective_from: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    applies_to: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    capacity: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # processor | joint_controller | independent_controller
    # {locale: {"path": str, "sha256": str}} — codes + hash, never inline PII.
    texts: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgreementAcceptance(Base):
    """An organisation's acceptance of a specific agreement version (§5.4).

    Same evidence shape as the citizen path (§2.4): proves *what text, at what
    version and locale* was accepted via ``text_sha256`` — no prose, no PII.
    """

    __tablename__ = "agreement_acceptances"
    __table_args__ = (
        UniqueConstraint(
            "owner_alias",
            "agreement_id",
            "agreement_version",
            name="uq_agreement_acceptance",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    owner_alias: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agreement_id: Mapped[str] = mapped_column(String, nullable=False)
    agreement_version: Mapped[str] = mapped_column(String(32), nullable=False)
    capacity: Mapped[str] = mapped_column(String(32), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"

    user_did: Mapped[str] = mapped_column(
        Text, ForeignKey("dids.did"), primary_key=True
    )
    organization_alias: Mapped[str] = mapped_column(
        String, primary_key=True
    )
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StatusList(Base):
    __tablename__ = "status_lists"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    purpose: Mapped[str] = mapped_column(
        String(32), nullable=False, default="revocation"
    )
    bitstring: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # The allocator. `bitstring` is a *revocation* register and must never
    # be read to find a free slot: its first unset bit does not move on
    # issuance, so every credential would take the same index, and setting
    # the bit to advance it would publish the credential revoked. See
    # services/status_list.allocate_status_list_index.
    next_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Changes when the register changes — that is, on revocation only. Issuance
    # moves `next_index` and leaves this alone, because the published
    # StatusList credential is unaffected by it.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EnrolmentToken(Base):
    """The out-of-band authorization that lets a verified organisation enrol.

    DCP's Credential Issuance Protocol leaves *how* an issuer decides a client
    may be issued to deliberately undefined, and names the carrier: **"if the
    issuer supports a pre-authorization code flow, the client MUST use the
    `pre-authorized_code` claim in the Self-Issued ID Token"**. This row is that
    code.

    It is the same primitive as :class:`OnboardingInvite`, one step later in the
    lifecycle, and for the same reason — the party presenting it has no
    credentials yet, because acquiring them is what it is doing. So it is treated
    like a credential: generated with `secrets`, stored as a SHA-256 hash,
    single-use, expiring, never readable back.

    **It grants nothing on its own.** Redeeming it also requires an SI token
    signed by the key being registered, so possession of a leaked code without
    that key binds no DID. The code says *which organisation*; the signature says
    *which key*. Neither alone is enough, which is what makes this an enrolment
    rather than a hand-over.
    """

    __tablename__ = "enrolment_tokens"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    code_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    #: The owner this code enrols. One code, one organisation — a code that
    #: enrolled "whoever presents it" would let any keyholder claim any verified
    #: organisation's identity.
    owner_alias: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Spent, not deleted — an operator asking "how did this DID get registered"
    #: needs the answer to still exist.
    redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: The DID that redeemed it. The audit trail from an organisation's
    #: verification to the key that now speaks for it.
    redeemed_did: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: What this token admits the organisation **as**. On the token rather than
    #: on the request, because a party that names its own roles can enrol as
    #: whatever it likes: the candidate states an intended role
    #: (`DSSC-BIZ-136`), the authority decides whether to grant it.
    roles: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    allowed_scopes: Mapped[list | None] = mapped_column(JsonType, nullable=True)


class CredentialRequest(Base):
    """One CIP credential request, and what became of it.

    The protocol is asynchronous by design: the Issuer Service acknowledges
    receipt (`201` + a `Location`), decides later, and delivers by writing to the
    client's Credential Service. `GET /issuer/requests/{issuerPid}` is how the
    client asks in the meantime, so the state has to be somewhere.

    `holder_pid` is the client's own id for the request and is echoed back
    untouched; `issuer_pid` is ours. Two ids rather than one because either side
    may be retrying, and a shared id would make "which request is this" a
    question neither side could answer alone.
    """

    __tablename__ = "credential_requests"

    issuer_pid: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    holder_pid: Mapped[str] = mapped_column(Text, nullable=False)
    #: Who asked — the `iss` of the SI token that carried the request. Access
    #: control on the status endpoint is "only the client that made the request",
    #: and this is what that comparison reads.
    holder_did: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    owner_alias: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: RECEIVED | REJECTED | ISSUED, exactly the CIP vocabulary.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="RECEIVED"
    )
    #: What was asked for: the `credentials[].id` values, resolved against the
    #: Issuer Metadata.
    requested: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    #: Why, when REJECTED. Operator-facing; the client sees only the status,
    #: because a rejection reason on an unauthenticated-ish surface is an oracle.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TrustedIssuer(Base):
    """The dataspace's list of accredited entities — `DSSC-TRF-05`, `-17`.

    A **governance statement**, not an observation. It says which entities this
    dataspace accepts attestations from, which is different from which entities
    have in fact issued something: deriving the list from the credentials that
    exist would let anything that managed to issue one list itself.

    Four requirements shape the columns, and each would be easy to leave out:

    - `TRF-05` — the listing includes **revoked** entries. A trust list that
      forgets what it used to trust cannot answer *"was this credential
      legitimate when it was issued"*, which is the question a verifier has
      about anything already in circulation. So revocation sets a status and a
      timestamp; nothing is deleted.
    - `TRF-19` — a trust anchor is accepted *in relation to a specific scope of
      attestation*. An entry that named no scope would read as "trusted for
      everything", which is the one thing a trust list must never imply by
      omission.
    - `TRF-21` — a trust service provider is a *designated issuer deriving
      authority from a trust anchor*, so an entry can name where its authority
      comes from.
    - `TRF-25`/`-26` — many trust services per anchor and vice versa, which is
      why authority is a field on the entry rather than a table shape.
    """

    __tablename__ = "trusted_issuers"

    did: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    #: `trust-anchor` | `trust-service-provider` (`TRF-21`).
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    #: The credential types this entity may attest (`TRF-19`). Empty is not
    #: "anything" — it is an entry nobody should trust for anything, and the
    #: published list says so rather than leaving it to be read as a wildcard.
    scope_of_attestation: Mapped[list] = mapped_column(
        JsonType, nullable=False, default=list
    )
    #: For a trust service provider, the anchor it derives authority from.
    derives_authority_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: `active` | `revoked`. Revoked entries stay listed (`TRF-05`).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    added_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Why it was revoked. A trust list that drops an entity without saying why
    #: leaves every verifier guessing whether credentials it already accepted
    #: are still good.
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
