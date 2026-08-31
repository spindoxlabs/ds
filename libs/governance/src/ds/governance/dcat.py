"""DCAT-AP shapes shared by every catalogue this platform publishes.

Two catalogues exist and they are built by different code: the compliance
evidence bundle (:mod:`ds.governance.compliance.evidence`) derives one from
`governance.yaml`, and `services/federated-catalog` republishes the union of
what it crawled. Both are `dcat:Catalog` documents, both are read by the same
consumers, and both owe the same two mandatory properties:

``dcat:service`` (`DSSC-PUB-41`, rulebook `C-7`)
    At least one ``dcat:DataService`` naming the endpoint that actually serves
    the datasets. Discovery without it tells a consumer that something exists
    and not where to ask for it.

``dcat:record`` (`DSSC-PUB-45`, rulebook `C-8`)
    A ``dcat:CatalogRecord`` per entry, carrying the catalogue's own metadata
    about the entry — when *this* catalogue last saw it, and where it came
    from — as distinct from the dataset's own description, which belongs to the
    publisher and which a catalogue must not claim as its own.

The shapes live here rather than in either caller so the two catalogues cannot
drift into two different readings of the same requirement.
"""

from __future__ import annotations

from typing import Any

DSP_PROTOCOL_IRI = "https://w3id.org/dspace/protocol/2025-1"

#: Terms every catalogue document this platform emits needs in its context.
#: ``foaf`` is here for ``foaf:primaryTopic``, which is how a catalogue record
#: points at the dataset it describes.
CATALOG_CONTEXT = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "odrl": "http://www.w3.org/ns/odrl/2/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}


def to_data_service(
    *,
    service_id: str,
    title: str,
    endpoint_url: str,
    serves_dataset: list[str] | None = None,
    endpoint_description: str | None = None,
    conforms_to: str | None = None,
) -> dict[str, Any]:
    """One ``dcat:DataService``.

    ``serves_dataset`` is a list of dataset IRIs, emitted as references. A
    service that serves nothing is still a legitimate service description — an
    empty catalogue behind a live endpoint — so the property is dropped rather
    than emitted empty, which would assert "serves exactly no datasets".
    """
    service: dict[str, Any] = {
        "@id": service_id,
        "@type": "dcat:DataService",
        "dct:title": title,
        "dcat:endpointURL": {"@id": endpoint_url},
        "dcat:endpointDescription": (
            {"@id": endpoint_description} if endpoint_description else None
        ),
        "dct:conformsTo": {"@id": conforms_to} if conforms_to else None,
        "dcat:servesDataset": (
            [{"@id": iri} for iri in serves_dataset] if serves_dataset else None
        ),
    }
    return {k: v for k, v in service.items() if v is not None}


def to_catalog_record(
    *,
    dataset_id: str,
    record_id: str,
    modified: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """One ``dcat:CatalogRecord`` describing this catalogue's entry for a dataset.

    ``modified`` is when the *record* changed, not when the dataset did — for a
    crawler that is the crawl timestamp, and it is the only freshness signal a
    consumer of an index can act on. ``dct:source`` names the catalogue the
    entry was taken from, which is what makes a federated entry attributable.
    """
    record: dict[str, Any] = {
        "@id": record_id,
        "@type": "dcat:CatalogRecord",
        "foaf:primaryTopic": {"@id": dataset_id},
        "dct:modified": modified,
        "dct:source": {"@id": source} if source else None,
    }
    return {k: v for k, v in record.items() if v is not None}
