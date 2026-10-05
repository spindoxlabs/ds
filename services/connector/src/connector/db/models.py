"""SQLAlchemy ORM models for ds-connector."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy.types import JSON

from .engine import Base
from .sealed import SealedJSON, SealedText, blind_index


def _uuid() -> str:
    return str(uuid.uuid4())


#: Every value `ConsentRequestORM.status` can hold, and the one declaration of
#: them. A plain tuple rather than an enum because the column is `Text` and a
#: type change would have to migrate rows that are already written.
#:
#: `expired` is the one that was missing, and its absence was not harmless: it is
#: written by the TTL sweep (`services/pending_sweep.py`) and projected by
#: `GET /consent/pending`, so a reader of this list concluded that a consent row
#: leaves `pending` only when somebody decides it — hiding the one path that
#: moves a row with nobody deciding anything.
#: `tests/test_consent_status_vocabulary.py` reads this tuple and every status
#: literal the services assign, and fails on a value written but not declared.
CONSENT_STATUSES: tuple[str, ...] = (
    "pending",
    "granted",
    "rejected",
    "revoked",
    "expired",
)

#: Every authority that can write a consent decision, and the one declaration of
#: them. Same shape and same reason as `CONSENT_STATUSES` above: a `Text` column,
#: so a type change would have to migrate rows already written.
#:
#: This is not decoration on the audit trail — `set_subject_data_sharing` reads it
#: to decide who may lift a standing withdrawal (`D-15c`). `subject` is the person
#: whose data it is, deciding through `POST /consent/my/shares`; `service` is a
#: plain service provisioning on their behalf through `POST /consent/admin/shares`
#: — **no longer written** since 2026-09-17, when that path was removed, and kept
#: for the rows it wrote; `operator` is the deployment operator (a person
#: holding `connector.admin`) writing through the same route;
#: `collector` is an organisation registering, at this connector, a decision it
#: took itself about one of its members (plan
#: `a-collector-registers-consent-at-the-holder`). A decision the collector only
#: *relays* — the member said it — is stamped `subject`, so a later service
#: provision cannot lift a relayed withdrawal (`D-15c`).
#: `tests/test_consent_status_vocabulary.py` fails on a value written but not
#: declared here, and migration 0012 holds the column to this set.
CONSENT_DECIDERS: tuple[str, ...] = (
    "subject",
    "service",
    "operator",
    "collector",
)


class ContractAgreementORM(Base):
    """Persisted EDC contract agreement for PEP + audit."""

    __tablename__ = "contract_agreements"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # This runtime's own id for the agreement. EDC generates it per side, so
    # the provider and the consumer hold *different* values for one negotiation.
    agreement_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # The shared DSP agreement id — `ContractAgreement.getAgreementId()`, equal
    # on both sides. It is the only agreement identifier a counterparty can
    # name, so it is what a data-plane request carries and what
    # `/internal/dataplane/authorize` resolves.
    dsp_agreement_id: Mapped[str | None] = mapped_column(Text, index=True)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    consumer_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_id: Mapped[str] = mapped_column(Text, nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    termination_reason: Mapped[str | None] = mapped_column(Text)


class ConsentRequestORM(Base):
    """Consent request from a consumer for a data subject's data."""

    __tablename__ = "consent_requests"
    __table_args__ = (
        CheckConstraint(
            "decided_by IN ({})".format(", ".join(f"'{d}'" for d in CONSENT_DECIDERS)),
            name="ck_consent_decided_by",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)  # User DID
    consumer_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    # Purpose slugs from the ODRL profile taxonomy, validated on write.
    # An empty list is never a wildcard: for a consent-required dataset it means
    # the person was never told the use, so the row fails closed.
    purpose: Mapped[list | None] = mapped_column(JSON)  # list[str]
    # Who the data goes to. `recipient` is an owner alias — the DSP consumer,
    # ODRL 2.2's `odrl:recipient`, the DSSC data recipient. `recipient_role`
    # names which function of that entity is acting, because a controller is not
    # the same thing as a legal entity: a grid operator's grid-operations and
    # metering functions are distinct controllers under unbundling rules, and
    # `D-11` makes the role part of the consent key for exactly that reason.
    #
    # **Renamed from `controller` / `controller_role` (migration `0013`).** That
    # name meant three things at once — the recipient, the subject's home
    # organisation and the GDPR Art. 4(7) controller — and only the first reading
    # held in every offer. The subject's organisation is the *collecting*
    # organisation now, established from the caller's token at the write.
    recipient: Mapped[str | None] = mapped_column(Text)
    recipient_role: Mapped[str | None] = mapped_column(Text)
    # The sharing offer this row was created from, when it came from one.
    offer_id: Mapped[str | None] = mapped_column(Text)
    # Evidence of the legal basis under which this row was written: the DPV
    # basis IRI plus the codes + versions + hashes that prove *what* was shown
    # and agreed. Never PII — `submission_ref` only, never a name, email, CF or
    # POD. The connector DB is not a PII store.
    legal_basis: Mapped[dict | None] = mapped_column(JSON)
    message: Mapped[str | None] = mapped_column(Text)
    # One of `CONSENT_STATUSES` above — which is the declaration, not this line.
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    # Which authority took this decision — one of `CONSENT_DECIDERS` above.
    #
    # **A rule reads this column, so it is not free-text and it is not nullable.**
    # `D-15c`: a withdrawal may only be lifted by the authority that made it, and
    # before this existed the only thing telling the two apart was
    # `legal_basis["source"]` — required on the service path, absent on the
    # subject's own, and absent altogether on the bare-dataset path, which
    # therefore had no answer to give. Inferring authority from an evidence field
    # whose job is something else is how a service came to overwrite a person's
    # withdrawal with nothing refusing it (issue #34).
    #
    # Rows written before the column default to `subject`, which is the
    # fail-closed direction: an old withdrawal of unknown provenance is treated
    # as the person's own, so a provisioning call is refused rather than allowed
    # to lift it.
    decided_by: Mapped[str] = mapped_column(
        Text, nullable=False, default="subject", server_default="subject"
    )
    # The organisation (its DID) whose token registered the decision this row
    # records, when an organisation token did — an accepted collector, or this
    # connector's own organisation. Stamped server-side from the verified token,
    # like `decided_by`, on whichever row the call decides. `None` for a person's
    # own decision and for a plain service or operator.
    collector: Mapped[str | None] = mapped_column(Text)
    # The subject's **typed data keys** at this holder (`["pod:…"]`), sent with
    # a registration so the data plane can match rows without calling the
    # collector back. They are personal data, which is why they live here and
    # nowhere else: never in `legal_basis`, never in provenance (which records
    # only that keys were supplied), never in a log line. A new registration
    # replaces them; a withdrawal drops them with the grant. Sealed at rest
    # (`sealed.py`): the column holds ciphertext, the attribute the list.
    subject_keys: Mapped[list | None] = mapped_column(SealedJSON)  # list[str]
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_url: Mapped[str | None] = mapped_column(Text)  # webhook target
    transfer_ids: Mapped[list | None] = mapped_column(JSON)  # list[str]
    # The negotiation this ask is blocking, when it came from the pending guard.
    #
    # `negotiation_id` is *this* connector's id for it — what the resume call
    # needs, since only the provider's own control plane can clear `pending`.
    # `correlation_id` is the counterparty's id for the same negotiation, and is
    # therefore the only handle the consumer can ask about (§6.6). Keeping both
    # is what lets the provider answer "is this negotiation waiting on a person"
    # without the consumer ever learning a provider-side identifier.
    negotiation_id: Mapped[str | None] = mapped_column(Text, index=True)
    correlation_id: Mapped[str | None] = mapped_column(Text, index=True)
    # When this ask stopped blocking anything, because the negotiation it was
    # raised for was terminated. It is what stops the TTL sweep retrying a
    # negotiation it has already dealt with: without it, "dead" is a property of
    # the consent rows alone, which stays true forever once it becomes true.
    negotiation_closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # **Not a column.** The authority that just replaced this row's keys, for the
    # key ledger's `key_change` entries (`db/key_ledger.py`). A key update leaves
    # `decided_by` alone, since it still names who *granted* and `D-15c` reads it;
    # the ledger still has to say who changed the keys. Set by the write path,
    # read and cleared by the flush listener.
    key_change_by = None


class ConsumerTransferORM(Base):
    """Transfer ownership for user-scoped consumer views."""

    __tablename__ = "consumer_transfers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    transfer_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    contract_agreement_id: Mapped[str] = mapped_column(Text, nullable=False)
    consumer_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConsumerAccessRequestORM(Base):
    """User-scoped access request started from the consumer catalogue."""

    __tablename__ = "consumer_access_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    counter_party_address: Mapped[str] = mapped_column(Text, nullable=False)
    offer_id: Mapped[str] = mapped_column(Text, nullable=False)
    assigner: Mapped[str] = mapped_column(Text, nullable=False)
    negotiation_id: Mapped[str | None] = mapped_column(Text, unique=True)
    contract_agreement_id: Mapped[str | None] = mapped_column(Text)
    transfer_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="negotiating")
    # The consumer's declared intent. Distinct from the offer's permitted
    # purposes, which live in the agreement policy: an offer saying "any of
    # these three" cannot answer why *this* request was made. Nullable because
    # declaring is optional — a request made before this existed, or by a caller
    # that says nothing, is recorded honestly as undeclared rather than
    # backfilled with the offer's set, which would invent a statement nobody made.
    declared_purpose: Mapped[list | None] = mapped_column(JSON)
    declared_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declared_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # An opaque external reference (ticket, document id) — never free text, and
    # never PII. See `NegotiateRequest._no_obvious_pii`.
    justification_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EdrEntryORM(Base):
    """The EDR of a transfer this connector started, as its EDC delivered it.

    EDC 0.18.0's v5 management API has no EDR endpoint (DR
    ``2026-04-09-edr-cache-deprecation``). The EDR arrives in the
    ``TransferProcessStarted`` event posted to the transfer's callback address
    (``POST /webhooks/edc-callback``) and is kept here, keyed by the transfer.

    ``data_address`` is the address **as delivered**, not a projection of it: a
    later DPS data plane on the consumer side reads the same event, and a data
    address that is not HTTP-pull does not fit ``endpoint``/``authorization``.
    ``authorization`` is a live bearer for the provider's data plane — treat the
    table like the vault EDC used to hold it in. That is why ``authorization``
    and ``data_address`` (which carries the same bearer) are sealed at rest
    (`sealed.py`); EDC's own cache keeps an EDR in its vault for the same
    reason (``VaultEndpointDataReferenceCache``).
    """

    __tablename__ = "edr_entries"

    transfer_id: Mapped[str] = mapped_column(Text, primary_key=True)
    participant_context_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    agreement_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    auth_type: Mapped[str] = mapped_column(Text, nullable=False, default="bearer")
    authorization: Mapped[str] = mapped_column(SealedText, nullable=False)
    data_address: Mapped[dict] = mapped_column(SealedJSON, nullable=False)
    event_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


