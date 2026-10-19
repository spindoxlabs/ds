"""`ir-cli org reissue`, and the two claims a reissue exists to carry.

An `OrganizationCredential` names the organisation on the platform
(`organizationId`, the owner's id) and its platform role (`organizationType`,
`organization.role` in owners.yaml — not the schema.org `type`, not the
participant `roles`). Organisations already holding a credential get one that
says so by a **reissue**: a successor issued, delivered to the holder's
store over the Storage API, and only then the predecessor suspended — not
revoked: it was replaced, not withdrawn (P-30). No enrolment, no
re-verification, no agreement step.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import REAL_ASYNC_CLIENT, register_custodian
from sqlalchemy import select
from test_org_apply import ALIAS, ORG_DID, _entry, _seed
from typer.testing import CliRunner

from identity_registry.db.models import Credential, Owner
from identity_registry.services import issuance, org_reissue
from identity_registry.services import org_onboarding as ops
from identity_registry.services.org_onboarding import suspension_index
from identity_registry.services.status_list import (
    SUSPENSION_LIST_ID,
    get_bit,
    get_or_create_status_list,
)


async def is_revoked(db, index: int) -> bool:
    """The revocation register's bit for *index*, as `/status/1` publishes it."""
    return get_bit((await get_or_create_status_list(db)).bitstring, index)


async def is_suspended(db, cred: Credential) -> bool:
    """The suspension register's bit for *cred*, as `/status/2` publishes it."""
    index = suspension_index(cred.credential_json)
    assert index is not None
    sl = await get_or_create_status_list(db, SUSPENSION_LIST_ID)
    return get_bit(sl.bitstring, index)


async def _org_credentials(db) -> list[Credential]:
    result = await db.execute(
        select(Credential).where(
            Credential.subject_did == ORG_DID,
            Credential.credential_type == "OrganizationCredential",
        )
    )
    return list(result.scalars().all())


async def _enrolled_with_credential(db, settings, entry: dict | None = None):
    """A verified, enrolled organisation holding one OrganizationCredential."""
    await register_custodian(db, ORG_DID)
    outcome = await ops.apply_owner_entry(db, settings, entry or _entry())
    await db.commit()
    assert outcome.ok, outcome.error
    [cred] = await _org_credentials(db)
    assert cred.status == "active"
    return cred


@pytest.fixture
def refusing_store(monkeypatch):
    """A holder store that answers every delivery with a 500."""

    def _client(**kwargs):
        kwargs.pop("transport", None)
        return REAL_ASYNC_CLIENT(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, text="store unavailable")
            ),
            **kwargs,
        )

    monkeypatch.setattr(issuance.httpx, "AsyncClient", _client)


# ── The claims ────────────────────────────────────────────────────


@pytest.mark.rule("P-2")
@pytest.mark.asyncio
async def test_the_credential_names_the_organisation_and_its_platform_role(
    db_session, tmp_path
):
    settings = await _seed(db_session, tmp_path)
    cred = await _enrolled_with_credential(db_session, settings)

    subject = cred.credential_json["credentialSubject"]
    assert subject["organizationId"] == ALIAS
    assert subject["organizationType"] == "rec"
    # Neither of the two other "types" an owner has: the schema.org class and
    # the dataspace participant role are what the entry says elsewhere.
    entry = _entry()
    assert entry["type"] == "schema:NGO" and entry["dataspace"]["roles"] == ["consumer"]
    assert subject["organizationType"] not in ("schema:NGO", "consumer")
    assert subject["roles"] == ["consumer"]


@pytest.mark.rule("P-2")
@pytest.mark.asyncio
async def test_an_owner_without_a_platform_role_gets_no_organization_type(
    db_session, tmp_path
):
    settings = await _seed(db_session, tmp_path)
    entry = _entry()
    del entry["organization"]
    cred = await _enrolled_with_credential(db_session, settings, entry)

    subject = cred.credential_json["credentialSubject"]
    assert subject["organizationId"] == ALIAS
    assert "organizationType" not in subject


def test_organization_type_reads_only_the_organization_role():
    owner = Owner(id="ex-00001", name="X", type="schema:NGO")
    assert ops.organization_type(owner) is None
    owner.organization_config = {"create": True}
    assert ops.organization_type(owner) is None
    owner.organization_config = {"create": True, "role": "dso"}
    assert ops.organization_type(owner) == "dso"


