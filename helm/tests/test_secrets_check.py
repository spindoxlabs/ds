"""`task secrets:check` over a decrypted helm secrets file (secrets plan P4).

The preflight an operator runs before an apply, on the file the deployment
decrypts. Never prints a value. Every test names the change that turns it red.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from conftest import HELM_DIR, REPO_DIR, pilot_secrets, pilot_values

CHECK = HELM_DIR / "tools" / "secrets_check.py"


def _check(tmp_path: Path, doc: dict | str) -> subprocess.CompletedProcess[str]:
    f = tmp_path / "secrets.dec.yaml"
    f.write_text(doc if isinstance(doc, str) else yaml.safe_dump(doc))
    return subprocess.run(
        [sys.executable, "-I", str(CHECK), str(f), "--repo", str(REPO_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def clean() -> dict:
    return pilot_secrets(pilot_values())


def _all_values(node, out=None):
    out = [] if out is None else out
    if isinstance(node, dict):
        for v in node.values():
            _all_values(v, out)
    elif isinstance(node, str) and len(node) >= 8:
        out.append(node)
    return out


def test_a_clean_file_passes(tmp_path, clean):
    r = _check(tmp_path, clean)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_example_fails_naming_every_placeholder(tmp_path):
    """P1: the committed example is the built-in red case. *Red:* skip the
    placeholder scan — the example passes."""
    r = _check(tmp_path, (HELM_DIR / "secrets.example.yaml").read_text())
    assert r.returncode != 0
    example = yaml.safe_load((HELM_DIR / "secrets.example.yaml").read_text())

    def paths(node, prefix):
        for k, v in node.items():
            p = f"{prefix}.{k}"
            if isinstance(v, dict):
                yield from paths(v, p)
            elif isinstance(v, str) and "CHANGE_ME" in v:
                yield p

    expected = list(paths(example["secrets"], "secrets"))
    assert expected
    for p in expected:
        assert p in r.stdout, p


def test_a_client_secret_equal_to_its_client_id_is_named(tmp_path, clean):
    """P2: the key → client mapping comes from `services/keycloak/clients*.yaml`.
    *Red:* hard-code the client list."""
    clean["secrets"]["svcDsPortalSecret"] = "svc-ds-portal"
    clean["secrets"]["participants"]["example-dso"]["organisationClientSecret"] = (
        "svc-ds-connector-example-dso"
    )
    r = _check(tmp_path, clean)
    assert r.returncode != 0
    assert "secrets.svcDsPortalSecret" in r.stdout and "svc-ds-portal" in r.stdout
    assert "secrets.participants.example-dso.organisationClientSecret" in r.stdout


def test_every_client_the_realm_files_declare_is_covered(tmp_path, clean):
    """P2, the other half: a client declared in the realm files with a
    `${VAR:-default}` secret and a matching helm key is checked without being
    listed in the checker. *Red:* hard-code the list, then add a client."""
    clean["secrets"]["svcDsFederatedCatalogSecret"] = "svc-ds-federated-catalog"
    r = _check(tmp_path, clean)
    assert r.returncode != 0
    assert "secrets.svcDsFederatedCatalogSecret" in r.stdout


def test_no_value_is_printed(tmp_path, clean):
    """P3. *Red:* echo the offending line."""
    bad = copy.deepcopy(clean)
    p = bad["secrets"]["participants"]
    p["example-dso"]["identityRegistryEncryptionKey"] = p["example-rec"][
        "identityRegistryEncryptionKey"
    ]
    p["example-rec"]["edcControlApiKey"] = "CHANGE_ME"
    r = _check(tmp_path, bad)
    assert r.returncode != 0
    for value in _all_values(bad["secrets"]):
        if value not in ("CHANGE_ME",):
            assert value not in r.stdout + r.stderr


def test_a_shared_custody_key_is_named(tmp_path, clean):
    p = clean["secrets"]["participants"]
    p["example-dso"]["edcControlApiKey"] = p["example-rec"]["edcControlApiKey"]
    r = _check(tmp_path, clean)
    assert r.returncode != 0
    assert "edcControlApiKey" in r.stdout


def test_edr_halves_that_do_not_match_are_named(tmp_path, clean):
    """P4: the public JWK must be the private one without its private members.
    *Red:* compare only the `kid`, then give the public value a matching `kid`
    and a different key — it passes."""
    p = clean["secrets"]["participants"]
    other = json.loads(p["example-dso"]["edcVault"]["edrSigningPublicJwk"])
    other["kid"] = json.loads(p["example-rec"]["edcVault"]["edrSigningPublicJwk"])[
        "kid"
    ]
    p["example-rec"]["edcVault"]["edrSigningPublicJwk"] = json.dumps(other)
    r = _check(tmp_path, clean)
    assert r.returncode != 0
    assert "example-rec" in r.stdout and "edrSigningPublicJwk" in r.stdout
    assert "example-dso" not in r.stdout


def test_a_committed_fixture_edr_key_is_named(tmp_path, clean):
    fixture = next(
        json.loads(line.split("=", 1)[1])
        for line in (REPO_DIR / "services/connector/config/rec-vault.properties")
        .read_text()
        .splitlines()
        if line.startswith("participant-private-key=")
    )
    v = clean["secrets"]["participants"]["example-rec"]["edcVault"]
    v["edrSigningPrivateJwk"] = json.dumps(fixture)
    v["edrSigningPublicJwk"] = json.dumps(
        {k: x for k, x in fixture.items() if k != "d"}
    )
    r = _check(tmp_path, clean)
    assert r.returncode != 0
    assert "fixture" in r.stdout
    assert fixture["d"] not in r.stdout


def test_the_dev_cookie_secret_is_named(tmp_path, clean):
    compose = (REPO_DIR / "docker-compose.yml").read_text()
    dev = next(
        line.split(":-", 1)[1].rstrip("}").strip()
        for line in compose.splitlines()
        if "OAUTH2_PROXY_COOKIE_SECRET" in line and ":-" in line
    )
    clean["secrets"]["oauth2ProxyCookieSecret"] = dev
    r = _check(tmp_path, clean)
    assert r.returncode != 0
    assert "secrets.oauth2ProxyCookieSecret" in r.stdout


def test_an_encrypted_file_is_refused_not_passed(tmp_path, clean):
    """A check that quietly passes because it could not look is the failure it
    exists to stop. *Red:* skip a file with a `sops:` key."""
    clean["sops"] = {"version": "3.9.0"}
    r = _check(tmp_path, clean)
    assert r.returncode != 0
    assert "encrypted" in r.stdout + r.stderr
