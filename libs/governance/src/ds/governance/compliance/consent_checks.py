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
from ..purposes import purpose_failure
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
    "offer-duplicate",
    "offer-datasets",
    "offer-consent-required",
    "offer-dataset-purpose",
    "offer-controller",
    "offer-legal-basis",
    "offer-durations",
    "offer-codes",
    "offer-hash-stability",
)


class ControllerLookup:
    """Which controller aliases resolve, for ``offer-controller``.

    Built from whatever the caller has: the owners YAML seed, or a live
    identity-registry.  ``available`` is explicit rather than inferred from
    emptiness — "no registry to check against" (warn) and "the registry has no
    such controller" (error) are different findings, and an empty set is a
    legitimate result of the second.

    It used to be ``RoleLookup`` and carry ``alias -> participant roles`` as
    well. That half is gone: an offer's ``controller_role`` is a controller
    *function*, and participant roles are DSP capacities the registry pins to
    ``{provider, consumer}``, so the two could never be compared. The vocabulary
    now lives beside the offers that use it
    (:class:`~ds.governance.sharing.SharingOfferCatalogue`), which is also why
    this lookup no longer needs the participants endpoint at all.
    """

    def __init__(
        self,
        aliases: Iterable[str] | None = None,
        available: bool = True,
    ):
        self._aliases = set(aliases or ())
        self.available = available

    def known(self, alias: str) -> bool:
        return alias in self._aliases


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
    """An exposed dataset must declare purposes, and each must resolve.

    An unresolvable entry is dropped by the mapper, so the dataset would be
    offered with one constraint fewer than its author intended. An **empty**
    list is the same defect with no entry to point at: the mapper emits no
    purpose constraint at all. This check used to iterate entries, so the empty
    case passed silently — `purpose_failure` is shared with the connector's
    sync-time gate so both now say the same thing.
    """
    for item in exposed:
        failure = purpose_failure(item.rule, profile)
        if failure:
            result.error("purpose-declared", f"Dataset {failure}", item.key)


# ── Sharing offers ───────────────────────────────────────────────────────────


def check_sharing_offers(
    result: ValidationResult,
    catalogue: SharingOfferCatalogue,
    exposed: list[DatasetEvidence],
    profile: OdrlProfile,
    controllers: ControllerLookup | None = None,
) -> None:
    """Validate the offers a person will actually be shown.

    Duplicate ids are not checked here: ``load_sharing_offers`` raises on one,
    keyed by id across every contributing file, so a duplicate cannot reach this
    function. `validator.validate` turns that into an ``offer-duplicate`` finding.
    """
    for offer in catalogue.offers:
        _check_offer_purpose(result, offer, profile)
        _check_offer_controller(result, offer, controllers, catalogue)
        _check_offer_legal_basis(result, offer)
        _check_offer_durations(result, offer)
        _check_offer_codes(result, offer)
        _check_offer_hash_stability(result, offer, profile)

    _check_dataset_offer_references(result, catalogue, exposed, profile)


