"""A collector asserts whose keys it registers; the holder can act on it (ADR-0027).

A collector (a community, `example-rec`) registers its members' decisions at the
holder (`example-dso`) with their typed keys. These tests pin what the holder
now records and refuses:

- **the assertion** — `legal_basis.key_assertion`: codes and hashes only,
  evidence always, a verification that has already happened; required by the
  offer's governance, and by default for a `pod:` key outside `DS_ENV=dev`;
- **one owner per `pod:` key** — a second subject is a 409, the same subject
  re-registering is not, and the key is free again once the last grant
  carrying it ends;
- **the record** — `ConsentGranted` carries the assertion, `keys_digest` and
  `assertion_ref`; every ledger entry names the assertion;
- **the holder's suspension** — out of the served set, on the ledger and the
  chain, shown to the collector, and lifted only by a newer verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
from ds.governance import KeyAssertionPolicy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.api.v1 import consent as consent_route
from connector.config import get_settings
from connector.db.models import (
    ConsentKeyAssertionORM,
    ConsentKeyEventORM,
    ConsentKeyOwnerORM,
    ConsentRequestORM,
)
from connector.db.sealed import blind_index
from connector.dependencies import get_prov
from connector.registry.participants import CollectorAnswer
from connector.services import consent_vocabulary, key_records
from connector.services.membership_check import Membership
from tests import make_headers, make_org_headers, make_user_headers

COLLECTOR = "did:web:rec.example.org"
GRID = "did:web:dso.example.org"
OFFER = "test-meter-release"
DATASET = "datasets.silver.grid_meters"
HOLDER_READ = ("connector.consent.holder.read",)
PROVISION = ("connector.consent.provision",)
EVIDENCE = {
    "source": "community-portal",
    "consent_text_version": "1.0",
    "rendered_text_sha256": "c" * 64,
}
KEY_A, KEY_B = "pod:EX000E00000001", "pod:EX000E00000002"


def member(n: int) -> str:
    return f"did:web:rec.example.org:users:ex-{n:05d}"


A, B = member(1), member(2)


def assertion(**overrides) -> dict:
    body = {
        "terms": "rec-pod-assertion/1",
        "terms_sha256": "1" * 64,
        "method": "uploaded-document",
        "verification_ref": "00000000-0000-4000-8000-000000000001",
        "verified_by": "2" * 64,
        "verified_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "evidence": [{"kind": "utility_bill", "sha256": "3" * 64}],
    }
    body.update(overrides)
    return body


def collector() -> dict:
    return make_org_headers(
        context=COLLECTOR,
        scopes=PROVISION + HOLDER_READ + ("connector.consent.collector.read",),
        alias="example-rec",
    )


def holder() -> dict:
    return make_org_headers(scopes=HOLDER_READ)


class _Owners:
    async def by_id(self, alias: str):
        if alias != "grid-operator":
            return None
        return type("Owner", (), {"id": alias, "did": GRID})()


class _Prov:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def consent_granted(self, **kw):
        self.calls.append(("consent_granted", kw))

    async def consent_revoked(self, **kw):
        self.calls.append(("consent_revoked", kw))

    async def key_suspension(self, **kw):
        self.calls.append(("key_suspension", kw))

    def of(self, name: str) -> list[dict]:
        return [kw for n, kw in self.calls if n == name]


@pytest.fixture
def prov(client):
    fake = _Prov()
    client._transport.app.dependency_overrides[get_prov] = lambda: fake
    return fake


@pytest.fixture(autouse=True)
def _wired(client, monkeypatch):
    async def _member(_url, *, user_did, organization_alias, token_provider=None):
        return (
            Membership.MEMBER
            if organization_alias == "example-rec"
            else (Membership.NOT_MEMBER)
        )

    async def _collector(_request, holder_did, collector_did):
        if collector_did == COLLECTOR:
            return CollectorAnswer(True, "example-rec", "an accepted collector")
        return CollectorAnswer(False, None, "not an accepted collector")

    async def _admitted(*_args, consumer_id, **_kwargs):
        return {OFFER} if consumer_id == GRID else set()

    monkeypatch.setattr(consent_route, "check_subject_membership", _member)
    monkeypatch.setattr(consent_route, "check_collector", _collector)
    monkeypatch.setattr(consent_route, "_admitted_wildcard_offers", _admitted)
    client._transport.app.state.owners_registry = _Owners()


@pytest.fixture
def offer_requires(monkeypatch):
    """Make the fixture offer declare `key_assertion`, as a holder's would."""

    def declare(**policy):
        real = consent_vocabulary.resolve_offer

        def resolve(offer_id):
            offer = real(offer_id)
            if offer.id != OFFER:
                return offer
            return offer.model_copy(
                update={"key_assertion": KeyAssertionPolicy(**policy)}
            )

        monkeypatch.setattr(consent_route.vocab, "resolve_offer", resolve)

    return declare


