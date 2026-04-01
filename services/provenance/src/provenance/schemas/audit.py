"""Audit log schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AccessLogEntry(BaseModel):
    consumer_id: str
    dataset_id: str
    agreement_id: str | None = None
    transfer_id: str | None = None
    query_params: dict | None = None
    subject_ids: list[str] = []
    rows_returned: int | None = None
    response_status: int | None = None
    duration_ms: int | None = None
    provider_id: str | None = None


class AccessLogRead(AccessLogEntry):
    id: str
    logged_at: datetime

    model_config = {"from_attributes": True}


class AccessLogSummary(BaseModel):
    dataset_id: str
    from_: datetime | None = None
    until: datetime | None = None
    total_queries: int
    unique_consumers: int
    unique_subjects: int
    queries_by_consumer: dict[str, int]
    queries_by_day: dict[str, int]
