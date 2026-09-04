"""A machine-local DID must not reach a production registry.

A `did:web` is a URL — `did:web:X` resolves at `https://X/.well-known/did.json`
— so the host *is* the identity, and a deployment's owner registry is one file
serving several environments. The dev value is the one somebody uncomments
first, and nothing on the path it is used for would notice: `/owners/resolve`,
a disclosure recipient and a consent row all compare the DID as a string.
Resolution starts mattering at credential issuance and negotiation, by which
time the wrong DID is in issued credentials and recorded provenance.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from conftest import make_headers
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from typer.testing import CliRunner

from identity_registry.cli.main import app as cli
from identity_registry.config import Settings
from identity_registry.dependencies import get_db, get_settings_dep
from identity_registry.main import create_app
from identity_registry.services.did import dev_only_did_reason, did_web_host

runner = CliRunner()


# ── The classifier ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "did,host",
    [
        ("did:web:greenland.dataspaces.localhost", "greenland.dataspaces.localhost"),
        # The percent-encoded port is the canonical spelling; the port is not
        # part of the host.
        ("did:web:rec.dataspaces.localhost%3A9010", "rec.dataspaces.localhost"),
        # Path segments name a person, not a host — only the first is the host.
        ("did:web:rec.example.org:users:alice", "rec.example.org"),
        ("did:web:greenland.celine.example.eu", "greenland.celine.example.eu"),
        ("did:key:z6MkjRagNiMu91DduvCvgEsqLZDVzrJzFrwahc4tXLt9DoHd", None),
        ("", None),
    ],
)
def test_did_web_host(did, host):
    assert did_web_host(did) == host


@pytest.mark.parametrize(
    "did",
    [
        "did:web:greenland.dataspaces.localhost",
        "did:web:provider.dataspaces.localhost",
        "did:web:rec.dataspaces.localhost%3A9010",
        "did:web:localhost",
        "did:web:127.0.0.1",
        "did:web:some-box.local",
    ],
)
def test_machine_local_dids_are_named(did):
    assert dev_only_did_reason(did) is not None


@pytest.mark.parametrize(
    "did",
    [
        # The shape this deployment is heading for: real subdomains of an
        # infrastructure the organisation actually serves.
        "did:web:greenland.ds.celine.example.eu",
        "did:web:dso.ds.celine.example.eu",
        "did:web:rec.example.org:users:alice",
        # Not did:web at all — this classifier has nothing to say about it.
        "did:key:z6MkjRagNiMu91DduvCvgEsqLZDVzrJzFrwahc4tXLt9DoHd",
    ],
)
def test_a_servable_did_is_not_refused(did):
    assert dev_only_did_reason(did) is None


def test_localhost_alone_is_not_enough_to_match():
    """`localhost.example.org` is a real host somebody could serve. Matching on
    the substring rather than the suffix would refuse it."""
    assert dev_only_did_reason("did:web:localhost.example.org") is None


# ── The refusal, at the two seed entry points ─────────────────────


def _owners_file(tmp_path, did: str, name: str = "owners.yaml"):
    path = tmp_path / name
    path.write_text(
        "owners:\n"
        "  - id: greenland\n"
        "    name: Greenland Soc. Coop.\n"
        f"    did: {did}\n"
        "    aliases: [rec]\n"
    )
    return path


def test_owner_import_refuses_a_dev_did_in_production(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    owners = _owners_file(tmp_path, "did:web:greenland.dataspaces.localhost")

    result = runner.invoke(cli, ["owner", "import", "--file", str(owners)])

    assert result.exit_code == 1
    assert "greenland.dataspaces.localhost" in result.output
    assert "did:web is a URL" in result.output


def test_the_same_seed_is_accepted_in_dev(tmp_path, monkeypatch):
    """The dev DIDs *are* `.localhost`, and that is correct there. A guard that
    fired in dev would make the committed dev seed unusable."""
    monkeypatch.setenv("DS_ENV", "dev")
    owners = _owners_file(tmp_path, "did:web:greenland.dataspaces.localhost")

    result = runner.invoke(cli, ["owner", "import", "--file", str(owners)])

    assert "did:web is a URL" not in result.output


def test_a_real_host_passes_the_guard_in_production(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    owners = _owners_file(tmp_path, "did:web:greenland.ds.celine.example.eu")

    result = runner.invoke(cli, ["owner", "import", "--file", str(owners)])

    assert "did:web is a URL" not in result.output


def test_forgetting_ds_env_refuses_rather_than_permits(tmp_path, monkeypatch):
    """`DS_ENV` unset means production (`ds_auth.production.current_env`), so a
    chart that drops the variable in a refactor fails loudly instead of writing
    a machine-local identity into a real registry."""
    monkeypatch.delenv("DS_ENV", raising=False)
    owners = _owners_file(tmp_path, "did:web:greenland.dataspaces.localhost")

    result = runner.invoke(cli, ["owner", "import", "--file", str(owners)])

    assert result.exit_code == 1


def test_every_violation_is_reported_in_one_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_ENV", "production")
    owners = tmp_path / "owners.yaml"
    owners.write_text(
        "owners:\n"
        "  - id: greenland\n    did: did:web:greenland.dataspaces.localhost\n"
        "  - id: spxl\n    did: did:web:provider.dataspaces.localhost\n"
        "  - id: dso\n    did: did:web:dso.ds.celine.example.eu\n"
        "  - id: openstreetmap\n    url: https://www.openstreetmap.org\n"
    )

    result = runner.invoke(cli, ["owner", "import", "--file", str(owners)])

    assert result.exit_code == 1
    assert "greenland" in result.output and "spxl" in result.output
    # The servable one and the one with no DID at all are not violations.
    assert "dso.ds.celine.example.eu" not in result.output
    assert "openstreetmap" not in result.output


def test_org_apply_refuses_a_dev_did_in_production(tmp_path, monkeypatch):
    """The other seed entry point, and the one a deployment's owners.yaml goes
    through — reached by the `--governance`/`--verified-by` path."""
    monkeypatch.setenv("DS_ENV", "production")
    owners = _owners_file(tmp_path, "did:web:greenland.dataspaces.localhost")

    result = runner.invoke(
        cli,
        ["org", "apply", "--file", str(owners), "--verified-by", "demo3-deployment"],
    )

    assert result.exit_code == 1
    assert "greenland.dataspaces.localhost" in result.output


def test_org_apply_ignores_a_dev_did_on_an_entry_it_would_not_write(
    tmp_path, monkeypatch
):
    """A file keeps entries for its other consumers. A machine-local DID on one
    this run does not select is not this command's business — the guard is about
    what gets written, not about auditing somebody else's rows."""
    monkeypatch.setenv("DS_ENV", "production")
    owners = tmp_path / "owners.yaml"
    owners.write_text(
        "owners:\n"
        "  - id: greenland\n    did: did:web:greenland.dataspaces.localhost\n"
        "  - id: dso\n    did: did:web:dso.ds.celine.example.eu\n"
    )
    gov = tmp_path / "governance.yaml"
    gov.write_text(
        "sources:\n"
        "  datasets.gold.a:\n"
        "    ownership: [{name: dso}]\n"
        "    dataspace: {expose: true}\n"
    )

    result = runner.invoke(
        cli,
        [
            "org",
            "apply",
            "--file",
            str(owners),
            "--governance",
            str(gov),
            "--verified-by",
            "demo3-deployment",
        ],
    )

    assert "greenland.dataspaces.localhost" not in result.output