# ── The reissue ───────────────────────────────────────────────────


@pytest.mark.rule("P-30")
@pytest.mark.asyncio
async def test_reissue_delivers_the_successor_then_suspends_the_predecessor(
    db_session, tmp_path, monkeypatch, credential_store
):
    settings = await _seed(db_session, tmp_path)
    old = await _enrolled_with_credential(db_session, settings)
    # The credential an organisation holds from before the claims existed.
    legacy = dict(old.credential_json)
    legacy["credentialSubject"] = {
        k: v
        for k, v in legacy["credentialSubject"].items()
        if k not in ("organizationId", "organizationType")
    }
    old.credential_json = legacy
    await db_session.commit()

    events: list[str] = []
    real_deliver = org_reissue.deliver_to_custodian
    real_suspend = org_reissue.suspend_status_list_index

    async def deliver(db, settings, **kwargs):
        # Recorded before it leaves, and the predecessor untouched while it does.
        successor = await db.get(Credential, kwargs["issuer_pid"])
        predecessor = await db.get(Credential, old.id, populate_existing=True)
        assert successor is not None and successor.status == "active"
        assert predecessor.status == "active"
        events.append("deliver")
        return await real_deliver(db, settings, **kwargs)

    async def suspend(db, index):
        events.append("suspend")
        return await real_suspend(db, index)

    monkeypatch.setattr(org_reissue, "deliver_to_custodian", deliver)
    monkeypatch.setattr(org_reissue, "suspend_status_list_index", suspend)

    outcome = await org_reissue.reissue_owner(db_session, settings, ALIAS)

    assert events == ["deliver", "suspend"]
    assert outcome.delivered and outcome.error is None
    assert outcome.suspended == [old.id]

    [message] = credential_store
    [delivered] = message["body"]["credentials"]
    assert delivered["credentialType"] == "OrganizationCredential"
    assert delivered["payload"]["id"] == outcome.successor
    subject = delivered["payload"]["credentialSubject"]
    assert subject["organizationId"] == ALIAS
    assert subject["organizationType"] == "rec"
    # The rest re-attested as it was.
    assert subject["roles"] == legacy["credentialSubject"]["roles"]
    assert subject["legalName"] == legacy["credentialSubject"]["legalName"]

    # Suspended, not revoked: the suspension bit set, the revocation bit not,
    # and no end stamped — a suspension is not an ending.
    await db_session.refresh(old)
    assert old.status == "suspended" and old.revoked_at is None
    assert await is_suspended(db_session, old)
    assert not await is_revoked(db_session, old.status_list_index)
    successor = await db_session.get(Credential, outcome.successor)
    assert successor.status == "active"
    assert not await is_suspended(db_session, successor)
    assert not await is_revoked(db_session, successor.status_list_index)


@pytest.mark.rule("P-30", "P-25")
@pytest.mark.asyncio
async def test_reinstating_after_a_reissue_leaves_the_predecessor_suspended(
    db_session, tmp_path, credential_store
):
    """`org suspend` then `org reinstate` must not revive what a reissue replaced.

    Suspending the organisation suspends the successor too, so both carry a set
    bit; reinstating lifts the successor's alone (P-30).
    """
    settings = await _seed(db_session, tmp_path)
    old = await _enrolled_with_credential(db_session, settings)
    outcome = await org_reissue.reissue_owner(db_session, settings, ALIAS)
    assert outcome.suspended == [old.id]

    owner = await db_session.get(Owner, ALIAS)
    await ops.suspend_owner(db_session, owner)
    await db_session.commit()
    successor = await db_session.get(Credential, outcome.successor)
    assert successor.status == "suspended"

    await ops.reinstate_owner(db_session, owner)
    await db_session.commit()
    await db_session.refresh(old)
    await db_session.refresh(successor)
    assert successor.status == "active"
    assert not await is_suspended(db_session, successor)
    assert old.status == "suspended"
    assert await is_suspended(db_session, old)


