"""JSON-LD context for PROV-O responses."""
from fastapi.responses import JSONResponse

DS_NAMESPACE = "https://dataspaces.localhost/ns/energy#"

PROV_CONTEXT: dict = {
    "prov":  "http://www.w3.org/ns/prov#",
    "xsd":   "http://www.w3.org/2001/XMLSchema#",
    "dct":   "http://purl.org/dc/terms/",
    "dcat":  "http://www.w3.org/ns/dcat#",
    "odrl":  "http://www.w3.org/ns/odrl/2/",
    "ds":    DS_NAMESPACE,

    # PROV-O relations — coerce values to IRI
    "wasGeneratedBy":    {"@id": "prov:wasGeneratedBy",   "@type": "@id"},
    "wasAttributedTo":   {"@id": "prov:wasAttributedTo",  "@type": "@id"},
    "wasDerivedFrom":    {"@id": "prov:wasDerivedFrom",   "@type": "@id"},
    "wasAssociatedWith": {"@id": "prov:wasAssociatedWith","@type": "@id"},
    "used":              {"@id": "prov:used",             "@type": "@id"},
    "actedOnBehalfOf":   {"@id": "prov:actedOnBehalfOf",  "@type": "@id"},
    "wasInformedBy":     {"@id": "prov:wasInformedBy",    "@type": "@id"},

    # Temporal — coerce to xsd:dateTime
    "startedAtTime":  {"@id": "prov:startedAtTime",  "@type": "xsd:dateTime"},
    "endedAtTime":    {"@id": "prov:endedAtTime",     "@type": "xsd:dateTime"},
    "generatedAtTime":{"@id": "prov:generatedAtTime","@type": "xsd:dateTime"},
    "invalidatedAtTime":{"@id":"prov:invalidatedAtTime","@type":"xsd:dateTime"},

    # Energy domain types
    "GridFrequencyDataset":   {"@id": f"{DS_NAMESPACE}GridFrequencyDataset"},
    "ConsumptionMeasurement": {"@id": f"{DS_NAMESPACE}ConsumptionMeasurement"},
    "GenerationMeasurement":  {"@id": f"{DS_NAMESPACE}GenerationMeasurement"},
    "DataCollectionActivity": {"@id": f"{DS_NAMESPACE}DataCollectionActivity"},
    "DataTransferActivity":   {"@id": f"{DS_NAMESPACE}DataTransferActivity"},
    "DSO":          {"@id": f"{DS_NAMESPACE}DSO"},
    "Prosumer":     {"@id": f"{DS_NAMESPACE}Prosumer"},
    "Aggregator":   {"@id": f"{DS_NAMESPACE}Aggregator"},
    "EnergyCommunity": {"@id": f"{DS_NAMESPACE}EnergyCommunity"},

    # Domain properties
    "underAgreement":    {"@id": f"{DS_NAMESPACE}underAgreement",   "@type": "@id"},
    "bytesTransferred":  {"@id": f"{DS_NAMESPACE}bytesTransferred", "@type": "xsd:integer"},
    "protocol":          {"@id": f"{DS_NAMESPACE}protocol"},
    "policyHash":        {"@id": f"{DS_NAMESPACE}policyHash"},
    "obligationType":    {"@id": f"{DS_NAMESPACE}obligationType"},
}


class JSONLDResponse(JSONResponse):
    media_type = "application/ld+json"

    def __init__(self, graph: list | dict, context_url: str, **kwargs):
        content = {
            "@context": context_url,
            "@graph": graph if isinstance(graph, list) else [graph],
        }
        super().__init__(content=content, **kwargs)