def _check_dataset_offer_references(
    result: ValidationResult,
    catalogue: SharingOfferCatalogue,
    exposed: list[DatasetEvidence],
    profile: OdrlProfile,
) -> None:
    """Walk the datasets, resolving each offer id they declare.

    This is the check that used to walk ``offer.datasets``. Inverted it becomes
    **local**: the dataset naming the offer is the same file declaring the
    purpose and the classification, so the three are validated against each
    other without reaching across repositories for the answer.
    """
    reached: set[str] = set()

    for item in exposed:
        rule = item.rule
        declared = rule.dataspace.sharing_offers
        for offer_id in declared:
            offer = catalogue.get(offer_id)
            if offer is None:
                result.error(
                    "offer-datasets",
                    f"Dataset declares sharing offer '{offer_id}', which does not "
                    "resolve — a dataset with an unresolvable offer is not shared, "
                    "so it must not be exposed",
                    item.key,
                )
                continue
            reached.add(offer_id)

            if rule.classification == "pii" and not rule.policy.consent.required:
                result.error(
                    "offer-consent-required",
                    f"PII dataset declares offer '{offer_id}' but does not set "
                    "policy.consent.required — the offer promises a control that is "
                    "not enforced",
                    item.key,
                )

            offer_slug = profile.purpose_slug(offer.purpose)
            if offer_slug is None:
                continue  # already reported by _check_offer_purpose
            declared_slugs = {
                profile.purpose_slug(entry) for entry in rule.policy.purpose
            } - {None}
            if offer_slug not in declared_slugs:
                result.error(
                    "offer-dataset-purpose",
                    f"Dataset declares offer '{offer_id}', whose purpose "
                    f"'{offer_slug}' it does not list in policy.purpose[] "
                    f"(declares: {sorted(declared_slugs)}) — the negotiated offer "
                    "would deny the very use the person agreed to",
                    item.key,
                )

    for offer in catalogue.offers:
        if offer.id not in reached:
            result.warning(
                "offer-datasets",
                f"Offer '{offer.id}' is declared by no exposed dataset — consenting "
                "to it shares nothing",
            )


def _check_offer_purpose(
    result: ValidationResult, offer: SharingOffer, profile: OdrlProfile
) -> None:
    if profile.purpose_slug(offer.purpose) is None:
        result.error(
            "offer-purpose",
            f"Offer '{offer.id}' declares purpose '{offer.purpose}', which is not in "
            "the ODRL profile taxonomy",
        )


def _check_offer_controller(
    result: ValidationResult,
    offer: SharingOffer,
    controllers: ControllerLookup | None,
    catalogue: SharingOfferCatalogue,
) -> None:
    """Two separate questions, and only the first one needs a registry.

    **Does the controller exist?** The owners registry answers that, and without
    one the finding downgrades to a warning — an offline run has nothing to
    resolve against and should say so rather than fail.

    **Is the named function one this controller has?** *catalogue* answers that,
    offline, always. It used to be asked of the identity-registry's participant
    ``roles``, which are DSP capacities pinned to ``{provider, consumer}`` — so
    the answer could not be *yes* for any legal ``controller_role`` and the check
    was unsatisfiable. See
    :class:`~ds.governance.sharing.SharingOfferCatalogue`.
    """
    alias = offer.recipients.controller
    if not alias.strip():
        result.error("offer-controller", f"Offer '{offer.id}' names no controller")
        return

    if controllers is None or not controllers.available:
        result.warning(
            "offer-controller",
            f"Offer '{offer.id}' controller '{alias}' was not checked — no owners "
            "registry available to this run",
        )
    elif not controllers.known(alias):
        result.error(
            "offer-controller",
            f"Offer '{offer.id}' controller '{alias}' does not resolve in the owners registry",
        )
        return

    role = offer.recipients.controller_role
    declared = catalogue.roles_of(alias)

    if role and not declared:
        result.error(
            "offer-controller",
            f"Offer '{offer.id}' declares controller_role '{role}', but controller "
            f"'{alias}' declares no controller_roles — a role naming nothing cannot "
            "keep consent to one function from reaching another. Declare "
            f"controller_roles['{alias}'] beside the offers, or drop the role",
        )
    elif role and role not in declared:
        result.error(
            "offer-controller",
            f"Offer '{offer.id}' declares controller_role '{role}', which is not one "
            f"of '{alias}' declared controller_roles {declared}",
        )
    elif declared and not role:
        # `D-11`: the consent key is (subject, purpose, controller-role). Naming
        # an unbundled entity without saying which function is consenting leaves
        # that key one element short, and the connector then matches on the legal
        # entity alone — which is what `D-11` calls insufficient.
        result.error(
            "offer-controller",
            f"Offer '{offer.id}' names controller '{alias}', which is unbundled into "
            f"{declared}, but declares no controller_role — consent to one function "
            "would reach the others",
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
            result.error(
                "offer-codes", f"Offer '{offer.id}' declares an empty measure code"
            )


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
