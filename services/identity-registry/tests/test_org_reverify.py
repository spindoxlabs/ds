"""`ir-cli org reverify`: a verified legal identity changes by a new verification.

`org apply` refuses to change a verified application's legal identity (409): the
issued OrganizationCredential asserts it. These cover the way it does change —
the declared identity written, the verification recorded anew, the credentials
asserting the old values revoked — and that a re-run, or an owner that is not
verified, or a new DID, is not that.
"""

from __future__ import annotations

import pytest
import yaml
from conftest import register_enrolled
from sqlalchemy import select
from test_org_apply import ALIAS, ORG_DID, _entry, _seed
from typer.testing import CliRunner

from identity_registry.db.models import Credential, OrganizationApplication, Owner
from identity_registry.services import org_onboarding as ops

NEW_NAME = "Example Community Cooperative S.c."


async def _owner(db_session) -> Owner:
    return (
        await db_session.execute(select(Owner).where(Owner.id == ALIAS))
    ).scalar_one()


async def _org_credentials(db_session) -> list[Credential]:
    result = await db_session.execute(
        select(Credential).where(
            Credential.subject_did == ORG_DID,
            Credential.credential_type == "OrganizationCredential",
        )
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_a_changed_legal_name_is_refused_by_apply_and_applied_by_reverify(
    db_session, tmp_path
):
    settings = await _seed(db_session, tmp_path)
    await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()

    changed = _entry(legal_name=NEW_NAME)
    refused = await ops.apply_owner_entry(db_session, settings, changed)
    await db_session.rollback()
    assert not refused.ok and "re-verification" in refused.error

    outcome = await ops.reverify_owner(
        db_session, changed, verified_by="registrar@example.test", evidence_ref="REG-7"
    )
    await db_session.commit()
    assert outcome.changes == {
        "legal_name": ("Example Community Cooperative", NEW_NAME)
    }

    owner = await _owner(db_session)
    assert owner.name == NEW_NAME
    assert owner.verified_by == "registrar@example.test"
    assert owner.evidence_ref == "REG-7"
    app = (
        await db_session.execute(
            select(OrganizationApplication).where(
                OrganizationApplication.alias == ALIAS
            )
        )
    ).scalar_one()
    assert (app.legal_name, app.verified_by, app.evidence_ref) == (
        NEW_NAME,
        "registrar@example.test",
        "REG-7",
    )

    # The file and the registry agree again, so the seed goes through.
    again = await ops.apply_owner_entry(db_session, settings, changed)
    assert again.ok, again.error


@pytest.mark.asyncio
async def test_the_credential_asserting_the_old_identity_is_revoked_then_reissued(
    db_session, tmp_path
):
    settings = await _seed(db_session, tmp_path)
    await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()
    await register_enrolled(db_session, ORG_DID, roles=["consumer"])
    await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()
    [old] = await _org_credentials(db_session)
    assert old.status == "active"

    changed = _entry(legal_name=NEW_NAME, registration_number="IT10987654321")
    outcome = await ops.reverify_owner(
        db_session, changed, verified_by="registrar@example.test"
    )
    await db_session.commit()
    assert outcome.revoked == [old.id]
    await db_session.refresh(old)
    assert old.status == "revoked" and old.revoked_at is not None

    applied = await ops.apply_owner_entry(db_session, settings, changed)
    await db_session.commit()
    assert {s.step: s.action for s in applied.steps}["credential"] == "issued"
    [new] = [c for c in await _org_credentials(db_session) if c.status == "active"]
    subject = new.credential_json["credentialSubject"]
    assert subject["legalName"] == NEW_NAME
    assert subject["registrationNumber"] == "IT10987654321"


@pytest.mark.asyncio
async def test_an_identity_that_already_matches_changes_nothing(db_session, tmp_path):
    settings = await _seed(db_session, tmp_path)
    await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()
    before = await _owner(db_session)
    verified_at, verified_by = before.verified_at, before.verified_by

    outcome = await ops.reverify_owner(
        db_session, _entry(), verified_by="registrar@example.test"
    )
    await db_session.commit()

    assert not outcome.changed and outcome.revoked == []
    after = await _owner(db_session)
    assert (after.verified_at, after.verified_by) == (verified_at, verified_by)


@pytest.mark.asyncio
async def test_an_owner_that_is_not_verified_is_refused(db_session, tmp_path):
    settings = await _seed(db_session, tmp_path)
    await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()
    await ops.suspend_owner(db_session, await _owner(db_session))
    await db_session.commit()

    with pytest.raises(ops.OrgOnboardingError, match="org reinstate"):
        await ops.reverify_owner(
            db_session,
            _entry(legal_name=NEW_NAME),
            verified_by="registrar@example.test",
        )


@pytest.mark.asyncio
async def test_a_new_did_is_not_a_reverification(db_session, tmp_path):
    settings = await _seed(db_session, tmp_path)
    await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()

    entry = _entry(legal_name=NEW_NAME)
    entry["did"] = "did:web:elsewhere.dataspaces.localhost"
    with pytest.raises(ops.OrgOnboardingError, match="new participant"):
        await ops.reverify_owner(
            db_session, entry, verified_by="registrar@example.test"
        )


@pytest.mark.asyncio
async def test_an_unregistered_owner_is_refused(db_session, tmp_path):
    await _seed(db_session, tmp_path)
    with pytest.raises(ops.OrgOnboardingError, match="org apply"):
        await ops.reverify_owner(
            db_session, _entry(), verified_by="registrar@example.test"
        )


def test_an_entry_without_a_dataspace_block_declares_its_name_and_did():
    assert ops.declared_identity(
        {"id": "x", "name": "X S.r.l.", "did": "did:web:x"}
    ) == {
        "legal_name": "X S.r.l.",
        "did": "did:web:x",
    }


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


def _owners_file(tmp_path, entry: dict):
    path = tmp_path / "owners.yaml"
    path.write_text(yaml.safe_dump({"owners": [entry]}))
    return path


def test_the_command_converges_what_apply_refuses(cli_database, tmp_path):
    from identity_registry.cli.main import app as cli

    runner = CliRunner()
    # No agreement and no address: the chain stops at verification, which is all
    # this needs and all a fresh registry can do without an imported agreement.
    entry = _entry(accepted=None, dsp_address=None)
    owners = _owners_file(tmp_path, entry)
    first = runner.invoke(cli, ["org", "apply", "--file", str(owners)])
    assert first.exit_code == 0, first.output

    entry["dataspace"]["legal_name"] = NEW_NAME
    owners = _owners_file(tmp_path, entry)
    refused = runner.invoke(cli, ["org", "apply", "--file", str(owners)])
    assert refused.exit_code == 1

    args = [
        "org",
        "reverify",
        "--file",
        str(owners),
        "--alias",
        ALIAS,
        "--verified-by",
        "registrar@example.test",
    ]
    dry = runner.invoke(cli, [*args, "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "dry-run" in dry.output and NEW_NAME in dry.output
    assert runner.invoke(cli, ["org", "apply", "--file", str(owners)]).exit_code == 1

    done = runner.invoke(cli, args)
    assert done.exit_code == 0, done.output
    assert "1 re-verified" in done.output
    assert runner.invoke(cli, args).output.count("unchanged") == 1
    assert runner.invoke(cli, ["org", "apply", "--file", str(owners)]).exit_code == 0


def test_the_command_reports_an_alias_the_file_does_not_declare(cli_database, tmp_path):
    from identity_registry.cli.main import app as cli

    owners = _owners_file(tmp_path, _entry())
    result = CliRunner().invoke(
        cli,
        [
            "org",
            "reverify",
            "--file",
            str(owners),
            "--alias",
            "nobody",
            "--verified-by",
            "registrar@example.test",
        ],
    )
    assert result.exit_code == 1
    assert "not declared" in result.output
