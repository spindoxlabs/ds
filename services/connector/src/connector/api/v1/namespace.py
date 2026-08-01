"""The published vocabularies — policy, sharing offers, and semantic models.

Two different layers are served here and the distinction is the one thing to keep
straight when editing this file.

``/ns/policy`` and ``/ns/sharing-offers`` publish the **policy** vocabulary: the
ODRL profile's purposes, operands and actions, and the offer codes a person is
asked about. ``/ns/{slug}`` publishes **semantic** vocabularies — SAREF, CIM,
COSEM — which describe what a dataset's columns *mean*. A dataset points at one
through ``dcat.conforms_to``; rulebook `M-4`, `M-7`, `M-11`.

Everything here is public and unauthenticated by design (`M-8`), and nothing here
makes an outbound call: the semantic vocabularies are read from a local cache
filled at startup or by ``task vocab:fetch``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ds.governance.models import OdrlProfile
from ds.governance.vocabulary_cache import VocabularyFetchError, read_cached

router = APIRouter(tags=["namespace"])


def _build_vocab(profile: OdrlProfile) -> dict:
    ns = profile.namespace
    pfx = profile.prefix

    graph: list[dict] = [
        # ── ODRL left-operands ─────────────────────────────────────────
        {
            "@id": profile.term(profile.membership_operand),
            "@type": "odrl:LeftOperand",
            "skos:definition": "Whether the consumer holds a valid membership credential for the dataspace.",
            "skos:example": "dataspaces.query",
        },
        {
            "@id": profile.term(profile.consent_operand),
            "@type": "odrl:LeftOperand",
            "skos:definition": "Whether the data subject has an active consent grant for the requesting consumer.",
            "skos:example": "active",
        },

        # ── ODRL action ────────────────────────────────────────────────
        {
            "@id": profile.term(profile.query_action),
            "@type": "odrl:Action",
            "skos:definition": (
                "Execute a parameterised query against the dataset. "
                "Results are returned to the consumer but not retained as a copy."
            ),
            "odrl:includedIn": {"@id": "odrl:use"},
        },

        # ── Party roles ────────────────────────────────────────────────
        {
            "@id": f"{pfx}:role:DataSubject",
            "@type": "odrl:PartyCollection",
            "skos:definition": "The set of natural persons whose personal data is contained in the dataset.",
        },
        {
            "@id": f"{pfx}:role:Provider",
            "@type": "odrl:PartyCollection",
            "skos:definition": "A participant that offers datasets in the dataspace.",
        },
        {
            "@id": f"{pfx}:role:Consumer",
            "@type": "odrl:PartyCollection",
            "skos:definition": "A participant that requests access to datasets in the dataspace.",
        },
    ]

    # ── Purpose concepts (deployer-configured) ─────────────────────────
    #
    # Served as a SKOS taxonomy: `skos:broader` is the local hierarchy that
    # `odrl:isA` matching follows, and the `skos:*Match` predicate records the
    # declared alignment to an external vocabulary (DPV). The two are
    # deliberately distinct — the mapping is for readers, never for matching,
    # because a broadMatch to a generic term would silently widen consent.
    for purpose in profile.purposes:
        entry: dict = {
            "@id": profile.purpose_iri(purpose.slug),
            "@type": "skos:Concept",
            "skos:prefLabel": purpose.label,
        }
        if purpose.definition:
            entry["skos:definition"] = purpose.definition
        if purpose.broader:
            entry["skos:broader"] = {"@id": profile.purpose_iri(purpose.broader)}
        if purpose.dpv_mapping:
            entry[f"skos:{purpose.dpv_mapping.relation}"] = {
                "@id": purpose.dpv_mapping.iri
            }
        graph.append(entry)

    return {
        "@context": {
            "@vocab": ns,
            pfx: ns,
            "odrl": "http://www.w3.org/ns/odrl/2/",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "skos": "http://www.w3.org/2004/02/skos/core#",
        },
        "@graph": graph,
    }


def _get_vocab() -> dict:
    """Build the vocabulary from the **active** ODRL profile.

    Two things this deliberately does not do, both of which it used to.

    It does not read ``CONNECTOR_ODRL_PROFILE_PATH`` from ``os.environ``: the
    profile is deployment configuration and `Settings` is the one reader of it,
    so a second reader is a second answer. `provider.py` and
    `consent_vocabulary` go through `Settings`, and this route serving a
    different profile from the one the sync publishes is a vocabulary nobody can
    negotiate against.

    It does not cache the built dict either. `POST /provider/sync` re-reads the
    profile and drops the vocabulary caches (`vocab.reset_caches()`); a cache
    here would survive that and keep serving the taxonomy the process booted
    with. The profile itself *is* cached — `vocab.get_profile()` — so what runs
    per request is the dict construction, over a handful of purposes.
    """
    from ...services import consent_vocabulary as vocab

    return _build_vocab(vocab.get_profile())


@router.get("/ns")
async def namespace_index():
    """Everything this participant publishes a vocabulary for.

    The browse entry point (`M-11`). Without it, a reader has to already know
    that `/ns/policy` exists in order to find it, which is not discovery.

    Semantic vocabularies report whether a local copy exists rather than hiding
    the ones that do not: an entry registered and uncached is a deployment
    problem an operator should be able to see from outside the container.
    """
    from ...services import consent_vocabulary as vocab

    profile = vocab.get_profile()
    registry = vocab.get_vocabularies()
    cache_dir = _cache_dir()

    return {
        "policy": {
            "href": "/ns/policy",
            "namespace": profile.namespace,
            "prefix": profile.prefix,
            "purposes": len(profile.purposes),
        },
        "sharingOffers": {
            "href": "/ns/sharing-offers",
            "offers": len(vocab.get_offers().offers),
        },
        "vocabularies": [
            {
                "slug": v.slug,
                "title": v.title,
                "version": v.version,
                "iri": v.iri,
                "href": f"/ns/{v.slug}",
                "cached": (cache_dir / v.cache_filename).is_file(),
            }
            for v in registry.vocabularies
        ],
    }


@router.get("/ns/vocabularies")
async def vocabularies_index():
    """The semantic vocabulary registry, on its own.

    Registered **before** ``/ns/{slug}`` — see the note on that route. A
    vocabulary may not be slugged ``vocabularies`` for the same reason.
    """
    from ...services import consent_vocabulary as vocab

    cache_dir = _cache_dir()
    return [
        {
            "slug": v.slug,
            "title": v.title,
            "version": v.version,
            "iri": v.iri,
            "source": v.source,
            "format": v.format,
            "href": f"/ns/{v.slug}",
            "cached": (cache_dir / v.cache_filename).is_file(),
        }
        for v in vocab.get_vocabularies().vocabularies
    ]


@router.get("/ns/policy")
async def policy_namespace():
    return JSONResponse(
        content=_get_vocab(),
        media_type="application/ld+json",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/ns/sharing-offers")
async def sharing_offers():
    """The offers a person can be asked about — a vocabulary, not data.

    Public by design, mirroring ``/ns/policy``: an onboarding wizard has to
    render these before anyone has an identity.  Served as codes plus an
    English label for every code; translation is entirely the frontend's job,
    so a locale can mistranslate a label but cannot invent a resolution or
    widen a coverage window.

    Dataset keys are not in this projection — which datasets back an offer is
    operator detail the person was never shown, and changing them deliberately
    does not invalidate consent.
    """
    from ...services import consent_vocabulary as vocab

    offers = [
        vocab.public_offer_projection(offer) for offer in vocab.get_offers().offers
    ]
    return JSONResponse(
        content=offers,
        headers={"Cache-Control": "public, max-age=300"},
    )


def _cache_dir():
    from pathlib import Path

    from ...config import get_settings

    return Path(get_settings().vocabulary_cache_dir)


# ── Semantic vocabularies ─────────────────────────────────────────────────────
#
# **This route is last, and that is load-bearing.** FastAPI resolves in
# registration order, so `/ns/{slug}` declared above would shadow `/ns/policy`,
# `/ns/sharing-offers` and `/ns/vocabularies` — each would resolve here, find no
# vocabulary with that slug, and 404. The existing public surface would break in
# a way no test of *this* route would notice, which is why
# `tests/test_ns_vocabularies.py` asserts the siblings still answer.

@router.get("/ns/{slug}")
async def vocabulary(slug: str):
    """A semantic vocabulary's cached JSON-LD definition.

    Served from disk only. The cache is filled at startup or by
    ``task vocab:fetch``, never by this request: a public unauthenticated route
    that fetched an operator-configured URL on demand would proxy for anyone who
    called it, and would go down whenever the upstream did.

    A registered vocabulary with no local copy is a **404 carrying the canonical
    IRI**, not a 500. The IRI is the identity and the registry is only a local
    convenience, so the honest answer is "not here, and here is where it lives".
    """
    from ...services import consent_vocabulary as vocab

    entry = vocab.get_vocabularies().by_slug.get(slug)
    if entry is None:
        raise HTTPException(404, f"No vocabulary '{slug}' is registered")

    try:
        document = read_cached(_cache_dir(), entry)
    except VocabularyFetchError as exc:
        # The cached file exists and is not readable JSON — the cache is lying
        # about what it holds, which is this deployment's fault, not the caller's.
        raise HTTPException(
            500, f"Vocabulary '{slug}' is cached but unreadable"
        ) from exc

    if document is None:
        raise HTTPException(
            404,
            {
                "detail": f"Vocabulary '{slug}' has no local copy",
                "iri": entry.iri,
                "source": entry.source,
            },
        )

    return JSONResponse(
        content=document,
        media_type="application/ld+json",
        headers={"Cache-Control": "public, max-age=86400"},
    )