def test_org_apply_guards_an_unselected_entry_that_carries_a_dataspace_block(
    tmp_path, monkeypatch
):
    """The third door on this guard
    ([#27](https://github.com/spindoxlabs/ds/issues/27)). `apply_owner_entry`
    skips an entry only when it carries **no** `dataspace:` block, so an entry
    with one is written whether the selector picked it or not — and that is how a
    **consumer** is onboarded, since `--governance` selects the owners of exposed
    datasets and a party that owns no data is never among them. Guarding the
    selection alone let a machine-local DID through on exactly the entry a
    deployment's consumer arrives on."""
    monkeypatch.setenv("DS_ENV", "production")
    owners = tmp_path / "owners.yaml"
    owners.write_text(
        "owners:\n"
        "  - id: dso\n    did: did:web:dso.ds.celine.example.eu\n"
        "  - id: spxl\n"
        "    did: did:web:spxl.dataspaces.localhost\n"
        "    dataspace:\n"
        "      legal_name: Spindox Labs S.r.l.\n"
        "      roles: [consumer]\n"
    )
    gov = tmp_path / "governance.yaml"
    gov.write_text(
        "sources:\n"
        "  datasets.gold.a:\n"
        "    ownership: [{name: dso}]\n"
        "    dataspace: {expose: true}\n"
    )

    result = runner.invoke(
        cli,
        [
            "org",
            "apply",
            "--file",
            str(owners),
            "--governance",
            str(gov),
            "--verified-by",
            "demo3-deployment",
        ],
    )

    assert result.exit_code == 1
    assert "spxl.dataspaces.localhost" in result.output
    # The selected entry is servable, and is not reported as a violation.
    assert "dso.ds.celine.example.eu" not in result.output


# ── The HTTP write paths ──────────────────────────────────────────
#
# [#25](https://github.com/spindoxlabs/ds/issues/25). The classifier above served
# one caller — the CLI, on the two seed entry points — so a production registry
# accepted over the API exactly what it refused from a file. The row is not
# dangerous, it is *dead*: nobody outside that machine can fetch the document, so
# `GET /owners/resolve` answers with a DID that resolves nowhere, which is the
# failure the owner-registry chain exists to prevent arriving through the other
# door.
#
# **The flag is the whole switch, and it is off by default.** Not keyed on
# `DS_ENV`, unlike the CLI guard: a failed bootstrap is a deploy an operator
# retries, an API that refuses is an operator locked out of their own registry if
# the classifier ever misjudges a host that genuinely serves. Off by default also
# means no deployment's behaviour changed when this landed — which is what the
# `_allowed` half of every pair below asserts, and it is the more important half.

