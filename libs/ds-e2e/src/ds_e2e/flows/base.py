from __future__ import annotations

from abc import ABC, abstractmethod

from ds_e2e.config import E2ESettings
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult


class BaseFlow(ABC):
    name: str
    description: str

    def __init__(self, settings: E2ESettings, http: HttpClient):
        self.settings = settings
        self.http = http

    @abstractmethod
    def execute(self) -> FlowResult: ...

    def cleanup(self) -> None:
        """Override for per-flow cleanup. Default: no-op."""
