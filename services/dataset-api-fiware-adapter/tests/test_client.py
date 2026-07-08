import pytest
from fastapi import HTTPException

from dataset_api_fiware.client import QuantumLeapClient
from dataset_api_fiware.schemas import FiwareQueryModel


class TestEndpointSelection:
    def _client(self):
        return QuantumLeapClient(
            base_url="http://ql:8668",
            fiware_service="test",
        )

    def test_single_entity_single_attr(self):
        c = self._client()
        q = FiwareQueryModel(
            dataset_id="ds", entity_type="T",
            entity_id="urn:x", attrs=["temp"],
        )
        path, s, m, l = c._select_endpoint(q)
        assert path == "/v2/entities/urn:x/attrs/temp"
        assert s is True

    def test_single_entity_multi_attr(self):
        c = self._client()
        q = FiwareQueryModel(
            dataset_id="ds", entity_type="T",
            entity_id="urn:x", attrs=["temp", "humidity"],
        )
        path, s, m, l = c._select_endpoint(q)
        assert path == "/v2/entities/urn:x"
        assert s is True

    def test_multi_entity_single_attr(self):
        c = self._client()
        q = FiwareQueryModel(
            dataset_id="ds", entity_type="ACMeasurement",
            attrs=["activePower"],
        )
        path, s, m, l = c._select_endpoint(q)
        assert path == "/v2/types/ACMeasurement/attrs/activePower"
        assert m is True

    def test_multi_entity_multi_attr(self):
        c = self._client()
        q = FiwareQueryModel(
            dataset_id="ds", entity_type="ACMeasurement",
            attrs=["activePower", "voltage"],
        )
        path, s, m, l = c._select_endpoint(q)
        assert path == "/v2/types/ACMeasurement"
        assert m is True

    def test_multi_entity_no_attr(self):
        c = self._client()
        q = FiwareQueryModel(dataset_id="ds", entity_type="ACMeasurement")
        path, s, m, l = c._select_endpoint(q)
        assert path == "/v2/types/ACMeasurement"
        assert m is True


class TestHeaders:
    def test_basic_headers(self):
        c = QuantumLeapClient(
            base_url="http://ql:8668",
            fiware_service="crs4",
            fiware_service_path="/test",
        )
        h = c._headers()
        assert h["fiware-Service"] == "crs4"
        assert h["fiware-ServicePath"] == "/test"
        assert "Authorization" not in h

    def test_jwt_forwarding(self):
        c = QuantumLeapClient(base_url="http://ql:8668", fiware_service="crs4")
        h = c._headers(user_token="tok123")
        assert h["Authorization"] == "Bearer tok123"

    def test_no_service_path(self):
        c = QuantumLeapClient(base_url="http://ql:8668", fiware_service="crs4")
        h = c._headers()
        assert "fiware-ServicePath" not in h


class TestQueryParams:
    def test_basic(self):
        c = QuantumLeapClient(base_url="http://ql:8668", fiware_service="test")
        q = FiwareQueryModel(
            dataset_id="ds", entity_type="T", limit=50, offset=10,
        )
        p = c._query_params(q)
        assert p["limit"] == 50
        assert p["offset"] == 10

    def test_entity_ids(self):
        c = QuantumLeapClient(base_url="http://ql:8668", fiware_service="test")
        q = FiwareQueryModel(dataset_id="ds", entity_type="T")
        p = c._query_params(q, entity_ids=["urn:1", "urn:2"])
        assert p["id"] == "urn:1,urn:2"

    def test_attrs(self):
        c = QuantumLeapClient(base_url="http://ql:8668", fiware_service="test")
        q = FiwareQueryModel(dataset_id="ds", entity_type="T", attrs=["a", "b"])
        p = c._query_params(q)
        assert p["attrs"] == "a,b"
