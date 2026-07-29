"""Sharing offers — what a person is actually asked to consent to.

A person does not consent to a dataset.  They consent to a **purpose-scoped
bundle, from a named controller, for a described category of recipient**.  This
module models that bundle, loads it from YAML with the same overlay mechanism
``governance.yaml`` uses, and derives the hash that decides whether a change is
material enough to require re-consent.

The schema is domain-neutral.  The purposes, measures and recipient categories
a deployment actually uses live in its ODRL profile and its offer file.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# ISO 8601 durations, the only shape the platform serves for coverage windows,
# retention and resolution.  Weeks (``P4W``) are mutually exclusive with the
# other designators, hence the alternation.
_ISO_DURATION = re.compile(
    r"^P(?!$)(\d+Y)?(\d+M)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+(\.\d+)?S)?)?$|^P\d+W$"
)

# DPV legal bases the platform recognises.  ``Consent`` is the only one that
# gets a toggle in a frontend; the others are disclosed, not asked.
DPV_LEGAL_BASES = (
    "https://w3id.org/dpv#Consent",
    "https://w3id.org/dpv#Contract",
    "https://w3id.org/dpv#LegitimateInterest",
    "https://w3id.org/dpv#LegalObligation",
    "https://w3id.org/dpv#PublicInterest",
    "https://w3id.org/dpv#VitalInterest",
)

CONSENT_BASIS = "https://w3id.org/dpv#Consent"

SUBJECT_SCOPES = ("own_data", "household", "community")


def is_iso_duration(value: str) -> bool:
    """True when *value* is a well-formed ISO 8601 duration (``P1Y``, ``PT15M``)."""
    return bool(value) and bool(_ISO_DURATION.match(value.strip()))


class OfferCoverage(BaseModel):
    """How far back and how far forward the sharing reaches."""

    retrospective: str | None = None   # ISO 8601, e.g. P1Y
    prospective: str | None = None     # ISO 8601, e.g. P2Y


class ProcessorCategory(BaseModel):
    """A *category* of recipient, not a list of names.

    Processors act on the controller's instructions under a DPA (GDPR Art. 28),
    so a new one joining the category is disclosed rather than re-consented.
    ``admitted_by`` is what makes the category checkable instead of a promise:
    each entry is a constraint the platform can evaluate at negotiation time.
    """

    category: str
    admitted_by: list[dict[str, Any]] = Field(default_factory=list)


class OfferRecipients(BaseModel):
    """Who may receive the data, and in what capacity.

    Independent controllers are never listed here — each one is its own offer,
    because consent under Art. 4(11) is consent to a *specific* controller's
    processing.  ``controller_role`` names which role of that participant is
    acting: a DSO's grid-operations and metering functions are different
    controllers under unbundling rules, same legal entity.
    """

    controller: str                      # owner alias
    controller_role: str | None = None   # one of that participant's roles
    processors: ProcessorCategory


class SharingOffer(BaseModel):
    """One consentable bundle.

    An offer does **not** name its datasets. The dataset names the offer, via
    ``dataspace.sharing_offers[]`` — see :class:`DataspaceSpec`. A file still
    declaring ``datasets:`` here is rejected on load rather than ignored: two
    homes for one fact is the failure this codebase has hit twice silently, and
    an ignored key looks like it worked.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    purpose: str                       # slug, must exist in the ODRL profile
    legal_basis: str                   # DPV legal-basis IRI
    recipients: OfferRecipients
    subject_scope: str = "own_data"
    measures: list[str] = Field(default_factory=list)
    resolution: str | None = None      # ISO 8601, e.g. PT15M
    coverage: OfferCoverage = Field(default_factory=OfferCoverage)
    consent_text_version: str = "1.0"
    revocable: bool = True
    retention: str | None = None

    @property
    def requires_consent(self) -> bool:
        """Only consent-based offers get a control in a frontend.

        Asking for consent where contractual necessity applies implies a choice
        that does not exist, which EDPB guidance treats as invalidating.
        """
        return self.legal_basis == CONSENT_BASIS

    def user_visible_facts(self, broader_chain: list[str] | None = None) -> dict[str, Any]:
        """The facts a person actually read, in canonical form.

        Which datasets back an offer is deliberately absent — that is a
        schema-migration concern the person was never shown, so changing it must
        not invalidate consent.  It is now a property of the *datasets*, which
        makes the exclusion structural rather than a rule to remember.
        Everything else here was on screen.
        """
        return {
            "purpose": self.purpose,
            "purpose_broader": list(broader_chain or []),
            "legal_basis": self.legal_basis,
            "controller": self.recipients.controller,
            "controller_role": self.recipients.controller_role,
            "processor_category": self.recipients.processors.category,
            "subject_scope": self.subject_scope,
            "measures": sorted(self.measures),
            "resolution": self.resolution,
            "coverage": {
                "retrospective": self.coverage.retrospective,
                "prospective": self.coverage.prospective,
            },
            "retention": self.retention,
            "revocable": self.revocable,
        }

    def user_visible_hash(self, broader_chain: list[str] | None = None) -> str:
        """SHA-256 over :meth:`user_visible_facts` — the re-consent trigger.

        Stable across a no-op reload: the payload is sorted-key JSON with no
        timestamps, so a redeploy of an unchanged offer produces the same hash
        and no re-consent storm.
        """
        payload = json.dumps(
            self.user_visible_facts(broader_chain),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SharingOfferCatalogue(BaseModel):
    """The loaded set of offers, indexed by id."""

    offers: list[SharingOffer] = Field(default_factory=list)

    @property
    def by_id(self) -> dict[str, SharingOffer]:
        return {offer.id: offer for offer in self.offers}

    def get(self, offer_id: str) -> SharingOffer | None:
        return self.by_id.get(offer_id)

    def consent_based(self) -> list[SharingOffer]:
        return [offer for offer in self.offers if offer.requires_consent]


def datasets_by_offer(
    sharing_offers_by_dataset: Mapping[str, Sequence[str]],
) -> dict[str, list[str]]:
    """Reverse the declaration: offer id → the dataset keys that name it.

    The dataset → offer direction is the one authored and the one enforced, but
    two paths genuinely need the reverse — expanding an offer into per-dataset
    consent rows, and reporting how many datasets an offer reaches. Deriving it
    here keeps that a *view*: there is still exactly one place the fact is
    written down.

    Order follows dataset declaration order, and duplicates within one dataset
    collapse, so the result is stable across reloads — a consent expansion that
    reordered between syncs would produce gratuitous row churn.
    """
    index: dict[str, list[str]] = {}
    for dataset_key, offer_ids in sharing_offers_by_dataset.items():
        for offer_id in dict.fromkeys(offer_ids):
            index.setdefault(offer_id, []).append(dataset_key)
    return index


def _parse(raw: dict[str, Any]) -> SharingOfferCatalogue:
    entries = raw.get("sharing_offers") or []
    return SharingOfferCatalogue(
        offers=[SharingOffer.model_validate(entry) for entry in entries if entry]
    )


def load_sharing_offers(
    path: Path | str | None,
    overlay_name: str | None = None,
) -> SharingOfferCatalogue:
    """Load ``sharing-offers.yaml``, merging ``sharing-offers.<overlay>.yaml``.

    Mirrors ``GovernanceResolver.from_file_with_override``: the overlay replaces
    offers with the same id and appends new ones, so a deployment can rebind a
    controller without forking the base file.  A missing base file yields an
    empty catalogue — a deployment with no offers is valid, it simply has
    nothing to ask.
    """
    if path is None:
        return SharingOfferCatalogue()
    base_path = Path(path)
    if not base_path.exists():
        logger.debug("No sharing offers file at %s — empty catalogue", base_path)
        return SharingOfferCatalogue()

    with base_path.open("r", encoding="utf-8") as f:
        catalogue = _parse(yaml.safe_load(f) or {})

    name = overlay_name or os.getenv("SHARING_OFFERS_OVERLAY_NAME")
    if not name:
        return catalogue

    overlay_path = base_path.parent / f"sharing-offers.{name}.yaml"
    if not overlay_path.exists():
        return catalogue
    with overlay_path.open("r", encoding="utf-8") as f:
        overlay = _parse(yaml.safe_load(f) or {})

    merged = {offer.id: offer for offer in catalogue.offers}
    merged.update({offer.id: offer for offer in overlay.offers})
    return SharingOfferCatalogue(offers=list(merged.values()))
