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
from typer.testing import CliRunner

from identity_registry.cli.main import app as cli
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
