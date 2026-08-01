"""`GET /ns/policy` serves the profile `Settings` names, and re-reads it on sync.

Two separate failures, both of which shipped:

* the route read ``CONNECTOR_ODRL_PROFILE_PATH`` straight from ``os.environ``
  while every other reader went through `Settings`, so the two could answer
  differently — and the one that publishes the catalogue is the other one;
* it cached the built vocabulary in its own ``lru_cache``, which
  `vocab.reset_caches()` does not reach, so `POST /provider/sync` re-read the
  profile from disk and this route kept serving the taxonomy the process
  booted with.

The second is the one that matters in a deployment: a consumer reads the
purpose taxonomy here before negotiating against policies the sync published
from a *different* profile.
"""
from __future__ import annotations

import textwrap

import pytest

from connector.api.v1 import namespace
from connector.config import Settings
from connector.services import consent_vocabulary as vocab

CUSTOM_PROFILE = textwrap.dedent(
    """
    namespace: "https://example.test/custom-policy/"
    prefix: "custom-policy"
    membership_operand: Membership
    consent_operand: ConsentStatus
    query_action: Query
    purpose_base: "purpose/"
    purposes:
      - slug: WidgetTelemetry
        label: Widget telemetry
    """
)


@pytest.fixture
def custom_profile(tmp_path):
    path = tmp_path / "custom-profile.yaml"
    path.write_text(CUSTOM_PROFILE, encoding="utf-8")
    return path


def _use_profile(monkeypatch, path) -> None:
    """Point `Settings` at *path* without touching ``os.environ``.

    Deliberately not `monkeypatch.setenv`: that would leave the two readers
    agreeing by accident, which is the thing under test.
    """
    settings = Settings(role="provider", odrl_profile_path=str(path) if path else None)
    monkeypatch.setattr(vocab, "get_settings", lambda: settings)
    vocab.reset_caches()


async def test_ns_policy_reads_the_profile_settings_names(
    client, monkeypatch, custom_profile
):
    _use_profile(monkeypatch, custom_profile)

    body = (await client.get("/ns/policy")).json()

    assert body["@context"]["@vocab"] == "https://example.test/custom-policy/"
    assert "custom-policy" in body["@context"]
    purposes = [n["@id"] for n in body["@graph"] if n.get("@type") == "skos:Concept"]
    assert purposes == ["https://example.test/custom-policy/purpose/WidgetTelemetry"]


async def test_ns_policy_follows_a_profile_change_after_reset_caches(
    client, monkeypatch, custom_profile
):
    """What `POST /provider/sync` does: re-read governance, drop the caches.

    Serve once so any cache is warm, then change the profile the way a sync
    would and serve again. The first response must not survive the reset.
    """
    _use_profile(monkeypatch, None)
    before = (await client.get("/ns/policy")).json()
    assert before["@context"]["@vocab"] != "https://example.test/custom-policy/"

    _use_profile(monkeypatch, custom_profile)
    after = (await client.get("/ns/policy")).json()

    assert after["@context"]["@vocab"] == "https://example.test/custom-policy/"


async def test_ns_policy_and_the_sync_agree_on_one_profile(
    client, monkeypatch, custom_profile
):
    """The published vocabulary and the mapper's must be the same object.

    `provider.py` maps assets and policies with `vocab.get_profile()`'s prefix;
    a consumer resolves the terms in those policies against what this route
    serves. Two profiles here is a catalogue nobody can negotiate against.
    """
    _use_profile(monkeypatch, custom_profile)

    body = (await client.get("/ns/policy")).json()

    assert body["@context"]["@vocab"] == vocab.get_profile().namespace
    assert namespace._get_vocab()["@context"] == body["@context"]