async def _share(client, subject, *, keys=None, key_assertion=None, enabled=True):
    body = {
        "subject_id": subject,
        "offer_id": OFFER,
        "enabled": enabled,
        "decided_by": "subject",
    }
    if enabled:
        body["legal_basis"] = dict(EVIDENCE)
        if key_assertion is not None:
            body["legal_basis"]["key_assertion"] = key_assertion
    if keys is not None:
        body["keys"] = keys
    return await client.post("/consent/admin/shares", headers=collector(), json=body)


async def _served(client) -> list[str]:
    r = await client.get(
        "/consent/admin/holder/keys", params={"offer_id": OFFER}, headers=holder()
    )
    assert r.status_code == 200, r.text
    return [k["key"] for k in r.json()["keys"]]


async def _suspend(client, key, headers=None):
    return await client.post(
        "/consent/admin/holder/keys/suspend",
        headers=headers or holder(),
        json={"key": key, "reason": "holder_change"},
    )


async def _rows(engine, model):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        return list((await session.execute(select(model))).scalars())


# ── the assertion ────────────────────────────────────────────────────────────


@pytest.mark.rule("D-12", "D-12b")
@pytest.mark.asyncio
async def test_an_assertion_is_stored_with_the_grant_and_on_its_own(client, engine):
    sent = assertion()
    r = await _share(client, A, keys=[KEY_A], key_assertion=sent)
    assert r.status_code == 200, r.text
    [row] = r.json()
    stored = row["legal_basis"]["key_assertion"]
    assert stored["method"] == "uploaded-document"
    assert stored["evidence"] == sent["evidence"]

    [record] = await _rows(engine, ConsentKeyAssertionORM)
    assert record.assertion == stored
    assert record.collector == COLLECTOR
    canonical = json.dumps(stored, sort_keys=True, separators=(",", ":"))
    assert record.assertion_ref == hashlib.sha256(canonical.encode()).hexdigest()


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_an_offer_that_requires_an_assertion_refuses_a_grant_without_one(
    client, offer_requires
):
    offer_requires(required=True, methods=["uploaded-document"])
    r = await _share(client, A, keys=[KEY_A])
    assert r.status_code == 422, r.text
    assert "requires a key_assertion" in r.text


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_a_method_the_offer_does_not_accept_is_refused(client, offer_requires):
    offer_requires(required=True, methods=["uploaded-document"])
    r = await _share(
        client,
        A,
        keys=[KEY_A],
        key_assertion=assertion(method="offline-with-evidence"),
    )
    assert r.status_code == 422, r.text
    assert "not accepted" in r.text


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_an_undeclared_offer_requires_it_for_a_pod_key_outside_dev(
    client, monkeypatch
):
    monkeypatch.setattr(consent_route, "is_production", lambda: True)
    r = await _share(client, A, keys=[KEY_A])
    assert r.status_code == 422, r.text
    assert "pod: keys outside DS_ENV=dev" in r.text
    # A key of another type is not a supply point; nothing is assumed.
    r = await _share(client, A, keys=["meter:EX-M-1"])
    assert r.status_code == 200, r.text
    # With the assertion, the pod: key goes through.
    r = await _share(client, A, keys=[KEY_A], key_assertion=assertion())
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_in_dev_an_undeclared_offer_does_not_require_it(client):
    r = await _share(client, A, keys=[KEY_A])
    assert r.status_code == 200, r.text


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"method": "offline"}, "plain offline"),
        ({"evidence": []}, "no evidence"),
        ({"evidence": [{"kind": "utility_bill", "sha256": "abc"}]}, "short digest"),
        ({"evidence": [{"kind": "receipt", "sha256": "3" * 64}]}, "unknown kind"),
        ({"terms_sha256": "Z" * 64}, "not hex"),
        ({"verified_by": "operator-7"}, "not a pseudonym"),
        ({"verification_ref": "row-17"}, "not a uuid"),
        (
            {"verified_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
            "in the future",
        ),
        ({"verified_at": "2026-01-01T09:00:00"}, "no timezone"),
        ({"fiscal_code": "x"}, "an extra field"),
        ({"terms": "someone@example.org"}, "an address"),
    ],
)
async def test_an_assertion_that_proves_nothing_is_refused(client, change, why):
    r = await _share(client, A, keys=[KEY_A], key_assertion=assertion(**change))
    assert r.status_code == 422, (why, r.text)


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_an_assertion_without_keys_is_refused(client):
    r = await _share(client, A, key_assertion=assertion())
    assert r.status_code == 422, r.text
    assert "sends no keys" in r.text


