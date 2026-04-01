"""ODRL custom namespace vocabulary endpoint."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["namespace"])

DS_NAMESPACE = "https://dataspaces.localhost/ns/energy#"

_ENERGY_VOCAB = {
    "@context": {
        "@vocab": DS_NAMESPACE,
        "ds": DS_NAMESPACE,
        "odrl": "http://www.w3.org/ns/odrl/2/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "skos": "http://www.w3.org/2004/02/skos/core#",
    },
    "@graph": [
        # ── ODRL left-operands ─────────────────────────────────────────────
        {
            "@id": "ds:accessScope",
            "@type": "odrl:LeftOperand",
            "skos:definition": "The OAuth scope required to access this dataset in the dataspace.",
            "skos:example": "dataspaces.query",
        },
        {
            "@id": "ds:consentStatus",
            "@type": "odrl:LeftOperand",
            "skos:definition": "Whether the data subject has an active consent grant for the requesting consumer.",
            "skos:example": "active",
        },
        {
            "@id": "ds:contractRequired",
            "@type": "odrl:LeftOperand",
            "skos:definition": "Whether a bilateral contract agreement is required before access is granted.",
        },
        {
            "@id": "ds:participantRole",
            "@type": "odrl:LeftOperand",
            "skos:definition": "The declared role of the consumer participant in the dataspace.",
        },

        # ── ODRL action ────────────────────────────────────────────────────
        {
            "@id": "ds:query",
            "@type": "odrl:Action",
            "skos:definition": (
                "Execute a parameterised query against the dataset. "
                "Results are returned to the consumer but not retained as a copy."
            ),
            "odrl:includedIn": {"@id": "odrl:use"},
        },

        # ── Purpose concepts ───────────────────────────────────────────────
        {
            "@id": "ds:purpose:EnergyBalancing",
            "@type": "skos:Concept",
            "skos:prefLabel": "Energy Community Balancing",
            "skos:definition": "Use of data for balancing energy production and consumption within an energy community.",
        },
        {
            "@id": "ds:purpose:GridMonitoring",
            "@type": "skos:Concept",
            "skos:prefLabel": "Grid Monitoring",
            "skos:definition": "Use of data for monitoring grid stability, load, and fault detection.",
        },
        {
            "@id": "ds:purpose:UrbanPlanning",
            "@type": "skos:Concept",
            "skos:prefLabel": "Urban Planning",
            "skos:definition": "Use of aggregated mobility or tourism data for urban infrastructure planning.",
        },

        # ── Party roles ────────────────────────────────────────────────────
        {
            "@id": "ds:role:DataSubject",
            "@type": "odrl:PartyCollection",
            "skos:definition": "The set of natural persons whose personal data is contained in the dataset.",
        },
        {
            "@id": "ds:role:Provider",
            "@type": "odrl:PartyCollection",
            "skos:definition": "A participant that offers datasets in the dataspace.",
        },
        {
            "@id": "ds:role:Consumer",
            "@type": "odrl:PartyCollection",
            "skos:definition": "A participant that requests access to datasets in the dataspace.",
        },

        # ── Dataset types ──────────────────────────────────────────────────
        {
            "@id": "ds:GridFrequencyDataset",
            "@type": "skos:Concept",
            "skos:prefLabel": "Grid Frequency Dataset",
        },
        {
            "@id": "ds:ConsumptionMeasurement",
            "@type": "skos:Concept",
            "skos:prefLabel": "Consumption Measurement",
        },
        {
            "@id": "ds:GenerationMeasurement",
            "@type": "skos:Concept",
            "skos:prefLabel": "Generation Measurement",
        },

        # ── Participant types ──────────────────────────────────────────────
        {
            "@id": "ds:DSO",
            "@type": "skos:Concept",
            "skos:prefLabel": "Distribution System Operator",
        },
        {
            "@id": "ds:Prosumer",
            "@type": "skos:Concept",
            "skos:prefLabel": "Prosumer",
        },
        {
            "@id": "ds:Aggregator",
            "@type": "skos:Concept",
            "skos:prefLabel": "Aggregator",
        },
        {
            "@id": "ds:EnergyCommunity",
            "@type": "skos:Concept",
            "skos:prefLabel": "Energy Community",
        },
    ],
}


@router.get("/ns/energy")
async def energy_namespace():
    return JSONResponse(
        content=_ENERGY_VOCAB,
        media_type="application/ld+json",
        headers={"Cache-Control": "public, max-age=86400"},
    )
