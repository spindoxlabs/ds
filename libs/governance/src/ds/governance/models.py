"""Governance v2 Pydantic models.

Fully backward-compatible with the legacy GovernanceRule (v1).
New fields are optional with safe defaults — v1 YAML files load unchanged.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ── v1 (unchanged) ────────────────────────────────────────────────────────────

class GovernanceOwner(BaseModel):
    name: str
    type: str = "OWNER"


class RowFilterArgs(BaseModel):
    """Arguments for one row-filter handler.

    `extra="allow"`: `column` is the only argument every handler in use takes,
    but a handler defines its own and governance is not the place that knows
    them — `rec_registry` reads a `urn_template` in the FIWARE adapter. Dropping
    an unrecognised argument here silently truncates it out of the
    `DataplaneRowFilter` the PDP puts on the wire, leaving the handler to run
    with a missing input. For `rec_registry` that resolves to an empty device
    set, which the adapter reads as *deny* — a correctly-configured dataset
    refused because a model narrower than its input threw the rest away.
    """

    model_config = ConfigDict(extra="allow")

    column: str


class RowFilter(BaseModel):
    handler: str
    args: RowFilterArgs


class GovernanceRule(BaseModel):
    """v1 governance rule — mirrors the legacy GovernanceRule exactly."""

    title: str | None = None
    description: str | None = None
    license: str | None = None
    attribution: str | None = None
    ownership: list[GovernanceOwner] = Field(default_factory=list)
    access_level: str | None = None        # open | internal | restricted | secret
    access_requirements: str | None = None # kept for backward compat
    classification: str | None = None      # pii | green | yellow | red
    tags: list[str] = Field(default_factory=list)
    retention_days: int | None = None
    documentation_url: str | None = None
    source_system: str | None = None
    # **Legacy.** `celine-utils/schema/governance.schema.json` — the canonical
    # authoring schema — defines `row_filters` and *not* this field. The real
    # dataset-api agrees: `row_filters/specs.py` documents `userFilterColumn`
    # as legacy and migrates it into `{handler: direct_user_match, args: {column}}`.
    #
    # Kept because deployed governance files still use it. Never read it
    # directly — call `subject_column(rule)`, which normalises both spellings.
    # Reading one spelling is how a correctly-configured dataset gets refused
    # (or, worse, served unfiltered).
    user_filter_column: str | None = None
    row_filters: list["RowFilter"] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


# ── v2 extensions ─────────────────────────────────────────────────────────────

class PolicyObligations(BaseModel):
    attribution: bool = False
    delete_after_days: int | None = None   # overrides retention_days for ODRL
    notify_on_access: bool = False
    anonymize_before_use: bool = False
    contract_required: bool = False        # auto True when access_level=restricted


class PolicyAudience(BaseModel):
    membership: str | None = "dataspaces.localhost"
    required_role: str | None = None
    required_scope: str = "dataspaces.query"


class PolicyConsent(BaseModel):
    required: bool = False           # auto True when user_filter_column is set
    scope: str = "per_subject"       # per_subject | per_dataset
    on_revocation: str = "terminate" # terminate | suspend


class DataspacePolicy(BaseModel):
    permitted_actions: list[str] | None = None   # None = auto-derive from access_level
    prohibited_actions: list[str] | None = None  # None = auto-derive from classification
    purpose: list[str] = Field(default_factory=list)
    valid_from: date | None = None
    valid_until: date | None = None
    obligations: PolicyObligations = Field(default_factory=PolicyObligations)
    audience: PolicyAudience = Field(default_factory=PolicyAudience)
    consent: PolicyConsent = Field(default_factory=PolicyConsent)


class DataspaceAsset(BaseModel):
    id: str | None = None
    content_type: str = "application/json"


class DataspaceDataAddress(BaseModel):
    type: str = "HttpData"
    base_url: str = "http://dataset-api:30002"
    proxy_path: bool = True
    proxy_query_params: bool = True
    query_params: dict[str, str] = Field(default_factory=dict)


class DataspaceContract(BaseModel):
    access_policy_id: str | None = None
    contract_policy_id: str | None = None
    #: The EDC ContractDefinition's own `@id`.
    #:
    #: Separate from `access_policy_id` since `GOV-12`: the contract definition
    #: used to *be* the access policy id, so a deployment that named one named
    #: both and the id stopped identifying which entity was meant. Unset, the
    #: mapper derives `<dataset-key>-contract`.
    contract_definition_id: str | None = None


class DataspaceSpec(BaseModel):
    expose: bool = False
    medallion: str | None = None   # bronze | silver | gold — inferred from key if None
    asset: DataspaceAsset = Field(default_factory=DataspaceAsset)
    data_address: DataspaceDataAddress = Field(default_factory=DataspaceDataAddress)
    contract: DataspaceContract = Field(default_factory=DataspaceContract)

    # Sharing offers this dataset is consentable under, by id.
    #
    # **The dataset points at the offer, never the reverse.** Offers are declared
    # by the producer that declares the dataset, in files beside it, so an offer
    # naming arbitrary dataset keys would let one producer write the consent text
    # for another producer's data. Here, only whoever declares the dataset can
    # bind an offer to it.
    #
    # An id that does not resolve means the dataset is **not exposed** — "no
    # sharing offer" and "not shared" are the same statement, and publishing it
    # with a dangling reference would advertise a consent gate that can never open.
    sharing_offers: list[str] = Field(default_factory=list)


class TemporalCoverage(BaseModel):
    """`dct:temporal` — the period the data covers, not the period it is offered."""

    start: str | None = None
    end: str | None = None


class DcatSpec(BaseModel):
    """DCAT-AP metadata for catalogue exposition — the canonical `dcat:` block.

    **This mirrors `dcatConfig` in `schemas/governance.schema.json` field for
    field, and that is a constraint rather than a coincidence.** That schema is
    defined by celine-utils and only cached here (`schemas/README.md`), so a
    field added on this side would be one this platform reads and no producer can
    validate against before authoring. Extending the shape means extending it
    upstream first.

    Every one of these was **received and never read** until this model existed.
    The schema has declared the block since before ds read any of it, and
    `GovernanceRuleV2` carried no `dcat` field — so the resolver swept it into
    `extra`, where it survived as an untyped dict that nothing looked at, and
    `compliance/evidence.py` emitted a DCAT dataset missing all of it. A producer
    authoring against the published schema got a valid file and no effect, which
    is worse than a rejection: a rejection is a message.

    Worth being precise about, because *"the data was lost"* would suggest the fix
    is to stop dropping it. It was never dropped. `extra` is the catch-all for
    keys ds does not model, and the defect was modelling nothing — so the fix is a
    typed field plus a reader, and `extra` correctly stops carrying it.

    ``conforms_to`` is a **single string** because that is what the canonical
    schema says (*"URI of a standard or specification the dataset conforms to"*).
    A dataset conforming to several models is a real case and a real limitation;
    widening it to a list is a celine-utils change, not a divergence to ship
    here. See `.agents/semantic-vocabulary.plan.md` decision `V-1`.
    """

    publisher_uri: str | None = None
    themes: list[str] = Field(default_factory=list)
    language_uris: list[str] = Field(default_factory=list)
    spatial_uris: list[str] = Field(default_factory=list)
    accrual_periodicity: str | None = None
    # The payload semantic model — SAREF, CIM, COSEM. Resolved against the
    # vocabulary registry (`vocabularies.py`) and served from `/ns/{slug}` when a
    # local copy exists. Rulebook `M-4`, `M-7`.
    conforms_to: str | None = None
    temporal: TemporalCoverage | None = None


class GovernanceRuleV2(GovernanceRule):
    """v2 governance rule — extends v1 with ODRL policy and EDC dataspace config."""

    policy: DataspacePolicy = Field(default_factory=DataspacePolicy)
    dataspace: DataspaceSpec = Field(default_factory=DataspaceSpec)
    dcat: DcatSpec = Field(default_factory=DcatSpec)


# ── ODRL Profile ─────────────────────────────────────────────────────────────

# The five SKOS mapping properties.  Only these may appear as a
# ``dpv_mapping.relation`` — anything else is a false interop claim.
SKOS_MATCH_RELATIONS = (
    "exactMatch",
    "broadMatch",
    "closeMatch",
    "narrowMatch",
    "relatedMatch",
)


class DpvMapping(BaseModel):
    """Alignment of a local purpose to an external vocabulary term (DPV).

    Documentation and interop only.  ``odrl:isA`` matching never follows this
    mapping — see :meth:`OdrlProfile.is_a`.  A mapping that claims
    ``exactMatch`` where the terms merely overlap would silently widen consent.
    """

    iri: str
    relation: str = "broadMatch"


class PurposeConcept(BaseModel):
    """A purpose concept in the ODRL profile taxonomy.

    ``broader`` builds the *local* hierarchy, which is the only thing
    enforcement looks at.  ``dpv_mapping`` records how the concept relates to
    an external vocabulary and is served for readers, never matched against.
    """

    slug: str
    label: str
    definition: str = ""
    broader: str | None = None
    dpv_mapping: DpvMapping | None = None


class OdrlProfile(BaseModel):
    """Configurable ODRL namespace profile.

    Deployers override via environment or config file to use their own
    namespace (e.g. Catena-X ``cx-policy:``), purpose taxonomy, and
    tag→purpose mapping.  The default profile ships empty — no
    domain-specific concepts are assumed.
    """

    namespace: str = "https://w3id.org/dsp/policy/"
    prefix: str = "dsp-policy"

    membership_operand: str = "Membership"
    consent_operand: str = "ConsentStatus"

    query_action: str = "Query"

    # A path segment, NOT a pseudo-prefix. `purpose:` would make purpose IRIs
    # compact to `purpose:Slug`, which JSON-LD rejects as confusable with a
    # compact IRI (IRI_CONFUSED_WITH_PREFIX) — the DSP catalogue response then
    # fails to serialise. See check_purpose_taxonomy, which enforces this.
    purpose_base: str = "purpose/"

    profile_iri: str | None = None

    #: The profile's version, carried into every offer this profile generates.
    #:
    #: `GOV-08`. Nothing in an emitted offer said which version of the policy
    #: vocabulary produced it, so a consumer holding an agreement could not ask
    #: what the terms meant when they negotiated, and a provider changing the
    #: profile could not tell which agreements predate the change. The rulebook
    #: files that under *metadata versioning*, and names this the smallest
    #: concrete piece of it.
    #:
    #: **Metadata, never a constraint.** It is emitted beside `@context`, not as
    #: an `odrl:constraint`, so it claims nothing about enforcement — the
    #: distinction `GOV-04` and `GOV-10` both turn on. A counterparty reads it;
    #: no policy engine evaluates it.
    #:
    #: Unset, no version key is emitted at all: an offer that names a version it
    #: does not have would be worse than one that stays silent.
    version: str | None = None

    tag_to_purpose: dict[str, str] = Field(default_factory=dict)
    purposes: list[PurposeConcept] = Field(default_factory=list)

    def term(self, local_name: str) -> str:
        """Build a full IRI from a local name."""
        return f"{self.namespace}{local_name}"

    def purpose_iri(self, slug: str) -> str:
        """Build a purpose IRI from a slug (e.g. ``EnergyBalancing``)."""
        return f"{self.namespace}{self.purpose_base}{slug}"

    # ── Purpose taxonomy ──────────────────────────────────────────────────

    @property
    def purpose_index(self) -> dict[str, PurposeConcept]:
        return {concept.slug: concept for concept in self.purposes}

    def purpose_slug(self, value: str) -> str | None:
        """Normalise a purpose reference to a slug known to this profile.

        Accepts a bare slug, a full profile IRI, or the ``{prefix}:{base}slug``
        compact form.  Returns ``None`` when the value is not in the taxonomy —
        callers treat that as a validation failure, never as a wildcard.
        """
        if not value:
            return None
        candidate = value.strip()
        for prefix in (
            f"{self.namespace}{self.purpose_base}",
            f"{self.prefix}:{self.purpose_base}",
            self.purpose_base,
        ):
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):]
                break
        return candidate if candidate in self.purpose_index else None

    def broader_chain(self, slug: str) -> list[str]:
        """Return ``[slug, parent, grandparent, …]`` following local ``broader``.

        Stops at an unknown or repeated slug, so a malformed profile degrades to
        a short chain instead of looping.  Cycles are reported by the
        ``purpose-hierarchy`` compliance check, not raised here.
        """
        index = self.purpose_index
        chain: list[str] = []
        seen: set[str] = set()
        current: str | None = slug
        while current and current in index and current not in seen:
            chain.append(current)
            seen.add(current)
            current = index[current].broader
        return chain

    def is_a(self, requested: str, consented: str) -> bool:
        """``odrl:isA`` — is *requested* the consented purpose or narrower?

        Matching follows **only** the local ``broader`` chain.  ``dpv_mapping``
        is deliberately not consulted: a ``broadMatch`` to a generic DPV term
        would otherwise let an unrelated use match a specific consent.
        """
        requested_slug = self.purpose_slug(requested)
        consented_slug = self.purpose_slug(consented)
        if not requested_slug or not consented_slug:
            return False
        return consented_slug in self.broader_chain(requested_slug)


_PROFILES_DIR = Path(__file__).parent / "profiles"
_DEFAULT_PROFILE_PATH = _PROFILES_DIR / "energy.yaml"


def profile_path_is_missing(path: Path | str | None) -> bool:
    """True when a profile path was *configured* and is not there.

    Separated out so a caller can register the condition with a startup guard —
    the fallback below is silent by design at import time, and a deployment that
    set the path wants to know at boot rather than at the first sync.
    """
    return bool(path) and not Path(path).exists()


def load_odrl_profile(path: Path | str | None = None) -> OdrlProfile:
    """Load an OdrlProfile from a YAML file.

    When *path* is ``None``, loads the bundled energy profile (platform default).
    When the file at *path* does not exist, falls back to the energy default —
    **loudly**, because that fallback is otherwise invisible and expensive.

    A typo'd ``CONNECTOR_ODRL_PROFILE_PATH`` silently yields the *platform*
    vocabulary. Every purpose the deployer declared then fails to resolve, and
    since the sync now refuses a dataset whose purpose does not resolve, the
    whole catalogue stops publishing — for a reason nothing would have reported
    at ``debug``. An explicitly configured path that is absent is a
    misconfiguration, not a default.
    """
    p = Path(path) if path is not None else _DEFAULT_PROFILE_PATH
    if not p.exists():
        if path is not None:
            logger.warning(
                "ODRL profile not found at %s — falling back to the bundled energy "
                "profile. Purposes declared against your own profile will not "
                "resolve and their datasets will not publish.",
                p,
            )
        else:
            logger.debug("ODRL profile not found at %s — falling back to energy default", p)
        p = _DEFAULT_PROFILE_PATH
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    logger.debug("Loaded ODRL profile from %s", p)
    return OdrlProfile.model_validate(raw)


def subject_column(rule: "GovernanceRule | GovernanceRuleV2") -> str | None:
    """The column carrying the data subject, however governance spelled it.

    Two spellings are in use and both are legitimate input:

    - `row_filters[].args.column` — canonical, and what
      `celine-utils/schema/governance.schema.json` defines;
    - `user_filter_column` — legacy, still present in deployed files.

    Mirrors `get_row_filter_specs` in the real dataset-api, which treats the
    second as legacy input to the first. Every consumer of this fact — the ODRL
    mapper, the connector's data-plane authorisation — must go through here,
    because the two readings disagree exactly where it matters: a consent-gated
    dataset declared canonically has no `user_filter_column`, and a reader that
    only knows that field concludes there is nothing to filter on.

    **Canonical wins** (`GOV-05`). This function read `user_filter_column`
    *first* until 2026-08-06 — contradicting the paragraph above, and
    contradicting `GovernanceMapper.to_asset_create`, which has always preferred
    `row_filters[0]`. A rule declaring both therefore published one column to EDC
    as `{prefix}:userFilterColumn` and reported the other to every
    `/internal/dataplane/authorize` decision: the catalogue described a filter on
    one column while the data plane filtered on another.

    The tie-break is not this repository's to invent. `get_row_filter_specs` in
    the real dataset-api appends the `row_filters` entries first and *then*
    migrates the legacy column in behind them, so the canonical spelling leads.
    The defect ledger recorded this row as an inversion in the mapper; the mapper
    was the half that already agreed with the data plane.
    """
    for row_filter in getattr(rule, "row_filters", None) or []:
        args = getattr(row_filter, "args", None)
        # A model when parsed from governance YAML, a plain dict when a rule is
        # built by hand in a test or a fixture.
        column = args.get("column") if isinstance(args, dict) else getattr(args, "column", None)
        if column:
            return str(column)
    if getattr(rule, "user_filter_column", None):
        return rule.user_filter_column
    return None
