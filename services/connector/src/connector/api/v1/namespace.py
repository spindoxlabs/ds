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
    for purpose in profile.purposes:
        entry: dict = {
            "@id": profile.purpose_iri(purpose.slug),
            "@type": "skos:Concept",
            "skos:prefLabel": purpose.label,
        }
        if purpose.definition:
            entry["skos:definition"] = purpose.definition
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
