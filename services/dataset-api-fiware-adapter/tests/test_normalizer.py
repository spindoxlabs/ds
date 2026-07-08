from dataset_api_fiware.normalizer import (
    normalize_single_entity,
    normalize_multi_entity,
    normalize_entities_list,
    normalize_response,
)


class TestSingleEntity:
    def test_basic(self):
        data = {
            "entityId": "urn:ngsi-ld:ACMeasurement:crs4:pv01",
            "index": ["2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z"],
            "attributes": [
                {"attrName": "activePower", "values": [100.5, 200.3]},
                {"attrName": "voltage", "values": [230.1, 229.8]},
            ],
        }
        rows = normalize_single_entity(data)
        assert len(rows) == 2
        assert rows[0]["entity_id"] == "urn:ngsi-ld:ACMeasurement:crs4:pv01"
        assert rows[0]["timestamp"] == "2024-01-01T00:00:00Z"
        assert rows[0]["activePower"] == 100.5
        assert rows[0]["voltage"] == 230.1
        assert rows[1]["activePower"] == 200.3

    def test_empty_index(self):
        data = {"entityId": "x", "index": [], "attributes": []}
        assert normalize_single_entity(data) == []

    def test_short_values(self):
        data = {
            "entityId": "x",
            "index": ["t1", "t2"],
            "attributes": [{"attrName": "a", "values": [1]}],
        }
        rows = normalize_single_entity(data)
        assert rows[0]["a"] == 1
        assert rows[1]["a"] is None


class TestMultiEntity:
    def test_basic(self):
        data = {
            "entityType": "ACMeasurement",
            "attrName": "activePower",
            "entities": [
                {
                    "entityId": "urn:1",
                    "index": ["t1", "t2"],
                    "values": [10, 20],
                },
                {
                    "entityId": "urn:2",
                    "index": ["t1"],
                    "values": [30],
                },
            ],
        }
        rows = normalize_multi_entity(data)
        assert len(rows) == 3
        assert rows[0]["entity_id"] == "urn:1"
        assert rows[0]["activePower"] == 10
        assert rows[2]["entity_id"] == "urn:2"
        assert rows[2]["activePower"] == 30

    def test_empty_entities(self):
        data = {"entityType": "T", "attrName": "a", "entities": []}
        assert normalize_multi_entity(data) == []


class TestEntitiesList:
    def test_basic(self):
        data = [
            {
                "id": "urn:1",
                "type": "T",
                "temperature": {"value": 22.5, "type": "Number"},
                "status": {"value": "on", "type": "Text"},
            },
            {
                "id": "urn:2",
                "type": "T",
                "temperature": {"value": 18.0, "type": "Number"},
            },
        ]
        rows = normalize_entities_list(data)
        assert len(rows) == 2
        assert rows[0]["entity_id"] == "urn:1"
        assert rows[0]["temperature"] == 22.5
        assert rows[0]["status"] == "on"
        assert rows[1]["temperature"] == 18.0

    def test_empty(self):
        assert normalize_entities_list([]) == []


class TestDispatch:
    def test_auto_detect_single(self):
        data = {"entityId": "x", "index": ["t1"], "attributes": []}
        rows = normalize_response(data)
        assert len(rows) == 1

    def test_auto_detect_multi(self):
        data = {"entities": [], "attrName": "a"}
        rows = normalize_response(data)
        assert rows == []

    def test_entities_list(self):
        data = [{"id": "x", "type": "T"}]
        rows = normalize_response(data, is_entities_list=True)
        assert len(rows) == 1

    def test_non_dict_returns_empty(self):
        assert normalize_response("garbage") == []
