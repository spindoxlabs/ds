"""An offboarded identity's DID stops resolving (R35).

The holder that serves a DID retires it once every credential it holds about
that identity is revoked in the issuer's register. Retiring keeps the row (the
identifier is evidence) and stops the document: 404, as for an unknown DID,
which is what a did:web resolver, EDC's included, reads as "does not resolve".
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from identity_registry.config import Settings
from identity_registry.db.models import Credential, Did
from identity_registry.services import did_retirement
from identity_registry.services.did_retirement import (
    anchor_reader,
    retire,
    retire_did,
    sweep,
)

CUSTODIAN = "did:web:rec.example.org"
PERSON = f"{CUSTODIAN}:users:ex-00001"
OTHER = f"{CUSTODIAN}:users:ex-00002"
ANCHOR = "did:web:trust-anchor.example.org"


def _credential(cid: str, subject: str, *, index: int | None = None, status="active"):
    return Credential(
        id=cid,
        credential_type="DataSubjectCredential",
        issuer_did=ANCHOR,
        subject_did=subject,
        credential_json={"credentialStatus": [{"statusPurpose": "revocation"}]},
        status=status,
        status_list_index=index,
        issued_at=datetime.now(UTC),
    )


def _participant() -> Settings:
    return Settings(role="participant", participant_did=CUSTODIAN)


def _reader(revoked: set[str], fail: set[str] = frozenset()):
    async def read(credential: Credential) -> bool | None:
        if credential.id in fail:
            raise RuntimeError("register unreachable")
        return credential.id in revoked

    return read


@pytest.fixture
async def held(db_session):
    db_session.add_all(
        [
            Did(did=CUSTODIAN, did_type="participant", active=True),
            Did(did=PERSON, did_type="user", active=True),
            Did(did=OTHER, did_type="user", active=True),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            _credential("p-1", PERSON),
            _credential("p-2", PERSON),
            _credential("o-1", OTHER),
            _credential("c-1", CUSTODIAN),
        ]
    )
    await db_session.commit()


@pytest.mark.rule("P-29")
async def test_a_person_whose_credentials_are_all_revoked_is_retired(db_session, held):
    result = await sweep(db_session, _participant(), _reader({"p-1", "p-2"}))

    assert result.retired == [PERSON] and result.clean
    person = await db_session.get(Did, PERSON)
    assert person.active is False and person.deactivated_at is not None
    # The held copies say so too, so they are no longer offered.
    assert (await db_session.get(Credential, "p-1")).status == "revoked"
    assert (await db_session.get(Did, OTHER)).active is True


@pytest.mark.rule("P-29")
async def test_one_standing_credential_keeps_the_did(db_session, held):
    result = await sweep(db_session, _participant(), _reader({"p-1"}))
    assert result.retired == []
    assert (await db_session.get(Did, PERSON)).active is True


@pytest.mark.rule("P-29")
async def test_an_unreadable_register_retires_nothing_and_is_reported(db_session, held):
    result = await sweep(
        db_session, _participant(), _reader({"p-1", "p-2"}, fail={"p-2"})
    )
    assert result.retired == [] and result.unknown == 1 and not result.clean
    assert (await db_session.get(Did, PERSON)).active is True


async def test_no_revocation_register_is_not_a_revocation(db_session, held):
    async def none(_):
        return None

    result = await sweep(db_session, _participant(), none)
    assert result.retired == []


@pytest.mark.rule("P-29")
async def test_a_participant_retires_its_own_did_once_revoked(db_session, held):
    result = await sweep(db_session, _participant(), _reader({"c-1"}))
    assert result.retired == [CUSTODIAN]


async def test_the_anchor_never_retires_a_participant_did(db_session, held):
    result = await sweep(db_session, Settings(), _reader({"c-1"}))
    assert CUSTODIAN not in result.retired


async def test_a_second_sweep_changes_nothing(db_session, held):
    await sweep(db_session, _participant(), _reader({"p-1", "p-2"}))
    again = await sweep(db_session, _participant(), _reader({"p-1", "p-2"}))
    assert again.retired == []


async def test_a_dry_run_changes_nothing(db_session, held):
    result = await sweep(
        db_session, _participant(), _reader({"p-1", "p-2"}), dry_run=True
    )
    assert result.retired == [PERSON]
    await db_session.rollback()
    assert (await db_session.get(Did, PERSON)).active is True


async def test_the_anchor_reads_its_own_record(db_session):
    assert await anchor_reader(_credential("a", PERSON, index=7, status="revoked"))
    assert not await anchor_reader(_credential("b", PERSON, index=8))
    # A copy it holds but did not issue names no index here: not its to read.
    assert await anchor_reader(_credential("c", PERSON, status="revoked")) is None


async def test_retire_is_idempotent(db_session, held):
    assert await retire_did(db_session, PERSON) is True
    assert await retire_did(db_session, PERSON) is False
    assert await retire_did(db_session, "did:web:nowhere.example.org") is None
    assert retire(Did(did="x", did_type="user", active=False)) is False


@pytest.mark.rule("P-29")
async def test_a_retired_did_no_longer_resolves(client, db_session, held):
    path = "/dids/" + PERSON + "/did.json"
    assert (await client.get(path)).status_code == 200
    await retire_did(db_session, PERSON)
    await db_session.commit()
    assert (await client.get(path)).status_code == 404


def test_the_cli_sweep_exits_non_zero_when_a_register_is_unreadable(monkeypatch):
    from identity_registry.cli import main as cli_main

    async def fake_ensure_db():
        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        return _Session

    async def fake_sweep(*_a, **_k):
        return did_retirement.SweepResult(examined=1, unknown=1)

    monkeypatch.setattr(cli_main, "_ensure_db", fake_ensure_db)
    monkeypatch.setattr(did_retirement, "sweep", fake_sweep)
    result = CliRunner().invoke(cli_main.app, ["did", "sweep"])
    assert result.exit_code == 1
    assert "1 unreadable" in result.output


async def test_a_holder_asks_the_issuer_s_register_at_the_anchor_s_address(
    monkeypatch,
):
    from ds_auth import user_credentials

    seen = {}

    def fake(vc, purpose, **kw):
        seen.update(kw, purpose=purpose)
        return True

    monkeypatch.setattr(user_credentials, "status_bit_set", fake)
    settings = Settings(
        role="participant",
        participant_did=CUSTODIAN,
        trust_anchor_url="https://trust-anchor.internal",
        trust_anchor_domain="trust-anchor.example.org",
    )
    read = did_retirement.register_reader(settings)
    assert await read(_credential("p-1", PERSON)) is True
    assert seen["purpose"] == "revocation"
    assert seen["register_origin"] == "https://trust-anchor.internal"
    assert seen["issuer"] == ANCHOR
