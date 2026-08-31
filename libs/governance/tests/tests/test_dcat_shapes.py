"""`dcat:DataService` and `dcat:record` — `DSSC-PUB-41` and `-45`.

Both are mandatory and neither existed anywhere in the platform. The shapes live
in `ds.governance.dcat` rather than in either caller because **two** catalogues
are published from this repository — the compliance evidence bundle here, and
the federated index in `services/federated-catalog` — and two independent
readings of the same requirement is how a conformance claim becomes untrue in
one place and not the other.
"""

from __future__ import annotations

import pytest

from ds.governance.dcat import (
    CATALOG_CONTEXT,
    DSP_PROTOCOL_IRI,
    to_catalog_record,
    to_data_service,
)


class TestDataService:
    @pytest.mark.rule("C-9")
    def test_minimum_shape(self):
        service = to_data_service(
            service_id="urn:svc:1",
            title="Provider DSP endpoint",
            endpoint_url="http://edc:19194/protocol",
        )
        assert service["@type"] == "dcat:DataService"
        assert service["dcat:endpointURL"] == {"@id": "http://edc:19194/protocol"}

    @pytest.mark.rule("C-7")
    def test_serves_dataset_is_emitted_as_references(self):
        service = to_data_service(
            service_id="urn:svc:1",
            title="t",
            endpoint_url="http://e",
            serves_dataset=["urn:a", "urn:b"],
        )
        assert service["dcat:servesDataset"] == [{"@id": "urn:a"}, {"@id": "urn:b"}]

    def test_an_empty_dataset_list_is_omitted_rather_than_emitted_empty(self):
        """ "Serves nothing" and "we are not saying" are different claims.

        A live endpoint whose catalogue is momentarily empty is a real state, and
        `"dcat:servesDataset": []` asserts it positively. Omission leaves the
        service description true either way.
        """
        service = to_data_service(
            service_id="urn:svc:1",
            title="t",
            endpoint_url="http://e",
            serves_dataset=[],
        )
        assert "dcat:servesDataset" not in service

    @pytest.mark.rule("C-7", "M-4")
    def test_conforms_to_distinguishes_a_negotiable_endpoint(self):
        dsp = to_data_service(
            service_id="urn:svc:1",
            title="t",
            endpoint_url="http://e",
            conforms_to=DSP_PROTOCOL_IRI,
        )
        plain = to_data_service(
            service_id="urn:svc:2",
            title="t",
            endpoint_url="http://e",
        )
        assert dsp["dct:conformsTo"] == {"@id": DSP_PROTOCOL_IRI}
        assert "dct:conformsTo" not in plain


class TestCatalogRecord:
    @pytest.mark.rule("C-8")
    def test_points_at_its_dataset_via_primary_topic(self):
        record = to_catalog_record(dataset_id="urn:a", record_id="urn:rec:a")
        assert record["@type"] == "dcat:CatalogRecord"
        assert record["foaf:primaryTopic"] == {"@id": "urn:a"}

    def test_carries_the_catalogues_own_metadata_not_the_datasets(self):
        record = to_catalog_record(
            dataset_id="urn:a",
            record_id="urn:rec:a",
            modified="2026-08-02",
            source="did:web:provider.example.test",
        )
        assert record["dct:modified"] == "2026-08-02"
        assert record["dct:source"] == {"@id": "did:web:provider.example.test"}

    def test_unknown_metadata_is_omitted(self):
        record = to_catalog_record(dataset_id="urn:a", record_id="urn:rec:a")
        assert "dct:modified" not in record
        assert "dct:source" not in record


@pytest.mark.rule("C-8")
def test_the_context_defines_foaf():
    """`foaf:primaryTopic` arrives with `dcat:record` and needs its prefix.

    An emitted term the context does not define is dropped by a JSON-LD
    processor rather than resolved, so the record would parse as nothing.
    """
    assert CATALOG_CONTEXT["foaf"] == "http://xmlns.com/foaf/0.1/"
