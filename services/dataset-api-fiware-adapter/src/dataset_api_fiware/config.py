from __future__ import annotations

from pydantic import BaseModel, Field


class FiwareSettings(BaseModel):
    enabled: bool = True
    default_timeout_ms: int = Field(default=10000, ge=1000)
    max_limit: int = Field(default=10000, ge=1)
    jwt_forwarding: bool = False
