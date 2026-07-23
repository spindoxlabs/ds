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
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── v1 (unchanged) ────────────────────────────────────────────────────────────

class GovernanceOwner(BaseModel):
    name: str
    type: str = "OWNER"


class RowFilterArgs(BaseModel):
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


class DataspaceSpec(BaseModel):
    expose: bool = False
    medallion: str | None = None   # bronze | silver | gold — inferred from key if None
    asset: DataspaceAsset = Field(default_factory=DataspaceAsset)
    data_address: DataspaceDataAddress = Field(default_factory=DataspaceDataAddress)
    contract: DataspaceContract = Field(default_factory=DataspaceContract)


class GovernanceRuleV2(GovernanceRule):
    """v2 governance rule — extends v1 with ODRL policy and EDC dataspace config."""

    policy: DataspacePolicy = Field(default_factory=DataspacePolicy)
    dataspace: DataspaceSpec = Field(default_factory=DataspaceSpec)


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


def load_odrl_profile(path: Path | str | None = None) -> OdrlProfile:
    """Load an OdrlProfile from a YAML file.

    When *path* is ``None``, loads the bundled energy profile (platform default).
    When the file at *path* does not exist, falls back to the energy default.
    """
    p = Path(path) if path is not None else _DEFAULT_PROFILE_PATH
    if not p.exists():
        logger.debug("ODRL profile not found at %s — falling back to energy default", p)
        p = _DEFAULT_PROFILE_PATH
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    logger.debug("Loaded ODRL profile from %s", p)
    return OdrlProfile.model_validate(raw)
