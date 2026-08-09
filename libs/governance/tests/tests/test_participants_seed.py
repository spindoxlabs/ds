"""Tests for the participants-seed loaders.

The subject is not parsing — it is the difference between *"no seed was asked
for"* and *"the seed you asked for is not there"*. Both used to return ``None``,
and ``check_owners`` treats ``None`` as "nothing to check against" and returns
early. So a caller that named a missing file got a clean PASS with the
`owner-participant` check silently skipped, which is exactly what
`.github/workflows/compliance.yml` did from `5484ff0` onwards.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ds.governance.compliance.validator import load_participant_dids

SEED = """\
participants:
  - id: did:web:rec.dataspaces.localhost
    roles: [provider]
  - id: did:web:third-party.dataspaces.localhost
    roles: [consumer]
  - id: did:web:nameless.example
"""


@pytest.fixture
def seed(tmp_path: Path) -> Path:
    path = tmp_path / "participants.yaml"
    path.write_text(SEED, encoding="utf-8")
    return path


class TestNoSeedRequested:
    """``None`` means the caller said nothing, and stays a supported offline run."""

    def test_dids_none(self):
        assert load_participant_dids(None) is None


class TestMissingSeedIsAnError:
    def test_dids_raise(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="does not exist"):
            load_participant_dids(tmp_path / "not-here.yaml")

    def test_the_message_names_the_way_out(self, tmp_path: Path):
        """A hard error has to say what to do instead, or it just gets deleted."""
        with pytest.raises(FileNotFoundError) as exc:
            load_participant_dids(tmp_path / "not-here.yaml")
        assert "Omit --participants" in str(exc.value)


class TestReadsTheSeed:
    def test_dids(self, seed: Path):
        assert load_participant_dids(seed) == {
            "did:web:rec.dataspaces.localhost",
            "did:web:third-party.dataspaces.localhost",
            "did:web:nameless.example",
        }

    def test_empty_seed_is_not_an_error(self, tmp_path: Path):
        """An empty list is a statement; a missing file is not."""
        path = tmp_path / "participants.yaml"
        path.write_text("participants: []\n", encoding="utf-8")
        assert load_participant_dids(path) == set()
