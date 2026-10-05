"""A person's credential lives a month and is renewed before it expires (`D-56`).

`ir-cli credential renew` issues a **successor** — same subject, DID, role and
organisation, a new id and status-list index — for every credential in the
renewal window, delivers it to the linked organisation's custodian and leaves
the predecessor to expire. The assertions that matter:

* nothing is renewed for a person who is no longer somebody's member, whose
  organisation is suspended, or whose credential was revoked or suspended —
  checked again at insert, not only when the candidates were chosen;
* a released (spent) DID is never revived;
* a second run issues nothing;
* every path that retires a person's credentials retires the successor too, so
  a release that raced a renewal sees what is left and goes again;
* `/users/resolve` puts the successor first, which is what the portal presents.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from conftest import (
    ANCHOR_DID,
    CUSTODIAN_DID,
    REAL_ASYNC_CLIENT,
    TEST_DATABASE_URL,
    make_headers,
    register_custodian,
)
from sqlalchemy import select, update
from test_suspended_organisation_cleanup import cli_database  # noqa: F401
from typer.testing import CliRunner

from identity_registry.config import Settings
from identity_registry.db.models import (
    Credential,
    Did,
    KeycloakMapping,
    OrganizationMembership,
    Owner,
    StatusList,
)

SUBJECT_ID = "ex-00001"
SUBJECT_DID = f"{CUSTODIAN_DID}:users:{SUBJECT_ID}"
ORG = "example-rec"
ROLE = "DataSubject"
OTHER_DID = "did:web:dso.dataspaces.localhost"
HEADERS = make_headers()
RESOLVE = make_headers(scope="identity-registry.resolve")


def _settings(**overrides) -> Settings:
    return Settings(database_url=TEST_DATABASE_URL, oidc_issuer_url=None, **overrides)


def _now() -> datetime:
    return datetime.now(UTC)


async def _ensure_anchor(db) -> None:
    """The anchor's key and DID, as `conftest.anchor_identity` writes them."""
    from identity_registry.config import get_settings
    from identity_registry.db.models import Key
    from identity_registry.services.crypto import encrypt_private_jwk, generate_key_pair

    if await db.get(Did, ANCHOR_DID) is not None:
        return
    kp = generate_key_pair(ANCHOR_DID)
    key = Key(
        owner_did=ANCHOR_DID,
        kid=kp.kid,
        private_jwk=encrypt_private_jwk(kp.private_jwk, get_settings().encryption_key),
        public_jwk=kp.public_jwk,
    )
    db.add(key)
    await db.flush()
    db.add(Did(did=ANCHOR_DID, did_type="participant", key_id=key.id))
    await db.commit()


async def _seed_member(db, *, owner_status: str = "verified", member: bool = True):
    """A verified organisation, its custodian, and a person who is its member."""
    await _ensure_anchor(db)
    await register_custodian(db)
    db.add(
        Owner(
            id=ORG,
            name="Example REC",
            did=CUSTODIAN_DID,
            status=owner_status,
            verified_by="test",
        )
    )
    db.add(Did(did=SUBJECT_DID, did_type="user", key_id=None))
    await db.flush()
    if member:
        db.add(OrganizationMembership(user_did=SUBJECT_DID, organization_alias=ORG))
    db.add(
        KeycloakMapping(
            did=SUBJECT_DID,
            keycloak_realm="dataspaces",
            keycloak_user_id="kc-ex-00001",
            username="person-a",
            subject_id=SUBJECT_DID,
        )
    )
    await db.commit()


