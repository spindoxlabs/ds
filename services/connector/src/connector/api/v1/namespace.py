"""ODRL custom namespace vocabulary endpoint."""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ds.governance.models import OdrlProfile, PurposeConcept, load_odrl_profile

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


@lru_cache(maxsize=1)
def _get_vocab() -> dict:
    """Load the ODRL profile and build the vocabulary once."""
    import os
    profile = load_odrl_profile(os.environ.get("CONNECTOR_ODRL_PROFILE_PATH"))
    return _build_vocab(profile)


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