# ── one owner per pod: key ───────────────────────────────────────────────────


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_a_second_subject_for_the_same_pod_key_is_a_conflict(client, engine):
    assert (await _share(client, A, keys=[KEY_A])).status_code == 200
    r = await _share(client, B, keys=[KEY_A])
    assert r.status_code == 409, r.text
    assert "held by another subject" in r.text
    # Neither the key nor the other subject is named.
    assert A not in r.text and KEY_A not in r.text
    # Nothing of B's was written.
    rows = await _rows(engine, ConsentRequestORM)
    assert {row.subject_id for row in rows} == {A}


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_the_same_subject_re_registering_its_key_is_fine(client, engine):
    assert (await _share(client, A, keys=[KEY_A])).status_code == 200
    assert (await _share(client, A, keys=[KEY_A, KEY_B])).status_code == 200
    owners = await _rows(engine, ConsentKeyOwnerORM)
    assert sorted((o.key_index, o.subject_id) for o in owners) == sorted(
        [(blind_index(KEY_A), A), (blind_index(KEY_B), A)]
    )
    assert all(o.released_at is None for o in owners)


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_the_key_is_free_once_the_last_grant_carrying_it_ends(client, engine):
    assert (await _share(client, A, keys=[KEY_A])).status_code == 200
    assert (await _share(client, A, enabled=False)).status_code == 200

    [owner] = await _rows(engine, ConsentKeyOwnerORM)
    assert owner.released_at is not None
    # Released, not deleted (retention).
    r = await _share(client, B, keys=[KEY_A])
    assert r.status_code == 200, r.text
    owners = await _rows(engine, ConsentKeyOwnerORM)
    active = [o.subject_id for o in owners if o.released_at is None]
    assert active == [B] and len(owners) == 2


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_a_key_change_releases_the_key_left_behind(client, engine):
    assert (await _share(client, A, keys=[KEY_A])).status_code == 200
    assert (await _share(client, A, keys=[KEY_B])).status_code == 200
    owners = {o.key_index: o for o in await _rows(engine, ConsentKeyOwnerORM)}
    assert owners[blind_index(KEY_A)].released_at is not None
    assert owners[blind_index(KEY_B)].released_at is None


# ── the record ───────────────────────────────────────────────────────────────