#: What happened to a key in a decision, and why. `added`/`removed` say whether
#: the decision started or stopped carrying the key while granted; the cause says
#: which act moved it. Declared once, like `CONSENT_STATUSES`.
KEY_EVENTS: tuple[str, ...] = ("added", "removed")
#: `holder_suspension` / `suspension_lifted` are the holder's own act on a key
#: (ADR-0027) and say nothing about the decision: the decision still carries the
#: key, the data plane does not serve it while it is suspended.
KEY_EVENT_CAUSES: tuple[str, ...] = (
    "grant",
    "withdrawal",
    "key_change",
    "backfill",
    "holder_suspension",
    "suspension_lifted",
)
#: The causes that move what a decision *carries*. The two holder causes above
#: are not among them, so "is this key still carried by a grant" reads past them.
DECISION_KEY_CAUSES: tuple[str, ...] = ("grant", "withdrawal", "key_change", "backfill")


class ConsentKeyEventORM(Base):
    """One key a granted decision started or stopped carrying (ADR-0022).

    The holder's history of the keys its data plane filters on. The consent rows
    cannot give it: a withdrawal drops `subject_keys` from the row and a new
    registration replaces them in place, and provenance carries no personal data
    (`L-3`). So every change is appended here, by `db/key_ledger.py`, in the flush
    that changes the row — it cannot drift from the rows, and no write path has
    to remember it.

    **No subject id.** The holder reads keys, never who stands behind them.
    `consent_id` ties the entry to its decision row and is never returned by a
    route. **Erasing the row does not erase its history** (ADR-0027, amending
    ADR-0022): the reference becomes null (`ON DELETE SET NULL`) and the entry is
    kept for the key-record retention period, the evidence of what was released
    on whose assertion (GDPR Art. 17(3)(e)); `connector.db.retention` purges it
    after that period and not before.

    ``assertion_ref`` names the collector's key assertion the decision carried
    when the entry was written (`consent_key_assertions`).
    """

    __tablename__ = "consent_key_events"
    __table_args__ = (
        CheckConstraint(
            "event IN ({})".format(", ".join(f"'{e}'" for e in KEY_EVENTS)),
            name="ck_consent_key_event",
        ),
        CheckConstraint(
            "cause IN ({})".format(", ".join(f"'{c}'" for c in KEY_EVENT_CAUSES)),
            name="ck_consent_key_event_cause",
        ),
        Index("ix_consent_key_events_offer_at", "offer_id", "at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    consent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("consent_requests.id", ondelete="SET NULL"), nullable=True
    )
    offer_id: Mapped[str | None] = mapped_column(Text)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    consumer_id: Mapped[str] = mapped_column(Text, nullable=False)
    #: The key, sealed (`sealed.py`). Never compared in SQL: a ciphertext is
    #: randomised. Equality lookups — and any uniqueness rule on a key — go
    #: through ``key_index``, which is set from it on every assignment.
    key: Mapped[str] = mapped_column(SealedText, nullable=False)
    key_index: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    cause: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str | None] = mapped_column(Text)
    collector: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assertion_ref: Mapped[str | None] = mapped_column(String(64))
    # Only so the unit of work inserts the decision row before its entries: a
    # bare foreign key does not order a flush, and Postgres enforces it. Never
    # read — `lazy="raise"` makes an accidental load an error, not a query.
    decision: Mapped[ConsentRequestORM] = relationship(lazy="raise")

    @validates("key")
    def _index_key(self, _name: str, value: str) -> str:
        self.key_index = blind_index(value)
        return value


