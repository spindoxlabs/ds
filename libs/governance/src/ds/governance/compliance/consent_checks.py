"""Pre-import validation for the consent vocabulary.

Three vocabularies have to agree before a person can be asked anything
meaningful: the ODRL profile's purpose taxonomy, the datasets declared in
``governance.yaml``, and the sharing offers a frontend renders.  These checks
are what keeps them linked — every failure here is a case where a person would
have been shown a promise the platform could not enforce.

Like ``checks.py``, nothing is specific to a deployment or a domain: the
taxonomy, the offers and the owners registry are all inputs.
"""
from __future__ import annotations

from typing import Iterable

from ..models import SKOS_MATCH_RELATIONS, OdrlProfile
from ..sharing import (
    CONSENT_BASIS,
    DPV_LEGAL_BASES,
    SUBJECT_SCOPES,
    SharingOffer,
    SharingOfferCatalogue,
    is_iso_duration,
)
from .checks import DatasetEvidence, ValidationResult

CONSENT_CHECKS = (
    "purpose-iri-shape",
    "purpose-hierarchy",
    "purpose-mapping",
    "purpose-labels",
    "purpose-declared",
    "offer-purpose",
    "offer-datasets",
    "offer-consent-required",
    "offer-dataset-purpose",
    "offer-controller",
    "offer-legal-basis",
    "offer-durations",
    "offer-codes",
    "offer-hash-stability",
)


class RoleLookup:
    """Owner alias → declared roles, for ``controller_role`` validation.

    Built from whatever the caller has: the owners YAML seed, or a live
    identity-registry.  ``available`` is explicit rather than inferred from
    emptiness — "no registry to check against" (warn) and "the registry has no
    such controller" (error) are different findings, and an empty map is a
    legitimate result of the second.
    """

    def __init__(
        self,
        roles_by_alias: dict[str, list[str]] | None = None,
        available: bool = True,
    ):
        self._roles = roles_by_alias or {}
        self.available = available

    def known(self, alias: str) -> bool:
        return alias in self._roles

    def roles(self, alias: str) -> list[str]:
        return list(self._roles.get(alias) or [])


# ── Purpose taxonomy ─────────────────────────────────────────────────────────


def check_purpose_taxonomy(result: ValidationResult, profile: OdrlProfile) -> None:
    """The taxonomy must be a forest of resolvable, labelled concepts."""
    index = profile.purpose_index

    _check_purpose_iri_shape(result, profile)

    for concept in profile.purposes:
        if concept.broader:
            if concept.broader not in index:
                result.error(
                    "purpose-hierarchy",
                    f"Purpose '{concept.slug}' declares broader '{concept.broader}', "
                    "which is not in the taxonomy",
                )
            elif _has_cycle(profile, concept.slug):
                result.error(
                    "purpose-hierarchy",
                    f"Purpose '{concept.slug}' is part of a broader cycle — "
                    "odrl:isA matching would never terminate",
                )

        if not concept.label.strip():
            result.error(
                "purpose-labels",
                f"Purpose '{concept.slug}' has no English label — a frontend with no "
                "translation would render a raw slug",
            )
        elif not concept.definition.strip():
            result.warning(
                "purpose-labels",
                f"Purpose '{concept.slug}' has no English definition",
            )

        mapping = concept.dpv_mapping
        if mapping is None:
            continue
        if "://" not in mapping.iri:
            result.error(
                "purpose-mapping",
                f"Purpose '{concept.slug}' maps to '{mapping.iri}', which is not an absolute IRI",
            )
        if mapping.relation not in SKOS_MATCH_RELATIONS:
            result.error(
                "purpose-mapping",
                f"Purpose '{concept.slug}' declares relation '{mapping.relation}' — "
                f"expected one of {list(SKOS_MATCH_RELATIONS)}",
            )


