"""Has an offer's meaning changed under consent already recorded against it?

An offer id is referenced by stored consent (`consent_requests.offer_id`), and
each row keeps the `user_visible_hash` and `consent_text_version` it was written
with. So the question "did the words change since this person agreed" is
answerable — and it is the one check that actually protects consent when offers
are contributed by whoever declares the datasets.

**This hazard is not created by distribution.** Editing the single
`sharing-offers.yaml` in place changes what recorded consent meant, and nothing
noticed before this module existed. Distribution only made it urgent enough to
build.

The rule: a changed `user_visible_hash` is fine **if** `consent_text_version`
moved with it — that is a deliberate re-consent, and the platform can tell the
difference. A changed hash at the *same* version is an edit pretending nothing
happened, and it is refused.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ds.governance.sharing import SharingOffer, SharingOfferCatalogue

from ..db.models import ConsentRequestORM

log = logging.getLogger(__name__)


async def recorded_offer_evidence(
    session: AsyncSession, offer_ids: Iterable[str]
) -> dict[str, set[tuple[str, str]]]:
    """offer id → the distinct ``(consent_text_version, user_visible_hash)`` pairs
    that consent rows were written with.

    A set, not the latest row: several versions legitimately coexist while people
    re-consent at their own pace, and the check has to consider all of them.
    """
    wanted = set(offer_ids)
    if not wanted:
        return {}

    rows = (
        await session.execute(
            select(ConsentRequestORM.offer_id, ConsentRequestORM.legal_basis).where(
                ConsentRequestORM.offer_id.in_(wanted)
            )
        )
    ).all()

    evidence: dict[str, set[tuple[str, str]]] = {}
    for offer_id, legal_basis in rows:
        if not offer_id or not isinstance(legal_basis, dict):
            continue
        version = legal_basis.get("consent_text_version")
        digest = legal_basis.get("user_visible_hash")
        if version and digest:
            evidence.setdefault(offer_id, set()).add((version, digest))
    return evidence


def drift_failure(
    offer: SharingOffer,
    current_hash: str,
    recorded: set[tuple[str, str]] | None,
) -> str | None:
    """Why this offer must not be republished, or ``None``.

    Fails when some recorded consent carries **this** ``consent_text_version``
    but a *different* ``user_visible_hash``: same version, different words. A
    different version is a deliberate revision and passes — the rows recorded
    under the old one keep meaning what they meant.
    """
    if not recorded:
        return None

    conflicting = {
        digest
        for version, digest in recorded
        if version == offer.consent_text_version and digest != current_hash
    }
    if not conflicting:
        return None

    return (
        f"has changed since consent was recorded against it: "
        f"{len(conflicting)} stored consent hash(es) differ from the current text "
        f"while consent_text_version is still '{offer.consent_text_version}'. "
        "Every consent already stored against this id would now mean something "
        "other than what the person read. Bump consent_text_version to publish a "
        "revision, or restore the previous wording."
    )


async def offers_with_drift(
    session: AsyncSession,
    catalogue: SharingOfferCatalogue,
    hash_of: "callable[[SharingOffer], str]",
) -> dict[str, str]:
    """offer id → failure message, for every offer whose meaning drifted.

    ``hash_of`` is injected rather than computed here because the hash covers the
    purpose's ``broader`` chain, which only the active ODRL profile knows.
    """
    ids = [offer.id for offer in catalogue.offers]
    evidence = await recorded_offer_evidence(session, ids)

    failures: dict[str, str] = {}
    for offer in catalogue.offers:
        failure = drift_failure(offer, hash_of(offer), evidence.get(offer.id))
        if failure:
            failures[offer.id] = failure
            log.error("Sharing offer %s %s", offer.id, failure)
    return failures
