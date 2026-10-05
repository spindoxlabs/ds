"""Renewal on Postgres: the re-check at insert holds under real row locks (`D-56`).

The unit suite proves the checks run again inside the inserting transaction;
SQLite ignores `FOR UPDATE`, so only a real server shows that a release holding
the membership row makes the renewal **wait** and then refuse, and that two
runs racing on one predecessor issue one successor between them.

Its own database, named per run and dropped afterwards.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from conftest import ADMIN_DB_URL, _server_dsn_prefix
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from identity_registry.config import Settings
from identity_registry.db.engine import Base
from identity_registry.db.models import (
    Credential,
    Did,
    Key,
    OrganizationMembership,
    Owner,
)

pytestmark = pytest.mark.integration

ANCHOR = "did:web:trust-anchor.dataspaces.localhost"
REC = "did:web:rec.example.org"
PERSON = f"{REC}:users:ex-00001"
ORG = "example-rec"


@pytest.fixture
async def factory():
    name = f"ir_renewal_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(ADMIN_DB_URL, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    url = f"{_server_dsn_prefix().replace('postgresql://', 'postgresql+asyncpg://')}/{name}"
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield (
            async_sessionmaker(engine, expire_on_commit=False),
            Settings(database_url=url, oidc_issuer_url=None),
        )
    finally:
        await engine.dispose()
        with psycopg.connect(ADMIN_DB_URL, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


async def _seed(db, settings: Settings) -> str:
    from identity_registry.services.crypto import (
        decrypt_private_jwk,
        encrypt_private_jwk,
        generate_key_pair,
    )
    from identity_registry.services.status_list import (
        SUSPENSION_LIST_ID,
        allocate_suspendable_index,
    )
    from identity_registry.services.vc import (
        build_data_subject_credential,
        sign_credential,
    )

    kp = generate_key_pair(ANCHOR)
    key = Key(
        owner_did=ANCHOR,
        kid=kp.kid,
        private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
        public_jwk=kp.public_jwk,
    )
    db.add(key)
    await db.flush()
    db.add(Did(did=ANCHOR, did_type="participant", key_id=key.id))
    db.add(
        Did(
            did=REC,
            did_type="participant",
            service_endpoints=[
                {
                    "type": "CredentialService",
                    "serviceEndpoint": "http://127.0.0.1:9/credentials",
                }
            ],
        )
    )
    db.add(
        Owner(id=ORG, name="Example REC", did=REC, status="verified", verified_by="it")
    )
    db.add(Did(did=PERSON, did_type="user"))
    await db.flush()
    db.add(OrganizationMembership(user_did=PERSON, organization_alias=ORG))
    index = await allocate_suspendable_index(db)
    vc = build_data_subject_credential(
        issuer_did=ANCHOR,
        subject_did=PERSON,
        role="DataSubject",
        linked_participant_did=REC,
        credentials_context_url=settings.credentials_context_url,
        dataspace_uri=settings.dataspace_uri,
        status_list_credential_url=settings.status_list_url(),
        suspension_list_credential_url=settings.status_list_url(SUSPENSION_LIST_ID),
        status_list_index=index,
        ttl_days=30,
    )
    signed = sign_credential(
        vc, decrypt_private_jwk(key.private_jwk, settings.encryption_key), key.kid
    )
    expires = datetime.now(UTC) + timedelta(days=3)
    db.add(
        Credential(
            id=signed["id"],
            credential_type="DataSubjectCredential",
            issuer_did=ANCHOR,
            subject_did=PERSON,
            credential_json=signed,
            status_list_index=index,
            issued_at=expires - timedelta(days=30),
            expires_at=expires,
        )
    )
    await db.commit()
    return signed["id"]


async def _one(factory, settings):
    """A renewal of the single candidate, up to and including the insert."""
    from identity_registry.services.org_onboarding import get_trust_anchor_key
    from identity_registry.services.renewal import (
        SigningKey,
        SubjectResult,
        candidates,
        renew_one,
    )

    async with factory() as db:
        key = await get_trust_anchor_key(db, settings)
        signing = SigningKey(kid=key.kid, private_jwk=key.private_jwk)
        (candidate,) = await candidates(db, settings)
        await db.rollback()
        result = SubjectResult(PERSON)
        successor = await renew_one(
            db,
            settings,
            candidate,
            result,
            anchor_key=signing,
            now=datetime.now(UTC),
        )
        return successor, result


async def _ids(factory) -> list[str]:
    async with factory() as db:
        return list(
            (await db.execute(select(Credential.id).order_by(Credential.issued_at)))
            .scalars()
            .all()
        )


@pytest.mark.rule("D-56")
async def test_a_renewal_waits_for_a_release_holding_the_membership(factory):
    make, settings = factory
    async with make() as db:
        old = await _seed(db, settings)

    async with make() as release:
        # Deleted, not committed: the release holds the row lock.
        await release.execute(delete(OrganizationMembership))
        renewal = asyncio.create_task(_one(make, settings))
        await asyncio.sleep(1.0)
        assert not renewal.done(), "the renewal did not wait for the membership row"
        await release.commit()

    successor, result = await asyncio.wait_for(renewal, 15)
    assert successor is None
    assert result.skipped == {"membership_gone": 1}
    assert await _ids(make) == [old]


@pytest.mark.rule("D-56")
async def test_two_runs_racing_on_one_predecessor_issue_one_successor(factory):
    make, settings = factory
    async with make() as db:
        old = await _seed(db, settings)

    outcomes = await asyncio.gather(_one(make, settings), _one(make, settings))

    issued = [s for s, _ in outcomes if s]
    assert len(issued) == 1
    assert sorted(r.skipped.get("already_renewed", 0) for _, r in outcomes) == [0, 1]
    assert sorted(await _ids(make)) == sorted([old, issued[0]])


@pytest.mark.rule("D-56")
async def test_a_full_run_on_postgres(factory):
    """Aware datetimes from Postgres, the delivery failure counted, the next
    run idempotent."""
    from identity_registry.services.renewal import renew_due

    make, settings = factory
    async with make() as db:
        await _seed(db, settings)

    async with make() as db:
        first = await renew_due(db, settings)
    # Nothing listens on the custodian's endpoint: recorded, not delivered.
    assert first.renewed == 1 and first.failed == 1

    async with make() as db:
        again = await renew_due(db, settings)
    assert again.renewed == 0
    assert len(await _ids(make)) == 2