@pytest.mark.rule("D-12b", "L-2")
@pytest.mark.asyncio
async def test_the_grant_event_carries_the_assertion_and_both_digests(
    client, engine, prov
):
    sent = assertion()
    r = await _share(client, A, keys=[KEY_B, KEY_A], key_assertion=sent)
    assert r.status_code == 200, r.text
    [event] = prov.of("consent_granted")
    stored = event["legal_basis"]["key_assertion"]
    ref = key_records.sha256_hex(key_records.canonical(stored))
    digest = key_records.sha256_hex(
        "\n".join(sorted([blind_index(KEY_A), blind_index(KEY_B)]))
    )
    assert event["assertion_ref"] == ref
    assert event["keys_digest"] == digest
    # Never the keys themselves.
    assert KEY_A not in json.dumps(event, default=str)

    entries = await _rows(engine, ConsentKeyEventORM)
    assert entries and {e.assertion_ref for e in entries} == {ref}


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_a_key_change_is_a_new_fact_on_the_chain(client, prov):
    await _share(client, A, keys=[KEY_A])
    await _share(client, A, keys=[KEY_A])  # identical re-run
    await _share(client, A, keys=[KEY_B])  # the keys changed
    ids = [e["event_id"] for e in prov.of("consent_granted")]
    assert ids[0] == ids[1]
    assert ids[2] != ids[0]
    digests = [e["keys_digest"] for e in prov.of("consent_granted")]
    assert digests[0] != digests[2]


# ── the holder's suspension ──────────────────────────────────────────────────


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_a_suspended_key_leaves_the_served_set_and_shows_suspended(
    client, engine, prov
):
    await _share(client, A, keys=[KEY_A], key_assertion=assertion())
    await _share(client, B, keys=[KEY_B])
    assert await _served(client) == [KEY_A, KEY_B]

    r = await _suspend(client, KEY_A)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["grants_affected"], body["already_suspended"]) == (1, False)
    assert await _served(client) == [KEY_B]

    entries = [
        (e.event, e.cause)
        for e in await _rows(engine, ConsentKeyEventORM)
        if e.key_index == blind_index(KEY_A)
    ]
    assert entries == [("added", "grant"), ("removed", "holder_suspension")]

    [event] = prov.of("key_suspension")
    assert event["action"] == "suspended"
    assert event["reason"] == "holder_change"
    assert event["keys_digest"] == key_records.sha256_hex(blind_index(KEY_A))
    assert event["subject_id"] == A
    assert KEY_A not in json.dumps(event, default=str)

    r = await client.get(
        "/consent/admin/subject-shares",
        params={"subject_id": A},
        headers=collector(),
    )
    assert r.status_code == 200, r.text
    [share] = r.json()
    assert share["keys"] == [KEY_A]
    assert share["suspended_keys"] == [KEY_A]

    # Idempotent while it stays suspended.
    again = (await _suspend(client, KEY_A)).json()
    assert again["already_suspended"] is True
    assert len(prov.of("key_suspension")) == 1


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_only_a_newer_verification_lifts_a_suspension(client, engine, prov):
    old = assertion(verified_at=(datetime.now(UTC) - timedelta(days=3)).isoformat())
    await _share(client, A, keys=[KEY_A], key_assertion=old)
    assert (await _suspend(client, KEY_A)).status_code == 200

    # The same, older verification does not lift it.
    r = await _share(client, A, keys=[KEY_A], key_assertion=old)
    assert r.status_code == 409, r.text
    assert "suspended by the holder" in r.text
    assert await _served(client) == []

    newer = assertion(
        verification_ref="00000000-0000-4000-8000-000000000002",
        verified_at=datetime.now(UTC).isoformat(),
    )
    r = await _share(client, A, keys=[KEY_A], key_assertion=newer)
    assert r.status_code == 200, r.text
    assert await _served(client) == [KEY_A]
    [row] = r.json()
    assert row["legal_basis"]["key_assertion"]["verification_ref"].endswith("2")

    causes = [
        e.cause
        for e in sorted(await _rows(engine, ConsentKeyEventORM), key=lambda e: e.id)
    ]
    assert causes == ["grant", "holder_suspension", "suspension_lifted"]
    lifted = [e for e in prov.of("key_suspension") if e["action"] == "lifted"]
    assert len(lifted) == 1 and lifted[0]["collector"] == COLLECTOR