async def _issue(
    db, *, expires_in: timedelta, role: str = ROLE, linked: str = CUSTODIAN_DID
) -> str:
    """A signed `DataSubjectCredential` with *expires_in* left, issued 30 days
    before it expires — what the admin API writes, aged."""
    from identity_registry.services.crypto import decrypt_private_jwk
    from identity_registry.services.org_onboarding import get_trust_anchor_key
    from identity_registry.services.status_list import (
        SUSPENSION_LIST_ID,
        allocate_suspendable_index,
    )
    from identity_registry.services.vc import (
        build_data_subject_credential,
        sign_credential,
    )

    settings = _settings()
    key = await get_trust_anchor_key(db, settings)
    index = await allocate_suspendable_index(db)
    vc = build_data_subject_credential(
        issuer_did=ANCHOR_DID,
        subject_did=SUBJECT_DID,
        role=role,
        community_role="consumer",
        linked_participant_did=linked,
        credentials_context_url=settings.credentials_context_url,
        dataspace_uri=settings.dataspace_uri,
        status_list_credential_url=settings.status_list_url(),
        suspension_list_credential_url=settings.status_list_url(SUSPENSION_LIST_ID),
        status_list_index=index,
        ttl_days=30,
        verified_by=linked,
        verification_method="id-document",
    )
    signed = sign_credential(
        vc, decrypt_private_jwk(key.private_jwk, settings.encryption_key), key.kid
    )
    expires = _now() + expires_in
    db.add(
        Credential(
            id=signed["id"],
            credential_type="DataSubjectCredential",
            issuer_did=ANCHOR_DID,
            subject_did=SUBJECT_DID,
            credential_json=signed,
            status_list_index=index,
            issued_at=expires - timedelta(days=30),
            expires_at=expires,
        )
    )
    await db.commit()
    return signed["id"]


async def _rows(db) -> dict[str, Credential]:
    db.expire_all()
    rows = (
        (
            await db.execute(
                select(Credential).where(
                    Credential.credential_type == "DataSubjectCredential"
                )
            )
        )
        .scalars()
        .all()
    )
    return {c.id: c for c in rows}


async def _renew(db, **kwargs):
    from identity_registry.services.renewal import renew_due

    return await renew_due(db, kwargs.pop("settings", _settings()), **kwargs)


async def _next_index(db) -> int:
    db.expire_all()
    rows = (await db.execute(select(StatusList.next_index))).scalars().all()
    return sum(rows)


@pytest.fixture
async def member(db_session, credential_store):
    await _seed_member(db_session)
    return credential_store


# ── lifetime ──────────────────────────────────────────────────────


@pytest.mark.rule("D-56")
async def test_a_person_is_issued_for_thirty_days_and_capped_at_ninety(
    client, db_session, anchor_identity, credential_store
):
    await register_custodian(db_session)
    for ttl, expected in ((None, 30), (200, 90), (45, 45)):
        body = {
            "subject_id": f"ex-ttl-{expected}",
            "role": ROLE,
            "linked_participant_did": CUSTODIAN_DID,
        }
        if ttl is not None:
            body["ttl_days"] = ttl
        r = await client.post(
            "/admin/credentials/data-subject", json=body, headers=HEADERS
        )
        assert r.status_code == 201, r.text
        cred = await db_session.get(Credential, r.json()["credentialId"])
        left = cred.expires_at.replace(tzinfo=UTC) - _now()
        assert timedelta(days=expected - 1) < left <= timedelta(days=expected)


@pytest.mark.rule("D-56")
def test_a_renewal_window_as_long_as_the_lifetime_is_refused():
    """Every successor would be due at birth and every run would issue again."""
    with pytest.raises(ValueError, match="RENEWAL_WINDOW_DAYS"):
        _settings(data_subject_credential_renewal_window_days=30)


# ── the window ────────────────────────────────────────────────────


@pytest.mark.rule("D-56")
async def test_a_credential_in_the_window_gets_a_successor(db_session, member):
    old = await _issue(db_session, expires_in=timedelta(days=5))

    report = await _renew(db_session)

    assert report.renewed == 1 and report.failed == 0
    rows = await _rows(db_session)
    assert len(rows) == 2
    new = next(c for c in rows.values() if c.id != old)
    # The predecessor is left to expire, untouched.
    assert rows[old].status == "active"
    assert new.status == "active"
    assert new.subject_did == SUBJECT_DID
    assert new.status_list_index != rows[old].status_list_index
    before = rows[old].credential_json["credentialSubject"]
    after = new.credential_json["credentialSubject"]
    for claim in ("id", "role", "linkedParticipant", "communityRole", "verifiedBy"):
        assert after[claim] == before[claim]
    left = new.expires_at.replace(tzinfo=UTC) - _now()
    assert timedelta(days=29) < left <= timedelta(days=30)


