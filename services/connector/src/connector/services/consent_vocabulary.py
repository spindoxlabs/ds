"""Resolution and matching for the consent vocabulary.

Three vocabularies meet here: the ODRL profile's purpose taxonomy, the datasets
declared in ``governance.yaml``, and the sharing offers a frontend renders.
Every consent write path resolves through this module, so a consent row can
never name a dataset that does not exist or a purpose nobody defined.

Loaded once per process and cached — governance and offers are deployment
configuration, not request state.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from ds.governance.models import GovernanceRuleV2, OdrlProfile, load_odrl_profile
from ds.governance.resolver import GovernanceResolver
from ds.governance.sharing import SharingOffer, SharingOfferCatalogue, load_sharing_offers

from ..config import Settings, get_settings

log = logging.getLogger(__name__)


class VocabularyError(ValueError):
    """A consent write named something outside the declared vocabulary."""


@lru_cache(maxsize=1)
def get_profile() -> OdrlProfile:
    return load_odrl_profile(get_settings().odrl_profile_path)


@lru_cache(maxsize=1)
def get_resolver() -> GovernanceResolver:
    settings = get_settings()
    return GovernanceResolver.from_file_with_override(
        Path(settings.governance_yaml_path),
        overlay_name=settings.governance_overlay_name,
    )


@lru_cache(maxsize=1)
def get_offers() -> SharingOfferCatalogue:
    settings = get_settings()
    return load_sharing_offers(
        _offers_path(settings),
        overlay_name=settings.sharing_offers_overlay_name,
    )


def _offers_path(settings: Settings) -> Path | None:
    if settings.sharing_offers_path:
        return Path(settings.sharing_offers_path)
    sibling = Path(settings.governance_yaml_path).parent / "sharing-offers.yaml"
    return sibling if sibling.exists() else None


def reset_caches() -> None:
    """Drop cached configuration — used by tests and after a governance reload."""
    get_profile.cache_clear()
    get_resolver.cache_clear()
    get_offers.cache_clear()


# ── Datasets ─────────────────────────────────────────────────────────────────


def known_dataset_keys() -> set[str]:
    return set(get_resolver().config.sources)


def resolve_dataset(dataset_id: str) -> GovernanceRuleV2:
    """Resolve a dataset key, or raise.

    ``GovernanceResolver.resolve`` falls back to ``defaults`` for an unknown
    key, which would let a typo be accepted as a valid consent target.  The
    membership test against declared sources is what makes this strict.
    """
    if dataset_id not in known_dataset_keys():
        raise VocabularyError(
            f"Unknown dataset '{dataset_id}' — not declared in governance"
        )
    return get_resolver().resolve(dataset_id)


def requires_consent(rule: GovernanceRuleV2) -> bool:
    """Whether this dataset's rows are gated on a data subject's consent."""
    return bool(
        rule.policy.consent.required
        or rule.user_filter_column
        or rule.row_filters
        or rule.classification == "pii"
    )


# ── Purposes ─────────────────────────────────────────────────────────────────


def normalise_purposes(purposes: list[str] | None) -> list[str]:
    """Validate purposes against the taxonomy and return them as slugs.

    Raises on any unknown entry rather than dropping it: a consent row that
    silently lost a purpose would record something other than what the person
    agreed to.
    """
    profile = get_profile()
    resolved: list[str] = []
    for entry in purposes or []:
        slug = profile.purpose_slug(entry)
        if slug is None:
            raise VocabularyError(
                f"Unknown purpose '{entry}' — not in the ODRL profile taxonomy"
            )
        if slug not in resolved:
            resolved.append(slug)
    return resolved


def purpose_covered(requested: list[str], consented: list[str]) -> bool:
    """``odrl:isA`` — is any requested purpose covered by any consented one?

    Matching walks the local ``broader`` chain only.  ``dpv_mapping`` is never
    consulted: our purposes are domain specialisations of DPV's generic terms,
    so a broadMatch would let an unrelated use satisfy a specific consent.

    An empty ``consented`` list is never a wildcard.  For a consent-required
    dataset it means the person was never told the use, so the consent does not
    meet GDPR Art. 4(11) — fail closed.
    """
    if not requested or not consented:
        return False
    profile = get_profile()
    return any(
        profile.is_a(want, have) for want in requested for have in consented
    )


# ── Sharing offers ───────────────────────────────────────────────────────────


def resolve_offer(offer_id: str) -> SharingOffer:
    offer = get_offers().get(offer_id)
    if offer is None:
        raise VocabularyError(f"Unknown sharing offer '{offer_id}'")
    return offer


def offer_broader_chain(offer: SharingOffer) -> list[str]:
    slug = get_profile().purpose_slug(offer.purpose)
    return get_profile().broader_chain(slug) if slug else []


def offer_user_visible_hash(offer: SharingOffer) -> str:
    return offer.user_visible_hash(offer_broader_chain(offer))


def public_offer_projection(offer: SharingOffer) -> dict:
    """The shape served by ``GET /ns/sharing-offers``.

    Codes plus an English fallback — never prose, never dataset keys.  A
    frontend composes its own sentences per locale from these codes, so it can
    mistranslate a label but cannot invent a resolution or widen a coverage
    window.
    """
    profile = get_profile()
    slug = profile.purpose_slug(offer.purpose)
    concept = profile.purpose_index.get(slug) if slug else None
    chain = offer_broader_chain(offer)
    return {
        "id": offer.id,
        "purpose": slug or offer.purpose,
        "purpose_broader": chain[1:],
        "legal_basis": offer.legal_basis,
        "requires_consent": offer.requires_consent,
        "recipients": {
            "controller": offer.recipients.controller,
            "controller_role": offer.recipients.controller_role,
            "processors": {"category": offer.recipients.processors.category},
        },
        "subject_scope": offer.subject_scope,
        "measures": list(offer.measures),
        "resolution": offer.resolution,
        "coverage": {
            "retrospective": offer.coverage.retrospective,
            "prospective": offer.coverage.prospective,
        },
        "consent_text_version": offer.consent_text_version,
        "revocable": offer.revocable,
        "retention": offer.retention,
        "user_visible_hash": offer.user_visible_hash(chain),
        # A count, not the keys: which datasets back an offer is operator
        # detail the person was never shown.
        "dataset_count": len(offer.datasets),
        "fallback_text_en": {
            "purpose_label": concept.label if concept else (slug or offer.purpose),
            "purpose_definition": concept.definition if concept else "",
            "processor_category": offer.recipients.processors.category,
        },
    }
