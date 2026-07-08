from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AggrMethod(str, Enum):
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


class AggrPeriod(str, Enum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"
    SECOND = "second"


class FiwareQueryModel(BaseModel):
    dataset_id: str
    entity_type: str
    entity_id: Optional[str] = None
    id_pattern: Optional[str] = None
    attrs: Optional[list[str]] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    aggr_method: Optional[AggrMethod] = None
    aggr_period: Optional[AggrPeriod] = None
    limit: int = Field(default=100, ge=1)
    offset: int = Field(default=0, ge=0)
    last_n: Optional[int] = Field(default=None, ge=1)