@pytest.mark.rule("P-30")
@pytest.mark.asyncio
async def test_a_failed_delivery_suspends_nothing(db_session, tmp_path, refusing_store):
    settings = await _seed(db_session, tmp_path)
    old = await _enrolled_with_credential(db_session, settings)

    outcome = await org_reissue.reissue_owner(db_session, settings, ALIAS)

    assert not outcome.delivered and "500" in outcome.error
    assert outcome.suspended == []
    await db_session.refresh(old)
    assert old.status == "active"
    assert not await is_suspended(db_session, old)
    assert not await is_revoked(db_session, old.status_list_index)
    # The successor left this registry (or may have): it stays on the register.
    successor = await db_session.get(Credential, outcome.successor)
    assert successor is not None and successor.status == "active"


@pytest.mark.rule("P-30")
@pytest.mark.asyncio
async def test_a_rerun_after_a_failed_delivery_suspends_every_other_credential(
    db_session, tmp_path, monkeypatch
):
    settings = await _seed(db_session, tmp_path)
    old = await _enrolled_with_credential(db_session, settings)

    status = {"code": 500}

    def _client(**kwargs):
        kwargs.pop("transport", None)
        return REAL_ASYNC_CLIENT(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status["code"], json={})
            ),
            **kwargs,
        )

    monkeypatch.setattr(issuance.httpx, "AsyncClient", _client)
    failed = await org_reissue.reissue_owner(db_session, settings, ALIAS)
    assert failed.error

    status["code"] = 201
    done = await org_reissue.reissue_owner(db_session, settings, ALIAS)
    assert done.delivered
    assert sorted(done.suspended) == sorted([old.id, failed.successor])
    live = [c.id for c in await _org_credentials(db_session) if c.status == "active"]
    assert live == [done.successor]
    for cred in await _org_credentials(db_session):
        if cred.id != done.successor:
            assert cred.status == "suspended"
            assert await is_suspended(db_session, cred)
            assert not await is_revoked(db_session, cred.status_list_index)


@pytest.mark.rule("P-30")
@pytest.mark.asyncio
async def test_a_predecessor_naming_no_suspension_register_is_refused_before_issuing(
    db_session, tmp_path, credential_store
):
    """Suspending it would set a bit no verifier fetches; revoking it would say
    the attestation was withdrawn. Neither is done, and nothing is issued."""
    settings = await _seed(db_session, tmp_path)
    old = await _enrolled_with_credential(db_session, settings)
    legacy = dict(old.credential_json)
    legacy["credentialStatus"] = [
        e for e in legacy["credentialStatus"] if e.get("statusPurpose") != "suspension"
    ]
    old.credential_json = legacy
    await db_session.commit()

    with pytest.raises(ops.OrgOnboardingError, match="no suspension register"):
        await org_reissue.reissue_owner(db_session, settings, ALIAS)
    assert [c.id for c in await _org_credentials(db_session)] == [old.id]
    assert credential_store == []
    await db_session.refresh(old)
    assert old.status == "active"
    assert not await is_revoked(db_session, old.status_list_index)


@pytest.mark.asyncio
async def test_dry_run_issues_delivers_and_suspends_nothing(
    db_session, tmp_path, credential_store
):
    settings = await _seed(db_session, tmp_path)
    old = await _enrolled_with_credential(db_session, settings)

    outcome = await org_reissue.reissue_owner(db_session, settings, ALIAS, dry_run=True)

    assert outcome.successor is None and not outcome.delivered
    assert outcome.suspended == [old.id]
    assert credential_store == []
    [only] = await _org_credentials(db_session)
    assert only.id == old.id and only.status == "active"


@pytest.mark.asyncio
async def test_an_organisation_with_no_current_credential_is_refused(
    db_session, tmp_path, credential_store
):
    settings = await _seed(db_session, tmp_path)
    await register_custodian(db_session, ORG_DID)
    # No agreement: verified and enrolled, but `org apply` issues nothing.
    await ops.apply_owner_entry(db_session, settings, _entry(accepted=None))
    await db_session.commit()

    with pytest.raises(ops.OrgOnboardingError, match="org apply"):
        await org_reissue.reissue_owner(db_session, settings, ALIAS)
    assert await _org_credentials(db_session) == []
    assert credential_store == []