@pytest.mark.rule("D-56")
async def test_outside_the_window_nothing_is_issued(db_session, member):
    await _issue(db_session, expires_in=timedelta(days=11))
    report = await _renew(db_session)
    assert report.renewed == 0 and report.not_due == 1
    assert len(await _rows(db_session)) == 1


@pytest.mark.rule("D-56")
async def test_the_window_is_a_setting(db_session, member):
    await _issue(db_session, expires_in=timedelta(days=15))
    report = await _renew(
        db_session,
        settings=_settings(data_subject_credential_renewal_window_days=20),
    )
    assert report.renewed == 1


@pytest.mark.rule("D-56")
async def test_a_second_run_the_same_day_issues_nothing(db_session, member):
    await _issue(db_session, expires_in=timedelta(days=3))
    await _renew(db_session)
    rows, index = await _rows(db_session), await _next_index(db_session)

    again = await _renew(db_session)

    assert again.renewed == 0 and again.failed == 0
    assert await _rows(db_session) == rows
    assert await _next_index(db_session) == index


@pytest.mark.rule("D-56")
async def test_delivered_only_to_the_linked_organisation(db_session, member):
    await register_custodian(db_session, OTHER_DID)
    await _issue(db_session, expires_in=timedelta(days=3))
    member.clear()

    await _renew(db_session)

    assert len(member) == 1
    assert member[0]["url"].startswith(
        f"http://rec.dataspaces.localhost/credentials/{CUSTODIAN_DID}"
    )
    payload = member[0]["body"]["credentials"][0]["payload"]
    assert payload["credentialSubject"]["linkedParticipant"] == CUSTODIAN_DID


# ── renewed only from a live predecessor ──────────────────────────


@pytest.mark.rule("D-56")
@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("membership", "membership_gone"),
        ("suspend_org", "organisation_not_verified"),
        ("suspend_credential", None),
        ("revoke_credential", None),
    ],
)
async def test_nothing_is_renewed_for_somebody_who_is_not_a_live_member(
    db_session, member, change, reason
):
    old = await _issue(db_session, expires_in=timedelta(days=3))
    if change == "membership":
        await db_session.execute(
            OrganizationMembership.__table__.delete().where(
                OrganizationMembership.user_did == SUBJECT_DID
            )
        )
    elif change == "suspend_org":
        await db_session.execute(
            update(Owner).where(Owner.id == ORG).values(status="suspended")
        )
    else:
        status = "suspended" if change == "suspend_credential" else "revoked"
        await db_session.execute(
            update(Credential).where(Credential.id == old).values(status=status)
        )
    await db_session.commit()

    report = await _renew(db_session)

    assert report.renewed == 0 and report.failed == 0
    assert list(await _rows(db_session)) == [old]
    if reason:
        assert report.subjects[SUBJECT_DID].skipped == {reason: 1}


@pytest.mark.rule("D-56")
@pytest.mark.parametrize("change", ["membership", "revoke_credential", "suspend_org"])
async def test_the_checks_run_again_at_insert(engine, db_session, member, change):
    """Chosen while live, changed before the insert: refused, nothing written.

    What a release looks like from the renewal's side — it removes the
    membership and revokes, in its own transactions, between the two reads.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from identity_registry.services.renewal import (
        SigningKey,
        SubjectResult,
        candidates,
        renew_one,
    )

    old = await _issue(db_session, expires_in=timedelta(days=3))
    settings = _settings()
    chosen = await candidates(db_session, settings)
    assert [c.credential_id for c in chosen] == [old]

    async with async_sessionmaker(engine, expire_on_commit=False)() as other:
        if change == "membership":
            await other.execute(OrganizationMembership.__table__.delete())
        elif change == "suspend_org":
            await other.execute(update(Owner).values(status="suspended"))
        else:
            await other.execute(
                update(Credential).where(Credential.id == old).values(status="revoked")
            )
        await other.commit()

    from identity_registry.services.org_onboarding import get_trust_anchor_key

    key = await get_trust_anchor_key(db_session, settings)
    result = SubjectResult(SUBJECT_DID)
    successor = await renew_one(
        db_session,
        settings,
        chosen[0],
        result,
        anchor_key=SigningKey(kid=key.kid, private_jwk=key.private_jwk),
        now=_now(),
    )

    assert successor is None
    assert list(await _rows(db_session)) == [old]
    assert sum(result.skipped.values()) == 1 and not result.failed


@pytest.mark.rule("D-56")
async def test_a_spent_did_is_never_revived(client, db_session, member):
    """Every credential revoked: the identity was released (ADR-0028). Not even
    the operator's recovery renews it."""
    old = await _issue(db_session, expires_in=timedelta(days=-2))
    r = await client.delete(f"/admin/credentials/{old}", headers=HEADERS)
    assert r.status_code == 204

    for kwargs in ({}, {"subject_did": SUBJECT_DID}):
        report = await _renew(db_session, **kwargs)
        assert report.renewed == 0
    assert list(await _rows(db_session)) == [old]