@pytest.mark.rule("D-12b")
@pytest.mark.asyncio
async def test_a_suspended_key_cannot_be_claimed_without_a_newer_verification(
    client,
):
    """Not by the old holder's collector, and not for a new subject either."""
    await _share(client, A, keys=[KEY_A])
    assert (await _suspend(client, KEY_A)).status_code == 200
    await _share(client, A, enabled=False)
    r = await _share(
        client,
        B,
        keys=[KEY_A],
        key_assertion=assertion(
            verified_at=(datetime.now(UTC) - timedelta(days=1)).isoformat()
        ),
    )
    assert r.status_code == 409, r.text
    r = await _share(
        client,
        B,
        keys=[KEY_A],
        key_assertion=assertion(verified_at=datetime.now(UTC).isoformat()),
    )
    assert r.status_code == 200, r.text


@pytest.mark.rule("D-12b", "D-20")
@pytest.mark.asyncio
async def test_only_the_holder_s_writers_suspend(client):
    await _share(client, A, keys=[KEY_A])
    # A collector is refused (it withdraws instead).
    assert (await _suspend(client, KEY_A, collector())).status_code == 403
    # A plain service token names no organisation.
    r = await _suspend(
        client, KEY_A, make_headers(scope="connector.consent.holder.read")
    )
    assert r.status_code == 403
    # A participant operator seat is not the holder.
    r = await _suspend(
        client,
        KEY_A,
        make_user_headers(organizations={"example-org": ["ds-participant-admin"]}),
    )
    assert r.status_code == 403
    # The deployment operator may.
    r = await _suspend(client, KEY_A, make_user_headers(roles=["platform-admin"]))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_a_suspension_names_a_reason_and_a_typed_key(client):
    r = await client.post(
        "/consent/admin/holder/keys/suspend",
        headers=holder(),
        json={"key": KEY_A, "reason": "because"},
    )
    assert r.status_code == 422
    r = await client.post(
        "/consent/admin/holder/keys/suspend",
        headers=holder(),
        json={"key": "EX000E00000001", "reason": "holder_change"},
    )
    assert r.status_code == 422


# ── the recipes ──────────────────────────────────────────────────────────────


def test_the_recipes_are_the_documented_ones():
    ki = sorted([blind_index(KEY_A), blind_index(KEY_B)])
    assert (
        key_records.keys_digest([KEY_B, KEY_A, KEY_A])
        == hashlib.sha256("\n".join(ki).encode()).hexdigest()
    )
    assert key_records.keys_digest([]) is None
    assert (
        key_records.decision_ref("agr-1", [KEY_B, KEY_A])
        == hashlib.sha256(("agr-1\n" + "\n".join(ki)).encode()).hexdigest()
    )
    assert (
        key_records.decision_ref("agr-1", []) == hashlib.sha256(b"agr-1\n").hexdigest()
    )
    # Keyed: the index is not a plain hash of the key.
    assert blind_index(KEY_A) != hashlib.sha256(KEY_A.encode()).hexdigest()


def test_the_settings_default_to_the_civil_limitation_period():
    assert get_settings().key_record_retention_days == 3650


@pytest.mark.asyncio
async def test_a_failed_emit_is_logged_as_an_error(caplog):
    from connector.clients.provenance import ProvenanceClient

    client = ProvenanceClient("http://127.0.0.1:9")
    with caplog.at_level(logging.WARNING, logger="connector.clients.provenance"):
        assert (
            await client.emit_event({"event_type": "QueryExecuted", "event_id": "q"})
            is None
        )
    await client.close()
    [record] = caplog.records
    assert record.levelno == logging.ERROR
    assert "QueryExecuted" in record.getMessage()


@pytest.mark.rule("D-12b")
def test_the_grid_operator_example_requires_the_assertion():
    """The shipped holder governance declares what ADR-0027 asks of a holder."""
    from pathlib import Path

    from ds.governance import load_sharing_offers

    path = (
        Path(__file__).parents[1] / "governance-grid-operator" / "sharing-offers.yaml"
    )
    catalogue = load_sharing_offers(path)
    for offer_id in ("grid-meter-release", "grid-meter-flexibility"):
        policy = catalogue.get(offer_id).key_assertion
        assert policy is not None and policy.required, offer_id
        assert "offline" not in policy.methods