@pytest.mark.asyncio
async def test_an_organisation_that_has_not_enrolled_is_refused(
    db_session, tmp_path, credential_store
):
    settings = await _seed(db_session, tmp_path)
    await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()

    with pytest.raises(ops.OrgOnboardingError, match="not enrolled"):
        await org_reissue.reissue_owner(db_session, settings, ALIAS)
    assert credential_store == []


@pytest.mark.asyncio
async def test_an_owner_with_no_did_is_refused(db_session, tmp_path):
    settings = await _seed(db_session, tmp_path)
    db_session.add(
        Owner(
            id="ex-00001",
            name="Example",
            status="verified",
            verified_by="ops@example.test",
        )
    )
    await db_session.commit()

    with pytest.raises(ops.OrgOnboardingError, match="no DID"):
        await org_reissue.reissue_owner(db_session, settings, "ex-00001")


@pytest.mark.asyncio
async def test_an_unregistered_owner_is_refused(db_session, tmp_path):
    settings = await _seed(db_session, tmp_path)
    with pytest.raises(ops.OrgOnboardingError, match="not registered"):
        await org_reissue.reissue_owner(db_session, settings, "nobody")


@pytest.mark.asyncio
async def test_a_holder_publishing_no_credential_service_is_refused_before_issuing(
    db_session, tmp_path
):
    settings = await _seed(db_session, tmp_path)
    await register_custodian(db_session, ORG_DID, credential_service=False)
    await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()
    [old] = await _org_credentials(db_session)

    with pytest.raises(ops.OrgOnboardingError, match="CredentialService"):
        await org_reissue.reissue_owner(db_session, settings, ALIAS)
    assert [c.id for c in await _org_credentials(db_session)] == [old.id]


# ── The command ───────────────────────────────────────────────────


@pytest.fixture
def cli_database(tmp_path, monkeypatch):
    """A schema-backed SQLite file of this test's own (never a live database)."""
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from identity_registry.config import get_settings
    from identity_registry.db.engine import Base

    url = f"sqlite+aiosqlite:///{tmp_path / 'registry.db'}"

    async def _create():
        eng = create_async_engine(url, poolclass=NullPool)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()

    asyncio.run(_create())
    monkeypatch.setenv("IDENTITY_REGISTRY_DATABASE_URL", url)
    monkeypatch.setenv("DB_SKIP_SCHEMA_CHECK", "true")
    get_settings.cache_clear()
    return url


def _prepare(url: str, tmp_path) -> str:
    """The file database holding one enrolled organisation and its credential."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    async def _go():
        eng = create_async_engine(url, poolclass=NullPool)
        async with async_sessionmaker(eng, expire_on_commit=False)() as db:
            settings = await _seed(db, tmp_path)
            cred = await _enrolled_with_credential(db, settings)
        await eng.dispose()
        return cred.id

    return asyncio.run(_go())


def _reissue_args(*extra: str) -> list[str]:
    return ["org", "reissue", "--alias", ALIAS, *extra]


def test_the_command_reissues_and_reports(cli_database, tmp_path, credential_store):
    from identity_registry.cli.main import app as cli

    old = _prepare(cli_database, tmp_path)
    runner = CliRunner()

    dry = runner.invoke(cli, _reissue_args("--dry-run"))
    assert dry.exit_code == 0, dry.output
    assert f"would suspend         {old}" in dry.output
    assert "dry-run" in dry.output and credential_store == []

    done = runner.invoke(cli, _reissue_args())
    assert done.exit_code == 0, done.output
    assert "organizationType      'rec'" in done.output
    assert f"suspended             {old}" in done.output
    assert "1 reissued, 0 failed" in done.output
    assert len(credential_store) == 1


def test_the_command_exits_non_zero_on_a_failed_delivery(
    cli_database, tmp_path, refusing_store
):
    from identity_registry.cli.main import app as cli

    _prepare(cli_database, tmp_path)
    result = CliRunner().invoke(cli, _reissue_args())
    assert result.exit_code == 1
    assert "not delivered, nothing suspended" in result.output
    assert "0 reissued, 1 failed" in result.output


def test_the_command_reports_a_refusal(cli_database, tmp_path):
    from identity_registry.cli.main import app as cli

    result = CliRunner().invoke(cli, ["org", "reissue", "--alias", "nobody"])
    assert result.exit_code == 1
    assert "not registered" in result.output