class ConsentKeyAssertionORM(Base):
    """A collector's assertion that the keys it registered are its member's (ADR-0027).

    The same record is stored inside the decision's ``legal_basis`` and carried
    by its ``ConsentGranted`` event; this copy is keyed by ``assertion_ref`` (the
    SHA-256 of its canonical JSON) so the key ledger and the key owners can
    point at it, and so it **outlives an erased decision row** for the
    key-record retention period. Codes and hashes only — no fiscal code, no POD,
    no name (the model that admits it is ``extra="forbid"``).
    """

    __tablename__ = "consent_key_assertions"

    assertion_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    assertion: Mapped[dict] = mapped_column(JSON, nullable=False)
    collector: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ConsentKeyOwnerORM(Base):
    """Which subject a ``pod:`` key belongs to at this holder (ADR-0027).

    **One active owner per key**: a partial unique index on ``key_index`` where
    ``released_at`` is null. A second subject registering the same key is a
    ``409``; the same subject re-registering it is not. The row is released when
    the last grant carrying the key ends, and kept for the key-record retention
    period after that. Keyed by the blind index, never the key.
    """

    __tablename__ = "consent_key_owners"
    __table_args__ = (
        Index(
            "ux_consent_key_owners_active",
            "key_index",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
            sqlite_where=text("released_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    key_index: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    collector: Mapped[str | None] = mapped_column(Text)
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assertion_ref: Mapped[str | None] = mapped_column(String(64))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


#: Why a holder may suspend a key. One reason today; a new one is a decision.
KEY_SUSPENSION_REASONS: tuple[str, ...] = ("holder_change",)


class ConsentKeySuspensionORM(Base):
    """A holder took a key out of the set its data plane serves (ADR-0027).

    Active while ``lifted_at`` is null — at most one per key (partial unique
    index). Lifted only by a grant whose ``key_assertion.verified_at`` is later
    than ``suspended_at``; ``lifted_by_assertion_ref`` names that assertion.
    """

    __tablename__ = "consent_key_suspensions"
    __table_args__ = (
        CheckConstraint(
            "reason IN ({})".format(
                ", ".join(f"'{r}'" for r in KEY_SUSPENSION_REASONS)
            ),
            name="ck_consent_key_suspension_reason",
        ),
        Index(
            "ux_consent_key_suspensions_active",
            "key_index",
            unique=True,
            postgresql_where=text("lifted_at IS NULL"),
            sqlite_where=text("lifted_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    key_index: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    suspended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    acted_by: Mapped[dict | None] = mapped_column(JSON)
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifted_by_assertion_ref: Mapped[str | None] = mapped_column(String(64))


# The ledger's writer listens on every flush; importing it here is what makes it
# impossible to load the models without it.
from . import key_ledger  # noqa: E402, F401