DEV_DID = "did:web:greenland.dataspaces.localhost"
REAL_DID = "did:web:greenland.celine.example.eu"


@pytest_asyncio.fixture
async def refusing_client(engine):
    """A client whose registry has the refusal turned on."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        oidc_issuer_url=None,
        refuse_dev_dids=True,
    )
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings_dep] = lambda: settings
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _owner_body(did: str, owner_id: str = "greenland") -> dict:
    return {"id": owner_id, "type": "schema:Organization", "name": "G", "did": did}


@pytest.mark.asyncio
async def test_create_owner_refuses_a_dev_did_when_enabled(refusing_client):
    r = await refusing_client.post(
        "/admin/owners", json=_owner_body(DEV_DID), headers=make_headers()
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    # The route and the field, because an operator gets this out of a client with
    # none of the context the CLI's stderr had — and the flag, because a refusal
    # that does not say how to lift it is a support ticket.
    assert "POST /admin/owners" in detail
    assert "field: did" in detail
    assert "IDENTITY_REGISTRY_REFUSE_DEV_DIDS" in detail


@pytest.mark.asyncio
async def test_create_owner_allows_a_dev_did_by_default(client):
    """The half that matters most: nothing changed for anyone who did not opt in."""
    r = await client.post(
        "/admin/owners", json=_owner_body(DEV_DID), headers=make_headers()
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_a_real_did_is_accepted_even_when_the_guard_is_on(refusing_client):
    """The guard refuses machine-local hosts, not DIDs. A `.eu` host under the
    same flag goes through, which is what stops this being an off switch for the
    route."""
    r = await refusing_client.post(
        "/admin/owners", json=_owner_body(REAL_DID), headers=make_headers()
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_update_owner_refuses_a_dev_did_when_enabled(refusing_client):
    created = await refusing_client.post(
        "/admin/owners", json=_owner_body(REAL_DID), headers=make_headers()
    )
    assert created.status_code == 201

    r = await refusing_client.put(
        "/admin/owners/greenland",
        json={"did": DEV_DID},
        headers=make_headers(),
    )
    assert r.status_code == 422
    assert "PUT /admin/owners/greenland" in r.json()["detail"]


@pytest.mark.asyncio
async def test_patch_owner_refuses_a_dev_did_when_enabled(refusing_client):
    created = await refusing_client.post(
        "/admin/owners", json=_owner_body(REAL_DID), headers=make_headers()
    )
    assert created.status_code == 201

    r = await refusing_client.patch(
        "/admin/owners/greenland",
        json={"did": DEV_DID},
        headers=make_headers(),
    )
    assert r.status_code == 422
    assert "PATCH /admin/owners/greenland" in r.json()["detail"]


# The two routes above are the ones a person reaches. These are the other three
# write paths #25 lists, and they need a little setup each — an invite for the
# public intake, an application row for the PATCH — which is why they are last
# rather than absent.


async def _invite(client) -> str:
    r = await client.post(
        "/admin/onboarding/invites",
        headers=make_headers(scope="identity-registry.organizations.write"),
        json={},
    )
    assert r.status_code == 201, r.text
    return r.json()["code"]


def _application(code: str, did: str) -> dict:
    return {
        "invite_code": code,
        "alias": "acme-energy",
        "legal_name": "Acme Energy",
        "roles": ["consumer"],
        "evidence_ref": "ticket-4711",
        "did": did,
    }


@pytest.mark.asyncio
async def test_public_intake_refuses_a_dev_did_when_enabled(refusing_client):
    """The one unauthenticated write on this service, and the route D.7's portal
    onboarding will drive — which is #25's own tiebreak for guarding at all."""
    code = await _invite(refusing_client)

    r = await refusing_client.post(
        "/onboarding/applications", json=_application(code, DEV_DID)
    )

    assert r.status_code == 422
    assert "POST /onboarding/applications" in r.json()["detail"]


@pytest.mark.asyncio
async def test_public_intake_allows_a_dev_did_by_default(client):
    code = await _invite(client)

    r = await client.post("/onboarding/applications", json=_application(code, DEV_DID))

    assert r.status_code == 201


@pytest.mark.asyncio
async def test_patch_application_refuses_a_dev_did_when_enabled(refusing_client):
    code = await _invite(refusing_client)
    created = await refusing_client.post(
        "/onboarding/applications", json=_application(code, REAL_DID)
    )
    assert created.status_code == 201
    queue = await refusing_client.get(
        "/admin/organizations/applications",
        headers=make_headers(scope="identity-registry.organizations.read"),
    )
    application_id = queue.json()[0]["id"]

    r = await refusing_client.patch(
        f"/admin/organizations/applications/{application_id}",
        json={"did": DEV_DID},
        headers=make_headers(),
    )

    assert r.status_code == 422
    assert application_id in r.json()["detail"]
