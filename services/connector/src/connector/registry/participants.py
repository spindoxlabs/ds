"""Participant registry — static trust anchor loaded from participants.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class Participant(BaseModel):
    id: str
    dsp_address: str
    allowed_scopes: list[str] = []
    role: str = "consumer"


class UnknownParticipantError(ValueError):
    pass


class ParticipantRegistry:
    def __init__(self, participants: list[Participant]):
        self._by_id: dict[str, Participant] = {p.id: p for p in participants}
        self._by_dsp: dict[str, Participant] = {p.dsp_address: p for p in participants}

    @classmethod
    def from_file(cls, path: Path) -> ParticipantRegistry:
        if not path.exists():
            return cls([])
        with path.open("r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        participants = [
            Participant.model_validate(p)
            for p in (raw.get("participants") or [])
        ]
        return cls(participants)

    @classmethod
    def empty(cls) -> ParticipantRegistry:
        return cls([])

    def validate(self, counter_party_address: str) -> Participant:
        """Return participant by DSP address; raise if not registered."""
        p = self._by_dsp.get(counter_party_address)
        if p is None:
            raise UnknownParticipantError(
                f"Participant with DSP address '{counter_party_address}' is not registered"
            )
        return p

    def get_by_id(self, participant_id: str) -> Participant | None:
        return self._by_id.get(participant_id)

    def all(self) -> list[Participant]:
        return list(self._by_id.values())