# ── expiry and recovery ───────────────────────────────────────────


@pytest.mark.rule("D-56")
async def test_a_recently_expired_credential_of_a_member_is_renewed(db_session, member):
    await _issue(db_session, expires_in=timedelta(days=-5))
    report = await _renew(db_session)
    assert report.renewed == 1


@pytest.mark.rule("D-56")
async def test_an_old_expiry_needs_the_operator(db_session, member):
    await _issue(db_session, expires_in=timedelta(days=-45))

    daily = await _renew(db_session)
    assert daily.renewed == 0
    assert daily.subjects[SUBJECT_DID].skipped == {"expired_beyond_grace": 1}

    recovery = await _renew(db_session, subject_did=SUBJECT_DID)
    assert recovery.renewed == 1


# ── failure ───────────────────────────────────────────────────────


@pytest.fixture
def refusing_store(monkeypatch):
    from identity_registry.services import issuance

    def _client(**kwargs):
        kwargs.pop("transport", None)
        return REAL_ASYNC_CLIENT(
            transport=httpx.MockTransport(lambda _r: httpx.Response(503)), **kwargs
        )

    monkeypatch.setattr(issuance.httpx, "AsyncClient", _client)


@pytest.mark.rule("D-56")
async def test_a_failed_signing_leaves_the_predecessor_and_the_next_run_retries(
    db_session, member, monkeypatch
):
    from identity_registry.services import renewal

    old = await _issue(db_session, expires_in=timedelta(days=3))

    real = renewal.sign_credential

    def _broken(*_a, **_k):
        raise RuntimeError("signing failed")

    monkeypatch.setattr(renewal, "sign_credential", _broken)
    failed = await _renew(db_session)
    assert failed.failed == 1 and failed.renewed == 0
    assert failed.subjects[SUBJECT_DID].failed == {"error": 1}
    rows = await _rows(db_session)
    assert list(rows) == [old] and rows[old].status == "active"

    monkeypatch.setattr(renewal, "sign_credential", real)
    retried = await _renew(db_session)
    assert retried.renewed == 1


@pytest.mark.rule("D-56")
async def test_a_failed_delivery_is_retried_on_the_next_run(
    db_session, member, monkeypatch
):
    """The successor is recorded either way; the next run re-delivers it."""
    from identity_registry.services import issuance

    await _issue(db_session, expires_in=timedelta(days=3))
    recording = issuance.httpx.AsyncClient

    def _refuse(**kwargs):
        kwargs.pop("transport", None)
        return REAL_ASYNC_CLIENT(
            transport=httpx.MockTransport(lambda _r: httpx.Response(503)), **kwargs
        )

    monkeypatch.setattr(issuance.httpx, "AsyncClient", _refuse)
    first = await _renew(db_session)
    assert first.renewed == 1 and first.failed == 1

    monkeypatch.setattr(issuance.httpx, "AsyncClient", recording)
    member.clear()
    second = await _renew(db_session)
    assert second.renewed == 0 and second.failed == 0
    assert second.subjects[SUBJECT_DID].redelivered == 1
    assert len(member) == 1
    assert len(await _rows(db_session)) == 2


def _seed_file(url: str, *, expires_in: timedelta) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    async def _go():
        eng = create_async_engine(url, poolclass=NullPool)
        async with async_sessionmaker(eng, expire_on_commit=False)() as db:
            await _seed_member(db)
            await _issue(db, expires_in=expires_in)
        await eng.dispose()

    asyncio.run(_go())


@pytest.fixture
def cli_db(cli_database, monkeypatch):  # noqa: F811
    """ir-cli refuses its dev defaults outside DS_ENV=dev; not this test's subject."""
    monkeypatch.setenv("DS_ENV", "dev")
    return cli_database


