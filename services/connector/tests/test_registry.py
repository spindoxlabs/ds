"""Tests for ParticipantRegistry."""
import textwrap
from pathlib import Path

import pytest

from connector.registry.participants import (
    Participant,
    ParticipantRegistry,
    UnknownParticipantError,
)


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "participants.yaml"
    p.write_text(textwrap.dedent(content))
    return p


def test_from_file_loads_participants(tmp_path):
    p = _write_yaml(tmp_path, """
        participants:
          - id: provider
            dsp_address: http://edc-provider:19194/protocol
            allowed_scopes: [dataspaces.query, dataspaces.admin]
            role: provider
          - id: consumer
            dsp_address: http://edc-consumer:29194/protocol
            allowed_scopes: [dataspaces.query]
            role: consumer
    """)
    registry = ParticipantRegistry.from_file(p)
    assert len(registry.all()) == 2


def test_validate_known_participant(tmp_path):
    p = _write_yaml(tmp_path, """
        participants:
          - id: consumer
            dsp_address: http://edc-consumer:29194/protocol
            allowed_scopes: [dataspaces.query]
            role: consumer
    """)
    registry = ParticipantRegistry.from_file(p)
    participant = registry.validate("http://edc-consumer:29194/protocol")
    assert participant.id == "consumer"


def test_validate_unknown_raises(tmp_path):
    registry = ParticipantRegistry.from_file(tmp_path / "missing.yaml")
    with pytest.raises(UnknownParticipantError):
        registry.validate("http://unknown:9999/protocol")


def test_get_by_id(tmp_path):
    p = _write_yaml(tmp_path, """
        participants:
          - id: provider
            dsp_address: http://edc-provider:19194/protocol
            role: provider
    """)
    registry = ParticipantRegistry.from_file(p)
    participant = registry.get_by_id("provider")
    assert participant is not None
    assert participant.role == "provider"
    assert registry.get_by_id("nonexistent") is None


def test_empty_registry():
    registry = ParticipantRegistry.empty()
    assert registry.all() == []
    with pytest.raises(UnknownParticipantError):
        registry.validate("any")