def _check_purpose_iri_shape(result: ValidationResult, profile: OdrlProfile) -> None:
    """Purpose IRIs must not compact to something confusable with a compact IRI.

    A ``purpose_base`` ending in ``:`` yields ``…/policy/purpose:Slug``, which
    JSON-LD compacts to ``purpose:Slug`` — indistinguishable from a compact IRI
    with prefix ``purpose``. Titanium raises ``IRI_CONFUSED_WITH_PREFIX`` and
    the whole DSP catalogue response fails to serialise with a 500, so this is
    an error rather than a style preference.
    """
    relative = profile.purpose_base
    if ":" in relative.split("/", 1)[0]:
        result.error(
            "purpose-iri-shape",
            f"purpose_base '{relative}' makes purpose IRIs compact to "
            f"'{relative}Slug', which JSON-LD rejects as confusable with a "
            "compact IRI — use a path segment such as 'purpose/'",
        )


def _has_cycle(profile: OdrlProfile, slug: str) -> bool:
    """True when following ``broader`` from *slug* revisits a concept.

    ``broader_chain`` stops on repetition, so a cycle shows up as a chain whose
    last concept still declares a broader term.
    """
    index = profile.purpose_index
    chain = profile.broader_chain(slug)
    if not chain:
        return False
    last = index.get(chain[-1])
    return bool(last and last.broader and last.broader in chain)


def check_dataset_purposes(
    result: ValidationResult,
    exposed: list[DatasetEvidence],
    profile: OdrlProfile,
) -> None:
    """Every ``policy.purpose[]`` entry must resolve in the active profile.

    An unresolvable entry is dropped by the mapper, so the dataset would be
    offered with one constraint fewer than its author intended.
    """
    for item in exposed:
        for entry in item.rule.policy.purpose:
            if profile.purpose_slug(entry) is None and "://" not in entry:
                result.error(
                    "purpose-declared",
                    f"policy.purpose entry '{entry}' is not in the ODRL profile taxonomy",
                    item.key,
                )


# ── Sharing offers ───────────────────────────────────────────────────────────


def check_sharing_offers(
    result: ValidationResult,
    catalogue: SharingOfferCatalogue,
    exposed: list[DatasetEvidence],
    profile: OdrlProfile,
    roles: RoleLookup | None = None,
) -> None:
    """Validate the offers a person will actually be shown."""
    by_key = {item.key: item for item in exposed}
    seen_ids: set[str] = set()

    for offer in catalogue.offers:
        if offer.id in seen_ids:
            result.error("offer-purpose", f"Duplicate sharing offer id '{offer.id}'")
        seen_ids.add(offer.id)

        _check_offer_purpose(result, offer, profile)
        _check_offer_datasets(result, offer, by_key, profile)
        _check_offer_controller(result, offer, roles)
        _check_offer_legal_basis(result, offer)
        _check_offer_durations(result, offer)
        _check_offer_codes(result, offer)
        _check_offer_hash_stability(result, offer, profile)


def _check_offer_purpose(
    result: ValidationResult, offer: SharingOffer, profile: OdrlProfile
) -> None:
    if profile.purpose_slug(offer.purpose) is None:
        result.error(
            "offer-purpose",
            f"Offer '{offer.id}' declares purpose '{offer.purpose}', which is not in "
            "the ODRL profile taxonomy",
        )


def _check_offer_datasets(
    result: ValidationResult,
    offer: SharingOffer,
    by_key: dict[str, DatasetEvidence],
    profile: OdrlProfile,
) -> None:
    if not offer.datasets:
        result.warning(
            "offer-datasets",
            f"Offer '{offer.id}' resolves to no dataset — consenting to it shares nothing",
        )

    offer_slug = profile.purpose_slug(offer.purpose)

    for key in offer.datasets:
        item = by_key.get(key)
        if item is None:
            result.error(
                "offer-datasets",
                f"Offer '{offer.id}' references dataset '{key}', which is not an "
                "exposed governance key",
            )
            continue

        rule = item.rule
        if rule.classification == "pii" and not rule.policy.consent.required:
            result.error(
                "offer-consent-required",
                f"Offer '{offer.id}' reaches PII dataset '{key}', which does not set "
                "policy.consent.required — the offer promises a control that is not enforced",
            )

        if offer_slug is None:
            continue
        declared = {
            profile.purpose_slug(entry) for entry in rule.policy.purpose
        } - {None}
        if offer_slug not in declared:
            result.error(
                "offer-dataset-purpose",
                f"Offer '{offer.id}' asks for purpose '{offer_slug}' but dataset '{key}' "
                f"does not declare it in policy.purpose[] (declares: {sorted(declared)}) — "
                "the negotiated offer would deny the very use the person agreed to",
            )