@pytest.mark.rule("D-56")
def test_the_job_exits_non_zero_when_a_renewal_failed(cli_db, refusing_store):
    from identity_registry.cli.main import app as cli

    _seed_file(cli_db, expires_in=timedelta(days=2))

    r = CliRunner().invoke(cli, ["credentials", "renew"])

    assert r.exit_code == 1, r.output
    report = json.loads(r.stdout)
    assert report["renewed"] == 1 and report["failed"] == 1
    assert report["subjects"] == [
        {
            "did": SUBJECT_DID,
            "renewed": 1,
            "redelivered": 0,
            "skipped": {},
            "failed": {"delivery": 1},
        }
    ]
    assert "@" not in r.stdout


@pytest.mark.rule("D-56")
def test_the_job_exits_zero_and_dry_run_writes_nothing(cli_db, credential_store):
    import sqlite3

    from identity_registry.cli.main import app as cli

    _seed_file(cli_db, expires_in=timedelta(days=2))
    count = (
        "SELECT count(*) FROM credentials WHERE credential_type='DataSubjectCredential'"
    )

    dry = CliRunner().invoke(cli, ["credential", "renew", "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert json.loads(dry.stdout)["skipped"] == {"would_renew": 1}
    with sqlite3.connect(cli_db.removeprefix("sqlite+aiosqlite:///")) as conn:
        assert conn.execute(count).fetchone()[0] == 1

    real = CliRunner().invoke(cli, ["credential", "renew", "--subject", SUBJECT_DID])
    assert real.exit_code == 0, real.output
    assert json.loads(real.stdout)["renewed"] == 1
    with sqlite3.connect(cli_db.removeprefix("sqlite+aiosqlite:///")) as conn:
        assert conn.execute(count).fetchone()[0] == 2


# ── what retires a person's credentials retires the successor ─────


async def _resolved(client) -> list[str]:
    import jwt as pyjwt

    r = await client.post(
        "/users/resolve", json={"username": "person-a"}, headers=RESOLVE
    )
    if r.status_code == 404:
        return []
    assert r.status_code == 200, r.text
    return [
        pyjwt.decode(c["vc_jws"], options={"verify_signature": False})["jti"]
        for c in r.json()["credentials"]
    ]


@pytest.mark.rule("D-56")
async def test_resolve_puts_the_successor_first(client, db_session, member):
    old = await _issue(db_session, expires_in=timedelta(days=3))
    await _renew(db_session)
    new = next(i for i in await _rows(db_session) if i != old)

    r = await client.post(
        "/users/resolve", json={"username": "person-a"}, headers=RESOLVE
    )
    body = r.json()
    assert await _resolved(client) == [new, old]
    assert body["roles"] == [ROLE]
    import jwt as pyjwt

    assert (
        pyjwt.decode(body["vc_jws"], options={"verify_signature": False})["jti"] == new
    )


@pytest.mark.rule("D-56")
async def test_resolve_breaks_an_issued_at_tie_by_expiry(client, db_session, member):
    """`issued_at` is kept to the second on some databases."""
    old = await _issue(db_session, expires_in=timedelta(days=3))
    await _renew(db_session)
    new = next(i for i in await _rows(db_session) if i != old)
    same = datetime(2026, 1, 1, tzinfo=UTC)
    await db_session.execute(update(Credential).values(issued_at=same))
    await db_session.commit()

    assert await _resolved(client) == [new, old]


@pytest.mark.rule("D-56")
async def test_a_release_that_raced_a_renewal_sees_the_successor_and_goes_again(
    client, db_session, member
):
    """The release read the predecessor, the renewal committed, the release
    revoked what it had read. Its read-back is what catches the successor
    (`credential_remains`), and its retry revokes it."""
    old = await _issue(db_session, expires_in=timedelta(days=3))
    held = await _resolved(client)
    assert held == [old]

    await _renew(db_session)  # commits between the release's read and revoke

    r = await client.delete(f"/admin/memberships/{SUBJECT_DID}/{ORG}", headers=HEADERS)
    assert r.status_code == 204
    for credential_id in held:
        r = await client.delete(f"/admin/credentials/{credential_id}", headers=HEADERS)
        assert r.status_code == 204

    remains = await _resolved(client)
    assert len(remains) == 1 and remains[0] != old

    for credential_id in remains:  # the release, again
        r = await client.delete(f"/admin/credentials/{credential_id}", headers=HEADERS)
        assert r.status_code == 204
    assert await _resolved(client) == []

    # And nothing comes back: no membership, and the DID is spent.
    report = await _renew(db_session, subject_did=SUBJECT_DID)
    assert report.renewed == 0
    assert all(c.status == "revoked" for c in (await _rows(db_session)).values())


@pytest.mark.rule("D-56")
async def test_deactivating_the_did_revokes_the_successor_too(
    client, db_session, member
):
    await _issue(db_session, expires_in=timedelta(days=3))
    await _renew(db_session)

    r = await client.delete(f"/admin/dids/{SUBJECT_DID}", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["credentials_revoked"] == 2
    assert {c.status for c in (await _rows(db_session)).values()} == {"revoked"}


@pytest.mark.rule("D-56")
async def test_a_role_transition_during_the_overlap_suspends_both(
    client, db_session, member
):
    """The predecessor still says `consumer`; leaving it live beside a
    `prosumer` successor is the two-disagreeing-credentials state `P-28` exists
    to prevent."""
    await _issue(db_session, expires_in=timedelta(days=3))
    await _renew(db_session)

    r = await client.post(
        "/admin/credentials/data-subject/transition",
        json={
            "subject_id": SUBJECT_ID,
            "role": ROLE,
            "to_role": "prosumer",
            "linked_participant_did": CUSTODIAN_DID,
        },
        headers=HEADERS,
    )
    assert r.status_code == 201, r.text

    rows = await _rows(db_session)
    live = [c for c in rows.values() if c.status == "active"]
    assert [c.id for c in live] == [r.json()["credentialId"]]
    assert live[0].credential_json["credentialSubject"]["communityRole"] == "prosumer"
    left = live[0].expires_at.replace(tzinfo=UTC) - _now()
    assert left <= timedelta(days=30)
    assert sum(c.status == "suspended" for c in rows.values()) == 2


# ── a re-approval never re-delivers an expired credential ─────────


async def _approve(client, linked: str = CUSTODIAN_DID):
    return await client.post(
        "/admin/credentials/data-subject",
        json={"subject_id": SUBJECT_ID, "role": ROLE, "linked_participant_did": linked},
        headers=HEADERS,
    )


@pytest.mark.rule("D-56")
async def test_a_re_approval_over_an_expired_credential_issues_a_fresh_one(
    client, db_session, member
):
    """Expired but never revoked: re-delivering it would hand the custodian a
    credential every verifier refuses. A fresh 30-day one is issued instead."""
    old = await _issue(db_session, expires_in=timedelta(days=-3))
    member.clear()

    r = await _approve(client)

    assert r.status_code == 201, r.text
    new = r.json()["credentialId"]
    assert new != old
    rows = await _rows(db_session)
    assert rows[new].subject_did == SUBJECT_DID
    left = rows[new].expires_at.replace(tzinfo=UTC) - _now()
    assert timedelta(days=29) < left <= timedelta(days=30)
    assert [d["body"]["credentials"][0]["payload"]["id"] for d in member] == [new]

    # And the next renewal run sees the fresh one, not the lapsed one.
    assert (await _renew(db_session)).renewed == 0


@pytest.mark.rule("D-56")
async def test_an_unexpired_credential_is_still_re_delivered(
    client, db_session, member
):
    old = await _issue(db_session, expires_in=timedelta(days=12))
    r = await _approve(client)
    assert r.status_code == 201, r.text
    assert r.json()["credentialId"] == old
    assert list(await _rows(db_session)) == [old]


@pytest.mark.rule("D-56")
async def test_another_organisations_expired_credential_still_refuses_the_role(
    client, db_session, member
):
    """The cross-organisation `409` holds over a lapsed credential too."""
    await register_custodian(db_session, OTHER_DID)
    old = await _issue(db_session, expires_in=timedelta(days=-3))
    r = await _approve(client, OTHER_DID)
    assert r.status_code == 409, r.text
    assert list(await _rows(db_session)) == [old]
