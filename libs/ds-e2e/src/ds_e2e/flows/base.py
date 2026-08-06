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
        """Restore whatever this flow changed outside its own records.

        `runner.run_flow` calls this in a `finally` for **every** flow, so it
        runs on the exception path as well as the happy one. Override it when a
        flow mutates the stack itself — `fail-closed` stops a container — and
        make it idempotent: `execute` is expected to undo its own work too, so
        this is the net, not the primary path.
        """