def _check_offer_controller(
    result: ValidationResult, offer: SharingOffer, roles: RoleLookup | None
) -> None:
    alias = offer.recipients.controller
    if not alias.strip():
        result.error("offer-controller", f"Offer '{offer.id}' names no controller")
        return

    if roles is None or not roles.available:
        result.warning(
            "offer-controller",
            f"Offer '{offer.id}' controller '{alias}' was not checked — no owners "
            "registry available to this run",
        )
        return

    if not roles.known(alias):
        result.error(
            "offer-controller",
            f"Offer '{offer.id}' controller '{alias}' does not resolve in the owners registry",
        )
        return

    role = offer.recipients.controller_role
    declared = roles.roles(alias)
    if role and declared and role not in declared:
        result.error(
            "offer-controller",
            f"Offer '{offer.id}' declares controller_role '{role}', which is not one of "
            f"'{alias}' roles {sorted(declared)}",
        )


def _check_offer_legal_basis(result: ValidationResult, offer: SharingOffer) -> None:
    if offer.legal_basis not in DPV_LEGAL_BASES:
        result.error(
            "offer-legal-basis",
            f"Offer '{offer.id}' declares legal_basis '{offer.legal_basis}', which is not "
            "a recognised DPV legal-basis IRI",
        )
        return
    if offer.legal_basis != CONSENT_BASIS and offer.revocable:
        result.warning(
            "offer-legal-basis",
            f"Offer '{offer.id}' is not consent-based but marked revocable — a frontend "
            "would offer a control the legal basis does not support",
        )


def _check_offer_durations(result: ValidationResult, offer: SharingOffer) -> None:
    durations: Iterable[tuple[str, str | None]] = (
        ("resolution", offer.resolution),
        ("retention", offer.retention),
        ("coverage.retrospective", offer.coverage.retrospective),
        ("coverage.prospective", offer.coverage.prospective),
    )
    for label, value in durations:
        if value is not None and not is_iso_duration(value):
            result.error(
                "offer-durations",
                f"Offer '{offer.id}' {label} '{value}' is not an ISO 8601 duration",
            )


def _check_offer_codes(result: ValidationResult, offer: SharingOffer) -> None:
    """Everything a frontend translates must be a code with an English fallback."""
    if offer.subject_scope not in SUBJECT_SCOPES:
        result.error(
            "offer-codes",
            f"Offer '{offer.id}' subject_scope '{offer.subject_scope}' is not one of "
            f"{list(SUBJECT_SCOPES)}",
        )
    if not offer.recipients.processors.category.strip():
        result.error(
            "offer-codes",
            f"Offer '{offer.id}' declares no processor category — the person would be "
            "told nothing about who receives the data",
        )
    if not offer.recipients.processors.admitted_by:
        result.warning(
            "offer-codes",
            f"Offer '{offer.id}' processor category "
            f"'{offer.recipients.processors.category}' has no admitted_by constraints — "
            "the category is a promise the platform cannot check",
        )
    if not offer.consent_text_version.strip():
        result.error(
            "offer-codes",
            f"Offer '{offer.id}' has no consent_text_version — acceptance could not be "
            "tied to what was shown",
        )
    for measure in offer.measures:
        if not measure.strip():
            result.error("offer-codes", f"Offer '{offer.id}' declares an empty measure code")


def _check_offer_hash_stability(
    result: ValidationResult, offer: SharingOffer, profile: OdrlProfile
) -> None:
    """A no-op reload must not change ``user_visible_hash``.

    If it did, every redeploy would suspend every consent row and re-ask the
    whole population.  Recomputing twice catches accidental non-determinism
    (a set, a timestamp) leaking into the hashed payload.
    """
    slug = profile.purpose_slug(offer.purpose)
    chain = profile.broader_chain(slug) if slug else []
    if offer.user_visible_hash(chain) != offer.user_visible_hash(chain):
        result.error(
            "offer-hash-stability",
            f"Offer '{offer.id}' user_visible_hash is not stable across recomputation",
        )
