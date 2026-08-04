"""`dcat:DataService` and `dcat:record` — rulebook `C-7`/`C-8`, `DSSC-PUB-41`/`-45`.

Both were mandatory and neither existed anywhere in the platform.

The blueprint is what decides *which* service a federated index names. A
catalogue is "a collection of offerings published by a provider in the form of
DCAT datasets and DCAT data services", and it "must include at least one data
service that references **the service providing these datasets**"
(`DSSC-PUB-39`, `-41`). This index provides nothing — it republishes
descriptions, and the recorded architecture makes it advisory (rulebook `C-2`).
So the service it names is each **crawled source's** endpoint, and a consumer
following it arrives at the provider it must negotiate with, not back here.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from federated_catalog.cache import CatalogCache, SourceEndpoint
from federated_catalog.config import get_settings
from federated_catalog.main import create_app

from .test_auth import make_headers

PROVIDER = "did:web:rec.dataspaces.localhost"
DSP = "http://172.17.0.1:19194/protocol/2025-1"
EXTERNAL = "https://opendata.example.test/catalogue"


@pytest_asyncio.fixture(scope="function")
async def client():
    app = create_app()
    cache = CatalogCache()
    cache.swap(
        {
            PROVIDER: [{"@id": "datasets.silver.meters_15m", "dct:title": "Meters"}],
            "opendata": [{"@id": "https://opendata.example.test/ds/1"}],
        },
        [],
        {
            PROVIDER: SourceEndpoint(
                url=DSP, conforms_to="https://w3id.org/dspace/protocol/2025-1"
            ),
            "opendata": SourceEndpoint(url=EXTERNAL),
        },
    )
    app.state.cache = cache
    app.state.settings = get_settings()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_catalogue_names_a_data_service_per_source(client):
    body = (await client.get("/catalog", headers=make_headers())).json()
    services = body["dcat:service"]
    assert len(services) == 2
    by_endpoint = {s["dcat:endpointURL"]["@id"]: s for s in services}

    assert set(by_endpoint) == {DSP, EXTERNAL}
    for service in services:
        assert service["@type"] == "dcat:DataService"


@pytest.mark.asyncio
async def test_a_dsp_source_declares_the_protocol_it_speaks(client):
    """`dct:conformsTo` separates "negotiate here" from "just fetch this".

    A DSP participant is a counterparty; a plain DCAT-AP source is a document. A
    consumer that cannot tell them apart would try to negotiate with an open-data
    portal.
    """
    body = (await client.get("/catalog", headers=make_headers())).json()
    by_endpoint = {s["dcat:endpointURL"]["@id"]: s for s in body["dcat:service"]}

    assert by_endpoint[DSP]["dct:conformsTo"] == {
        "@id": "https://w3id.org/dspace/protocol/2025-1"
    }
    assert "dct:conformsTo" not in by_endpoint[EXTERNAL]


@pytest.mark.asyncio
async def test_a_service_lists_only_its_own_datasets(client):
    body = (await client.get("/catalog", headers=make_headers())).json()
    by_endpoint = {s["dcat:endpointURL"]["@id"]: s for s in body["dcat:service"]}

    assert by_endpoint[DSP]["dcat:servesDataset"] == [
        {"@id": "datasets.silver.meters_15m"}
    ]
    assert by_endpoint[EXTERNAL]["dcat:servesDataset"] == [
        {"@id": "https://opendata.example.test/ds/1"}
    ]


@pytest.mark.asyncio
async def test_every_entry_carries_a_catalogue_record(client):
    body = (await client.get("/catalog", headers=make_headers())).json()
    records = body["dcat:record"]
    assert len(records) == len(body["dcat:dataset"]) == 2

    topics = {r["foaf:primaryTopic"]["@id"] for r in records}
    assert topics == {
        "datasets.silver.meters_15m",
        "https://opendata.example.test/ds/1",
    }
    for record in records:
        assert record["@type"] == "dcat:CatalogRecord"


@pytest.mark.asyncio
async def test_a_record_attributes_the_entry_and_dates_the_crawl(client):
    """What a record says that the dataset cannot.

    `dct:modified` is when *this index* last saw the entry — the only freshness
    signal a reader of an advisory index can act on — and `dct:source` is which
    crawled catalogue it came from, which is what makes a federated entry
    attributable rather than anonymous.
    """
    body = (await client.get("/catalog", headers=make_headers())).json()
    record = next(
        r
        for r in body["dcat:record"]
        if r["foaf:primaryTopic"]["@id"] == "datasets.silver.meters_15m"
    )
    assert record["dct:source"] == {"@id": PROVIDER}
    assert record["dct:modified"] == client._transport.app.state.cache.last_crawl_iso


@pytest.mark.asyncio
async def test_search_results_carry_records_for_the_page_only(client):
    body = (
        await client.post(
            "/catalog/search",
            json={"provider": PROVIDER},
            headers=make_headers(),
        )
    ).json()
    assert len(body["dcat:dataset"]) == 1
    assert len(body["dcat:record"]) == 1
    assert body["dcat:record"][0]["foaf:primaryTopic"] == {
        "@id": "datasets.silver.meters_15m"
    }


@pytest.mark.asyncio
async def test_the_context_defines_the_terms_the_documents_use(client):
    """A term emitted and not defined is not JSON-LD, it is JSON.

    `foaf:` in particular arrives only with `dcat:record` — the context carried
    no `foaf` prefix before, so every `foaf:primaryTopic` would have been dropped
    by a processor rather than resolved.
    """
    ctx = (await client.get("/catalog/context")).json()["@context"]
    assert ctx["foaf"] == "http://xmlns.com/foaf/0.1/"
    assert ctx["dcat:record"] == {"@container": "@set"}
    assert ctx["dcat:service"] == {"@container": "@set"}
