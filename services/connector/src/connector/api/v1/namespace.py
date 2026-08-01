"""ODRL custom namespace vocabulary endpoint."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ds.governance.models import OdrlProfile

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
