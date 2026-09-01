"""Governance models — the shared shape from upstream, ds's own on top of it.

**`celine.governance` defines the grammar of `governance.yaml`; this module adds
what is ds's** (`ADR-0013`). Until 2026-09-01 it restated the whole shape, and the
restatement was a subset: pydantic drops what a model does not declare, so a field
ds did not know about lost its meaning rather than being carried. `expose`,
`ontology` and `dataspace.odrl_action` were all being received and dropped.

The split follows the rule the cached `schemas/governance.schema.json` already
follows — *the shape lives where it is defined, the use lives where it is used*:

| From `celine.governance` | Here |
|---|---|
| `GovernanceRule`, `DataspaceConfig`, `DcatConfig`, `OntologyConfig`, `GovernanceOwner`, `TemporalCoverage` | the ODRL profile and its purpose taxonomy, the `policy` view, the EDC sub-objects, `RowFilter` |

**Subclassing, not forking, and that is upstream's own design.**
`DataspaceConfig`'s docstring says the EDC sub-objects "are `ds`'s concern and are
carried in its own `DataspaceSpec` subclass"; `GovernanceRule`'s says "`ds` extends
this". Both are `extra="ignore"`, so a file may carry ds's fields without upstream's
model rejecting it, and ds's subclass sees every field upstream models.

Nothing here may import `celine.utils`. `celine.governance` is deliberately thin —
`pydantic`, `pyyaml`, `jsonschema` — and that thinness is the reason ds can take the
dependency at all; see the ADR.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import yaml
from celine.governance.models import (
    DataspaceConfig,
    DcatConfig,
)

# Re-exported under their own names — `X as X` is the explicit-re-export form, and
# it is what tells a linter these are the module's public surface rather than dead
# imports. Every one was declared in this file, field for field, until `ADR-0013`.
# Keeping the names here means no consumer of `ds.governance` had to change.
from celine.governance.models import GovernanceOwner as GovernanceOwner
from celine.governance.models import GovernanceRule as GovernanceRule
from celine.governance.models import OntologyConfig as OntologyConfig
from celine.governance.models import TemporalCoverage as TemporalCoverage
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


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


# `GovernanceRule` — upstream's, imported above. The class that stood here
# declared the same fields **minus `expose` and `ontology`**, which is the whole
# defect `ADR-0013` describes: a subset model does not fail to read a field, it
# makes the field unsayable.
#
# Two of its comments were load-bearing and now live upstream, on the fields
# themselves: `user_filter_column` is legacy and superseded by `row_filters` (never
# read it directly — call `subject_column`, which normalises both spellings and
# lets the canonical one win, `GOV-05`), and `expose` is tri-state with `None`
# meaning *not stated*.


# ── v2 extensions ─────────────────────────────────────────────────────────────


class PolicyObligations(BaseModel):
    attribution: bool = False
    delete_after_days: int | None = None  # overrides retention_days for ODRL
    notify_on_access: bool = False
    anonymize_before_use: bool = False
    contract_required: bool = False  # auto True when access_level=restricted


class PolicyAudience(BaseModel):
    membership: str | None = "dataspaces.localhost"
    required_role: str | None = None
    required_scope: str = "dataspaces.query"


class PolicyConsent(BaseModel):
    required: bool = False  # auto True when user_filter_column is set
    scope: str = "per_subject"  # per_subject | per_dataset
    on_revocation: str = "terminate"  # terminate | suspend


class DataspacePolicy(BaseModel):
    permitted_actions: list[str] | None = None  # None = auto-derive from access_level
    prohibited_actions: list[str] | None = (
        None  # None = auto-derive from classification
    )
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


class DataspaceSpec(DataspaceConfig):
    """The dataspace block — upstream's fields, plus the EDC ones that are ds's.

    Inherited and no longer restated: `expose`, `medallion`, `purpose`,
    `consent_required`, `contract_required`, `odrl_action`. The last four ds used
    to drop outright — `dataspace` is excluded from `extra`, so a file could state
    `odrl_action` and ds could not even see that it had been said.

    **`purpose`, `consent_required` and `contract_required` are carried here and
    read from `policy`.** `_canonical_policy` copies them across at parse time and
    ds's readers all go through `policy`; this model now holds them too because it
    inherits them. `resolver._merge_dataspace` applies the same union/OR rules the
    policy merge applies, so the two cannot come apart — but the duplication is
    real and temporary, and phase 2 of the migration decides which one survives.

    Added here, and staying here: the EDC-specific sub-objects. That is not ds
    asserting a boundary — it is the one upstream drew, in `DataspaceConfig`'s own
    docstring.
    """

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


class DcatSpec(DcatConfig):
    """DCAT-AP metadata for catalogue exposition — the canonical `dcat:` block.

    **Upstream's `DcatConfig`, with nothing added, and the empty body is the
    point.** This class used to mirror `dcatConfig` field for field with a comment
    saying the mirroring was a constraint: celine-utils defines the shape
    (`schemas/README.md`), so a field added on this side would be one ds reads and
    no producer could validate against before authoring. A subclass enforces what
    the comment could only ask for.

    Kept as a name rather than replaced by `DcatConfig` at every call site because
    `ds.governance.DcatSpec` is part of this library's public surface and
    `services/connector` constructs it by name.

    Every one of these fields was **received and never read** until ds modelled the
    block at all: the resolver swept `dcat:` into `extra`, where it survived as an
    untyped dict nothing looked at, and `compliance/evidence.py` emitted a DCAT
    dataset missing all of it. A producer authoring against the published schema
    got a valid file and no effect, which is worse than a rejection — a rejection
    is a message.

    `conforms_to` is a **single string** because that is what the canonical schema
    says. A dataset conforming to several models is a real case and a real
    limitation; widening it is a celine-utils change, not a divergence to ship here.
    Now that this is a subclass, that is enforced rather than merely intended.
    """


class GovernanceRuleV2(GovernanceRule):
    """Upstream's rule, extended with ds's ODRL policy view and EDC config.

    `GovernanceRule` already carries every field of the shape, `expose` and
    `ontology` included. What is added here is what upstream deliberately does not
    model — see its docstring: "`ds` extends this with `policy` (ODRL/EDC) and its
    richer `DataspaceSpec`".

    **`row_filters` is re-typed, and that is the one narrowing worth stating.**
    Upstream keeps `list[dict]`, because a handler defines its own arguments and
    governance is not the place that knows them. ds parses them into `RowFilter` /
    `RowFilterArgs` because the data-plane decision contract puts them on the wire
    (`dataplane.py`), and `RowFilterArgs` is `extra="allow"` precisely so the
    narrowing does not truncate a handler's arguments — dropping `rec_registry`'s
    `urn_template` resolves an empty device set, which the FIWARE adapter reads as
    *deny*.

    `expose` is inherited and populated, and **nothing reads it yet**. Phase 3 of
    `ADR-0013`'s migration is what calls `effective_expose` / `exposure_conflict` at
    sync time and closes
    [#20](https://github.com/spindoxlabs/ds/issues/20); until then the only gate in
    force is `dataspace.expose`, exactly as before. Carrying the value is still
    strictly better than sweeping it into `extra`: it is now visible to a reader
    and to a test, which is what the ADR is about.
    """

    # `type: ignore[assignment]` — mypy applies the Liskov rule to a mutable
    # attribute and `list[RowFilter]` is not `list[dict]`. The narrowing is the
    # point (see the docstring) and pydantic re-validates on assignment, so the
    # unsoundness mypy is guarding against cannot occur here. There is no way to
    # express a covariant model-field override; the alternative is not narrowing.
    row_filters: list[RowFilter] = Field(default_factory=list)  # type: ignore[assignment]
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
                candidate = candidate[len(prefix) :]
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
            logger.debug(
                "ODRL profile not found at %s — falling back to energy default", p
            )
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
        column = (
            args.get("column")
            if isinstance(args, dict)
            else getattr(args, "column", None)
        )
        if column:
            return str(column)
    if getattr(rule, "user_filter_column", None):
        return rule.user_filter_column
    return None
