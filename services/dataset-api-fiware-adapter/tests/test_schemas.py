from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from dataset_api_fiware.schemas import (
    AggrMethod,
    AggrPeriod,
    FiwareQueryModel,
)


def test_minimal_query():
    q = FiwareQueryModel(dataset_id="ds1", entity_type="ACMeasurement")
    assert q.limit == 100
    assert q.offset == 0
    assert q.entity_id is None
    assert q.attrs is None


def test_full_query():
    q = FiwareQueryModel(
        dataset_id="ds1",
        entity_type="ACMeasurement",
        entity_id="urn:ngsi-ld:ACMeasurement:crs4:pv01",
        attrs=["activePower", "reactivePower"],
        from_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        to_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        aggr_method=AggrMethod.AVG,
        aggr_period=AggrPeriod.HOUR,
        limit=500,
        offset=10,
        last_n=50,
    )
    assert q.aggr_method == AggrMethod.AVG
    assert q.aggr_period == AggrPeriod.HOUR
    assert q.limit == 500
    assert q.last_n == 50


def test_invalid_limit():
    with pytest.raises(ValidationError):
        FiwareQueryModel(dataset_id="ds1", entity_type="T", limit=0)


def test_invalid_offset():
    with pytest.raises(ValidationError):
        FiwareQueryModel(dataset_id="ds1", entity_type="T", offset=-1)


def test_aggr_method_values():
    for m in ("count", "sum", "avg", "min", "max"):
        assert AggrMethod(m).value == m


def test_aggr_period_values():
    for p in ("year", "month", "day", "hour", "minute", "second"):
        assert AggrPeriod(p).value == p
